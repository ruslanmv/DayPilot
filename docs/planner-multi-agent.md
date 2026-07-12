# The multi-agent day planner

How DayPilot turns a pile of tasks into an **optimized, efficient, productive
day** for a principal AI/ML engineer — and how the planner itself improves
through time under governance.

## 1. Design review of the original planner

The original day-planning path (batch B4) had a solid governed skeleton and a
naive brain:

| Aspect | Before | Assessment |
|---|---|---|
| Plan lifecycle | `DRAFT → PROPOSED → APPROVED → ACTIVE → WRAPPED` state machine, events, wrap-up, continuity | **Keep** — governance and continuity are right |
| Plan generation | `build_or_get_draft`: single greedy pass copying up to 12 tasks into blocks, preserving whatever times they had | **Replace** — no prioritization, no energy curve, no optimization, no AI |
| Replanning | None — a draft was built once | **Add** |
| Conversation | None — the plan was not something you could talk to | **Add** |
| Calendar interaction | Blocks were display-only | **Add** — every block must be clickable |
| Feedback loop | Nothing measured whether plans were good; nothing improved the planner | **Add** — governed self-optimization |

## 2. The multi-agent architecture

Simple by design: **five small single-responsibility agents** cooperating over a
shared state, expressed as a graph with the **LangGraph API shape** so it can be
moved onto the real `langgraph` package without rewriting any node
(`services/orchestrator/daypilot_orchestrator/planner/graph.py` is a ~100-line,
dependency-free `StateGraph` with `add_node` / `add_edge` /
`add_conditional_edges` / `START` / `END` / `compile().invoke()` and a loop guard).

```text
        ┌────────────────────────────────────────────────┐
        │                                                ▼
START → prioritize → schedule → critique ──(score < bar)─┘   (≤ max_iterations)
                                   │
                             (good enough)
                                   ▼
                               finalize → END
```

| Agent | Responsibility |
|---|---|
| **Context** (`service._collect_tasks`) | Gather open tasks joined with project risk — the planner's ground truth. |
| **Prioritizer** | Score every task: priority × weight + due-today bonus + project-risk bonus + deep-work bonus. |
| **Scheduler** | Place blocks by the **energy curve**: 90-min deep-work blocks in the morning peak, lunch protected, meetings/reviews batched after lunch, admin batched at the end of the day, 15-min buffers everywhere. Honors critic hints (`protect_morning`, `batch_admin`). |
| **Critic** | Score the candidate 0–100 (focus share 45% + few context switches 25% + high-priority coverage 30%) and loop back to the scheduler with concrete hints until the plan beats `target_score` — bounded by `max_iterations`. This loop is what makes the plan *optimized* rather than a single greedy pass. |
| **Finalizer** | Produce the plan narrative via the paired **Ollabridge** model when reachable (`DAYPILOT_MODEL_BACKEND=ollabridge`), with a deterministic fallback so planning works offline and in CI. |

The result is persisted into the **existing** `DayPlan`/`PlanBlock` tables, so
Focus Mode, wrap-up, continuity, and the approval lifecycle all keep working —
the planner is a brain upgrade, not a parallel system. Every run records the
graph path, score, and config version on the event stream.

### Why these heuristics

Time-management research and practice for senior engineers converge on: protect
2+ hours of morning deep work; batch meetings to kill context-switch cost; push
shallow admin to the low-energy end of day; keep buffers so one overrun doesn't
cascade; and never schedule through lunch. The critic encodes those as a
measurable score, so "optimized" is a number you can see (and the revision loop
can improve).

## 3. Using it

**API** (`/v1/planner`):

```bash
POST /v1/planner/plans/2026-07-13/generate      # run the graph, persist blocks
POST /v1/planner/plans/2026-07-13/generate      # {"instruction": "protect my morning"} → replan
POST /v1/planner/plans/2026-07-13/chat          # {"message": "move admin to the afternoon"}
GET  /v1/planner/config                          # active PlannerConfig version
POST /v1/planner/review                          # run the self-optimization review
POST /v1/planner/config/apply                    # apply an APPROVED proposal
```

`chat` answers questions from the plan (focus time, what's next) and treats
change requests ("move", "replan", "protect", "batch"…) as replans — the
instruction is translated into scheduler hints.

**UI — the Planning tab.** A timeline of the optimized day where **every block
is clickable** (Start focus · Mark done · Move ±30 min), a one-tap **Replan**
button, the critic's score badge, and a **chat panel** to converse with the plan.
Works in the desktop shell and the mobile shell.

## 4. The planner improves through time (governed)

The planner never silently modifies itself. Every tunable lives in
`PlannerConfig` (weights, energy windows, block lengths, quality bar), and:

1. Every generated plan records **metrics** (`planner.metrics` events): score,
   focus minutes, context switches, iterations, config version.
2. `POST /v1/planner/review` (run periodically — a Routine/cron) aggregates the
   recent metrics, diagnoses weaknesses (low focus → longer deep blocks and a
   higher deep-work weight; many switches → stronger switch penalty; critic
   always hitting the cap → adjust the bar), and proposes a **new config
   version** with a human-readable rationale.
3. The proposal opens an **Approval Center** item. Only an approved proposal is
   applied — as an append-only `planner.config` event; `active_config` reads the
   latest applied version, and the whole history stays auditable.
4. When tuning cannot fix a finding, the review emits a **code-review
   suggestion**: file a GitPilot coding run against `planner/agents.py` — source
   changes go through the same approval-gated coding workflow as any other code.

This is the same trust posture as everywhere else in DayPilot: *the model may
propose; the platform decides.*

## 5. Files

| File | Purpose |
|---|---|
| `planner/graph.py` | LangGraph-compatible StateGraph runtime (swap-in `langgraph` later). |
| `planner/agents.py` | PlannerConfig + prioritize/schedule/critique/finalize nodes + graph wiring. |
| `planner/service.py` | Persistence into DayPlan/PlanBlock, replan, chat, Ollabridge narrative. |
| `planner/revision.py` | Metrics, periodic review, approval-gated config versions. |
| `app/routers/planner.py` | The `/v1/planner` API. |
| `packages/ui-bridge/src/planning/` | The Planning tab (timeline, popover actions, replan, chat). |
| `tests/test_planner_multiagent.py` | Graph, agents, day-shape, persistence, chat, revision loop. |
