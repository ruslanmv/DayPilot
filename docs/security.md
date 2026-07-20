# Security and Governance

DayPilot uses a policy-first design.

## Defaults

- Local-first storage.
- Dry-run MCP writes.
- Approval required for all mutating actions.
- Imported HomePilot personas are disabled by default.
- Tool scopes are explicit.
- Prompt injection controls are required before production.

## High-Risk Actions

- Sending external messages.
- Deleting or moving user data.
- Writing code or changing repositories.
- Creating calendar events.
- Calling external phone numbers.
- Reading sensitive local folders.

## Identity, sessions, and secrets

- **Local accounts** use scrypt password hashing; session tokens are stored only
  as SHA-256 hashes. Sessions are HttpOnly cookies with CSRF double-submit and
  are rate-limited (lockout after repeated failures). Failed logins persist
  durably so lockout survives a rolled-back request.
- **Secrets by reference.** Provider keys, OAuth tokens, and mailbox passwords
  live in the credential store keyed by a `secret_reference`. They are never
  written to a database row, an API payload, a log, a trace, or a prompt.
  Disconnecting a provider or mailbox deletes the referenced secret.
- **Workspace isolation.** Assistant runs, mailboxes, provider connections, and
  approvals are scoped per workspace and never leak across workspaces.

## Assistant tool risk classes

The assistant orchestrator classifies every capability it can touch:

| Risk class | Assistant may… |
|---|---|
| `READ_ONLY` | invoke directly (reads only) |
| `CONTROLLED_LOCAL_WRITE` | invoke directly (local DayPilot state only) |
| `APPROVAL_REQUIRED` | **prepare only** — open an approval, never perform |
| `BLOCKED` | never available |

`assert_not_directly_performed()` makes the "prepare only, never perform"
guarantee **structural**: the assistant cannot send email, write a calendar
event, or run code directly. It opens a pending approval (and, for coding, a
gated job linked to that approval); the action runs only after explicit human
approval. See [assistant-orchestrator.md](./assistant-orchestrator.md).

## Prompt-injection controls

Untrusted content (emails, documents) and every assistant message are scanned for
instruction-override, permission-grant, and exfiltration patterns
(`security/injection_guard.py`). Flagged content is tagged with untrusted
provenance and, above threshold, quarantined and surfaced in the Approval Center.
A flagged assistant turn can never silently escalate: write intents still go
through the approval path, and attempts to bypass approval ("send it without
asking") are refused, not obeyed.

## Mail is non-destructive

The mailbox setup probe opens the INBOX read-only and speaks EHLO/STARTTLS to
SMTP without ever issuing `MAIL FROM` — it never sends and never marks a message
read. Reads use `BODY.PEEK`; the adapter never deletes or expunges. Sending stays
draft-and-approve. See [email-non-destructive-policy.md](./email-non-destructive-policy.md).
