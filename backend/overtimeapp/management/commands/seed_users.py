"""Idempotently provision the manager accounts and their role profiles.

Passwords are never stored in source or passed on the command line. Supply them
privately in the process environment, either per account:

    SEED_PASSWORD_YASSIR_AMRANI=... python manage.py seed_users

or once for every account with ``SEED_PASSWORD``. An account created without a
supplied password receives a generated one that is printed a single time.
Existing accounts keep their current password unless ``--reset-passwords`` is
given, so re-running this command after a password change is safe.
"""
import os
import secrets

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from overtimeapp.models import DEPARTMENT_CHOICES, ROLE_CHOICES, UserProfile

# Login is by username; usernames are the email local-part in lower case.
ACCOUNTS = (
    {
        'username': 'yassir.amrani',
        'email': 'Yassir.AMRANI@mubea.com',
        'first_name': 'Yassir',
        'last_name': 'AMRANI',
        'role': 'admin',
        'department': None,
        'is_staff': True,
        'is_superuser': True,
        'password_env': 'SEED_PASSWORD_YASSIR_AMRANI',
    },
    {
        'username': 'andre-nicolas.faucon',
        'email': 'Andre-Nicolas.Faucon@mubea.com',
        'first_name': 'Andre-Nicolas',
        'last_name': 'Faucon',
        'role': 'head_manager',
        'department': None,
        'is_staff': False,
        'is_superuser': False,
        'password_env': 'SEED_PASSWORD_ANDRE_NICOLAS_FAUCON',
    },
    {
        'username': 'mariam.oumalek',
        'email': 'Mariam.Oumalek@mubea.com',
        'first_name': 'Mariam',
        'last_name': 'Oumalek',
        'role': 'hr_manager',
        'department': None,
        'is_staff': False,
        'is_superuser': False,
        'password_env': 'SEED_PASSWORD_MARIAM_OUMALEK',
    },
    {
        'username': 'mehdi.bousfiha',
        'email': 'Mehdi.BOUSFIHA@mubea.com',
        'first_name': 'Mehdi',
        'last_name': 'BOUSFIHA',
        'role': 'dept_manager',
        'department': 'production',
        'is_staff': False,
        'is_superuser': False,
        'password_env': 'SEED_PASSWORD_MEHDI_BOUSFIHA',
    },
    {
        'username': 'charaf.erraoui',
        'email': 'Charaf.ERRAOUI@mubea.com',
        'first_name': 'Charaf',
        'last_name': 'ERRAOUI',
        'role': 'dept_manager',
        'department': 'logistics',
        'is_staff': False,
        'is_superuser': False,
        'password_env': 'SEED_PASSWORD_CHARAF_ERRAOUI',
    },
)


class Command(BaseCommand):
    help = 'Create or update the configured manager accounts and their role profiles.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report the planned changes without writing to the database.',
        )
        parser.add_argument(
            '--reset-passwords',
            action='store_true',
            help='Replace existing passwords with the resolved value instead of keeping them.',
        )

    def handle(self, *args, **options):
        self._validate_accounts()
        dry_run = options['dry_run']

        for account in ACCOUNTS:
            existing = User.objects.filter(username=account['username']).first()
            if dry_run:
                action = 'create' if existing is None else 'update'
                self.stdout.write(f"[dry run] would {action} {account['username']} ({account['role']})")
                continue

            password = None
            if existing is None or options['reset_passwords']:
                password, generated = self._resolve_password(account)
            else:
                generated = False

            with transaction.atomic():
                if existing is None:
                    user = User(username=account['username'])
                else:
                    user = User.objects.select_for_update().get(pk=existing.pk)
                user.email = account['email']
                user.first_name = account['first_name']
                user.last_name = account['last_name']
                user.is_active = True
                user.is_staff = account['is_staff']
                user.is_superuser = account['is_superuser']
                if password:
                    user.set_password(password)
                user.save()
                UserProfile.objects.update_or_create(
                    user=user,
                    defaults={'role': account['role'], 'department': account['department']},
                )

            if existing is None:
                self.stdout.write(self.style.SUCCESS(f"Created {account['username']} ({account['role']})"))
            else:
                self.stdout.write(f"Updated {account['username']} ({account['role']})")
            if generated:
                self.stdout.write(self.style.WARNING(f"  Generated password for {account['username']}: {password}"))
                self.stdout.write('  Store it now; it is not saved in plain text and will not be shown again.')

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run complete: no changes were written.'))

    def _validate_accounts(self):
        roles = dict(ROLE_CHOICES)
        departments = dict(DEPARTMENT_CHOICES)
        for account in ACCOUNTS:
            username = account['username']
            if account['role'] not in roles:
                raise CommandError(f'Account {username} has an unknown role: {account["role"]}')
            if account['department'] is not None and account['department'] not in departments:
                raise CommandError(f'Account {username} has an unknown department: {account["department"]}')
            if account['role'] == 'dept_manager' and not account['department']:
                raise CommandError(f'Department manager {username} requires a department.')

    def _resolve_password(self, account):
        """Return ``(password, generated)`` from the environment, or a fresh random value."""
        password = os.getenv(account['password_env']) or os.getenv('SEED_PASSWORD')
        if password:
            return password, False
        return secrets.token_urlsafe(12), True
