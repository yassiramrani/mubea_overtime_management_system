"""Send one message through the configured mail backend to verify delivery.

Run this after setting the EMAIL_* values, before relying on the outbox:

    python manage.py send_test_email --to Yassir.AMRANI@mubea.com

The command never touches the notification outbox, so it cannot mark a real
notification as failed. Failures are reported on the terminal only and are not
stored; the exception text usually names the SMTP reason (for example a refused
sender or an authentication failure) and does not contain the password.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

SMTP_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

# Backends that only record a message locally rather than delivering it.
LOCAL_ONLY_BACKENDS = {
    'django.core.mail.backends.console.EmailBackend',
    'django.core.mail.backends.locmem.EmailBackend',
    'django.core.mail.backends.dummy.EmailBackend',
    'django.core.mail.backends.filebased.EmailBackend',
}


class Command(BaseCommand):
    help = 'Send a single test email through the configured backend to verify delivery.'

    def add_arguments(self, parser):
        parser.add_argument('--to', required=True, help='Recipient address for the test message.')

    def handle(self, *args, **options):
        recipient = options['to'].strip()
        try:
            validate_email(recipient)
        except ValidationError:
            raise CommandError(f'Invalid recipient address: {recipient}')

        if settings.EMAIL_BACKEND in LOCAL_ONLY_BACKENDS:
            self.stdout.write(self.style.WARNING(
                f'{settings.EMAIL_BACKEND} is configured, so nothing leaves this machine. '
                'Select a delivering backend to test real delivery.'))

        self.stdout.write(f'Backend: {settings.EMAIL_BACKEND}')
        self.stdout.write(f'Sender: {settings.DEFAULT_FROM_EMAIL}')
        if settings.EMAIL_BACKEND == SMTP_BACKEND:
            scheme = 'SSL' if settings.EMAIL_USE_SSL else f'TLS={settings.EMAIL_USE_TLS}'
            self.stdout.write(f'Server: {settings.EMAIL_HOST}:{settings.EMAIL_PORT} ({scheme})')
        elif settings.EMAIL_BACKEND.endswith('OutlookComEmailBackend'):
            self.stdout.write('Sending through the signed-in Outlook desktop profile; DEFAULT_FROM_EMAIL is ignored.')

        try:
            accepted = send_mail(
                subject='Overtime notifications test',
                message='Test message from the overtime management system. Real notifications use the same settings.',
                from_email=None,
                recipient_list=[recipient],
                fail_silently=False,
            )
        except Exception as exc:
            raise CommandError(f'Delivery failed ({type(exc).__name__}): {exc}')

        if accepted != 1:
            raise CommandError('The mail backend did not accept the message.')

        self.stdout.write(self.style.SUCCESS(f'Test message accepted for {recipient}.'))
        self.stdout.write('Check the mailbox; delivery is asynchronous once the server accepts the message.')
