# Project status

Updated 14 September 2026.

The application implements advance overtime submission, approval/rejection, pending withdrawal, employee assignment, audit history, and persisted review CSV exports. Phase 1 addresses workflow usability, filter/pagination behavior, assignment repair, browser verification, and setup accuracy.

**This is not a production-ready declaration.** Use [verification evidence](docs/VERIFICATION.md) for actual commands, results, and limitations. Earlier test counts and completion claims are historical and must not be treated as evidence for the current files.

## Current boundaries

- Hours represent total employee-hours. HR approval is needed before interpreting legacy quantities.
- CSV files use `approval-review-v1`; no automatic SAP connection or verified SAP import adapter exists.
- Assignments use eligible application user accounts; a separate personnel directory has not been implemented.
- Browser login uses expiring tokens in local storage. App-managed MFA and cookie-based browser sessions are Phase 2 work.
- A notification outbox and delivery command exist. A real delivery schedule and verified SMTP service still need target-environment setup.
- Production settings, Linux service/proxy examples, backups tooling, and CI configuration exist. They do not establish an installed service, active remote CI, or tested production recovery.

## Remaining phases

| Phase | Required outcome |
|---|---|
| 2 — Authentication | Verified email, authenticator MFA, recovery, protected admin access, and cookie sessions |
| 3 — Staging and CI | Portable containers, reproducible staging, active remote CI, compiled-app browser checks, and readiness monitoring |
| 4 — Business acceptance | HR-approved units, eligibility, permissions, and review CSV handoff |
| 5 — Operations | Chosen host/domain, TLS/SMTP, scheduled notifications, alerting, off-host backups, tested recovery and rollback |
| 6 — Pilot and launch | Full acceptance and load testing, one-department pilot, and HR/IT sign-off |

Hosting remains undecided. Public access is the intended release target and depends on the authentication and operational phases. Direct SAP integration, actual-hours/payroll processing, SSO, and approved-request amendments are deferred beyond this release.

See [production readiness](docs/PRODUCTION_READINESS.md) for preserved migration/operational guidance and [Getting started](GETTING_STARTED.md) for local setup.
