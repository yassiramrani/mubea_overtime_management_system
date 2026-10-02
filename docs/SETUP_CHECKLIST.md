# Setup and launch checklist

This replaces the historical “files to create” checklist. Django APIs and React dashboards already exist. Follow [Getting started](../GETTING_STARTED.md) for exact Windows/Linux commands; use [verification evidence](VERIFICATION.md) to confirm which checks have actually passed.

## Local installation

- [ ] Use Python 3.12 and Node 22.12 or later in the Node 22 series.
- [ ] Install backend requirements in its virtual environment and frontend dependencies with `npm ci`.
- [ ] Create local environment files only if absent; review them without overwriting existing configuration.
- [ ] Back up an existing database, perform the legacy preflight when upgrading, and apply migrations.
- [ ] Create an individual superuser and separate manager users/profiles; assign the department manager's department.
- [ ] Start Django on localhost port 8000 and Vite on localhost port 3000.
- [ ] Confirm login and the submit → approve → assign → preview/download workflow.
- [ ] Run the delivery command and inspect local notifications.
- [ ] Run backend checks, PostgreSQL concurrency tests, frontend build, and the isolated browser suite.

## Phase 1 acceptance

- [ ] Changing or clearing filters starts at page one without restoring an old page.
- [ ] HR can remove every selected employee, including one hidden by search or made ineligible after assignment.
- [ ] Search fixtures are deterministic; search, sorting, estimates, refresh/retry, and export selection across pages are checked.
- [ ] Submission, approval, assignment repair, export, and failure scenarios pass browser verification.
- [ ] Desktop/mobile layouts, keyboard access, focus, and errors are inspected.
- [ ] Setup/status documentation agrees with the implementation and records verification limits.

These boxes are an installation/review worksheet, not automated results. Completion evidence belongs in [VERIFICATION.md](VERIFICATION.md).

## Remaining launch gates

- [ ] Phase 2: verified-email accounts, authenticator MFA and recovery, secure cookie sessions, and MFA protection for API/admin access.
- [ ] Phase 3: portable deployment containers, staging, active remote CI, and browser checks against the compiled application.
- [ ] Phase 4: HR approval of employee-hours, eligibility, roles/departments, and the manual CSV handoff.
- [ ] Phase 5: selected hosting, domain/TLS, real SMTP, notification scheduling, alerts, encrypted off-host backups, recovery and rollback rehearsal.
- [ ] Phase 6: acceptance/load tests, one-department pilot, operational ownership, and HR/IT sign-off.

The current CSV is a review format. An accepted SAP contract is required before building or using a direct SAP import adapter. Actual-hours/payroll processing, SSO, and approved-request amendments remain outside this release.
