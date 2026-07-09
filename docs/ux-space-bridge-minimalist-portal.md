# DayPilot Premium Minimalist Portal

This document is the permanent UI/UX architecture specification for the DayPilot portal. It converts the previous rich command-bridge demo into a calmer, Apple-like minimalist workspace: one conversational command surface, one temporal planning surface, one task ledger, and one non-disruptive context drawer.

## Design thesis

DayPilot should feel like a premium personal operating system rather than a conventional dashboard. The screen should not show everything at once. It should show the next useful decision, then reveal deeper telemetry only when the Commander asks for it.

Principles:

1. **Chat-first control:** the primary interaction is natural language, like ChatGPT, with short confirmations from the AI planner.
2. **Context on demand:** task blocks are clickable, but they never navigate away or open modal interruptions. They open a right-side drawer.
3. **Calendar as AI flight path:** day and week views show how AI distributes work, meetings, and background agent processes.
4. **Task separation:** manual Commander tasks and autonomous `.hpersona` work must never be visually mixed.
5. **Color as telemetry:** accent colors indicate state, not decoration.

## Visual token contract

```text
Base background      #080c14 / #090d16
Surface              #111625
Elevated surface     #151b2b / #182032
Border               rgba(255,255,255,0.06)
Primary text         #f8fafc
Secondary text       #94a3b8
Apple Blue           #007aff  active user focus / commander work
Cyber Cyan           #00f0ff  sync / solver telemetry
System Purple        #af52de  autonomous .hpersona work
Alert Orange         #ff9500  blockers / merge conflicts
Success Green        #34c759  ready / safe / synchronized
Sans font            -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif
Mono font            SFMono-Regular, Menlo, Monaco, Consolas, monospace
``` 

## Global shell ASCII

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│  DAYPILOT                         Neural workday, quietly organized              ● SYNCED   │
├───────────────┬──────────────────────────────────────────────┬───────────────────────────────┤
│               │                                              │                               │
│  Command      │  Strategic Feed                              │  Strategy Blocks              │
│  Bridge       │  Chat-first planning surface                  │  Context-on-demand timeline    │
│               │                                              │                               │
│  Calendar     │  ┌────────────────────────────────────────┐  │  ┌─────────────────────────┐  │
│  Core         │  │ AI: Today is protected for deep work.  │  │  │ 09:00 Inbox Sweep       │  │
│               │  └────────────────────────────────────────┘  │  │ Sec-Core · critical     │  │
│  Tasks        │                                              │  └─────────────────────────┘  │
│  Ledger       │  ┌────────────────────────────────────────┐  │  ┌─────────────────────────┐  │
│               │  │ You: Add a meeting prep at 16:00.      │  │  │ 11:00 Model Boundaries  │  │
│  HomePilot    │  └────────────────────────────────────────┘  │  │ Commander · focus       │  │
│  GitPilot     │                                              │  └─────────────────────────┘  │
│               │  ┌────────────────────────────────────────┐  │  ┌─────────────────────────┐  │
│               │  │ Type a directive, priority, or change… │  │  │ 16:00 Strategy Brief    │  │
│               │  └────────────────────────────────────────┘  │  │ Commander · scheduled   │  │
│               │                                              │  └─────────────────────────┘  │
└───────────────┴──────────────────────────────────────────────┴───────────────────────────────┘
```

## Zone A — Strategic Feed

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Strategy Orchestration                                                │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ✦ DayPilot                                                          │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ I balanced your day around two deep-work blocks and one        │  │
│  │ critical inbox sweep. Calendar conflicts are hidden unless     │  │
│  │ they need a decision.                                          │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│                                                Commander             │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Insert a critical task to review Matrix Contract models at 18:00│  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ✦ DayPilot                                                          │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Added. I moved passive email parsing to Sec-Core and protected │  │
│  │ 18:00 as Commander focus time.                                │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Ask DayPilot to schedule, rebalance, summarize, or delegate…   │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

Rules:

- No button clusters inside the chat surface.
- One input at the bottom; voice and submit controls may remain icon-only.
- Chat directives update schedule state, task ledger state, and agent process state together.

## Zone B — Clickable Strategy Blocks

```text
┌─────────────────────────────────────────┐
│ Today's Strategy                         │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ 09:00–10:30                         │ │
│ │ Inbox Sweep & Contract Telemetry     │ │
│ │ Sec-Core · critical · running        │ │
│ └─────────────────────────────────────┘ │
│ ┌─────────────────────────────────────┐ │
│ │ 11:00–13:00                         │ │
│ │ Refactor Model Boundaries            │ │
│ │ Commander · focus · active           │ │
│ └─────────────────────────────────────┘ │
│ ┌─────────────────────────────────────┐ │
│ │ 16:30–17:30                         │ │
│ │ Ecosystem Sync Briefing              │ │
│ │ Commander · scheduled                │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

Click behavior:

```text
┌───────────────────────────────────────────────────────┬─────────────────────────────┐
│ Current view remains fixed                            │ Detail Drawer slides in      │
│ No routing                                             │ ┌─────────────────────────┐ │
│ No centered modal                                      │ │ Refactor Boundaries     │ │
│ No layout interruption                                 │ │ Monday · 11:00–13:00    │ │
│                                                        │ │                         │ │
│                                                        │ │ Context                 │ │
│                                                        │ │ - ingested email        │ │
│                                                        │ │ - linked GitPilot diff  │ │
│                                                        │ │ - .hpersona output      │ │
│                                                        │ └─────────────────────────┘ │
└───────────────────────────────────────────────────────┴─────────────────────────────┘
```

## Zone C — Calendar Core View

### Day Horizon

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Temporal Matrix                           [ Day Horizon ] [ Week Horizon ]   │
├─────────┬────────────────────────────────────────────────────────────────────┤
│ 08:00   │                                                                    │
├─────────┼────────────────────────────────────────────────────────────────────┤
│ 09:00   │ ┌──────────────────────────────────────────────────────────────┐   │
│         │ │ Inbox Sweep & Contract Telemetry · Sec-Core · critical       │   │
│         │ └──────────────────────────────────────────────────────────────┘   │
├─────────┼────────────────────────────────────────────────────────────────────┤
│ 11:00   │ ┌──────────────────────────────────────────────────────────────┐   │
│         │ │ Refactor Model Execution Boundaries · Commander · focus      │   │
│         │ └──────────────────────────────────────────────────────────────┘   │
├─────────┼────────────────────────────────────────────────────────────────────┤
│ 14:00   │ ┌──────────────────────────────────────────────────────────────┐   │
│         │ │ GitPilot Dependency Patch Review · Git-Core · autonomous     │   │
│         │ └──────────────────────────────────────────────────────────────┘   │
├─────────┼────────────────────────────────────────────────────────────────────┤
│ 18:00   │ ┌──────────────────────────────────────────────────────────────┐   │
│         │ │ Matrix Contract Model Review · Commander · scheduled         │   │
│         │ └──────────────────────────────────────────────────────────────┘   │
└─────────┴────────────────────────────────────────────────────────────────────┘
```

### Week Horizon

```text
┌───────┬────────────┬────────────┬────────────┬────────────┬────────────┬────────────┬────────────┐
│       │ Mon        │ Tue        │ Wed        │ Thu        │ Fri        │ Sat        │ Sun        │
├───────┼────────────┼────────────┼────────────┼────────────┼────────────┼────────────┼────────────┤
│ 09:00 │ Inbox/RAG  │            │ Sync prep  │            │ Audit pass │            │            │
├───────┼────────────┼────────────┼────────────┼────────────┼────────────┼────────────┼────────────┤
│ 11:00 │ Model core │ PR review  │            │ Research   │ Deep work  │            │            │
├───────┼────────────┼────────────┼────────────┼────────────┼────────────┼────────────┼────────────┤
│ 14:00 │            │ Git-Core   │ Calendar   │            │ Briefing   │            │            │
├───────┼────────────┼────────────┼────────────┼────────────┼────────────┼────────────┼────────────┤
│ 18:00 │            │            │            │ Contract   │            │            │            │
└───────┴────────────┴────────────┴────────────┴────────────┴────────────┴────────────┴────────────┘
```

## Operational Ledger

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Operational Ledger                                      REALTIME STATE MATRIX│
├───────────────────────────────────────┬──────────────────────────────────────┤
│ Commander Assignments                 │ Autonomous Agents (.hpersona)         │
│ manual, high-leverage work            │ background scanning and execution      │
├───────────────────────────────────────┼──────────────────────────────────────┤
│ ┌───────────────────────────────────┐ │ ┌──────────────────────────────────┐ │
│ │ Refactor Model Boundaries          │ │ │ Sec-Core parsing incoming email   │ │
│ │ status: active                     │ │ │ status: running                   │ │
│ │ time: 11:00–13:00                  │ │ │ source: Matrix RAG                │ │
│ └───────────────────────────────────┘ │ └──────────────────────────────────┘ │
│ ┌───────────────────────────────────┐ │ ┌──────────────────────────────────┐ │
│ │ Matrix Contract Review             │ │ │ Git-Core generating patches       │ │
│ │ status: scheduled                  │ │ │ status: scheduled                 │ │
│ │ time: 18:00–19:00                  │ │ │ source: local repo index          │ │
│ └───────────────────────────────────┘ │ └──────────────────────────────────┘ │
└───────────────────────────────────────┴──────────────────────────────────────┘
```

## Context Telemetry Drawer

The right drawer is the only approved deep-detail reveal pattern. It should display task source, execution frame, ingested emails, GitPilot branches, RAG citations, and `.hpersona` outputs while preserving the current screen behind it.

```text
┌──────────────────────────────┐
│ Context Telemetry             │
│ Refactor Model Boundaries     │
├──────────────────────────────┤
│ Execution Frame               │
│ Monday · 11:00–13:00          │
├──────────────────────────────┤
│ Source                        │
│ model-serving · orchestrator  │
├──────────────────────────────┤
│ Vector Context Elements       │
│ emails, code diffs, RAG notes │
└──────────────────────────────┘
```

## State flow

```text
User directive in chat
        │
        ▼
Parse intent and priority
        │
        ├── update strategy blocks
        ├── update day/week calendar allocation
        ├── update Commander task ledger
        └── update autonomous .hpersona process ledger
        │
        ▼
Non-disruptive confirmation message in Strategic Feed
```

## Responsive behavior

```text
Desktop:  rail | chat | strategy blocks
Tablet:   top nav + chat stacked over strategy blocks
Mobile:   single column tabs; drawer becomes full-height sheet
```

The mobile experience should still feel like the same command bridge: no dense dashboards, no uncontrolled metrics, no stacked toolbars.
