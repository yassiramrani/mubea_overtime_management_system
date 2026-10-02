"""Refuse fixture writes outside smoke.mjs's isolated temporary SQLite database."""
import os
from pathlib import Path
from tempfile import gettempdir


def require_smoke_database():
    database = Path(os.environ.get('DB_NAME', '')).resolve()
    if (
        os.environ.get('DB_ENGINE') != 'django.db.backends.sqlite3'
        or database.name != 'db.sqlite3'
        or not database.parent.name.startswith('overtime-smoke-')
        or database.parent.parent != Path(gettempdir()).resolve()
        or not os.environ.get('SMOKE_PASSWORD')
        or os.environ.get('EMAIL_BACKEND') != 'django.core.mail.backends.locmem.EmailBackend'
    ):
        raise RuntimeError('Smoke fixtures require an isolated temporary database and in-memory email.')
    return database
