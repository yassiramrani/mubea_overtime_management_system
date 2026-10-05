# React frontend

This is an existing React/TypeScript application built with Vite. See [Getting started](../GETTING_STARTED.md) for full Windows/Linux setup and manager accounts.

Use Node 22.12 or later in the Node 22 series. Install exactly the lockfile dependencies with `npm ci`.

## Commands

From `frontend/`:

```text
npm ci
npm run dev -- --host 127.0.0.1 --strictPort
npm run build
```

The development server uses port 3000. The build runs TypeScript checks and writes assets to `dist/`. Run `npm run preview -- --host 127.0.0.1` for local inspection on port 4173; preview is not a production server and does not include the development API proxy.

## API configuration

Copy `.env.example` to `.env` only if no local file exists. `VITE_API_URL=/api` is the default API base. Vite's development proxy forwards `/api`, `/health` and `/admin/` to `http://127.0.0.1:8000`.

All `VITE_` values are public build-time configuration. Do not add passwords, API secrets, or tokens. Restart Vite after changing configuration.

For another local backend port, set `VITE_API_PROXY` in the **terminal environment**; the current Vite config reads `process.env` rather than loading that variable from a dotenv file.

Windows PowerShell:

```powershell
$env:VITE_API_PROXY = 'http://127.0.0.1:8010'
npm run dev -- --host 127.0.0.1 --strictPort
```

Linux Bash:

```bash
VITE_API_PROXY=http://127.0.0.1:8010 npm run dev -- --host 127.0.0.1 --strictPort
```

For a deployment build, explicitly use a relative API URL to avoid embedding a developer's hostname:

```powershell
$env:VITE_API_URL = '/api'
npm run build
```

```bash
VITE_API_URL=/api npm run build
```

A deployed reverse proxy must serve the frontend, route `/api/` to Django, and fall back to `index.html` for frontend routes. Deployment examples are in `../deploy/`.

## Screens and behavior

- `/login`: username/password login and error recovery.
- `/dept-manager`: request creation, estimates, filters, history, withdrawal, and assigned teams.
- `/head-manager`: review, approval/rejection, department filters, and audit details.
- `/hr-manager`: employee assignment, explicit export selection, preview, saved batches, and import-result recording.
- `/administration`: system console for administrators — key figures, longest-waiting approval queue, notification-outbox health, department workload, and saved export batches. Django superusers also manage accounts here: create users, assign roles and departments, reset passwords, grant Django administration access, and deactivate leavers.

Every signed-in workspace header offers **Change password**: it asks for the current password, applies Django's password validators, rotates the API token, and signs out the account's other sessions.

Current login stores expiring API tokens in local storage. App-managed MFA and cookie-based sessions are planned for Phase 2. A compiled frontend alone does not make the public deployment ready.

## Isolated browser verification

```text
npx playwright install chromium
npm run test:smoke
```

On Linux, use `npx playwright install --with-deps chromium` if Chromium's system libraries are missing and package installation is permitted.

The smoke test creates synthetic users with a generated password in a temporary SQLite database, starts Django on port 8009 and Vite on port 3109, and launches headless Chromium. It uses an in-memory mail backend. It does not use the configured application's database or send SMTP email. Leave both ports free.

The test selects `../backend/venv/Scripts/python.exe` on Windows and `../backend/venv/bin/python` on Linux. To use another environment, set `SMOKE_PYTHON` to its absolute interpreter path:

```powershell
$env:SMOKE_PYTHON = (Resolve-Path ..\backend\.venv\Scripts\python.exe).Path
$env:SMOKE_OUTPUT = Join-Path (Resolve-Path ..).Path '.verification/browser'
npm run test:smoke
```

```bash
SMOKE_PYTHON="$(realpath ../backend/.venv/bin/python)" \
SMOKE_OUTPUT="$(realpath ..)/.verification/browser" npm run test:smoke
```

Only set that interpreter override if the alternate environment exists and includes the backend dependencies. Omit `SMOKE_PYTHON` for the standard `venv` setup. `SMOKE_OUTPUT` retains screenshots and CSV artifacts in the chosen directory; otherwise they are stored under the temporary test directory.

Build and browser checks are separate: the current browser test uses Vite's development server. Testing a compiled staging deployment is a later release gate. See [verification evidence](../docs/VERIFICATION.md) for the scenarios actually run and their results.
