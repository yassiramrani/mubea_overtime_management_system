# Django backend

See [Getting started](../GETTING_STARTED.md) for the canonical Windows/Linux installation and account setup. Use Python 3.12 and install `requirements.txt` in a virtual environment. Run management commands from this directory.

## Configuration and authentication

`core.settings` loads local environment values through python-dotenv. SQLite and console email support local development. `core.production_settings` requires PostgreSQL, a strong secret, Redis, SMTP, explicit hosts, and HTTPS configuration; supply `DJANGO_SETTINGS_MODULE=core.production_settings` in the process environment when deploying.

Current browser authentication is username/password token login, with an eight-hour default token lifetime and server-side logout. Tokens are stored in browser local storage. Django session authentication is also accepted by the API. App MFA, verified-email enrollment, recovery screens, and migration to cookie-based browser sessions are **planned Phase 2 work**.

## Main API contracts

Routes below are relative to `/api/`. Lists use role-scoped access and normally return paginated `count`, `next`, `previous`, and `results` fields with 20 records per page.

| Method and route | Behavior |
|---|---|
| `POST auth/login/` | Accept `username` and `password`; return `token` |
| `POST auth/logout/` | Delete the user's token and end the Django session |
| `GET users/me/` | Current user and effective role |
| `GET users/?search=...` | HR/admin employee search; eligible accounts only |
| `GET profiles/my_profile/` | Current stored profile, if present |
| `GET requests/` | Role-scoped requests; `status`, `department`, `search`, `ordering`, and `page` filters |
| `POST requests/` | Submit an advance overtime request |
| `PATCH requests/{id}/approve/` | Approve a pending request; no request-field payload |
| `PATCH requests/{id}/reject/` | Reject a pending request with `rejection_reason` |
| `POST requests/{id}/withdraw/` | Requester withdraws a pending request with `reason` |
| `GET requests/{id}/history/` | Audit history for a visible request |
| `GET assignments/` | HR/admin assignment list |
| `POST assignments/` | Create or replace a request's employee selection using `expected_version` |
| `POST sap-exports/preview/` | Validate the explicitly selected request IDs and versions |
| `POST sap-exports/export_to_csv/` | Create a saved review CSV batch |
| `GET export-batches/` | Saved export history |
| `GET export-batches/{id}/download/` | Authenticated re-download |
| `POST export-batches/{id}/record_result/` | Record a human-reported confirmed/failed import outcome |
| `GET email-logs/` | Application-admin notification log |

An API client sends `Authorization: Token <token>` after login. Do not commit tokens or put credentials into shared command examples.

Submission accepts `department`, `title`, `description`, `reason`, `start_date`, `end_date`, `total_hours`, optional `hourly_rate`, and `requires_employee_assignment`. Workflow/identity fields are server-controlled. Hours are total employee-hours, not hours per person.

Assignment writes accept `overtime_request`, `assigned_employees` (user IDs), `expected_version`, and optional `notes`. Send the request's latest displayed version. Required-name requests need at least one eligible employee; optional-name requests may clear all names. Exported assignments are locked.

Export preview/creation accepts `request_ids` and `versions`, where `versions` maps each stringified request ID to its displayed version. A stale version returns HTTP 409: refresh and review before retrying. Exporting saves the CSV; it does not communicate with SAP. Confirmation requires `sap_reference`; failure requires `result_note`. Confirmed results cannot be overwritten.

Generic request/assignment PUT, PATCH, and DELETE are disabled. Workflow records in Django administration are read-only. Only a Django superuser can manage application roles; staff status alone does not grant workflow permissions. Request ordering supports `created_at`, `total_hours`, and `estimated_cost`, with `-` for descending order.

## Notifications

Business actions enqueue notification rows in the same database transaction. Deliver due rows with the virtual-environment interpreter:

```text
python manage.py send_notifications --limit 100
```

Use `.\venv\Scripts\python.exe` on Windows or `./venv/bin/python` on Linux if the environment is not activated. This is a scheduled management command, not Celery. Local console mail is printed by this command; SMTP is only used when configured. Retries stop after five failed attempts. Delivery can be duplicated if the process crashes after SMTP acceptance; it is at least once.

## Local checks

```text
python manage.py check
python manage.py makemigrations --check --dry-run --settings=core.test_settings
python manage.py test overtimeapp --settings=core.test_settings --noinput
```

Use the environment's interpreter as above. The isolated test settings use in-memory SQLite unless PostgreSQL is explicitly selected; they use test hashing and in-memory mail and must never serve production.

## PostgreSQL tests

Use only a disposable PostgreSQL instance/database and an account allowed to create test databases. Do not point these commands at a production account. Supply the password through a local environment variable or secret store before running; it is intentionally omitted below.

Windows PowerShell:

```powershell
$env:TEST_DB_ENGINE = 'postgresql'
$env:DB_ENGINE = 'django.db.backends.postgresql'
$env:DB_NAME = 'overtime_test'
$env:DB_USER = 'overtime_test'
$env:DB_HOST = '127.0.0.1'
$env:DB_PORT = '5432'
.\venv\Scripts\python.exe manage.py test overtimeapp --settings=core.test_settings --noinput
```

Linux Bash:

```bash
TEST_DB_ENGINE=postgresql DB_ENGINE=django.db.backends.postgresql \
DB_NAME=overtime_test DB_USER=overtime_test DB_HOST=127.0.0.1 DB_PORT=5432 \
./venv/bin/python manage.py test overtimeapp --settings=core.test_settings --noinput
```

Use a dedicated terminal for test connection variables so they do not affect later development commands. PostgreSQL tests exercise concurrent decisions and exports that SQLite cannot establish.

## Deployment and migration

Use the [production readiness guide](../docs/PRODUCTION_READINESS.md) for migration preflight, deployment examples, outbox scheduling, backups, and remaining launch gates. Gunicorn/systemd examples target Linux; the Windows quick start uses Django's local development server.

Recorded checks live in [verification](../docs/VERIFICATION.md). Having production settings and tests does not establish production readiness.
