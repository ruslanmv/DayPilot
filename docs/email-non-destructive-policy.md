# DayPilot Email — Non-Destructive Policy

DayPilot must never behave like an aggressive email client. The policy is
enforced server-side in `daypilot_orchestrator/email/policy.py`, not in the UI.

## Default posture

```text
No hard delete            No auto-send
No expunge                No overwrite draft without versioning
No destructive move       No external forwarding without approval
No mark-as-read by AI      No AI mailbox mutation without visible confirmation
```

## Action classes

**Always safe** (read-only or local-only) — never require approval:

- read, summarize, classify
- create DayPilot task / note
- draft reply, save draft
- add local (DayPilot) label
- suggest archive, suggest follow-up

**Risky** (mailbox mutation / send / egress) — require an explicit, visible
approval payload:

- send, archive, move, mark read
- apply server label/folder, forward externally
- download attachment, share email content with another agent

**Destructive** — forbidden by default; require a specific allow flag *and*
approval:

- delete (`DAYPILOT_EMAIL_ALLOW_DELETE`)
- expunge (`DAYPILOT_EMAIL_ALLOW_EXPUNGE`)

## Send flow (draft-and-approve)

```text
User: "Draft a reply"     → safe: draft created, pending approval opened
User edits the draft
User clicks Send          → send drawer shows the exact action
Approval confirmed        → SMTP submit, APPEND copy to Sent
```

Sending is refused with `403` unless (a) an approved approval record exists for
the draft and (b) the request carries an explicit approval payload
(`confirmed_by_user: true`). The Email Sentinel never sends on its own.

## Read safety

Inbox reads use IMAP `BODY.PEEK` and `readonly` SELECT, so listing or opening a
message never implicitly sets `\Seen`. Marking read is a risky action.

## Reversibility

DayPilot only ever APPENDs (drafts, sent copies) and sets local labels. Original
messages are never modified, moved, or removed under the default policy, so the
mailbox is safe to point at a real account.
