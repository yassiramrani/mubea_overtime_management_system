from datetime import timedelta
from io import StringIO
import json
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from .management.commands.check_notifications import Command
from .models import EmailLog
from .notification_health import notification_queue_health


@override_settings(NOTIFICATIONS_STALE_MINUTES=15)
class NotificationHealthTests(TestCase):
    def setUp(self):
        self.now = timezone.now()

    def message(self, *, age_seconds=0, **fields):
        item = EmailLog.objects.create(**{
            'recipient': 'private-recipient@example.com',
            'subject': 'Private overtime details',
            'body': 'Private message body',
            'error_message': 'Private SMTP error',
            'email_type': 'request_submitted',
            'status': 'queued',
            **fields,
        })
        EmailLog.objects.filter(pk=item.pk).update(sent_at=self.now - timedelta(seconds=age_seconds))
        return item

    def health(self, **options):
        return notification_queue_health(now=self.now, **options)

    def test_empty_or_sent_only_queue_is_healthy(self):
        empty = self.health()
        self.assertTrue(empty['healthy'])
        self.assertIsNone(empty['oldest_queued_age_seconds'])
        self.message(status='sent', attempts=5, body='', age_seconds=86400)
        sent = self.health()
        self.assertTrue(sent['healthy'])
        self.assertEqual(sent['queued_count'], 0)
        self.assertEqual(sent['unhealthy_count'], 0)
        self.assertIsNone(sent['oldest_queued_age_seconds'])

    def test_stale_threshold_includes_exact_boundary_and_override(self):
        self.message(age_seconds=899)
        self.assertTrue(self.health()['healthy'])
        self.message(age_seconds=900)
        health = self.health()
        self.assertFalse(health['healthy'])
        self.assertEqual(health['queued_count'], 2)
        self.assertEqual(health['stale_queued_count'], 1)
        self.assertEqual(health['oldest_queued_age_seconds'], 900)
        self.assertTrue(self.health(stale_minutes=16)['healthy'])
        with override_settings(NOTIFICATIONS_STALE_MINUTES=14):
            self.assertEqual(self.health()['stale_queued_count'], 2)

    def test_retry_backoff_does_not_hide_stale_queue_age(self):
        self.message(age_seconds=1800, attempts=4, next_attempt_at=self.now + timedelta(hours=1))
        health = self.health()
        self.assertFalse(health['healthy'])
        self.assertEqual(health['stale_queued_count'], 1)
        self.assertEqual(health['exhausted_queued_count'], 0)
        self.assertEqual(health['oldest_queued_age_seconds'], 1800)

    def test_failed_messages_are_unhealthy_even_when_queue_is_empty(self):
        self.message(status='failed', attempts=5, age_seconds=86400)
        health = self.health()
        self.assertFalse(health['healthy'])
        self.assertEqual(health['failed_count'], 1)
        self.assertEqual(health['unhealthy_count'], 1)
        self.assertEqual(health['queued_count'], 0)
        self.assertIsNone(health['oldest_queued_age_seconds'])

    def test_exhausted_and_empty_body_rows_are_unhealthy_before_age_threshold(self):
        self.message(attempts=5)
        self.message(body='')
        self.message(attempts=6, body='', age_seconds=1800)
        health = self.health()
        self.assertFalse(health['healthy'])
        self.assertEqual(health['stale_queued_count'], 1)
        self.assertEqual(health['exhausted_queued_count'], 2)
        self.assertEqual(health['empty_body_queued_count'], 2)
        self.assertEqual(health['unhealthy_count'], 3)

    def test_healthy_json_command_output(self):
        self.message(age_seconds=600, next_attempt_at=self.now + timedelta(minutes=2))
        output = StringIO()
        with patch('overtimeapp.notification_health.timezone.now', return_value=self.now):
            call_command('check_notifications', '--json', stdout=output)
        health = json.loads(output.getvalue())
        self.assertTrue(health['healthy'])
        self.assertEqual(health['queued_count'], 1)
        self.assertEqual(health['oldest_queued_age_seconds'], 600)

    def test_unhealthy_command_has_safe_json_and_never_mutates_or_sends(self):
        self.message(status='failed', attempts=5)
        self.message(age_seconds=1800)
        before = list(EmailLog.objects.order_by('pk').values())
        output = StringIO()
        with patch('django.core.mail.get_connection') as mail_connection:
            with self.assertRaises(CommandError) as raised:
                call_command('check_notifications', '--json', stdout=output)
            mail_connection.assert_not_called()
        self.assertEqual(raised.exception.returncode, 1)
        health = json.loads(output.getvalue())
        self.assertFalse(health['healthy'])
        self.assertEqual(health['failed_count'], 1)
        self.assertEqual(health['stale_queued_count'], 1)
        self.assertEqual(list(EmailLog.objects.order_by('pk').values()), before)
        for secret in ('private-recipient', 'Private overtime', 'Private message', 'Private SMTP'):
            self.assertNotIn(secret, output.getvalue())
            self.assertNotIn(secret, str(raised.exception))

    def test_command_line_keeps_json_on_stdout_and_failure_on_stderr(self):
        self.message(status='failed')
        output, errors = StringIO(), StringIO()
        command = Command(stdout=output, stderr=errors)
        with self.assertRaises(SystemExit) as raised:
            # Django's CLI wrapper closes every database connection in a finally block.
            # Inside a TestCase that kills the surrounding test transaction on PostgreSQL,
            # so the framework cleanup is neutralized; it is not command behaviour.
            with patch('django.core.management.base.connections.close_all'):
                command.run_from_argv(['manage.py', 'check_notifications', '--json', '--skip-checks'])
        self.assertEqual(raised.exception.code, 1)
        self.assertFalse(json.loads(output.getvalue())['healthy'])
        self.assertIn('CommandError: Notification queue is unhealthy.', errors.getvalue())

    def test_human_output_contains_only_aggregate_counts(self):
        self.message(body='')
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command('check_notifications', stdout=output)
        self.assertIn('Notification queue unhealthy:', output.getvalue())
        self.assertIn('empty_body=1', output.getvalue())
        self.assertNotIn('private-recipient', output.getvalue())

    def test_threshold_validation_precedes_database_queries(self):
        for value in (0, -1, 525601, True, '15', 1.5):
            with self.subTest(value=value):
                with self.assertNumQueries(0), self.assertRaises(ValueError):
                    self.health(stale_minutes=value)
        for value in (0, -1, 525601):
            with self.subTest(command_value=value):
                output = StringIO()
                with self.assertNumQueries(0), self.assertRaises(CommandError) as raised:
                    call_command('check_notifications', stale_minutes=value, stdout=output)
                self.assertEqual(raised.exception.returncode, 2)
                self.assertEqual(output.getvalue(), '')
        with override_settings(NOTIFICATIONS_STALE_MINUTES=0):
            with self.assertRaises(CommandError):
                call_command('check_notifications', stdout=StringIO())
            call_command('check_notifications', stale_minutes=15, stdout=StringIO())
