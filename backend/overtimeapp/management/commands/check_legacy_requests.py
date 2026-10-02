from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = 'Read-only data preflight before the workflow integrity migration.'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute('SELECT id FROM overtime_requests WHERE end_date < start_date OR total_hours < 0.5 OR hourly_rate < 0')
            invalid = [row[0] for row in cursor.fetchall()]
            cursor.execute("SELECT COUNT(*) FROM overtime_requests WHERE status = 'approved' AND (approved_by_id IS NULL OR approval_date IS NULL)")
            unaudited = cursor.fetchone()[0]
        if unaudited:
            self.stdout.write(self.style.WARNING(f'{unaudited} legacy approved requests lack complete approval attribution. Review against authoritative records; do not invent an approval history.'))
        if invalid:
            raise CommandError(f'Invalid request IDs: {invalid}. Correct against authoritative records before applying constraints.')
        self.stdout.write(self.style.SUCCESS('Date, hours, and rate constraints are satisfied.'))
