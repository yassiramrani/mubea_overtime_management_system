# Stage 1 notification setup

Updated 5 October 2026. HTML and plain-text snapshots, test redirection, and queue
health checks are implemented. The production sender, installed delivery timer,
and external alert routing remain pending.

## Easy local path: Outlook

On this Windows workspace, `backend/.env` already selects
`overtimeapp.email_backends.OutlookComEmailBackend`. Keep Outlook desktop signed
in with the intended mailbox. This uses the desktop profile rather than SMTP
credentials; company programmatic-access policy still applies. `DEFAULT_FROM_EMAIL`
does not change which Outlook profile sends the message. Production settings
refuse this backend.

Local demo mode is now enabled in the existing `backend/.env`, redirecting all
notification mail to its configured sender address. Restart a running Django
backend to load these settings. No messages were sent during setup and no timer
was installed. Use fictional requests for demonstrations.

Inspect the new messages without sending anything. From `backend/`:

```powershell
.\venv\Scripts\python.exe ..\scripts\preview_notifications.py
```

From `backend/`, open `../.verification/stage1/index.html` for the HTML previews. The script
uses fictional requests, in-memory SQLite, and Django's memory mail backend. It
does not read or change the configured development database. Preview and MIME
files are local verification artifacts excluded from Git.

To verify actual Outlook delivery later, use a separate PowerShell terminal with
your own test mailbox in place of the placeholder:

```powershell
$env:EMAIL_BACKEND = 'overtimeapp.email_backends.OutlookComEmailBackend'
$env:NOTIFICATIONS_TEST_MODE = 'True'
$env:NOTIFICATIONS_REDIRECT_TO = 'your-test-mailbox@example.com'
.\venv\Scripts\python.exe manage.py send_test_email --to your-test-mailbox@example.com
```

This sends one clearly marked test message and leaves the outbox untouched.
Confirm it arrives in the mailbox; backend acceptance alone does not establish
receipt. Close the terminal to discard its environment overrides.

## Test redirection and delivery switch

| Setting | Behavior |
|---|---|
| `NOTIFICATIONS_TEST_MODE=True` | Adds `[TEST]` to the subject and a TEST / DEMO banner to text and HTML |
| `NOTIFICATIONS_REDIRECT_TO` | Comma-separated test mailbox allowlist; replaces every original recipient when test mode is on |
| `NOTIFICATIONS_DELIVERY_ENABLED` | Permits outbox delivery; defaults to True in development and False in production |
| `NOTIFICATIONS_STALE_MINUTES` | Queue-age alert threshold in whole minutes; defaults to 15 |

Test mode requires a valid, nonempty redirect list. A redirect list requires test
mode. Misconfiguration is rejected before sending or consuming outbox attempts.
Both `send_test_email` and `send_notifications` use this policy, including old queued
messages. The original recipient is displayed inside the test message; the saved
outbox content and recipient remain unchanged.

**Use fictional data in a disposable database for outbox demonstrations.** A
successful redirected message is marked `sent` and will not be replayed to its
original recipient when test mode is turned off. Test recipients see the saved
request details and employee names. Verify the sender separately with
`send_test_email`; it never consumes queued notifications.

New notifications store both variants at the time of their workflow event. Later
request edits or URL changes do not rewrite the snapshot. Old rows with an empty
`html_body` retain plain-text delivery. Apply migration `0003_emaillog_html_body`
before running the new application code.

## Production scheduling

IT still needs to choose an internal SMTP relay or approve a future Graph sender.
Only SMTP is currently supported by `core.production_settings`; a Graph backend
is not implemented. Keep the desktop Outlook fallback for development.

After configuring SMTP on the actual host, keep
`NOTIFICATIONS_DELIVERY_ENABLED=False`, run `send_test_email`, and confirm receipt.
For real production notifications, set `NOTIFICATIONS_TEST_MODE=False` and clear
`NOTIFICATIONS_REDIRECT_TO` so intended recipients receive them. Then set
`NOTIFICATIONS_DELIVERY_ENABLED=True` in the production environment file
and install the adapted `deploy/overtime-mail.service.example` and `.timer.example`
as `overtime-mail.service` and `overtime-mail.timer`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now overtime-mail.timer
systemctl list-timers overtime-mail.timer
journalctl -u overtime-mail.service --since '10 minutes ago'
```

The timer runs `send_notifications --limit 100` every minute, one worker at a time.
These are installation instructions, not an installed service. Disabled delivery
exits before selecting rows, so an early timer cannot exhaust retries.
`send_test_email` remains available while outbox delivery is disabled. SMTP uses
the configured `EMAIL_TIMEOUT` to bound a stalled connection.

## Queue checks and alert routing

From `backend/`, this command is read-only and never sends alert mail:

```powershell
.\venv\Scripts\python.exe manage.py check_notifications --json
```

Exit 0 means a healthy queue; exit 1 reports terminal failures, stale queued
messages, exhausted queued attempts, or queued messages with an empty body. Exit 2
means an invalid age threshold. JSON stdout contains aggregate counts, age, and
check time; errors go to stderr. Database or configuration failures also exit
nonzero and should be treated as failed monitoring checks.

Queue age uses the existing `EmailLog.sent_at` enqueue timestamp, despite that
field's historical name. Retries update `next_attempt_at` and do not reset age.
The default threshold is 15 minutes; tune `NOTIFICATIONS_STALE_MINUTES` or use
`--stale-minutes 30` if the agreed delivery window differs. The five-attempt retry
limit remains in effect, and terminal failures remain visible until supervised
recovery after the sender issue is resolved. Check possible prior delivery before
resending: delivery is at least once.

Adapt `deploy/overtime-mail-health.service.example` and `.timer.example` as
`overtime-mail-health.service` and `overtime-mail-health.timer` for a minute-based
check. Route its exit status/journal output into the chosen operator monitoring
system. No external alert destination is configured by these examples. Monitor
timer/service execution independently: an empty or recent queue can be healthy
even when delivery is disabled or the delivery timer is missing.

See [verification](VERIFICATION.md) for checks actually run and
[remaining work](REMAINING_WORK.md) for outstanding Stage 1 rollout items.
