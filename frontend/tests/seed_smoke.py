"""Fixture data exclusively for the temporary database allocated by smoke.mjs."""
import os
from datetime import timedelta
import django
from smoke_database import require_smoke_database

require_smoke_database()
django.setup()
from django.core.management import call_command
from django.contrib.auth.models import User
from overtimeapp.models import UserProfile, OvertimeRequest
from decimal import Decimal
from django.utils import timezone

call_command('migrate', verbosity=0)
for name, role, department in [('smoke-dept', 'dept_manager', 'logistics'), ('smoke-head', 'head_manager', None), ('smoke-hr', 'hr_manager', None), ('smoke-fixture', 'dept_manager', 'maintenance')]:
    user = User.objects.create_user(name, f'{name}@example.invalid', os.environ['SMOKE_PASSWORD'])
    UserProfile.objects.create(user=user, role=role, department=department)
User.objects.create_superuser('smoke-admin', 'smoke-admin@example.invalid', os.environ['SMOKE_PASSWORD'])
for index in range(25):
    User.objects.create_user(f'employee-{index:02}', first_name=f'Employee {index:02}')
dept = User.objects.get(username='smoke-dept')
head = User.objects.get(username='smoke-head')
fixture_manager = User.objects.get(username='smoke-fixture')
start_date = timezone.localdate() + timedelta(days=30)
created_base = timezone.now() - timedelta(days=45)
for index in range(23):
    historical = OvertimeRequest.objects.create(request_id=f'SMOKE-HISTORY-{index:02}', requester=dept,
        department='logistics', title=f'Historical approval request {index:02}',
        description='Inventory preparation', reason='Upcoming stock count', start_date=start_date,
        end_date=start_date, total_hours=Decimal(index + 1), status='rejected', rejection_reason='Schedule changed')
    approved = OvertimeRequest.objects.create(request_id=f'SMOKE-APPROVED-{index:02}', requester=fixture_manager,
        department='maintenance', title=f'Approved maintenance fixture {index:02}',
        description='Planned maintenance', reason='Equipment preparation', start_date=start_date,
        end_date=start_date, total_hours=Decimal('2'), status='approved', requires_employee_assignment=False,
        approved_by=head, approval_date=created_base + timedelta(days=1))
    # Search terms such as "00" must never accidentally match a random request UUID.
    # Explicit timestamps also make both orderings independent of database timer precision.
    OvertimeRequest.objects.filter(pk=historical.pk).update(created_at=created_base + timedelta(seconds=index))
    OvertimeRequest.objects.filter(pk=approved.pk).update(created_at=created_base + timedelta(days=1, seconds=index))
