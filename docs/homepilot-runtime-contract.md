# HomePilot runtime contract (frozen)

The integration direction is fixed: **HomePilot owns the agents; DayPilot
connects to them and manages their work.** These rules are non-negotiable and
are enforced in code by
`services/orchestrator/daypilot_orchestrator/homepilot/contracts.py`.

## The ten rules

1. HomePilot and DayPilot have **separate databases**.
2. DayPilot **never reads HomePilot database tables** directly.
3. DayPilot **never shares HomePilot storage volumes**.
4. The **browser never calls HomePilot** directly — only DayPilot's backend does.
5. DayPilot stores a **remote agent reference** (`HomePilotAgentLink`), not a
   copied persona. Prompt and memory are never persisted in DayPilot.
6. HomePilot **cannot execute** DayPilot email, calendar, project, or coding
   actions directly.
7. HomePilot **proposes** actions; DayPilot **validates and executes** them.
8. Every external write remains **subject to DayPilot approval**.
9. Removing an agent in HomePilot marks it **offline** in DayPilot — historical
   tasks and conversations are **never deleted**.
10. The local `.hpersona` importer remains only as an **optional offline
    fallback** (`DAYPILOT_HOMEPILOT_IMPORTS_ENABLED`).

## Deployment

HomePilot runs beside DayPilot on a shared Docker network (`pilot-net`), reached
at `http://homepilot:7860/api` (containers) or
`http://host.docker.internal:7860/api` (host install). Auth is an API key sent as
`X-API-Key` or `Authorization: Bearer`. The key lives in DayPilot's credential
store by `secret_reference`; only safe metadata is persisted.

## Tool mode

DayPilot always sends `X-HomePilot-Tool-Mode: propose`. HomePilot uses the
persona's identity/memory/context and returns `x_directives` (proposed
operations) — it must not perform external writes. DayPilot validates each
directive (type ∈ allowed set, arguments, workspace ownership, capability,
limits) and maps action proposals to drafts + Approvals.

## Feature flags (all default `false`)

`DAYPILOT_HOMEPILOT_RUNTIME_ENABLED` (master), `_SYNC_ENABLED`, `_CHAT_ENABLED`,
`_DELEGATION_ENABLED`, `_IMPORTS_ENABLED`. A feature is active only when the
master flag **and** its own flag are set.
