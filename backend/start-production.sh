#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export DJANGO_SETTINGS_MODULE=core.production_settings
python manage.py check --deploy --fail-level WARNING
exec gunicorn core.wsgi:application --bind "${BIND_ADDRESS:-127.0.0.1:8000}" --workers "${WEB_WORKERS:-3}" --timeout 60 --access-logfile - --error-logfile -
