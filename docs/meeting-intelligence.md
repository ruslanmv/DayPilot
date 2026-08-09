# Meeting Intelligence — connecting Outlook and Google Calendar

> **Show up prepared for every meeting.**
> DayPilot understands your upcoming meetings, gathers the relevant context,
> protects preparation time, and gives you talking points before you join.

This document is the design for that capability. It starts with an honest audit
of what the AI planner does today, because the gap between what the planner
*says* and what it *knows* is the reason this feature is worth building — and is
the thing that must be fixed first.

---

## Using it

What is built and usable today. The design that follows explains why it is
shaped this way and what comes next.

### 1. Register the OAuth app

Calendar connections reuse the same app registration as mailbox OAuth — same
client id and secret — but the **redirect is per flow** and has to be registered
separately in the provider console. Both point at DayPilot's calendar callback:

```
<public-origin>/v1/calendar/callback
```

```bash
# .env — Microsoft 365 / Outlook
MS_GRAPH_CLIENT_ID=
MS_GRAPH_CLIENT_SECRET=
MS_GRAPH_CALENDAR_REDIRECT_URI=https://daypilot.example.com/v1/calendar/callback

# .env — Google Calendar
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_CALENDAR_REDIRECT_URI=https://daypilot.example.com/v1/calendar/callback
```

Delegated permissions to grant in the console — **read-only**:

| Provider | Scope |
|---|---|
| Microsoft | `Calendars.Read`, `offline_access`, `openid`, `email` |
| Google | `calendar.readonly`, `userinfo.email`, `openid` |

`Calendars.Read` is a delegated permission that does not require admin consent.
`offline_access` (and Google's `access_type=offline`) is what makes a refresh
token available, so the connection survives past the first hour.

A provider with no client id configured is reported unavailable and the button
says so, rather than sending you to an identity provider that will reject you:

```bash
curl http://localhost:8080/v1/calendar/providers
```

### 2. Connect

Open **Calendar**. With nothing connected the page shows the offer rather than an
empty grid — an empty grid says "you have nothing on" when the truth is "DayPilot
cannot see your calendar".

```
Show up prepared for every meeting
[ Connect Outlook Calendar ]  [ Connect Google Calendar ]
```

One click starts the flow; you are returned to Calendar when it completes. You do
**not** have to visit Settings first. Once connected the header carries the
connection:

```
Outlook · Synced 2m ago ✓        Day | Week
```

Click it for the account, last sync, **Sync now**, and Calendar settings.

### 3. Choose what DayPilot may read

**Settings → Calendar** (⌘, then Calendar), four sections:

| Section | What it decides |
|---|---|
| **1. Calendar connections** | Which accounts are connected, when each last synced, connect/sync/disconnect. |
| **2. Meeting preparation** | Whether to prepare you at all, for which meetings (external/client · important · every), how much prep time, and whether a prep block is placed automatically. |
| **3. Meeting context** | **The allow-list.** Exactly what a brief may read. |
| **4. Planning** | Whether accepted meetings are fixed time, whether declined meetings are ignored, whether tentative ones block, and the buffers around a meeting. |

Section 3 is the one to read carefully. It is a permission, and the server
enforces it:

- **Nothing outside the list reaches the model.** The brief is assembled from the
  permitted sources and the model receives that assembly — it is not handed a
  tool that can reach into an integration on its own.
- **A source whose integration is not connected is disabled**, not silently
  ignored. Granting Slack context means nothing without Slack connected, and the
  checkbox says so instead of implying otherwise.
- **The calendar event itself cannot be switched off** — a brief about a meeting
  that may not read the meeting would be nonsense.
- **An unknown source id is dropped rather than stored.** A typo that persisted
  would be a permission nobody could look up.
- **Private events default to metadata only** — title, time, attendee count,
  never the body — until you change it per workspace.

Defaults on a fresh workspace are DayPilot's own context only: the event,
projects, tasks and knowledge documents. Connecting a calendar grants nothing
external.

### 4. What the plan will and will not claim

The Planning surface reports what it actually checked:

| Situation | What the plan says |
|---|---|
| No calendar connected | *No calendar connected — this plan does not know about your meetings* |
| Connected, never synced | *Calendar connected but never synced — meetings may be missing* |
| Connected, fresh, overlaps | *N overlapping meetings on your calendar* |
| Connected, stale | *Calendar has not synced recently — conflicts may be out of date* |
| Connected, fresh, none | ✅ *No calendar conflicts* |

That last line is the only one that used to appear, and it appeared whenever the
critic had no complaints — see Part 1.

### 5. Governance

Reads run immediately. **Every write to an external calendar opens an approval
and a durable job, and does not execute until you decide it** — the same
Integration Gateway rule that governs Slack and GitHub. There is deliberately no
setting that skips it: a toggle that could turn it off would make the guarantee a
preference.

Tokens live in the credential store keyed by connection id, never in the
database, a log, or a prompt. The only thing from the token that reaches the
database is the account address, so the UI can show which mailbox is connected.

### API

```text
GET  /v1/calendar/providers            which providers this deployment can offer
POST /v1/calendar/connect/{provider}   begin OAuth → { authorizationUrl }
GET  /v1/calendar/callback             finish OAuth → records the connection
GET  /v1/calendar/status               connected? providers? lastSyncAt? freshness?
GET  /v1/calendar/settings             settings + the source catalogue
PUT  /v1/calendar/settings             partial update; bad values are 400
POST /v1/calendar/sync                 refresh the local store
GET  /v1/calendar/events               read the local store (no provider call)
GET  /v1/calendar/conflicts            overlapping events
```

### Not built yet

Be clear about the edge of the feature:

- **Sync is still the seed fixture.** The Graph adapter, the OAuth flow and the
  connection model are real; `sync_events()` still returns `_SEED_EVENTS`, so a
  connected calendar does not yet import your actual meetings.
- **The planner does not yet reserve meetings.** Fixed intervals, prep blocks and
  the interval-aware scheduler are the next batch.
- **Meeting briefs are designed, not built.** The context allow-list that governs
  them is enforced and testable today; the assembler is not written.

---

## Part 1 — What the AI-generated calendar actually does today

### The planner is task-driven, not calendar-driven

`generate_plan()` builds its state from exactly one source:

```python
# planner/service.py:94
state = {
    "tasks": _collect_tasks(session, workspace_id),
    "config": cfg,
    "hints": _hints_from_instruction(instruction),
}
```

`_collect_tasks()` (`planner/service.py:30`) reads `Task` rows only — open
statuses, `owner == "you"`, capped at 16. **No `CalendarEvent` row reaches the
scheduling graph.** The planner has never seen a real meeting.

### Meeting-ness is inferred from the title

Because there are no calendar events, "meeting" is a guess made from words:

```python
# planner/agents.py:79 — classify_kind()
_MEETING = ("meeting", "sync", "1:1", "standup", "call", "interview",
            "alignment", "demo")
```

That guess drives placement. This is fragile in both directions, and we have
already been bitten by it: *"Deep work — standup delivery"* — focused work on the
standup **feature** — classified as a meeting because its subject contained
"standup", and was both scheduled and labelled as one. A guard was added for
explicit deep-work titles, but the underlying approach is unchanged: a title is
being used where a calendar record belongs.

### Every meeting gets the same 45 minutes in the same window

```python
# planner/agents.py:135, 166-172
meeting_start = max(_minutes(cfg.meeting_window_start), lunch_end)  # 13:15 default
...
for t in meetings + reviews:
    if cursor + 45 > end_cap:
        break
    cursor = place(t, cursor, 45)
```

Every "meeting" is 45 minutes, batched after lunch, in title order. A real 10:00
Outlook meeting cannot exist in this model at all — there is no mechanism for a
block the scheduler is not allowed to move.

### Three things the UI currently says that it has not earned

This is the part that matters most.

| The UI says | Where | What is actually true |
|---|---|---|
| *"a fixed meeting on your calendar"* | `planner/service.py:247` | The block came from a **task whose title contained a meeting word**. Nothing was read from a calendar. |
| *"No calendar conflicts"* | `planner/service.py:158` | Emitted when `critique["issues"]` is empty. The critic scores focus share, context switches and priority coverage. **It never looks at `CalendarEvent`.** The string is a rename of "the critic had no complaints". |
| `calendarConnected: true` | `planner/service.py:200-202` | ```python
from ..email.policy import email_enabled
calendar_connected = email_enabled()
``` Calendar connectivity is inferred from **whether the email module is switched on**. |

A product whose entire positioning is *observable, governed, never invents
progress* should not be telling a user there are no calendar conflicts when it
has not looked. **These three are worth fixing whether or not the rest of this
feature is built.**

### The calendar plane exists, but is a fixture

`calendar/service.py` has genuine conflict detection (`detect_conflicts`, an
O(n²) overlap scan) and an approval-gated draft path (`propose_event_draft`).
Its docstring already claims Google Calendar and Microsoft 365. But:

```python
_SEED_EVENTS = [
    {"external_id": "ev-1", "title": "Client Alpha review",
     "start_at": "2026-07-10T09:00:00", ...},
    ...
]

def sync_events(session, workspace_id="default"):
    """Mock/seed sync — upsert calendar events read-only."""
```

Three hardcoded events on a fixed 2026 date. Worse, `GET /v1/calendar/events`
**calls `sync_events()` on the read path** (`routers/calendar.py:26`) — so
"syncing" is a side effect of rendering. Any real Graph sync must not live there.

### What is already right

Three foundations are production-shaped and should not be redesigned:

1. **The Integration Gateway's governance split** (`integrations/service.py:163`)
   — reads execute immediately; writes open an `Approval` **and** a durable `Job`
   in `blocked_on_approval` and do not run until decided. This is exactly the
   model calendar writes need.
2. **A complete Microsoft OAuth implementation already exists.**
   `api-gateway/app/mail_oauth.py` implements the authorization-code flow with
   PKCE, one-time CSRF state, tokens stored **only** in the credential store,
   refresh, and an injectable `httpx` transport for tests. Its env vars are
   already named `MS_GRAPH_CLIENT_ID` / `MS_GRAPH_REDIRECT_URI`. It is bound to
   `MailboxConnection` and mailbox scopes — **generalize it, do not rewrite it.**
3. **The durable job queue + worker pattern** (`jobs/`, `scripts/standup_worker.py`)
   — self-arming, lapse-healing, backoff, dead-letter. Delta sync is the same
   shape.

---

## Part 2 — The feature

### The loop

```text
                 MICROSOFT 365 / GOOGLE
                          │
                  Graph / Calendar API
                          │
                          ▼
                 Integration Gateway
           reads now │ writes approval-gated
                          │
                          ▼
                Calendar Context Store
          occurrences · attendees · join links
          response status · sensitivity · sync cursor
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
        AI Day Planner          Meeting Agent
      fixed intervals first   assembled context only
              │                       │
              └───────────┬───────────┘
                          ▼
                 DayPilot Planning UI
              🔒 meeting + prep + buffer
                          │
                          ▼
              notes → decisions → actions
                          │
                    Approval Center
```

### Five things a connected calendar unlocks

1. **Connect.** Read meetings from Graph; keep a local synchronized store.
   Reads allowed, modifications approval-gated.
2. **Plan around them.** Meetings become fixed intervals; deep work, reviews,
   admin and lunch are placed in the **actual remaining gaps**.
3. **Prepare.** A brief assembled from the agenda, attendees, linked project,
   related tasks, documents, prior notes and permitted Slack threads.
4. **Manage.** Join · Open in Outlook · Prepare · Notes · related work · Propose
   reschedule. A 10–15 minute prep block before meetings that warrant one.
5. **Continue.** Notes become proposed tasks, follow-ups and decisions. DayPilot
   proposes; the Approval Center decides.

---

## Part 3 — The planner change

### Meetings must not become tasks

Beyond the conceptual argument, the code makes this concrete: `_collect_tasks()`
caps at **16 rows** and filters `owner == "you"`. A day with eight Outlook
meetings would consume half the planning budget with items the scheduler is not
allowed to move — and would inherit task semantics (priority scoring, "done")
that a meeting does not have.

So extend the state instead:

```python
state = {
    "tasks": _collect_tasks(session, workspace_id),
    "fixed_events": _collect_fixed_events(session, workspace_id, plan_date),
    "config": cfg,
    "hints": _hints_from_instruction(instruction),
}
```

### Reserve intervals first, then fill the gaps

`schedule_node()` currently walks a cursor from `day_start` and hopes. It should
compute free intervals and place work into them:

```text
today                                     after
─────────────────────────           ─────────────────────────
08:30  deep                         08:30 ─ 09:45  deep work
10:15  deep                         09:45 ─ 10:00  Prepare: Client Alpha
12:30  lunch                        10:00 ─ 11:00  🔒 Client Alpha Review
13:15  meeting (45m, guessed)       11:00 ─ 12:30  deep work
14:15  meeting (45m, guessed)       12:30 ─ 13:15  Lunch
...                                 13:15 ─ 14:00  🔒 Team Architecture
                                    14:15 ─ 15:45  project work
                                    16:00 ─ 17:00  admin
```

Rules:

- A fixed event is never moved, shortened or reordered by the scheduler.
- A **declined** meeting does not reserve time. A **tentative** one reserves it
  but is eligible for a reschedule proposal.
- `show_as: free` (and `oof`, differently) does not block deep work.
- An all-day event does not consume the working day.
- Deep-work blocks are split at interval boundaries rather than overflowing.
- If a meeting overlaps another, the planner reports the conflict — from real
  events — instead of silently absorbing it.

### 🔒 is a truth marker, not decoration

A locked block means *this came from your external calendar; the AI did not
invent it, and cannot move it on its own.* Proposing a move is allowed; the
Graph write goes through the Approval Center like every other external write.

### Critic metrics that reflect a real day

```text
calendarConflicts      real overlaps between fixed events
backToBackMeetings     zero-gap transitions
meetingMinutes         time not available for work
prepCoverage           meetings needing prep that got it
focusFragmentation     longest uninterrupted focus run
```

And `_quality_explanation()` stops claiming "No calendar conflicts" unless
`calendarConflicts == 0` **and** a calendar is connected and fresh. With no
calendar connected it should say so plainly, not imply a clean check.

---

## Part 4 — Outlook as a first-class provider

### Naming

Today `register_provider("calendar", lambda: GoogleCalendarProvider())`
(`integrations/providers/extra.py:139`) — the name asserts Calendar = Google.

```text
google_calendar      Google Calendar
microsoft_calendar   Microsoft 365 / Outlook
calendar             deprecated alias → google_calendar
```

Keep the alias so existing `IntegrationConnection` rows keep resolving; log a
deprecation on use and migrate rows in a later release.

### Shared canonical capabilities

Both providers expose the same ids so nothing downstream branches on vendor:

```text
events.read      READ    list occurrences in a window
event.read       READ    one event with attendees + body
freebusy.read    READ    availability
events.write     WRITE   create / update / move   (approval-gated)
event.respond    WRITE   accept / decline          (approval-gated, later)
```

### Module layout

`extra.py` should not become a drawer of unrelated integrations:

```text
integrations/providers/
  google_calendar/adapter.py
  microsoft_calendar/adapter.py
```

---

## Part 5 — Microsoft Graph specifics

### calendarView, then delta

```http
GET /me/calendarView?startDateTime=…&endDateTime=…     # first window
GET /me/calendarView/delta?…                            # subsequent syncs
```

`calendarView` returns **actual occurrences** in a range, including exceptions to
recurring series — which is what a planner needs. `delta` then returns only what
changed, so a local store stays current without refetching the calendar.

```text
first connection → sync (today − 7d … today + 30d) → store deltaLink
subsequent sync  → follow deltaLink → apply adds / updates / deletes
```

Request **immutable IDs** (`Prefer: IdType="ImmutableId"`): ordinary Outlook
event IDs can change when an item moves between folders, which would silently
duplicate rows in the local store.

### Sync belongs on the job queue, not the read path

Following the standup worker exactly:

```text
calendar.sync         every N minutes per connection; self-arming, lapse-healing
calendar.backfill     one-shot on connect
```

`GET /v1/calendar/events` then reads the local store and never calls a provider.
This also fixes today's bug where rendering the calendar performs a write.

### Least-privilege scopes

Connect read-only first:

```text
Connect Outlook Calendar
  ✓ Read meetings                      Calendars.Read
  ✓ Use meetings to optimize my plan
  ✓ Create meeting briefs
  [ ] Enable calendar changes          Calendars.ReadWrite  (optional, later)
```

`Calendars.Read` is a delegated permission that does not require admin consent;
`Calendars.ReadWrite` does more than we need for the MVP. DayPilot approval-gates
writes internally regardless, but the authorization layer should also be minimal —
an internal gate is not a substitute for not holding the permission.

---

## Part 6 — What we store

The current `CalendarEvent` (`models.py:728`) holds id, title, start, end, owner,
source, status, location, notes, project_id. That is far too thin for meeting
intelligence, and its ownership is split — it has both `workspace_id` and
`calendar_account_id → users.id`. **Pick one** (workspace, to match every other
table) before adding fields.

| Field | Why |
|---|---|
| `provider`, `connection_id` | which account this came from |
| `calendar_id` | multi-calendar support |
| `external_id` (immutable), `ical_uid` | identity; cross-calendar dedupe |
| `series_master_id` | recurring-series understanding |
| `start_at`, `end_at`, `timezone`, `is_all_day` | correct placement |
| `show_as` | free / busy / tentative / oof — drives whether time is reserved |
| `response_status` | a declined meeting must not block the day |
| `organizer`, `attendees` | preparation, and "external attendees?" |
| `location`, `is_online_meeting`, `join_url`, `web_link` | Join / Open in Outlook |
| `body_preview` | agenda |
| `sensitivity` | privacy policy (below) |
| `change_key`, `last_modified_at` | brief freshness |

Plus per-connection sync state: `delta_link`, `synced_through`, `last_sync_at`,
`last_error`.

---

## Part 7 — The Meeting Brief

Importing Outlook is table stakes. The brief is the feature.

```text
CLIENT ALPHA — ARCHITECTURE REVIEW
Today · 14:00–15:00 · Microsoft Teams                    [ Join ]

Why this meeting matters
Decision required on deployment architecture before Friday's milestone.

People
Jane Smith — Client Engineering  ·  David Rossi — Platform  ·  You — Organizer

Since the last meeting
• API gateway prototype completed
• PR #142 still blocked on auth review
• Client asked about EU data residency in Slack
• Architecture v3 updated yesterday

Open decisions
1. Single-region vs dual-region deployment
2. Whether embeddings move to the client VPC

Suggested talking points
• Recommend dual-region for production workload only
• Explain the additional operational cost
• Confirm Q4 traffic assumptions before committing

Questions to ask
• Is 99.9% or 99.99% availability contractual?
• Will customer data leave the EU?

Sources used
✓ Calendar event   ✓ Project Alpha   ✓ 3 documents   ✓ 1 Slack thread
○ Email — not connected     ○ Web research — disabled

[ Add 15 min prep ]   [ Ask DayPilot ]   [ Open project ]
```

### Assembled context, not open access

```text
Calendar event
  ├── linked project
  ├── related open tasks
  ├── RAG documents (permitted sources only)
  ├── previous meeting notes
  ├── Slack threads (chat.read only)
  └── GitHub activity
              ↓
       MeetingContext          ← the only thing the model sees
              ↓
         Ollabridge
              ↓
        MeetingBrief           ← every claim carries its source
```

The model receives the **assembled** context. It does not get a tool that can
reach into every integration. That is what "control of context" has to mean for
this to be safe in an enterprise setting — and it is the same discipline the
standup already uses: evidence rows pointing at real objects, never prose.

### Privacy defaults

Events marked `private` or `confidential` are processed **metadata-only** (title,
time, attendee count) until the user opts in per calendar. Graph exposes
`sensitivity`, so this is enforceable rather than aspirational.

### Freshness

`POST /v1/meetings/{id}/prepare` records `eventVersion` (from `change_key`). When
Outlook changes the event afterwards the brief shows:

> **Meeting changed since this brief was generated — Refresh**

rather than serving stale preparation as if it were current. Same instinct as the
standup's content hash: a snapshot must know when it has gone out of date.

---

## Part 8 — API shape

Separate synchronization from intelligence:

```text
/v1/integrations
  POST /oauth/microsoft_calendar/start
  GET  /oauth/microsoft_calendar/callback

/v1/calendar
  GET  /events            local store only — never calls a provider
  POST /sync              enqueue calendar.sync
  GET  /conflicts
  GET  /status            connected? providers? lastSyncAt? freshness?

/v1/meetings
  GET  /upcoming
  GET  /{eventId}
  POST /{eventId}/prepare
  GET  /{eventId}/brief
  PUT  /{eventId}/notes
  POST /{eventId}/actions      → proposed tasks / follow-ups (approval-gated)
```

And `planner_readiness` stops asking the email module:

```json
{
  "calendarConnected": true,
  "calendarProviders": ["microsoft_calendar"],
  "lastCalendarSyncAt": "2026-08-08T09:12:00Z",
  "calendarFreshness": "fresh"
}
```

so Planning can say *"Outlook synced 2 minutes ago · 6 meetings today"* and mean it.

---

## Part 9 — Where the work lands

| Area | Change |
|---|---|
| ~~`integrations/providers/extra.py`~~ | ✅ Google Calendar extracted to `providers/calendars.py` |
| ~~`providers/calendars.py`~~ | ✅ Graph adapter (calendarView + delta, immutable ids, UTC) |
| ~~`integrations/registry.py`~~ | ✅ Both registered; `calendar` kept as a deprecated alias |
| ~~`api-gateway/app/calendar_oauth.py`~~ | ✅ PKCE flow reused for calendars → `IntegrationConnection` |
| ~~`calendar/connections.py`, `calendar/settings.py`~~ | ✅ Real connection status; behaviour + context policy |
| `calendar/service.py` | Replace `_SEED_EVENTS` with connection-backed sync (✅ sync is off the read path) |
| `db/models.py` + migration | Richer `CalendarEvent`; per-connection sync state; single ownership |
| `jobs/` + `scripts/calendar_worker.py` | `calendar.sync` / `calendar.backfill`, self-arming |
| `planner/service.py` | `_collect_fixed_events()`; truthful readiness; truthful strengths |
| `planner/agents.py` | Interval-aware scheduler; calendar-aware critic metrics |
| `meetings/` (new) | Context assembly, brief generation, freshness, post-meeting proposals |
| `api-gateway/routers/` | OAuth + `/v1/meetings` |
| `ui-bridge/src/planning/` | 🔒 fixed blocks, prep blocks, meeting drawer |
| Home / Focus Mode | Next Meeting card; meeting Focus Mode |

The Integration Gateway and Approval Center are **not** redesigned. They are
already the right foundation.

---

## Part 10 — Staging

**Shipped — the honesty fixes and the connection surface (C1/C2).**

- `calendarConnected` now comes from `calendar/connections.py`, which reads the
  workspace's real `IntegrationConnection` rows, and readiness reports
  `calendarProviders`, `lastCalendarSyncAt` and `calendarFreshness` alongside it.
- "No calendar conflicts" is claimed only when a calendar is **connected**,
  **fresh**, and had **zero real overlaps on the planned day** (`conflicts_on`).
  Otherwise the plan says what it actually knows: no calendar connected, never
  synced, N overlapping meetings, or not synced recently.
- `GET /v1/calendar/events` no longer calls `sync_events()`. Reading the
  calendar performs no write and no provider round trip; syncing is
  `POST /v1/calendar/sync`.
- Providers are registered as `google_calendar` and `microsoft_calendar` with
  identical canonical capabilities, and `calendar` kept as a deprecated alias so
  existing connections keep resolving. The Graph adapter reads `calendarView`
  with immutable ids and UTC times, and follows a `deltaLink` when it has one.
- Connecting is real: `POST /v1/calendar/connect/{provider}` starts an
  authorization-code + PKCE flow (read-only scopes) reusing the mailbox OAuth
  machinery, and the callback records an `IntegrationConnection` with tokens in
  the credential store only. A provider with no OAuth client configured says so
  rather than dead-ending at the identity provider.
- **Settings → Calendar** is the configuration surface: connections, meeting
  preparation, the meeting-context allow-list, and planning behaviour. The
  Calendar page carries the connection chip and the connect offer, so nobody has
  to find Settings before they can connect.

The remaining untruth — *"a fixed meeting on your calendar"* for a title guess —
goes away with the scheduler change below, because then it will be true.

**Next — real Graph sync and fixed meetings in the planner.**

Real `calendarView`/`delta` sync on the job queue, the richer event record,
fixed meetings reserved before work is placed, Teams join links,
attendee/agenda context, meeting briefs with source disclosure, optional prep
blocks. Google Calendar rides the same canonical capabilities.

**Then — calendar management.** Create / reschedule / cancel through
`Calendars.ReadWrite`, still approval-gated.

**Then — the continuation loop.** meeting → notes → decisions → tasks →
follow-up draft → next meeting, every external write through the Approval Center.

---

## Acceptance criteria

1. A 10:00 Outlook meeting appears in the plan at 10:00 and the scheduler never
   moves it.
2. A **declined** meeting does not reserve time; a tentative one does.
3. "No calendar conflicts" appears only when a calendar is connected, fresh, and
   has zero real overlaps — otherwise the UI says what it actually knows.
4. `calendarConnected` reflects a calendar connection, never the email flag.
5. A recurring meeting with an exception shows the exception's real time.
6. Deleting a meeting in Outlook removes it from the plan on the next sync.
7. Rendering the calendar performs no provider call and no write.
8. A brief names every source it used, and marks itself stale when the event
   changes.
9. A `private` event contributes metadata only until the user opts in.
10. No calendar write reaches Google or Microsoft without an Approval Center
    decision, and every attempt is audited.
11. Tokens live only in the credential store — never in the database, logs, or a
    prompt.
