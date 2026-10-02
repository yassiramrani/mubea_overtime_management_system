# Remaining work

**Mubea Overtime Management System** — updated 2 October 2026.

This plan records what remains before the application can be launched. It follows
the phases in [PROJECT_STATUS.md](../PROJECT_STATUS.md) and adds the notification
work carried out on 2 October 2026.

---

## Where things stand

| Item | State |
|---|---|
| Backend tests | 49 pass locally; the 3 PostgreSQL concurrency tests are skipped without a PostgreSQL service |
| Remote CI | Active on `main` and passing; the backend job runs the PostgreSQL concurrency tests |
| Django checks | `manage.py check` clean; no pending migrations |
| Frontend | Build and browser workflow both pass |
| Notifications | Outbox, delivery command and two verified senders exist; nothing drains the outbox automatically |
| Manager accounts | Provisioning command ready and applied to the local development database only |
| Production sender | Undecided; needs IT |
| Hosting | Undecided |

---

## Stage 0 — Landed, 2 October 2026

| # | Task | Outcome |
|---|---|---|
| 0.1 | Commit and push the notification work | `9ae43e8` and `c3a030b` on `main`; CI green on Linux for both jobs |
| 0.2 | Frontend build and browser checks | `npm run build` and `npm run test:smoke` both pass |
| 0.3 | Create the development database and accounts | Five manager accounts provisioned |
| 0.4 | Correct stale documentation | Project status, verification record and setup instructions updated |

---

## Stage 1 — Notifications, finished properly

| # | Task | Depends on |
|---|---|---|
| 1.1 | Decide the production sender: Microsoft Graph app-only, or an internal relay | IT |
| 1.2 | Schedule `send_notifications` every minute | 1.1 |
| 1.3 | Keep the Outlook backend as the Windows and development fallback | — |
| 1.4 | Add HTML message templates; messages are plain text today | — |
| 1.5 | Optional: redirect and test-mode safeguard so a demonstration cannot be mistaken for real traffic | — |
| 1.6 | Alert on failed emails and stale queue rows | 1.2 |

**Highest risk in the plan.** A message is marked `failed` permanently after five
delivery attempts and is never retried. Verify the sender (1.1) **before** enabling
any scheduler (1.2), or the first misconfiguration silently loses every notification.

---

## Stage 2 — Authentication (Phase 2)

Verified email enrollment; authenticator MFA; account recovery; protected
administration; migration from local-storage tokens to cookie-based sessions.

Today the browser uses username and password tokens in local storage, with no MFA
and no recovery path. This stage is the gate on any public exposure.

---

## Stage 3 — Staging and CI (Phase 3)

Portable containers; a reproducible staging environment; browser checks against the
compiled application; readiness monitoring.

CI exists and passes, including the browser workflow. The gap is a containerised,
repeatable staging target and monitoring.

---

## Stage 4 — Business acceptance (Phase 4)

HR confirmation that `total_hours` means **employee-hours**; confirmed employee
eligibility rules; accepted permission model; approved review-CSV handoff.

Approvals lacking an approver or date stay blocked from export until reconciled
against authoritative records. Mostly meetings rather than code, and every
downstream phase rests on this interpretation.

---

## Stage 5 — Operations (Phase 5)

Chosen host and domain; TLS; a real sender over SMTP or an API; scheduled
notifications; alerting; off-host encrypted backups; a tested restore and rollback.

Scaffolding exists under `deploy/`, but no service is installed and no recovery has
been rehearsed against live infrastructure.

---

## Stage 6 — Pilot and launch (Phase 6)

Acceptance and load testing; a one-department pilot; HR and IT sign-off.

---

## Blocked on other people

| Decision | Owner | Blocks |
|---|---|---|
| Hosting and domain | Management / IT | All of Stage 5 |
| Sender identity: Graph application, internal relay, or service mailbox | IT | 1.1, 1.2, 1.6 |
| Employee-hours interpretation | HR | Stage 4 and legacy data |
| Legacy approval reconciliation | HR / business | Export eligibility |
| MFA and SSO requirements | IT | Stage 2 design |

## Work needing no external input

All of Stage 0 (done); items 1.3 to 1.6; all of Stage 2; the container and staging
work in Stage 3; backup and restore tooling in Stage 5.

---

## Recommended order

```
0.1 → 0.2 → 0.3 → 0.4        done, 2 October 2026
  ↓
1.1  once IT answers  →  1.2  →  1.6
  ↓
Stage 4 sign-off             cheapest item, largest unblocking effect
  ↓
Stage 2 (authentication)  ∥  Stage 3 (staging)
  ↓
Stage 5 (operations)  →  Stage 6 (pilot and launch)
```

Stage 4 looks like administration rather than engineering, but it is the cheapest
item with the largest unblocking effect — and the one nobody schedules.

---

## Known caveats to carry forward

- The Outlook sender runs only on Windows where the desktop client is signed in and
  running, and it sends from that person's mailbox. Production settings refuse to
  start unless the SMTP backend is selected, so it cannot become the production
  sender by accident.
- The local mail capture server accepts unauthenticated mail and must stay bound to
  `127.0.0.1`.
- Notification emails carry no indication that they are test messages.
- Delivery is at least once: a crash after the mail server accepts a message but
  before the database commit can duplicate it.
- No real SMTP authentication, no SAP import, and no production deployment has been
  performed or verified.
