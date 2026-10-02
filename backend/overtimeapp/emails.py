"""Durable notification outbox. Delivery is handled by send_notifications."""
from django.conf import settings
from django.contrib.auth.models import User
from .models import EmailLog


class OvertimeEmailService:
    @staticmethod
    def queue(overtime_request, recipients, email_type, subject, message, route):
        url = f'{settings.PUBLIC_BASE_URL.rstrip("/")}/{route}'
        body = f'{subject}\n\nRequest: {overtime_request.request_id}\nTitle: {overtime_request.title}\nDepartment: {overtime_request.get_department_display()}\nAuthorized employee-hours requested: {overtime_request.total_hours}\n\n{message}\n\nOpen dashboard: {url}\n'
        for recipient in sorted(set(email for email in recipients if email)):
            EmailLog.objects.create(overtime_request=overtime_request, recipient=recipient,
                                    email_type=email_type, subject=subject, body=body, status='queued')

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
