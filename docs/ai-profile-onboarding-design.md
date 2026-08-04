# AI profile and first-run onboarding

DayPilot's first run creates a trustworthy, editable **AI profile** that helps
planning and assistant responses fit the person, while making it obvious what
is sent to a model. The AI profile is **not** a HomePilot persona: a persona
describes an agent; the AI profile describes the signed-in person and their
preferences. DayPilot owns the latter and supplies only a minimum,
purpose-limited projection to the assistant or a remote persona for a given
request.

## Principles

1. **Backend is the source of truth.** The browser may cache a revision/ETag
   and a draft, but never owns profile or completion state.
2. **Explicit beats inferred.** User-entered values override connected-source
   metadata, which overrides confirmed inferences. Unconfirmed observations
   never enter durable prompt context.
3. **Purpose-limited context.** The backend selects fields for a planning,
   drafting, knowledge, or agent-delegation purpose; it never serializes the
   whole row into a prompt.
4. **Preview and control.** Users inspect "What AI sees", disable a category,
   export, and reset learned context without deleting their account.
5. **Preferences never grant permissions.** Approval and tool policy stay an
   independent, higher-priority enforcement layer. Profile text can tailor
   wording but cannot grant a capability or suppress an approval.
6. **No silent memory.** Durable learned personalization requires confirmation
   and stays visible, editable, expirable, and deletable.

## Data model

Three additive, tenant-scoped tables (migration `0018_ai_profile`), keyed by
`(user_id, workspace_id)` because work preferences may differ per workspace.
None store credentials, mailbox secrets, documents, or conversation history.

- **`user_ai_profiles`** — timezone/locale/preferred-name/pronouns, allowlisted
  `use_cases`, and validated `schedule`/`planning`/`communication`/
  `accessibility`/`boundaries` JSON, plus `category_consent` and a `revision`
  for optimistic concurrency and a `reviewed_at` freshness stamp.
- **`user_profile_goals`** — profile-level outcomes, archivable/expirable on
  their own instead of rewriting the profile blob.
- **`onboarding_progress`** — flow version, status, current step, completed
  steps. Integration completion is always recomputed from authoritative
  resource state; the stored map is presentation progress, not a security fact.

Every category is a strict Pydantic model (`profile_schemas.py`) with
`extra='forbid'`, enums for all free choices, camelCase aliases, IANA-timezone
and BCP-47 validation, and rejection of overlapping/inverted work windows and
oversized text.

## API

All routes derive `(user, workspace)` from the authenticated session, or a
well-defined local owner when session enforcement is off — never from a
client-supplied id. Cookie-authenticated writes require the `X-CSRF-Token`
double-submit. Profile writes use `If-Match`/revision; a stale revision returns
`409 profile_revision_conflict` with the current value.

```
GET|PUT|PATCH  /v1/profile/ai
DELETE         /v1/profile/ai/learned          reset confirmed/suggested observations
GET            /v1/profile/ai/context-preview?purpose=…
GET            /v1/profile/ai/export
POST           /v1/profile/ai/import-legacy     one-time, allowlisted safe fields

GET|POST       /v1/profile/goals
PATCH|DELETE   /v1/profile/goals/{goal_id}

GET|PATCH      /v1/onboarding                   PATCH saves navigation/dismissal only
POST           /v1/onboarding/complete          validates required fields + records review
```

`GET /v1/onboarding` returns one view model — profile completeness plus
provider/mail/calendar/knowledge status — so the UI does not race requests.
Every category/consent change, goal mutation, export, learned-reset, and
completion emits an audit event listing changed field **names** only.

## Context assembly

`daypilot_orchestrator/profile/context_builder.py` is the only place a profile
becomes model context. `ProfileContextBuilder.build(session, workspace_id,
purpose, …)` returns a typed projection: it applies a per-purpose allowlist and
per-category consent, keeps declared-value provenance, caps every list/string to
a deterministic token budget, and lists the included category names (never
values). `render_system_section()` wraps it in a `<user_profile>` DATA block
that forbids treating any value as an instruction and sanitizes user strings, so
an injection string in a goal or boundary cannot change tool permissions.

| Purpose | Includes |
|---|---|
| planning | timezone, schedule, planning prefs, active goals, boundaries |
| drafting | locale, communication prefs, boundaries |
| knowledge | locale, answer format, selected project |
| agent_delegation | task-relevant goal, constraints, capability summary |
| assistant | timezone, locale, communication, boundaries |

The assistant turn projects the profile behind `DAYPILOT_PROFILE_CONTEXT_ENABLED`
(default on) and records the applied revision + category names on the run. The
`context-preview` endpoint returns the **exact** builder output the assistant
uses, so "What AI sees" is the real projection.

## Settings — Your profile

Settings → **Your profile** (`YourProfilePanel`) is the complete editor, in six
tabs: Identity, Work style, Goals, Communication, AI context & privacy (category
toggles + live "What AI sees" preview + export + reset), and Setup checklist
(integration status + Restart setup, which never erases a saved profile). Saves
guard on the revision, surface Saving/Saved/Error via `aria-live`, and keep
edits after a recoverable error.

## Delivery status

- **Phase 1 (done)** — tables/migration, schemas, repository/service, profile +
  goals + onboarding APIs, audit events, and authorization/validation/
  concurrency tests.
- **Phase 3 (done)** — `ProfileContextBuilder`, context-preview + export,
  assistant wiring behind a flag, golden purpose-allowlist tests.
- **Phase 2 (done)** — Settings "Your profile" editor + client; the first-run
  wizard captures the required minimum (timezone + use cases) and lets the
  server own completion. A full six-stage cosmetic wizard remains optional.
- **Phase 4 (done)** — consented learning (`user_profile_observations`):
  suggestions start `suggested` and only a user-confirmed, non-expired one
  enters context (declared always wins); rejections suppress repeat
  suggestions; `DELETE /v1/profile/ai/learned` forgets confirmed/suggested
  rows. Confirm/Dismiss lives in Settings → AI context & privacy.
