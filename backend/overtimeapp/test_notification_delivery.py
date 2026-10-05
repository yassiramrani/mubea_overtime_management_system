"""Exercise actual message assembly and fail-closed outbox delivery policy."""
import json
import os
import subprocess
import sys
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .delivery import send_notification_mail
from .models import EmailLog


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   NOTIFICATIONS_DELIVERY_ENABLED=True, NOTIFICATIONS_TEST_MODE=False,
                   NOTIFICATIONS_REDIRECT_TO=[])
class NotificationDeliveryTests(TestCase):
    def queue(self, **extra):
        return EmailLog.objects.create(recipient='head@example.com', subject='Approval needed',
                                       body='Saved request text', html_body='<p>Saved request HTML</p>',
                                       email_type='request_submitted', status='queued', **extra)

    def deliver(self):
        call_command('send_notifications', stdout=StringIO())

    def test_delivers_multipart_snapshot_once_and_preserves_original_content(self):
        row = self.queue()
        self.deliver()
        self.deliver()
        row.refresh_from_db()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['head@example.com'])
        self.assertEqual(mail.outbox[0].body, row.body)
        self.assertEqual(mail.outbox[0].alternatives[0], (row.html_body, 'text/html'))
        self.assertEqual(row.status, 'sent')
        self.assertEqual(row.attempts, 1)
        self.assertIsNotNone(row.delivered_at)

    def test_legacy_plain_text_row_remains_deliverable(self):
        row = self.queue()
        EmailLog.objects.filter(pk=row.pk).update(html_body='')
        self.deliver()
        self.assertEqual(mail.outbox[0].body, row.body)
        self.assertEqual(mail.outbox[0].alternatives, [])

    @override_settings(NOTIFICATIONS_TEST_MODE=True,
                       NOTIFICATIONS_REDIRECT_TO=['demo@example.com', 'DEMO@example.com'])
    def test_redirects_queued_rows_and_marks_both_bodies_without_changing_snapshot(self):
        row = self.queue()
        self.deliver()
        row.refresh_from_db()
        message = mail.outbox[0]
        self.assertEqual(message.to, ['demo@example.com'])
        self.assertEqual(message.subject, '[TEST] Approval needed')
        self.assertIn('TEST / DEMO', message.body)
        self.assertIn('head@example.com', message.body)
        self.assertIn('TEST / DEMO', message.alternatives[0].content)
        self.assertEqual(row.recipient, 'head@example.com')
        self.assertEqual(row.subject, 'Approval needed')
        self.assertEqual(row.html_body, '<p>Saved request HTML</p>')
        self.assertEqual(row.status, 'sent')

    @override_settings(NOTIFICATIONS_TEST_MODE=True, NOTIFICATIONS_REDIRECT_TO=['demo@example.com'])
    def test_test_banner_escapes_original_recipient_and_fits_full_html_document(self):
        send_notification_mail('Subject', 'Text', ['<script>@example.com'],
                               '<!DOCTYPE html><html><body style="margin:0"><p>Hello</p></body></html>')
        html = mail.outbox[0].alternatives[0].content
        self.assertTrue(html.startswith('<!DOCTYPE html>'))
        self.assertLess(html.index('<body'), html.index('TEST / DEMO'))
        self.assertIn('&lt;script&gt;@example.com', html)
        self.assertNotIn('<script>', html)

    def test_invalid_redirect_config_does_not_send_or_consume_attempts(self):
        row = self.queue()
        configs = [
            {'NOTIFICATIONS_TEST_MODE': True, 'NOTIFICATIONS_REDIRECT_TO': []},
            {'NOTIFICATIONS_TEST_MODE': False, 'NOTIFICATIONS_REDIRECT_TO': ['demo@example.com']},
            {'NOTIFICATIONS_TEST_MODE': True, 'NOTIFICATIONS_REDIRECT_TO': ['invalid']},
            {'NOTIFICATIONS_TEST_MODE': True, 'NOTIFICATIONS_REDIRECT_TO': ['a@example.com\r\nBcc:b@example.com']},
            {'NOTIFICATIONS_TEST_MODE': 'False', 'NOTIFICATIONS_REDIRECT_TO': []},
        ]
        for config in configs:
            with self.subTest(config=config), override_settings(**config):
                with self.assertRaises(CommandError):
                    self.deliver()
                with self.assertRaises(ImproperlyConfigured):
                    send_notification_mail('S', 'B', ['head@example.com'])
        row.refresh_from_db()
        self.assertEqual(row.attempts, 0)
        self.assertEqual(row.status, 'queued')
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(NOTIFICATIONS_DELIVERY_ENABLED=False)
    def test_delivery_disabled_leaves_queue_untouched_but_allows_sender_verification(self):
        row = self.queue()
        with self.assertRaisesMessage(CommandError, 'Notification delivery is disabled'):
            self.deliver()
        row.refresh_from_db()
        self.assertEqual(row.attempts, 0)
        self.assertEqual(row.status, 'queued')
        call_command('send_test_email', '--to', 'operator@example.com', stdout=StringIO())
        self.assertEqual(mail.outbox[0].to, ['operator@example.com'])
        self.assertTrue(mail.outbox[0].subject.startswith('[TEST]'))

    @override_settings(NOTIFICATIONS_TEST_MODE=True, NOTIFICATIONS_REDIRECT_TO=['demo@example.com'])
    def test_sender_verification_cannot_bypass_redirect_policy(self):
        output = StringIO()
        call_command('send_test_email', '--to', 'head@example.com', stdout=output)
        self.assertEqual(mail.outbox[0].to, ['demo@example.com'])
        self.assertTrue(mail.outbox[0].subject.startswith('[TEST]'))
        self.assertNotIn('[TEST] [TEST]', mail.outbox[0].subject)
        self.assertIn('accepted for demo@example.com', output.getvalue())
        self.assertFalse(EmailLog.objects.exists())

    def test_failures_back_off_and_become_terminal_after_five_attempts(self):
        row = self.queue()
        with patch('overtimeapp.delivery.EmailMultiAlternatives.send',
                   side_effect=OSError('sensitive-server-detail')) as send:
            for attempt in range(1, 6):
                EmailLog.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now())
                before = timezone.now()
                self.deliver()
                row.refresh_from_db()
                self.assertEqual(row.attempts, attempt)
                self.assertGreaterEqual(row.next_attempt_at, before + timedelta(minutes=2 ** attempt))
                self.assertEqual(row.status, 'failed' if attempt == 5 else 'queued')
                self.assertNotIn('sensitive-server-detail', row.error_message)
            self.deliver()
        self.assertEqual(send.call_count, 5)
        self.assertIsNone(row.delivered_at)

    def test_zero_acceptance_retries_instead_of_recording_sent(self):
        row = self.queue()
        with patch('overtimeapp.delivery.EmailMultiAlternatives.send', return_value=0):
            self.deliver()
        row.refresh_from_db()
        self.assertEqual(row.status, 'queued')
        self.assertEqual(row.attempts, 1)
        self.assertIsNone(row.delivered_at)


class NotificationProductionSettingsTests(SimpleTestCase):
    def load_settings(self, **extra):
        env = os.environ.copy()
        for key in ('NOTIFICATIONS_DELIVERY_ENABLED', 'NOTIFICATIONS_TEST_MODE', 'NOTIFICATIONS_REDIRECT_TO'):
            env.pop(key, None)
        env.update(DEBUG='False', SECRET_KEY='test-only-unique-secret-for-settings-check-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ',
                   DB_ENGINE='django.db.backends.postgresql', REDIS_URL='redis://127.0.0.1:6379/1',
                   EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                   ALLOWED_HOSTS='overtime.example.com', PUBLIC_BASE_URL='https://overtime.example.com',
                   AUTH_TOKEN_TTL_SECONDS='28800', EMAIL_TIMEOUT='37')
        env.update(extra)
        # Prevent dotenv from loading the developer's notification values into the child.
        code = ('import dotenv; dotenv.load_dotenv=lambda *a, **k: None; '
                'import json; import core.production_settings as s; '
                'print(json.dumps({"delivery":s.NOTIFICATIONS_DELIVERY_ENABLED,"timeout":s.EMAIL_TIMEOUT}))')
        return subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True)

    def test_production_defaults_to_disabled_and_honors_configured_mail_timeout(self):
        result = self.load_settings()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'delivery': False, 'timeout': 37})

    def test_production_sender_requires_explicit_delivery_opt_in(self):
        result = self.load_settings(NOTIFICATIONS_DELIVERY_ENABLED='True')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['delivery'])

    def test_production_refuses_outlook_backend(self):
        result = self.load_settings(EMAIL_BACKEND='overtimeapp.email_backends.OutlookComEmailBackend')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Production requires a configured SMTP email backend', result.stderr)

    def test_malformed_delivery_opt_in_is_rejected(self):
        result = self.load_settings(NOTIFICATIONS_DELIVERY_ENABLED='yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('NOTIFICATIONS_DELIVERY_ENABLED must be True or False', result.stderr)
