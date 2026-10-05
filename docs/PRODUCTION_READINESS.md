# Advance overtime approval: implementation and launch plan

The confirmed business workflow is **approval of overtime in advance**, not payment for actual hours worked. `total_hours` means total employee-hours: five people for three hours is 15 hours. This unit needs HR sign-off before importing legacy records; existing quantities were not automatically reinterpreted or multiplied.

## Implemented

- Explicit submission, approval, rejection, and pending-request withdrawal actions. Generic request and assignment PUT/PATCH/DELETE are disabled. Workflow and audit models are read-only in Django admin.
- Only head managers/application admins can decide requests, and they cannot decide their own submissions. Creation rejects injected workflow fields. Rejection and withdrawal require reasons.
- Transactional decisions, assignments, audit events, and notification queue writes. PostgreSQL row locks serialize decisions and exports. Assignment saves and exports require the displayed request version.
- UUID-based request identifiers, a 64-character field, and database constraints for ordered dates, minimum hours, and nonnegative rates. Estimated costs correctly handle zero or removed rates.
- An append-only application audit feed with action, actor name, time, and submitted request snapshot. Existing history is not invented. Database operators remain privileged and need separately controlled access and backups.
- Optional named-employee assignment: managers specify whether names are required before export; HR can add names to either kind of request. Assigned employees must be active non-administrative accounts.
- Explicit export selection, validation preview, persisted CSV content/checksum, immutable batches, duplicate prevention, authenticated re-download, and separately recorded SAP import outcomes. Confirmed outcomes cannot be overwritten.
- Legacy approvals lacking approver/date are blocked from export until reconciled. Previously exported legacy rows remain excluded from new batches; no missing historic files are fabricated.
- Durable HTML and plain-text email snapshots, corrected dashboard URLs, one row per recipient, bounded retries and terminal failure status. Approval notifications also reach the requester. Sending no longer blocks the request API. Optional recipient redirection marks test messages; queue monitoring reports failed and stuck rows.
- Paginated dashboards, status/history visibility, justification and cost on the approval screen, assigned names and rejection reasons on the department screen, saved assignment editing, and export history on the HR screen.
- Login throttling, eight-hour token lifetime by default, server-side logout, protected routes that wait for authentication, no prefilled demo password, and relative API URLs with Vite proxy support.
- Supported Django stack and updated frontend dependencies; repeatable backend, concurrency, and browser workflow checks; CI configuration; strict production settings; production server and reverse-proxy/service examples.

## SAP contract is still required

The generated format is **`approval-review-v1`**, a request-level review CSV. It is not claimed to be an accepted SAP interface. Creating a file does not send anything to SAP. “Import confirmed” is a human-recorded result requiring a SAP reference.

Ask the SAP team for an accepted advance-authorization sample and the import transaction/interface. Confirm:

1. Required personnel, department, cost-center and overtime-type identifiers.
2. Whether unnamed department authorizations are accepted.
3. Whether rows represent a request, employee, date, or shift.
4. The meaning of hours, currency, rate, and time-zone/date boundaries.
5. Encoding, separators, decimal/date formats, column order, maximum lengths and validation rules.
6. Import errors, partial acceptance, corrections, and deduplication identifiers.

The review CSV escapes spreadsheet formula prefixes in text. A final machine-import adapter must implement the SAP contract rather than blindly reuse those review-file transformations. No automatic SAP connection or payroll calculation has been added.

## Migrate the existing installation

Stop application writes during the migration window. Keep the old application release and a tested database backup. Do not reset or delete existing data.

```bash
cd backend
source venv/bin/activate
python -m pip install -r requirements.txt
python manage.py check_legacy_requests
python manage.py migrate --noinput
python manage.py check
python manage.py test overtimeapp --settings=core.test_settings --noinput
```

`check_legacy_requests` only reads IDs/counts. It rejects records that would violate the new constraints and flags approved records missing attribution. Reconcile invalid records with authorized source documents before migrating. Do not manufacture an approver or silently change quantities. New request IDs are generated only for new requests; existing IDs remain unchanged.

After migration, verify at least one existing request, assignment and export record. Deploy backend and frontend together because assignments now require `expected_version`, export creation requires explicit `request_ids` and `versions`, and repeat downloads use the saved batch endpoint. Approved requests are intentionally immutable; correction/amendment workflow is a future feature, so do not edit database rows to bypass the lock.

## Production deployment

Use Python 3.12 and Node 22.12+ (or a newer supported compatible runtime). Install the pinned backend requirements; use `npm ci` and `VITE_API_URL=/api npm run build` in `frontend` so a local API URL is not embedded in the deployed bundle.

Configure a dedicated environment file outside source control, with:

- `DJANGO_SETTINGS_MODULE=core.production_settings`, `DEBUG=False`.
- A unique random `SECRET_KEY` of at least 50 characters, never the development value.
- PostgreSQL connection settings and a least-privileged runtime account; migrations can use a separately privileged account.
- `REDIS_URL` for shared login-throttle counters across API workers.
- Explicit `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and HTTPS `PUBLIC_BASE_URL`.
- Real SMTP settings, sender identity, and `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`.
- `TRUST_PROXY_SSL_HEADER=True` only when using a controlled proxy that overwrites incoming forwarding headers.

Production settings fail early for unsafe defaults. They retain HTTPS, secure cookies and HSTS with subdomains/preload; ensure all subdomains of the application hostname are HTTPS before rollout. Run:

```bash
python manage.py check --deploy --fail-level WARNING
python manage.py collectstatic --noinput
bash start-production.sh
```

Adapt `deploy/nginx.conf.example` and the systemd examples to the actual domain, TLS certificate paths, service account and installation path. They are examples, not installed services. Restrict `/admin/` through company network controls where appropriate. Serve static assets and the compiled frontend through the proxy. Do not expose export files through a public media directory.

The supplied CI runs backend checks and PostgreSQL tests, builds the frontend, and runs the isolated browser workflow. It requires a GitHub repository; no repository, remote, deployment, or production service was created automatically.

## Email operations

After sender verification, set `NOTIFICATIONS_DELIVERY_ENABLED=True` and run `python manage.py send_notifications --limit 100` every minute, using the supplied service/timer example or an equivalent scheduler. Production defaults to disabled delivery; an early timer exits without consuming attempts. The command sends due queued messages, uses exponential retry delays, and stops after five failed attempts. Inspect queued/failed messages in Django admin or the admin-only email-log API. Before go-live, verify every active head/HR manager has a deliverable email and that each required role exists.

Verify the SMTP configuration from the target host before scheduling delivery:

```text
python manage.py send_test_email --to <operator-address>
```

This sends a single message through the configured backend and exits non-zero with the server's reason on failure; it does not read or write the notification outbox. `EMAIL_TIMEOUT` bounds a stuck SMTP conversation so a hung server cannot block the scheduled command. Set `EMAIL_USE_TLS=True` for STARTTLS on port 587, or `EMAIL_PORT=465` with `EMAIL_USE_TLS=False` and `EMAIL_USE_SSL=True` for implicit TLS.

Run `python manage.py check_notifications --json` every minute and route its nonzero exit status to operator monitoring. It detects failed, stale, exhausted and empty-body queued messages without sending mail or exposing recipient/content data. Adapt the supplied `overtime-mail-health` service/timer examples; they do not configure external alert routing. Monitor timer execution independently too.

`NOTIFICATIONS_TEST_MODE=True` requires a valid `NOTIFICATIONS_REDIRECT_TO` allowlist and marks subjects/text/HTML. Successful redirected rows become `sent` and will never be replayed to their original recipients. Use fictional data in a disposable database for demonstrations. See [notification setup](NOTIFICATIONS.md) for the full activation sequence and local preview command.

Before activating real production notifications, set `NOTIFICATIONS_TEST_MODE=False` and clear `NOTIFICATIONS_REDIRECT_TO`, then explicitly enable delivery after sender verification.

The local mail catcher and the Outlook desktop backend are development and prototype aids only; `core.production_settings` refuses to start unless the SMTP backend is selected, so neither can become the production sender by accident.

Delivery is **at least once**: a process crash after SMTP acceptance but before the database commit can cause a duplicate notification. Business actions and exports remain deduplicated independently. No real SMTP messages were sent during automated verification.

## Monitoring, backup and recovery

- Monitor HTTPS `/health/`, error rates, response latency, PostgreSQL/Redis availability, queue age, failed emails, and failed SAP imports. `/health/` checks the database, not SMTP or Redis.
- Run scheduled PostgreSQL custom-format backups using the supplied `deploy/backup_database.py` with restricted storage permissions. Encrypt and copy backups to independent storage, set retention, and choose recovery objectives with IT.
- Restore backups into an isolated empty database using `pg_restore --no-owner --dbname=<restore_database> <backup.dump>`; verify request/audit/export counts and the download of a stored batch. Test this regularly, not just backup creation.
- Use immutable application releases. If rollback is needed after writes under the new schema, assess compatibility before swapping code. Restoring an older backup loses later writes and requires an explicitly coordinated recovery plan.
- Create and test real alert routing, scheduled jobs, TLS renewal and an on-call runbook on the target infrastructure. No production destination or credentials were supplied, so these operational checks remain launch gates.

## Further product work

These are intentionally still pending rather than hidden behind a production-ready claim:

- A separate employee directory with SAP personnel identifiers and optional login linkage. Current assignments still use application accounts.
- Per-day/per-employee allocations, shifts, breaks, time zones and overlap checks when required by the SAP contract/company policy.
- HR-approved limits, department budgets, eligibility rules and thresholds; currency/rate ownership must be specified.
- Drafts, return-for-correction, versioned amendments, approved-request cancellation, and controlled replacement exports with partial-import reconciliation.
- Delegated approvers, reminder/escalation rules, reporting, and optional corporate SSO/MFA.
- Actual-hours/payroll processing is outside the confirmed advance-authorization scope.

## Verification commands

```bash
# Backend unit/integration checks (SQLite; PostgreSQL concurrency cases skip)
cd backend
python manage.py test overtimeapp --settings=core.test_settings --noinput
python manage.py makemigrations --check --dry-run --settings=core.test_settings

# PostgreSQL: use only a disposable test instance/account with database-create permission
TEST_DB_ENGINE=postgresql DB_ENGINE=django.db.backends.postgresql \
DB_NAME=overtime_test DB_USER=overtime_test DB_PASSWORD=<test-password> \
DB_HOST=127.0.0.1 DB_PORT=5432 \
python manage.py test overtimeapp --settings=core.test_settings --noinput

# Browser: creates an isolated temporary SQLite database and fake users,
# starts localhost ports 8009/3109, exercises submission → approval → assignment → export.
cd ../frontend
npm ci
npx playwright install chromium
npm run build
npm run test:smoke
```

The smoke script requires the backend virtual environment at `backend/venv` or an explicit `SMOKE_PYTHON` path. It uses fake users and an in-memory email backend; it does not alter the application's configured database or send real email. Set `SMOKE_OUTPUT` to retain screenshots and the test CSV in a chosen directory.
