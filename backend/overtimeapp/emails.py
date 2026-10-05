"""Durable notification outbox. Delivery is handled by send_notifications."""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailLog


class OvertimeEmailService:
    @staticmethod
    def queue(overtime_request, recipients, email_type, subject, message, route):
        url = f'{settings.PUBLIC_BASE_URL.rstrip("/")}/{route}'
        role_label, cta_label = {
            'head-manager': ('Head Manager', 'Review overtime request'),
            'hr-manager': ('HR Manager', 'Open HR dashboard'),
            'dept-manager': ('Department Manager', 'Open department dashboard'),
        }.get(route, ('Overtime Manager', 'Open dashboard'))
        if route == 'dept-manager':
            cta_label = {
                'request_approved': 'View approved request',
                'request_rejected': 'Review rejection',
                'assignment_ready': 'View employee assignment',
            }.get(email_type, cta_label)
        elif route == 'hr-manager' and email_type == 'request_approved':
            cta_label = 'Prepare approval for export'

        event_label = dict(EmailLog._meta.get_field('email_type').choices).get(email_type, 'Overtime Update')
        context = {
            'subject': subject,
            'event_label': event_label,
            'message': message,
            'request_id': overtime_request.request_id,
            'title': overtime_request.title,
            'department': overtime_request.get_department_display(),
            'requester_name': overtime_request.requester.get_full_name() or overtime_request.requester.username,
            'status': overtime_request.get_status_display(),
            'start_date': str(overtime_request.start_date),
            'end_date': str(overtime_request.end_date),
            'total_hours': format(Decimal(str(overtime_request.total_hours)), '.2f'),
            'description': overtime_request.description,
            'reason': overtime_request.reason,
            'assignment_context': (
                'Named employee assignment required'
                if overtime_request.requires_employee_assignment
                else 'Department authorization without named employees'
            ),
            'submitted_at': OvertimeEmailService._format_timestamp(overtime_request.created_at),
            'approved_at': OvertimeEmailService._format_timestamp(overtime_request.approval_date),
            'rejected_at': OvertimeEmailService._format_timestamp(overtime_request.rejection_date),
            'approver_name': (
                overtime_request.approved_by.get_full_name() or overtime_request.approved_by.username
                if overtime_request.approved_by_id else ''
            ),
            'role_label': role_label,
            'cta_label': cta_label,
            'url': url,
        }
        # Persist both variants now: retries must deliver the original notification,
        # even if the request or the dashboard URL changes before delivery.
        body = render_to_string('overtimeapp/emails/notification.txt', context)
        html_body = render_to_string('overtimeapp/emails/notification.html', context)
        for recipient in sorted(set(email for email in recipients if email)):
            EmailLog.objects.create(overtime_request=overtime_request, recipient=recipient,
                                    email_type=email_type, subject=subject, body=body,
                                    html_body=html_body, status='queued')

    @staticmethod
    def _format_timestamp(value):
        if value is None:
            return ''
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime('%Y-%m-%d %H:%M %Z').strip()

    @staticmethod
    def send_request_submitted_notification(item):
        recipients = User.objects.filter(is_active=True, profile__role='head_manager').values_list('email', flat=True)
        OvertimeEmailService.queue(item, recipients, 'request_submitted', f'Overtime approval needed — {item.request_id}', 'Review the justification and dates before deciding.', 'head-manager')

    @staticmethod
    def send_approval_notification(item):
        recipients = User.objects.filter(is_active=True, profile__role='hr_manager').values_list('email', flat=True)
        OvertimeEmailService.queue(item, recipients, 'request_approved', f'Overtime approved — {item.request_id}', 'Prepare this advance authorization for export.', 'hr-manager')
        OvertimeEmailService.queue(item, [item.requester.email], 'request_approved', f'Overtime approved — {item.request_id}', 'Your request has been approved.', 'dept-manager')

    @staticmethod
    def send_rejection_notification(item):
        OvertimeEmailService.queue(item, [item.requester.email], 'request_rejected', f'Overtime rejected — {item.request_id}', item.rejection_reason, 'dept-manager')

    @staticmethod
    def send_assignment_notification(item, employees):
        names = ', '.join(u.get_full_name() or u.username for u in employees) or 'No named employees (department authorization)'
        OvertimeEmailService.queue(item, [item.requester.email], 'assignment_ready', f'Employees assigned — {item.request_id}', f'Assigned employees: {names}', 'dept-manager')
