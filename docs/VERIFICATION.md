# Verification — 7 September 2026

## Outcome

**Fixed:** the request-owner approval bypass and equivalent generic update/delete paths. Request owners cannot set workflow fields through creation, PATCH or PUT; approved records cannot be edited or deleted through generic APIs. Assignment reparenting and generic assignment mutations are blocked. Django admin exposes workflow records read-only. Normal submission → head-manager decision → HR assignment → advance-approval export remains functional.

The patch uses explicit action endpoints, strict input contracts and transactional workflow writes. It does not change the confirmed business model to actual-hours payroll. SAP compatibility is still unverified without the company's import contract.

## Changed areas

- `backend/overtimeapp/views.py`, `serializers.py`, `models.py`, `admin.py`, `urls.py`: workflow boundaries, identifiers/constraints, audit feed, optional assignment and saved export batches.
- `backend/overtimeapp/emails.py`, `management/commands/send_notifications.py`: transactional email outbox, bounded delivery retries and corrected routes.
- `backend/overtimeapp/authentication.py`, `auth_views.py`, `backend/core/settings.py`, `urls.py`: expiring tokens, login throttle, server logout and database health endpoint.
- `backend/overtimeapp/migrations/0002_auditevent_exportbatch_emaillog_attempts_and_more.py`: schema changes; existing IDs and data retained.
- `frontend/src/pages/*`, `components/Workflow.tsx`, `hooks/usePaged.ts`, auth/API helpers, routes and styles: paginated workflow screens, details/history, optional employee selection, export preview/history and authentication-loading fixes.
- Backend/frontend dependency manifests, `core/test_settings.py`, `core/production_settings.py`, startup scripts, `.github/workflows/checks.yml`, `deploy/*`, and production documentation.

## Ordered checks

| Gate | Command or check | Result |
|---|---|---|
| Syntax, imports and model configuration | `python manage.py check` | Passed |
| Migration consistency | `python manage.py makemigrations --check --dry-run --settings=core.test_settings` | No changes detected |
| Original exploit and related regressions | `python manage.py test overtimeapp --settings=core.test_settings --noinput` | 23 tests passed; 3 PostgreSQL-only concurrency tests skipped on SQLite |
| PostgreSQL validation | Same test command with `TEST_DB_ENGINE=postgresql` and an isolated PostgreSQL 16 instance | All 26 tests passed |
| Production configuration | `python manage.py check --deploy --fail-level WARNING` with dedicated representative production environment | Passed; zero warnings, none silenced |
| Frontend type/build check | `VITE_API_URL=/api npm run build` | Passed with upgraded Vite/React Router |
| Frontend dependency installation audit | `npm install` after advisory-driven upgrades | Reported 0 vulnerabilities; not a full source security audit |
| Browser workflow | `npm run test:smoke` | Passed using fake users, temporary database and local servers |
| Local migration preservation | Backup, migration, record-count comparison | Existing 1 request, 1 assignment, 1 export and 8 users retained |
| PostgreSQL backup/restore rehearsal | `deploy/backup_database.py`, then `pg_restore` into a separate empty database | Passed with fake test data |

The focused backend tests cover injected approval/requester/cost fields, PATCH/PUT/DELETE attacks, role/ownership isolation, repeated decisions, required rejection reasons, pending withdrawal, assignment reparenting, inactive/empty assignments, version conflicts, duplicate exports, authenticated re-download, explicit import confirmation, ID collisions/length, database constraints, rounding overflow, optional-name clearing, admin immutability, notification retry/rollback, logout/token expiry and login throttling.

Three PostgreSQL tests race approval against rejection, export against export, and assignment against export. Each permits one action and returns a conflict for the competing action. Tests ran against a disposable PostgreSQL database which was then stopped.

The browser test covers pagination beyond 20 records, login and authenticated page refresh, request submission, head-manager approval, HR employee selection, saved selection readback, CSV preview/download, saved export history, server logout and the department's assigned-employee view. Desktop and mobile screenshots were inspected; mobile overflow assertions and browser runtime-error checks passed.

A separate read-only security reviewer found two edge cases: rounded costs exceeding the decimal field limit, and optional employee names that could not be cleared. Both were corrected and covered by regression tests. The reviewer found no remaining ordinary-user approval forgery or assignment reparenting route in the reviewed boundary.

## Limits and retained evidence

No production deployment, real SMTP delivery, actual SAP import, complete employee-policy validation, corporate SSO integration, external alert routing or live-infrastructure restore was performed. The production deployment check validates configuration, not the availability of the configured external services.

Local logs, screenshots, the fake-data CSV and a private pre-migration SQLite backup are under ignored `.verification/`. Source-backed instructions and launch gates are in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md). The independent reviewer covered the changed workflow boundary; this was not an exhaustive repository security scan.
