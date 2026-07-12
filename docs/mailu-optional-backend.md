# Mailu as DayPilot's Optional Email Backend

Mailu is the recommended open-source, self-hostable mail backend for DayPilot's
optional Email module. DayPilot owns the premium UI, AI assistant, drafts,
signatures, approvals, and the non-destructive policy; Mailu is infrastructure.

## Why Mailu

- Docker-based full mail server: **IMAP, SMTP/submission**, webmail/admin,
  aliases, auto-forward/reply, quotas, TLS/DKIM/DANE/MTA-STS, antispam/antivirus.
- Documented **Docker Compose** and **Kubernetes** deployment, plus a **REST
  admin API** with Swagger/OpenAPI discovery (for provisioning/config only).
- Permissive (**MIT**) posture for Mailu-specific code — favorable for product
  embedding, unlike GPL/AGPL stacks (mailcow, Nylas Sync Engine).

## Integration pattern

Use the **universal IMAP/SMTP content plane** for all mailbox workflows (inbox,
drafts, sent, reply, send) and the **REST admin API** only for account/domain
provisioning. Because the reviewed Mailu docs do not surface a first-party
mailbox webhook framework, pair it with an **IMAP IDLE / polling sidecar** for
event ingestion (DayPilot's event bridge, future work).

Point DayPilot at Mailu:

```env
DAYPILOT_EMAIL_ENABLED=true
DAYPILOT_EMAIL_PROVIDER=imap_smtp
IMAP_HOST=mailu            # or your Mailu front host
IMAP_PORT=993
SMTP_HOST=mailu
SMTP_PORT=587
EMAIL_USERNAME=you@yourdomain
EMAIL_PASSWORD=...
```

Start Mailu alongside DayPilot with the override compose file:

```bash
docker compose -f docker-compose.yml -f infra/docker/mailu.override.compose.yml up
```

## Alternates

- **Modoboa** — Python/Django/Vue, Postfix+Dovecot, REST + OpenAPI, ISC license.
  Best fit if you want to stay close to Python across the stack.
- **Docker Mailserver** — MIT, lean, file-configured, explicit OAuth2 SASL, but
  no first-party REST admin plane (DayPilot supplies more orchestration).

## Non-goals

- **mailcow** is feature-rich but GPL-3.0 (license mismatch).
- **Haraka** / **Postal** are SMTP-edge / transactional-delivery specialists,
  not mailbox backends.
- **Nylas Sync Engine** is archived, AGPL, and stored credentials unencrypted —
  do not adopt.
