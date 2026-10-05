# Overtime Management System

Manage advance overtime requests from department submission through head-manager approval, HR employee assignment, and a reviewed CSV handoff.

**The app is not production-ready.** Phase 1 improves and verifies the existing workflow. Public access with app-managed MFA is planned for Phase 2; current browser login still uses expiring tokens. Hosting, real email delivery, operational acceptance, and HR approval remain launch gates.

## Current application

- Department managers submit requests, search/filter their history, withdraw pending requests with a reason, and view assigned teams.
- Head managers review requests, estimated costs, and audit history, then approve or reject them.
- HR managers assign eligible employees, preview explicitly selected exports, download saved batches, and record import outcomes.
- Administrators get a system console: key figures, the longest-waiting approval queue, notification-outbox health, department workload, and saved export batches. Superusers provision accounts there — create users, assign roles and departments, reset passwords, grant Django administration access, and deactivate leavers.
- Every signed-in user can change their own password from the workspace header; other sessions for that account are signed out.
- Workflow changes use explicit audited actions. Generic request/assignment edits and deletion are disabled.
- Notifications enter a durable outbox; a scheduled management command delivers them.

The CSV format is `approval-review-v1`, a request-level review file. Downloading it does not send data to SAP. Direct SAP integration and actual-hours/payroll processing are outside the current release.

## Start here

- [Getting started](GETTING_STARTED.md): Windows and Linux installation, accounts, and local checks.
- [Backend guide](backend/README.md): API contracts, database tests, and notification commands.
- [Frontend guide](frontend/README.md): Vite configuration, builds, and isolated browser tests.
- [Current status](PROJECT_STATUS.md), [verification evidence](docs/VERIFICATION.md), and [production readiness](docs/PRODUCTION_READINESS.md).
- [Setup checklist](docs/SETUP_CHECKLIST.md): development checks and remaining launch gates.

## Stack and layout

Python 3.12, Django 5.2, Django REST Framework, React 18, TypeScript, and Vite. SQLite supports local development; PostgreSQL is required by production settings and concurrency verification. Use Node 22.12 or later in the Node 22 series and the supplied npm lockfile.

| Directory | Purpose |
|---|---|
| `backend/core/` | Django settings and entry points |
| `backend/overtimeapp/` | Workflow, access rules, APIs, migrations, tests, and notification outbox |
| `frontend/src/` | Login and manager dashboards |
| `frontend/tests/` | Isolated Playwright workflow and synthetic fixtures |
| `deploy/` | Deployment and backup examples; not installed services |
| `docs/` | Setup, verification, and production requirements |

Existing deployment examples and CI configuration are starting points. They do not establish a deployed service or an active remote CI run.
