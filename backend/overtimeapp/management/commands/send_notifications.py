"""Deliver a bounded batch of queued emails; schedule this command every minute."""
from datetime import timedelta
import logging
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from overtimeapp.models import EmailLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send due notification emails with up to five attempts. Run every minute.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        if not 1 <= options['limit'] <= 1000:
            raise CommandError('Limit must be between 1 and 1000.')
        ids = list(EmailLog.objects.filter(status='queued', next_attempt_at__lte=timezone.now(), attempts__lt=5)
                   .exclude(body='').order_by('next_attempt_at').values_list('pk', flat=True)[:options['limit']])
        sent = 0
        for pk in ids:
            # Workers serialize on each message. Delivery is at least once: a process crash
            # after SMTP acceptance but before commit may cause a retry of the same message.
            with transaction.atomic():
                item = EmailLog.objects.select_for_update().get(pk=pk)
                if item.status != 'queued' or item.next_attempt_at > timezone.now():
                    continue
                item.attempts += 1
                try:
                    if send_mail(item.subject, item.body, None, [item.recipient]) != 1:
                        raise RuntimeError('Mail backend did not accept the message')
                    item.status = 'sent'
                    item.delivered_at = timezone.now()
                    item.error_message = ''
                    sent += 1
                except Exception as exc:
                    item.status = 'failed' if item.attempts >= 5 else 'queued'
                    # Do not persist SMTP errors that may include credentials or message data.
                    item.error_message = f'Delivery failed ({type(exc).__name__}). Check mail service configuration.'
                    item.next_attempt_at = timezone.now() + timedelta(minutes=2 ** item.attempts)
                    logger.warning('Notification %s delivery attempt %s failed', item.pk, item.attempts)
                item.save(update_fields=['attempts', 'status', 'delivered_at', 'error_message', 'next_attempt_at'])
        self.stdout.write(f'Sent {sent} notifications; examined {len(ids)} queued messages.')
