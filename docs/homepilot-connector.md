# HomePilot connector (contract v1)

The reverse direction of the [HomePilot runtime bridge](homepilot-runtime-contract.md).
The bridge lets DayPilot use HomePilot personas; this connector lets a HomePilot
account read the workday a DayPilot user has explicitly shared, and ask DayPilot
to *prepare* actions that DayPilot governs.

**Ownership rule (unchanged):** HomePilot owns persona intelligence; DayPilot
owns workday operations and approval-governed execution. Nothing here copies
persona memory into DayPilot, merges databases, or adds a second workflow
engine — proposals use DayPilot's existing Approval Center and executors.

Code: `services/api-gateway/app/homepilot_connector.py`,
`services/api-gateway/app/routers/homepilot_connector.py`.
Tests: `tests/test_homepilot_connector.py`.

## Security audit finding

The existing HomePilot integration routes (`/v1/homepilot/*`, `/v1/agents/profiles*`)
and most other gateway routes take `workspaceId` from the query or body and
do not authenticate the caller. That is the local-first design (one owner per
install), but it means **those routes must not be exposed to a network** in a
multi-user deployment. This change does not alter them. The new connector
surface does not follow that pattern: every request authenticates a scoped
grant and derives the workspace from verified membership.

## Pairing (device flow + PKCE, RFC 8628 / RFC 7636 style)

```
HomePilot server                         DayPilot                       User (in DayPilot)
POST /v1/integrations/homepilot/pairings
  { codeChallenge (S256), scopes, accountRef }
                                   ──►  pairingId, userCode (10 min)
                                                                  opens /#/connect/homepilot?code=…
                                        GET  /consent/{userCode}  ◄── signed in (dp_session)
                                        POST /consent/{userCode}  ◄── approve: workspace + scopes, CSRF
POST /pairings/{pairingId}/token { codeVerifier }
                                   ──►  accessToken (dph_…), once
```

* The workspace must be one the approving user is a member of; the request
  cannot name another.
* A `read_only` member cannot grant `actions.propose`.
* Only the SHA-256 of the token is stored. The token is returned once.
* A pairing is single use, expires after ten minutes, and the exchange
  requires the PKCE verifier.

## Scopes

| Scope | Allows |
|---|---|
| `plan.read` | Today's plan, current focus block, next block, standup draft |
| `tasks.read` | Open tasks |
| `projects.read` | Operational projects: status, risk, next human action |
| `calendar.read` | Events from one hour ago to two days ahead, and overlaps |
| `approvals.read` | Pending approvals |
| `notifications.read` | Recent notifications |
| `actions.propose` | Ask DayPilot to prepare actions (DayPilot decides) |
| `wellness.read` | Reserved. **Not grantable** while wellness data exists only in the browser. |

## API (HomePilot's server, `Authorization: Bearer dph_…`)

| Route | |
|---|---|
| `GET /v1/integrations/homepilot/manifest` | Versioned feature manifest. Public without a token; with one it also reports `authorized` / `available` per feature. |
| `GET /v1/integrations/homepilot/account` | Display name, workspace, role, scopes |
| `GET /v1/integrations/homepilot/context?include=plan,tasks,…&limit=10` | One aggregate read. A section outside the grant is `{"status":"not_authorized"}`, never silently empty. Limit capped at 25. |
| `POST /v1/integrations/homepilot/proposals` | Prepare an action (below) |
| `GET /v1/integrations/homepilot/proposals/{id}` | Durable status |
| `DELETE /v1/integrations/homepilot/grant` | HomePilot revokes its own grant on disconnect |

User side (DayPilot session cookie, CSRF on writes):
`GET|POST /v1/integrations/homepilot/consent/{userCode}`,
`GET /v1/integrations/homepilot/grants`, `DELETE /v1/integrations/homepilot/grants/{id}`.

Every request re-checks: token known, not revoked, not expired, user active,
user still a member of the grant's workspace. Removing a membership cuts
access immediately (`403 membership_revoked`).

## Manifest: weather and wellness

`weather` and `wellness` are reported as `"kind": "ui_only"`,
`supported: false`, `available: false`. DayPilot's Weather view calls
Open-Meteo from the browser and the wellness timer lives in `localStorage`;
there is no backend data to share, so none is exposed.

## Proposals

```json
POST /v1/integrations/homepilot/proposals
X-DayPilot-Hop: 1
{ "capability": "task.create", "title": "…", "detail": "…", "arguments": {},
  "idempotencyKey": "…", "origin": {"system": "homepilot", "ref": "project:conversation"} }
```

| Capability | Risk | On approval |
|---|---|---|
| `task.create` | low | DayPilot creates the task |
| `task.update` | low | DayPilot updates title, priority, next action or context of a task **in the same workspace** |
| `project.update` | low | DayPilot updates next human action, status or risk of a project in the same workspace |
| `calendar.create`, `calendar.update` | low / medium | DayPilot's calendar integration executor |
| `document.generate` | low | DayPilot's document executor |

Anything else — `email.send`, `message.send`, `calendar.cancel`, coding,
GitHub, finance, HR, system changes — is refused (`422 capability_not_allowed`).

Each proposal becomes a DayPilot task in `waiting_for_approval` plus a pending
`Approval`, exactly like a persona proposal. Nothing runs until the user
decides in the Approval Center; then `homepilot_platform.on_approval_decided`
runs it through `action_mapping.execute_approved` (approve) or marks it
rejected. An executor that cannot do the job ends `failed` with a reason —
never a silent success.

* **Idempotency:** the same `idempotencyKey` on the same grant returns the same
  proposal (`"duplicate": true`); enforced by a unique index.
* **Loops:** `X-DayPilot-Hop >= 3` or `origin.system == "daypilot"` → `508`.
* **Untrusted text:** titles and details are length-bounded and stripped of
  control characters; `arguments` must be a JSON object under 8 KB. Text can
  never change the capability, the workspace or the approval.

## Audit

`audit_logs.event_type`: `homepilot.connector.pairing.requested|approved|denied`,
`grant.issued|revoked`, `context.read`, `proposal.created|refused`.

## Configuration

| Variable | Default | |
|---|---|---|
| `DAYPILOT_HOMEPILOT_CONNECTOR_ENABLED` | `true` | `false` makes the whole surface 404 |

The user must have a DayPilot account (first-run bootstrap creates the owner)
to approve a pairing.

## Rollout and rollback

Migration `0030_homepilot_connector` adds three tables
(`homepilot_pairings`, `homepilot_grants`, `homepilot_proposals`) and changes
none. Roll back by setting `DAYPILOT_HOMEPILOT_CONNECTOR_ENABLED=false`, or
`alembic downgrade 0029_presentations_extensions`. Revoking every grant:
`UPDATE homepilot_grants SET revoked_at = CURRENT_TIMESTAMP`.

Not implemented yet: the operator-web consent page at `#/connect/homepilot`
(the API is complete; the page is the next UI step), token expiry policy
(grants do not expire unless `expires_at` is set), and per-request rate
limiting on the pairing endpoint.
