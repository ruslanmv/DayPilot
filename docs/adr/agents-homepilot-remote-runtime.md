# ADR: HomePilot agents as a remote runtime for DayPilot

**Status:** Accepted · **Date:** 2026-07-25

## Context

DayPilot needs an "AI staff" of agents (directory → dedicated workspace →
tasks/approvals). HomePilot already owns rich, project-backed personas —
identity, portrait, role, system prompt, long-term memory, sessions, models, and
MCP/A2A tools — and exposes an OpenAI-compatible API where a persona is addressed
as `persona:<project_id>`.

Rebuilding personas inside DayPilot would duplicate a large, evolving system and
fork identity/memory. Instead, DayPilot connects to a **side-by-side HomePilot
install** and reuses its agents.

## Decision

**HomePilot owns the agents. DayPilot connects to them and manages their work.**

- HomePilot owns: identity, appearance, role/personality, system prompt, memory,
  its own sessions, models, MCP/A2A capabilities, gallery + `.hpersona` imports.
- DayPilot owns: the four-column Agents directory, the per-agent workspace,
  DayPilot tasks/progress, approval requests, email/calendar/project/document/
  coding actions, delegation visibility, activity/audit, workspace permissions,
  and whether a HomePilot agent is enabled in DayPilot.

DayPilot stores a **remote reference** (`HomePilotAgentLink`), never a copied
persona. Conversation turns are routed to the real persona over HomePilot's
OpenAI-compatible endpoint in **propose-only** mode: HomePilot reasons with full
persona context but returns proposed operations as structured directives;
DayPilot validates them and executes external writes only through its own
integrations, always behind the Approval Center.

## Consequences

- No duplication of persona/memory/gallery; HomePilot remains the source of truth.
- A hard trust boundary: HomePilot proposes, DayPilot validates + executes.
- DayPilot depends on a reachable HomePilot for live agent chat; when HomePilot
  is offline, agents show offline and local history is preserved.
- The pre-existing local `.hpersona` importer is demoted to an optional offline
  fallback (`DAYPILOT_HOMEPILOT_IMPORTS_ENABLED`).

See `docs/homepilot-runtime-contract.md` for the ten frozen rules and
`services/orchestrator/daypilot_orchestrator/homepilot/contracts.py` for their
code form.
