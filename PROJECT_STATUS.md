# Project status

Updated 5 October 2026.

The application implements advance overtime submission, approval/rejection, pending withdrawal, employee assignment, audit history, persisted review CSV exports, an administration console, superuser account management, and a self-service password change. Phase 1 addresses workflow usability, filter/pagination behavior, assignment repair, browser verification, and setup accuracy.

**This is not a production-ready declaration.** Use [verification evidence](docs/VERIFICATION.md) for actual commands, results, and limitations. Earlier test counts and completion claims are historical and must not be treated as evidence for the current files.

## Current boundaries

- Hours represent total employee-hours. HR approval is needed before interpreting legacy quantities.
- CSV files use `approval-review-v1`; no automatic SAP connection or verified SAP import adapter exists.
- Assignments use eligible application user accounts; a separate personnel directory has not been implemented.
- Browser login uses expiring tokens in local storage. App-managed MFA and cookie-based browser sessions are Phase 2 work. Signed-in users can change their own password (their other sessions are signed out); recovery for a locked-out user still requires a superuser reset from the console.
- Administration-console account and role management is restricted to Django superusers; staff and profile-admins cannot change roles. Deactivation replaces deletion, so workflow history and PROTECTed references stay intact, and the console refuses self-lockout and last-administrator removal.
- Notifications now store HTML and plain-text snapshots, support test-recipient redirection, and expose failed/stuck queue checks. The existing signed-in Outlook desktop sender remains the easy Windows development path. Production delivery defaults to disabled until sender verification and explicit opt-in. A production sender, installed scheduler and external alert routing still need target-environment setup; nothing drains the outbox automatically yet. See [notification setup](docs/NOTIFICATIONS.md).
- Production settings, Linux service/proxy examples, and backup tooling exist. They do not establish an installed service or tested production recovery. Remote CI runs on every push and passed on Linux for the current revision (run #6): full suite on PostgreSQL including concurrency tests, frontend build and browser workflow.


## Remaining phases

| Phase | Required outcome |
|---|---|
| 2 — Authentication | Verified email, authenticator MFA, recovery, protected admin access, and cookie sessions |
| 3 — Staging and CI | Portable containers, reproducible staging, compiled-app browser checks against the current changes, and readiness monitoring. Remote CI exists and passes; staging does not. |
| 4 — Business acceptance | HR-approved units, eligibility, permissions, and review CSV handoff |
| 5 — Operations | Chosen host/domain, TLS/SMTP, scheduled notifications, alerting, off-host backups, tested recovery and rollback |
| 6 — Pilot and launch | Full acceptance and load testing, one-department pilot, and HR/IT sign-off |

Hosting remains undecided. Public access is the intended release target and depends on the authentication and operational phases. Direct SAP integration, actual-hours/payroll processing, SSO, and approved-request amendments are deferred beyond this release.

See [production readiness](docs/PRODUCTION_READINESS.md) for preserved migration/operational guidance and [Getting started](GETTING_STARTED.md) for local setup.
