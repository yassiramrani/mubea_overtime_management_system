"""Read-only, aggregate health of the durable notification outbox."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Min, Q
from django.utils import timezone

from .models import EmailLog


MAX_STALE_MINUTES = 525600


def validate_stale_minutes(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_STALE_MINUTES:
        raise ValueError(f'Stale minutes must be an integer between 1 and {MAX_STALE_MINUTES}.')
    return value


def notification_queue_health(*, stale_minutes=None, now=None):
    """Return counts and age only; never expose message content or change rows.

    EmailLog.sent_at is the existing auto_now_add enqueue timestamp, despite its
    legacy name. Retries update next_attempt_at, so age must use sent_at instead.
    A queued row becomes stale at or beyond the configured age threshold.
    """
    threshold = validate_stale_minutes(
        getattr(settings, 'NOTIFICATIONS_STALE_MINUTES', 15) if stale_minutes is None else stale_minutes
    )
    checked_at = timezone.now() if now is None else now
    queued = Q(status='queued')
    failed = Q(status='failed')
    stale = queued & Q(sent_at__lte=checked_at - timedelta(minutes=threshold))
    exhausted = queued & Q(attempts__gte=5)
    empty_body = queued & Q(body='')
    result = EmailLog.objects.aggregate(
        queued_count=Count('pk', filter=queued),
        failed_count=Count('pk', filter=failed),
        stale_queued_count=Count('pk', filter=stale),
        exhausted_queued_count=Count('pk', filter=exhausted),
        empty_body_queued_count=Count('pk', filter=empty_body),
        unhealthy_count=Count('pk', filter=failed | stale | exhausted | empty_body),
        oldest_queued_at=Min('sent_at', filter=queued),
    )
    oldest = result.pop('oldest_queued_at')
    result.update(
        healthy=result['unhealthy_count'] == 0,
        checked_at=checked_at.isoformat(),
        stale_minutes=threshold,
        oldest_queued_age_seconds=None if oldest is None else max(0, int((checked_at - oldest).total_seconds())),
    )
    return result
