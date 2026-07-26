# HomePilot agents — rollout runbook

The whole integration is **off by default** and gated by feature flags. Roll it
out one capability at a time, verifying at each step. Nothing here changes
DayPilot's existing behavior until a flag is set.

## Flags (all default `false`)

| Flag | Turns on |
| --- | --- |
| `DAYPILOT_HOMEPILOT_RUNTIME_ENABLED` | Master switch. Off ⇒ the whole surface 404s. |
| `DAYPILOT_HOMEPILOT_SYNC_ENABLED` | Discover + refresh agents from HomePilot. |
| `DAYPILOT_HOMEPILOT_CHAT_ENABLED` | Live conversation + directive → task mapping. |
| `DAYPILOT_HOMEPILOT_DELEGATION_ENABLED` | Manager → worker delegation. |
| `DAYPILOT_HOMEPILOT_IMPORTS_ENABLED` | Offline `.hpersona` import fallback. |

A feature is active only when the master flag **and** its own flag are set.

## Rollout order

1. **Connect (master only).** Set `RUNTIME_ENABLED`. In Settings → HomePilot,
   connect your install (side-by-side `http://homepilot:7860/api`, host
   `http://host.docker.internal:7860/api`, or cloud `https://homepilot.ruslanmv.com/api`).
   Verify: the panel shows *connected*, the bound **account**, and local/cloud.
2. **Sync.** Add `SYNC_ENABLED`, click *Refresh agents*. Verify the directory
   lists your personas (all **disabled** until you enable them). Enable one.
3. **Chat.** Add `CHAT_ENABLED`. Open the agent, send a message. Verify a reply
   persists, and that a proposed action becomes a **Waiting for approval** task
   with a pending Approval. Approve it and watch the lifecycle reach
   **Completed**. Confirm the capability probe set `chatMode` (bridge vs
   chat-only).
4. **Delegation (optional).** Add `DELEGATION_ENABLED`. Verify a manager can
   hand a sub-task to a worker and the chain reads `You → manager → worker`,
   within the safety limits (depth ≤ 2, ≤ 3 workers, ≤ 10 child tasks, worker
   capability ≤ manager, same account).
5. **Offline import (optional).** Add `IMPORTS_ENABLED` only for genuinely
   offline installs. Verify `/agents/add` shows the `.hpersona` method with a
   preview + dependency check.

## Verify

- Backend: `pytest tests/` (HomePilot suites: `test_homepilot_*`).
- Contracts/compat: `tests/test_setup_and_health_contract.py`.
- Builds: `pnpm -r run build`.
- Failure behavior: see `docs/homepilot-failure-matrix.md`.

## Observability

Each bridge turn writes an `homepilot.bridge.turn` audit record (counts only —
no message text): mode, directives created, approvals proposed, directives
rejected, delegations, whether the reply was sanitized. Approvals + executions
write their own `agent.action.*` audit records. Export via
`GET /v1/approvals/audit/export`.

## Rollback

Unset a flag to disable that capability instantly — no data is deleted. Unset
`RUNTIME_ENABLED` to make the whole surface inert. Agent references, tasks,
approvals, and conversations are preserved (a removed persona is marked
*offline*, never deleted), so re-enabling resumes exactly where you left off.

## Multi-account safety

Each connection is bound to the HomePilot account it authenticated as; agents
are stamped with that account and a key/account change re-scopes rather than
blending. See `docs/daypilot-bridge.md` (HomePilot) for the identity endpoint.
