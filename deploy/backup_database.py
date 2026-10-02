#!/usr/bin/env python3
"""Create a private PostgreSQL backup from the configured Django connection."""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.production_settings')
import django
django.setup()
from django.conf import settings

if len(sys.argv) != 2:
    raise SystemExit('Usage: python deploy/backup_database.py /secure/path/unique-backup.dump')
db = settings.DATABASES['default']
if db['ENGINE'] != 'django.db.backends.postgresql':
    raise SystemExit('This backup command requires PostgreSQL.')
destination = Path(sys.argv[1]).resolve()
env = {**os.environ, 'PGHOST': str(db.get('HOST', '')), 'PGPORT': str(db.get('PORT', '5432')),
       'PGUSER': str(db.get('USER', '')), 'PGPASSWORD': str(db.get('PASSWORD', '')), 'PGDATABASE': str(db['NAME'])}
fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    with os.fdopen(fd, 'wb') as output:
        subprocess.run(['pg_dump', '--format=custom', '--no-owner'], env=env, stdout=output, check=True)
except BaseException:
    destination.unlink(missing_ok=True)
    raise
print(f'Backup created: {destination}')
