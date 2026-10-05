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

## Administration console, account management and password change (5 October 2026)

| Area | Command / check | Result |
|---|---|---|
| Backend suite | `manage.py test overtimeapp --settings=core.test_settings --noinput` | 88 tests run locally: 85 passed, 3 PostgreSQL-only concurrency tests skipped |
| Remote CI | `Application checks` on `main`, run #6 | Passed on Linux for this revision: the full 88-test suite against PostgreSQL (concurrency and notification-health modules included) plus the frontend build and browser workflow |
| Account API tests | New `AdminAccountManagementTests` | Superuser-only create/update, role and department rules, deactivation blocks login, password validators, self- and last-administrator guards |
| Password change tests | New `PasswordChangeTests` | Token rotation invalidates the previous token; wrong current password and weak or unchanged passwords rejected |
| Browser workflow | `npm run test:smoke` | Dept → head → HR → admin console; creates and deactivates an account; rotates a password and signs in with it |
| Console captures | `SMOKE_OUTPUT=.verification/admin-dashboard` | Desktop/mobile console, account-lifecycle and password-dialog captures retained locally (ignored) |

## Stage 1 notification progress (5 October 2026)

These checks cover the current local changes; earlier counts below are historical.

| Area | Command / check | Result |
|---|---|---|
| Backend suite | `manage.py test overtimeapp --settings=core.test_settings --noinput` | 88 tests run: 85 passed, 3 PostgreSQL-only concurrency tests skipped locally; remote CI runs all 88 against PostgreSQL |
| Stage 1 regression coverage | New template, delivery and health test modules included in the suite | 31 tests passed; covers event types/routes, escaping/snapshots, multipart and legacy text, redirection, disabled delivery, five-attempt terminal failure and queue-health boundaries |
| Django checks and migrations | `manage.py check`, `makemigrations --check --dry-run` with `core.test_settings` | No issues; no missing migrations |
| Production configuration | `manage.py check --deploy --fail-level WARNING` with representative production environment and disabled delivery | Passed with no warnings; does not contact SMTP or establish real infrastructure |
| Local database upgrade | SQLite backup, `migrate`, before/after row-count comparison | Migration `0003_emaillog_html_body` applied; 5 users retained, workflow/outbox tables remained empty |
| Local queue health | `manage.py check_notifications --json` | Exit 0; healthy empty queue, no rows changed or mail sent |
| Easy Windows demo configuration | Private environment backup; enabled test mode in existing local Outlook configuration | All notification recipients redirect to the existing configured sender address; Django checks and empty-queue health passed; no mail sent |
| Fictional notification previews | `python ../scripts/preview_notifications.py` | 5 multipart messages accepted by memory mail backend; every recipient redirected to `demo@example.com`; HTML/TXT/EML and index generated under `.verification/stage1/` |
| Independent integration review | Read-only review of changed notification paths and tests | No blocking integration issues reported |

The final backend log is `.verification/stage1-backend-tests.log`. A private local
backup is `.verification/backups/before-stage1-2026-10-05.sqlite3`. The preview
generator forces in-memory SQLite and local mail, independently of the configured
database and sender.

**Limits for this change:** no real email was sent, no production SMTP/Graph sender
was configured, and no scheduler or external alert routing was installed. Outlook
COM plain-text/HTML handling was tested with mocks. Browser preview and actual
Outlook rendering were not verified; `agent-browser` was unavailable locally.
PostgreSQL concurrency and notification-health tests were later rerun by remote CI
(run #6 passed on Linux; see the console section above).
Production outbox delivery is disabled by default until explicit opt-in after
sender verification. Demo deliveries mark rows sent; use fictional data in a
disposable database. See [notification setup](NOTIFICATIONS.md).

## Account provisioning and notification delivery (2 October 2026)

Added after the review above; the ordered checks above do not cover it.

| Area | Command | Result |
|---|---|---|
| Manager account provisioning | `manage.py seed_users` against a disposable SQLite database, run twice | Created five accounts with the expected email, role, department and staff/superuser flags; the second run updated without duplicating and preserved existing passwords |
| Backend suite | `manage.py test overtimeapp --settings=core.test_settings --noinput` | Passed, 49 tests; the three PostgreSQL concurrency tests were skipped without a PostgreSQL service |
| Django checks | `manage.py check`, `manage.py makemigrations --check --dry-run` | No issues; no pending migrations |
| Frontend build | `npm run build` | Passed (Vite 8.2.2, 91 modules), Node 24.19.0 |
| Browser workflow | `npm run test:smoke` | Passed using fake users, generated server passwords and a temporary database; Chromium installed for the pinned Playwright 1.62.1 |
| Remote CI on the pushed commit | `Application checks` on `main` | Passed on Linux; the backend job ran the PostgreSQL concurrency tests that are skipped locally, and the frontend job passed |
| Outbox delivery over SMTP | Full workflow against a disposable database, delivered to `scripts/mail_catcher.py` | Four messages delivered; recipients resolved to the head manager, HR manager and requester, each with the matching role route |
| Delivery through a mail client | Same workflow with every account redirected to one mailbox, delivered through the signed-in Outlook desktop client | Four messages accepted by Exchange and received in the Inbox |

**Not established:** real delivery to the intended recipients, a production SMTP or API sender, automatic scheduling of `send_notifications`, HTML message bodies, or any SMTP authentication. Delivery over SMTP, delivery through Outlook, and the local capture server all ran against disposable databases that were then deleted. The Outlook sender is Windows-only, requires a signed-in desktop client, and `core.production_settings` refuses to start unless the SMTP backend is selected, so it cannot become the production sender by accident. A message is marked `failed` permanently after five delivery attempts, so the sender must be verified before any scheduler is enabled.
