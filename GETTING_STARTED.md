# Getting started

These instructions run the current Django and Vite application locally. They do not deploy a public service. For an existing installation, back up its data and follow the [migration guidance](docs/PRODUCTION_READINESS.md#migrate-an-existing-installation) before applying migrations.

## Prerequisites

- Python 3.12 with virtual-environment support.
- Node 22.12 or later in the Node 22 series, with npm.
- A terminal opened in the project root.
- PostgreSQL for production and concurrency tests; the local quick start uses SQLite.

Use the commands for your operating system. The explicit virtual-environment interpreter avoids activation-policy problems on Windows. If a `backend/venv` already exists, verify its Python version instead of recreating it.

## 1. Install the backend

Windows PowerShell:

```powershell
cd backend
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
```

Linux Bash:

```bash
cd backend
python3.12 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
if [ ! -e .env ]; then cp .env.example .env; fi
```

Review `backend/.env` locally before continuing. Preserve existing values if you already have an installation. For a fresh local setup, the example uses `DEBUG=True`, SQLite, a console email backend, and localhost URLs. Replace the development secret with a locally generated value; do not reuse it for deployment or share it.

To generate a Django secret locally, run the appropriate interpreter:

```powershell
.\venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

```bash
./venv/bin/python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

For PostgreSQL, create a database/account separately, then set `DB_ENGINE=django.db.backends.postgresql` and the `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` values. Run all backend commands from `backend/`; the example's relative SQLite path is resolved from that working directory.

## 2. Initialize and start Django

After the one-time installation above, Windows users can start both services with one command from the project root:

```powershell
.\start.cmd
```

Or, from `frontend/`, run `npm start`. This applies migrations, then opens separate windows for Django and Vite.

Windows PowerShell, still in `backend/`:

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py createsuperuser
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Linux Bash, still in `backend/`:

```bash
./venv/bin/python manage.py migrate
./venv/bin/python manage.py createsuperuser
./venv/bin/python manage.py check
./venv/bin/python manage.py runserver 127.0.0.1:8000
```

Choose your own administrator credentials. The setup does not create a demo account or a shared default password. Backend URLs:

- Administration: `http://127.0.0.1:8000/admin/`.
- API root: `http://127.0.0.1:8000/api/`.
- Database health check: `http://127.0.0.1:8000/health/`.

## 3. Create manager accounts

Sign in to Django administration as the superuser. Create separate active users, then add their **User profiles**:

| Account | Profile role | Department |
|---|---|---|
| Department manager | `dept_manager` | Required; choose the manager's department |
| Head manager | `head_manager` | Optional |
| HR manager | `hr_manager` | Optional |

Use distinct people/accounts for submission and approval; self-approval is rejected. Keep ordinary manager accounts non-staff and non-superuser. Application accounts currently also serve as the employee directory: assignments accept active non-staff, non-superuser accounts whose profile role is not `admin`. Standalone employee accounts do not need a manager role.

Set email addresses for accounts involved in notifications. The console backend displays mail only when the delivery command runs. Creating records does not prove SMTP delivery.

## 4. Start the frontend

Open a second terminal in the project root.

Windows PowerShell:

```powershell
cd frontend
npm ci
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
npm run dev -- --host 127.0.0.1 --strictPort
```

Linux Bash:

```bash
cd frontend
npm ci
if [ ! -e .env ]; then cp .env.example .env; fi
npm run dev -- --host 127.0.0.1 --strictPort
```

Open `http://127.0.0.1:3000` and sign in with a manager's **username and password**. The example `VITE_API_URL=/api` sends requests through Vite's local proxy to Django on port 8000. Keep `VITE_` variables free of secrets: Vite embeds them in browser code. The [frontend guide](frontend/README.md) explains alternate API ports.

## 5. Check the local workflow

Submit a request as a department manager, approve it as a different head manager, assign employees as HR, then preview and download the review CSV. Check the department view and audit history afterward. `total_hours` means total employee-hours: five people working three hours is 15 employee-hours. HR must approve this interpretation before using legacy quantities operationally.

In a third terminal in `backend/`, deliver queued local notifications:

```powershell
.\venv\Scripts\python.exe manage.py send_notifications --limit 100
```

```bash
./venv/bin/python manage.py send_notifications --limit 100
```

Run this command periodically to process due notifications; no Celery worker is used.

## 6. Run checks

From `backend/`, use your platform's interpreter for each command:

```powershell
.\venv\Scripts\python.exe manage.py test overtimeapp --settings=core.test_settings --noinput
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=core.test_settings
```

```bash
./venv/bin/python manage.py test overtimeapp --settings=core.test_settings --noinput
./venv/bin/python manage.py makemigrations --check --dry-run --settings=core.test_settings
```

These settings use in-memory SQLite by default; PostgreSQL concurrency cases require the [separate PostgreSQL test configuration](backend/README.md#postgresql-tests).

From `frontend/`:

```text
npm run build
npx playwright install chromium
npm run test:smoke
```

On Linux, Chromium may also require system libraries; use `npx playwright install --with-deps chromium` where system package installation is permitted. The smoke test starts its own local servers on ports 8009 and 3109 and uses a temporary SQLite database with generated users/passwords. Leave those ports free.

The script detects `backend/venv/Scripts/python.exe` on Windows and `backend/venv/bin/python` on Linux. For a differently named environment, set an absolute path before running it:

```powershell
$env:SMOKE_PYTHON = (Resolve-Path ..\backend\.venv\Scripts\python.exe).Path
npm run test:smoke
```

```bash
SMOKE_PYTHON="$(realpath ../backend/.venv/bin/python)" npm run test:smoke
```

Use those overrides only if that alternate environment exists and has the backend requirements installed. See [verification](docs/VERIFICATION.md) for recorded results and limitations.

## Troubleshooting

- **Port already in use:** stop the existing development process or configure matching frontend/backend ports. Smoke ports must remain available.
- **API cannot be reached:** verify Django's `/health/`, the Vite proxy target, and `VITE_API_URL`; restart Vite after changing its environment.
- **Login works but a dashboard is inaccessible:** verify the user's active status, profile role, and department.
- **No notification received:** inspect the outbox, run `send_notifications`, and check whether the configured backend prints mail locally or uses SMTP.
- **Version conflict:** refresh the request, review current assignments, and retry. Exported assignments are intentionally locked.
- **Existing database needs changes:** use migrations and a backup; do not delete the database or fabricate approval history.
