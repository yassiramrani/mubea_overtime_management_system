"""Simulate external account/assignment changes in the guarded smoke database only."""
import sys
import django
from smoke_database import require_smoke_database

require_smoke_database()
django.setup()

from django.contrib.auth.models import User
from django.db.models import F
from overtimeapp.models import OvertimeRequest

if sys.argv[1:] == ['deactivate-employee']:
    changed = User.objects.filter(username='employee-00', is_active=True).update(is_active=False)
elif sys.argv[1:] == ['advance-assignment-version']:
    changed = OvertimeRequest.objects.filter(
        requester__username='smoke-dept', title='Inventory overtime smoke approval', status='approved'
    ).update(version=F('version') + 1)
else:
    raise RuntimeError('Unknown smoke fixture operation.')
if changed != 1:
    raise RuntimeError(f'Expected exactly one smoke fixture update; changed {changed}.')
