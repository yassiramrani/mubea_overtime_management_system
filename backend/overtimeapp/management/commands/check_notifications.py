"""Report notification queue health without sending or updating messages."""
import json

from django.core.management.base import BaseCommand, CommandError

from overtimeapp.notification_health import notification_queue_health


class Command(BaseCommand):
    help = 'Read-only notification queue health; exits 1 for failed or stuck messages.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--stale-minutes', type=int,
            help='Override NOTIFICATIONS_STALE_MINUTES (default 15); whole minutes from 1 to 525600.',
        )
        parser.add_argument('--json', action='store_true', help='Print aggregate health as JSON.')

    def handle(self, *args, **options):
        try:
            health = notification_queue_health(stale_minutes=options['stale_minutes'])
        except ValueError as exc:
            raise CommandError(str(exc), returncode=2) from exc

        if options['json']:
            self.stdout.write(json.dumps(health, sort_keys=True))
        else:
            outcome = 'healthy' if health['healthy'] else 'unhealthy'
            age = health['oldest_queued_age_seconds']
            oldest = 'none' if age is None else f'{age}s'
            self.stdout.write(
                f'Notification queue {outcome}: queued={health["queued_count"]}, '
                f'failed={health["failed_count"]}, stale={health["stale_queued_count"]}, '
                f'exhausted={health["exhausted_queued_count"]}, '
                f'empty_body={health["empty_body_queued_count"]}; '
                f'oldest_queued_age={oldest}, stale_minutes={health["stale_minutes"]}.'
            )

        if not health['healthy']:
            # Django writes this safe error to stderr. JSON stdout stays parseable.
            raise CommandError('Notification queue is unhealthy. Review queue counts and mail service logs.', returncode=1)
