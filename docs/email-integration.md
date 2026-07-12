# DayPilot Email Integration (optional module)

The **Email** tab is a single, optional, feature-flagged DayPilot feature. It is
**additive, removable, and non-destructive**. DayPilot works fully with Email
disabled — no background sync starts, the sidebar hides the tab, and the
`/v1/email/*` routes return `404 feature_disabled`.

## Architecture: two planes, DayPilot owns the semantics

The frontend never talks to a mail server directly.

```text
DayPilot UI  →  api-gateway  →  Email service (orchestrator email module)
                                   ↓
                           MailboxAdapter
                           ├── MockMailAdapter      (demo/dev, default)
                           ├── ImapSmtpAdapter       (Mailu / generic IMAP+SMTP)
                           ├── Gmail / Microsoft      (imap_smtp plane + OAuth token)
                           └── MailuAdminAdapter*      (provisioning only, *future)
```

- **Content plane** — IMAP for reads and APPEND-to-Drafts/Sent, SMTP submission
  for sends. This is portable across Mailu, generic IMAP/SMTP, Gmail, and
  Microsoft 365, so DayPilot behaves identically everywhere.
- **Admin plane** — provisioning/config via a backend's REST API (e.g. Mailu's
  Swagger/OpenAPI admin API). Out of the content path.
- **Event bridge** — where backends lack mailbox webhooks (Mailu does), DayPilot
  converts IMAP IDLE / UID deltas into normalized internal events (future).

The **non-destructive policy and all assistant behavior live in DayPilot**, not
the backend. The mail server stores messages; DayPilot owns drafts, signatures,
approvals, classification, and safety.

## Recommended backend: Mailu (permissive, self-hostable)

Mailu is a Docker-based full mail server (IMAP, SMTP/submission, webmail/admin,
aliases, quotas, TLS/DKIM/antispam) with Docker Compose + Kubernetes docs and a
REST admin API — under a permissive (MIT) posture for its own code. It is the
recommended optional self-hosted backend. Strong alternates: **Modoboa**
(Python/Django, ISC, REST+OpenAPI) and **Docker Mailserver** (MIT, lean, OAuth2
SASL). See `docs/mailu-optional-backend.md`.

Enable it with `infra/docker/mailu.override.compose.yml` and point DayPilot at
it via `DAYPILOT_EMAIL_PROVIDER=imap_smtp` (or `mailu`) plus IMAP/SMTP creds.

## Feature flag

```env
DAYPILOT_EMAIL_ENABLED=false        # off by default
DAYPILOT_EMAIL_PROVIDER=mock        # mock | mailu | imap_smtp | gmail | microsoft
DAYPILOT_EMAIL_ALLOW_SEND=true      # sending still requires per-action approval
DAYPILOT_EMAIL_ALLOW_DELETE=false   # destructive, off
DAYPILOT_EMAIL_ALLOW_EXPUNGE=false  # destructive, off
```

## API surface (gateway)

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/email/status` | Always reachable; `{enabled: bool}` |
| GET | `/v1/email/folders` | Requires enabled |
| GET | `/v1/email/messages` | Read-only sync + Sentinel classification |
| POST | `/v1/email/messages/{uid}/draft-reply` | Safe: creates draft + pending approval |
| POST | `/v1/email/drafts/send` | Risky: **403 unless approved AND approval payload confirmed** |
| POST | `/v1/email/messages/{uid}/create-task` | Safe: email → DayPilot task |

See `docs/email-non-destructive-policy.md` for the full safety model.
