"""Mail delivery policy shared by the outbox and sender verification command."""
import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.utils.html import escape


def validate_notification_configuration():
    """Fail before sending or consuming retries when redirection is misconfigured."""
    test_mode = settings.NOTIFICATIONS_TEST_MODE
    redirect_to = settings.NOTIFICATIONS_REDIRECT_TO
    if not isinstance(test_mode, bool) or not isinstance(redirect_to, (list, tuple)):
        raise ImproperlyConfigured('Notification test mode requires a boolean and a recipient list.')
    if test_mode and not redirect_to:
        raise ImproperlyConfigured('NOTIFICATIONS_TEST_MODE requires NOTIFICATIONS_REDIRECT_TO.')
    if redirect_to and not test_mode:
        raise ImproperlyConfigured('NOTIFICATIONS_REDIRECT_TO requires NOTIFICATIONS_TEST_MODE=True.')
    recipients = []
    for address in redirect_to:
        try:
            if not isinstance(address, str):
                raise ValidationError('Invalid address type.')
            validate_email(address)
        except ValidationError as exc:
            raise ImproperlyConfigured('NOTIFICATIONS_REDIRECT_TO contains an invalid email address.') from exc
        if address.lower() not in {recipient.lower() for recipient in recipients}:
            recipients.append(address)
    return test_mode, recipients


def send_notification_mail(subject, body, recipients, html_body=''):
    """Deliver saved content, using only the test allowlist when test mode is on."""
    test_mode, redirect_to = validate_notification_configuration()
    if test_mode:
        original = ', '.join(recipients)
        if not subject.startswith('[TEST]'):
            subject = f'[TEST] {subject}'
        marker = f'TEST / DEMO — redirected notification.\nOriginal recipient(s): {original}'
        body = f'{marker}\n\n{body}'
        if html_body:
            banner = (
                '<div style="padding:16px;background:#fff3cd;color:#664d03;'
                'font-family:Arial,sans-serif;font-size:14px;">'
                '<strong>TEST / DEMO — redirected notification.</strong><br>'
                f'Original recipient(s): {escape(original)}</div>'
            )
            body_tag = re.search(r'<body\b[^>]*>', html_body, flags=re.IGNORECASE)
            if body_tag:
                html_body = html_body[:body_tag.end()] + banner + html_body[body_tag.end():]
            else:
                html_body = banner + html_body
        recipients = redirect_to
    message = EmailMultiAlternatives(subject=subject, body=body, from_email=None, to=recipients)
    if html_body:
        message.attach_alternative(html_body, 'text/html')
    return message.send(fail_silently=False)
