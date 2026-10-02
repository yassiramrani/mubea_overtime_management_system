"""
Email service for overtime management system notifications
"""
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class OvertimeEmailService:
    """Handle all email notifications for overtime management"""

    @staticmethod
    def send_request_submitted_notification(overtime_request):
        """
        Send email to head manager when overtime request is submitted
        """
        try:
            from .models import UserProfile
            
            # Get all head managers
            head_managers = User.objects.filter(
                profile__role='head_manager'
            ).values_list('email', flat=True)
            
            if not head_managers:
                logger.warning("No head managers found for notification")
                return False
            
            subject = f"New Overtime Request - {overtime_request.request_id}"
            
            context = {
                'request': overtime_request,
                'requester_name': overtime_request.requester.get_full_name(),
                'department': overtime_request.get_department_display(),
                'dashboard_url': f"{settings.PUBLIC_BASE_URL}/dashboard/approvals",
            }
            
            html_message = render_to_string('emails/request_submitted.html', context)
            text_message = render_to_string('emails/request_submitted.txt', context)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=list(head_managers)
            )
            email.attach_alternative(html_message, "text/html")
            email.send()
            
            # Log email
            from .models import EmailLog
            EmailLog.objects.create(
                overtime_request=overtime_request,
                recipient=', '.join(head_managers),
                subject=subject,
                email_type='request_submitted',
                status='sent'
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending request submitted email: {str(e)}")
            return False

    @staticmethod
    def send_approval_notification(overtime_request):
        """
        Send email to HR manager when request is approved
        """
        try:
            from .models import UserProfile
            
            # Get all HR managers
            hr_managers = User.objects.filter(
                profile__role='hr_manager'
            ).values_list('email', flat=True)
            
            if not hr_managers:
                logger.warning("No HR managers found for notification")
                return False
            
            subject = f"Approved Overtime Request - {overtime_request.request_id}"
            
            context = {
                'request': overtime_request,
                'requester_name': overtime_request.requester.get_full_name(),
                'department': overtime_request.get_department_display(),
                'dashboard_url': f"{settings.PUBLIC_BASE_URL}/dashboard/assignments",
            }
            
            html_message = render_to_string('emails/request_approved_hr.html', context)
            text_message = render_to_string('emails/request_approved_hr.txt', context)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=list(hr_managers)
            )
            email.attach_alternative(html_message, "text/html")
            email.send()
            
            # Log email
            from .models import EmailLog
            EmailLog.objects.create(
                overtime_request=overtime_request,
                recipient=', '.join(hr_managers),
                subject=subject,
                email_type='request_approved',
                status='sent'
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending approval email to HR: {str(e)}")
            return False

    @staticmethod
    def send_rejection_notification(overtime_request):
        """
        Send email to department manager when request is rejected
        """
        try:
            subject = f"Overtime Request Rejected - {overtime_request.request_id}"
            
            context = {
                'request': overtime_request,
                'rejection_reason': overtime_request.rejection_reason,
                'dashboard_url': f"{settings.PUBLIC_BASE_URL}/dashboard/requests",
            }
            
            html_message = render_to_string('emails/request_rejected.html', context)
            text_message = render_to_string('emails/request_rejected.txt', context)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[overtime_request.requester.email]
            )
            email.attach_alternative(html_message, "text/html")
            email.send()
            
            # Log email
            from .models import EmailLog
            EmailLog.objects.create(
                overtime_request=overtime_request,
                recipient=overtime_request.requester.email,
                subject=subject,
                email_type='request_rejected',
                status='sent'
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending rejection email: {str(e)}")
            return False

    @staticmethod
    def send_assignment_notification(overtime_request, assigned_employees):
        """
        Send email to department manager with assignment details
        """
        try:
            subject = f"Overtime Assignment Confirmed - {overtime_request.request_id}"
            
            employee_list = [emp.get_full_name() for emp in assigned_employees]
            
            context = {
                'request': overtime_request,
                'assigned_employees': employee_list,
                'dashboard_url': f"{settings.PUBLIC_BASE_URL}/dashboard/requests",
            }
            
            html_message = render_to_string('emails/assignment_notification.html', context)
            text_message = render_to_string('emails/assignment_notification.txt', context)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[overtime_request.requester.email]
            )
            email.attach_alternative(html_message, "text/html")
            email.send()
            
            # Log email
            from .models import EmailLog
            EmailLog.objects.create(
                overtime_request=overtime_request,
                recipient=overtime_request.requester.email,
                subject=subject,
                email_type='assignment_ready',
                status='sent'
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending assignment notification: {str(e)}")
            return False


# For backwards compatibility
send_email = OvertimeEmailService()
