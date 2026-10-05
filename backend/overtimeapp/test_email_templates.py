from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal
from html.parser import HTMLParser

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils.html import escape

from .emails import OvertimeEmailService
from .models import EmailLog, OvertimeRequest, UserProfile


class LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.append(dict(attrs).get('href'))


@override_settings(PUBLIC_BASE_URL='https://overtime.example.com/portal/')
class NotificationTemplateTests(TestCase):
    def setUp(self):
        self.requester = self.create_user('dept', 'dept_manager', 'logistics')
        self.head = self.create_user('head', 'head_manager')
        self.hr = self.create_user('hr', 'hr_manager')
        self.item = OvertimeRequest.objects.create(
            requester=self.requester,
            department='logistics',
            title='Inventory count',
            description='Count warehouse stock.\nCheck all bins.',
            reason='Month end inventory',
            start_date='2026-10-05',
            end_date='2026-10-06',
            total_hours=Decimal('12.50'),
        )

    def create_user(self, username, role, department=None, **kwargs):
        user = User.objects.create_user(username, kwargs.pop('email', f'{username}@example.com'), **kwargs)
        UserProfile.objects.create(user=user, role=role, department=department)
        return user

    def assert_dashboard_link(self, log, route):
        expected = f'https://overtime.example.com/portal/{route}'
        parser = LinkCollector()
        parser.feed(log.html_body)
        self.assertEqual(parser.links, [expected, expected])
        self.assertIn(f'Open dashboard: {expected}', log.body)

    def test_submission_preserves_recipient_filtering_and_contains_request_context(self):
        self.create_user('inactive-head', 'head_manager', is_active=False)
        self.create_user('blank-head', 'head_manager', email='')
        self.create_user('duplicate-head', 'head_manager', email=self.head.email)
        self.create_user('admin', 'admin')
        OvertimeEmailService.send_request_submitted_notification(self.item)

        log = EmailLog.objects.get()
        self.assertEqual(log.recipient, self.head.email)
        self.assertEqual(log.email_type, 'request_submitted')
        self.assertEqual(log.status, 'queued')
        self.assert_dashboard_link(log, 'head-manager')
        for text in [self.item.request_id, 'Inventory count', 'Logistics', '12.50',
                     '2026-10-05', '2026-10-06', 'Month end inventory',
                     'Named employee assignment required', 'Review overtime request']:
            with self.subTest(text=text):
                self.assertIn(text, log.body)
                self.assertIn(text, log.html_body)
        self.assertIn('Employee-hours requested', log.html_body)
        self.assertIn('Authorized employee-hours requested: 12.50', log.body)
        self.assertIn('Count warehouse stock.<br>Check all bins.', log.html_body)
        self.assertIn('Count warehouse stock.\nCheck all bins.', log.body)

    def test_approval_has_distinct_hr_and_requester_actions_and_decision_context(self):
        self.item.status = 'approved'
        self.item.approved_by = self.head
        self.item.approval_date = datetime(2026, 10, 4, 9, 30, tzinfo=datetime_timezone.utc)
        self.item.save()
        OvertimeEmailService.send_approval_notification(self.item)

        self.assertEqual(EmailLog.objects.count(), 2)
        for recipient, route, message, action in [
            (self.hr.email, 'hr-manager', 'Prepare this advance authorization for export.', 'Prepare approval for export'),
            (self.requester.email, 'dept-manager', 'Your request has been approved.', 'View approved request'),
        ]:
            with self.subTest(recipient=recipient):
                log = EmailLog.objects.get(recipient=recipient)
                self.assertEqual(log.email_type, 'request_approved')
                self.assert_dashboard_link(log, route)
                for text in [message, action, '2026-10-04', 'Approved by', self.head.username]:
                    self.assertIn(text, log.body)
                    self.assertIn(text, log.html_body)

    def test_rejection_shows_reason_date_and_requester_action(self):
        self.item.status = 'rejected'
        self.item.rejection_reason = 'Budget unavailable.\nTry next month.'
        self.item.rejection_date = datetime(2026, 10, 4, 9, 30, tzinfo=datetime_timezone.utc)
        self.item.save()
        OvertimeEmailService.send_rejection_notification(self.item)

        log = EmailLog.objects.get()
        self.assertEqual(log.recipient, self.requester.email)
        self.assertEqual(log.email_type, 'request_rejected')
        self.assert_dashboard_link(log, 'dept-manager')
        self.assertIn('Budget unavailable.\nTry next month.', log.body)
        self.assertIn('Budget unavailable.<br>Try next month.', log.html_body)
        self.assertIn('Rejected on', log.html_body)
        self.assertIn('2026-10-04', log.html_body)
        self.assertIn('Review rejection', log.html_body)

    def test_assignment_includes_escaped_employee_names_and_no_named_employee_context(self):
        employee = User.objects.create_user('employee', first_name='<img src=x>', last_name='A & B')
        OvertimeEmailService.send_assignment_notification(self.item, [employee])
        log = EmailLog.objects.get()
        self.assertEqual(log.email_type, 'assignment_ready')
        self.assertEqual(log.recipient, self.requester.email)
        self.assert_dashboard_link(log, 'dept-manager')
        self.assertIn('Assigned employees: <img src=x> A & B', log.body)
        self.assertIn('Assigned employees: &lt;img src=x&gt; A &amp; B', log.html_body)
        self.assertNotIn('<img', log.html_body)
        self.assertIn('View employee assignment', log.html_body)

        self.item.requires_employee_assignment = False
        self.item.save()
        OvertimeEmailService.send_assignment_notification(self.item, [])
        empty_assignment = EmailLog.objects.exclude(pk=log.pk).get()
        for body in [empty_assignment.body, empty_assignment.html_body]:
            self.assertIn('No named employees (department authorization)', body)
            self.assertIn('Department authorization without named employees', body)

    def test_export_notification_uses_same_template_and_hr_route(self):
        OvertimeEmailService.queue(
            self.item, [self.hr.email], 'export_notification', 'Approval export ready',
            'Export batch is ready for review.', 'hr-manager',
        )
        log = EmailLog.objects.get()
        self.assertEqual(log.email_type, 'export_notification')
        self.assertIn('Export Notification', log.html_body)
        self.assertIn('Export batch is ready for review.', log.html_body)
        self.assert_dashboard_link(log, 'hr-manager')

    def test_html_escapes_all_dynamic_content_without_changing_plain_text(self):
        payload = '<script>alert("x")</script> & <a href="evil">link</a>'
        self.requester.first_name = payload
        self.requester.save()
        self.item.title = payload
        self.item.description = payload
        self.item.reason = payload
        self.item.save()
        OvertimeEmailService.queue(
            self.item, [self.head.email], 'request_submitted', payload, payload, 'head-manager',
        )

        log = EmailLog.objects.get()
        self.assertIn(escape(payload), log.html_body)
        self.assertGreaterEqual(log.html_body.count(escape(payload)), 6)
        self.assertNotIn('<script>', log.html_body)
        self.assertNotIn('href="evil"', log.html_body)
        self.assertIn(payload, log.body)
        self.assertNotIn('&lt;script&gt;', log.body)
        self.assertEqual(log.subject, payload)
        self.assert_dashboard_link(log, 'head-manager')

    def test_outbox_snapshots_both_variants_before_request_and_settings_change(self):
        OvertimeEmailService.send_request_submitted_notification(self.item)
        log = EmailLog.objects.get()
        original_body, original_html = log.body, log.html_body

        OvertimeRequest.objects.filter(pk=self.item.pk).update(
            title='Replacement title', reason='Replacement justification',
            total_hours=Decimal('42.00'), start_date='2026-11-01', end_date='2026-11-02',
        )
        self.item.refresh_from_db()
        self.requester.username = 'replacement-user'
        self.requester.save()
        with override_settings(PUBLIC_BASE_URL='https://replacement.example.com'):
            log.refresh_from_db()
            self.assertEqual(log.body, original_body)
            self.assertEqual(log.html_body, original_html)
            self.assert_dashboard_link(log, 'head-manager')
            OvertimeEmailService.send_request_submitted_notification(self.item)

        later = EmailLog.objects.exclude(pk=log.pk).get()
        self.assertIn('Replacement title', later.body)
        self.assertIn('Replacement title', later.html_body)
        self.assertIn('42.00', later.html_body)
        self.assertIn('https://replacement.example.com/head-manager', later.html_body)
        self.assertNotIn('Replacement title', log.html_body)

    def test_legacy_rows_remain_plain_text_until_replaced_by_new_notifications(self):
        legacy = EmailLog.objects.create(
            overtime_request=self.item, recipient=self.head.email,
            email_type='request_submitted', subject='Existing notification', body='Existing body',
            status='queued',
        )
        legacy.refresh_from_db()
        self.assertEqual(legacy.html_body, '')
        self.assertEqual(legacy.body, 'Existing body')
