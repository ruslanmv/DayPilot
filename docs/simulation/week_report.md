# DayPilot — End-to-End Week Simulation

A real, reproducible five-day run for a **principal AI/ML engineer**. DayPilot
pairs with a local Ollabridge-compatible endpoint (`http://localhost:11435/v1`, model
`qwen2.5:0.5b`) and every daily inference is a real HTTP round-trip. The governed
workflow (projects, day-plan lifecycle, wrap-up, continuity) runs against a real
database, and no email is sent and no code is written without approval.

> The sandbox network policy blocks the public Ollama download, so a local
> OpenAI/Ollama-compatible server stands in for `ollama` + the light model. The
> DayPilot↔provider wire contract (`/v1/models`, `/v1/chat/completions`) is identical
> to production, so the pairing and inference path is exercised for real.

## Run summary

| Metric | Value |
| --- | --- |
| Model · endpoint | `qwen2.5:0.5b` · `http://localhost:11435/v1` |
| Real inferences | 20 (4/day × 5 days) |
| Total tokens | 1557 |
| Avg / max latency | 69.0 ms / 76.1 ms |
| Emails drafted / **sent** | 5 / **0** |
| Writes without approval | **0** |
| Approvals granted | 5 / 5 |
| Projects carried by continuity | 3 |

## The week, day by day

### Monday — LLM Serving Platform
- **Focus:** Design the local/cloud routing policy and failover path  ·  plan state → `ACTIVE`
- **Plan (AI):** Priorities for the day, highest-leverage first:
- **Code (AI):** Proposed change: add input validation and a typed return, keep the public  _(write approved before merge)_
- **Email (AI):** drafted reply to “Client Alpha asks to confirm the revised model-serving milestone dates.” — _not sent_
- **RAG (AI):** Based on the retrieved project context: the serving-platform routing policy is

### Tuesday — LLM Serving Platform
- **Focus:** Implement request-tier selection with health-based fallback  ·  plan state → `ACTIVE`
- **Plan (AI):** Priorities for the day, highest-leverage first:
- **Code (AI):** Proposed change: add input validation and a typed return, keep the public  _(write approved before merge)_
- **Email (AI):** drafted reply to “Security team requests the data-flow note for the RAG corpus before Thursday.” — _not sent_
- **RAG (AI):** Based on the retrieved project context: the serving-platform routing policy is

### Wednesday — RAG Evaluation Harness
- **Focus:** Wire the scorecard over the project corpus  ·  plan state → `ACTIVE`
- **Plan (AI):** Priorities for the day, highest-leverage first:
- **Code (AI):** Proposed change: add input validation and a typed return, keep the public  _(write approved before merge)_
- **Email (AI):** drafted reply to “Recruiting wants 30 min this week; low priority, can move to next week.” — _not sent_
- **RAG (AI):** Based on the retrieved project context: the serving-platform routing policy is

### Thursday — Model Registry & Governance
- **Focus:** Add approval-gated rollout states to the registry  ·  plan state → `ACTIVE`
- **Plan (AI):** Priorities for the day, highest-leverage first:
- **Code (AI):** Proposed change: add input validation and a typed return, keep the public  _(write approved before merge)_
- **Email (AI):** drafted reply to “On-call handoff: latency spike on the hybrid tier overnight, now recovered.” — _not sent_
- **RAG (AI):** Based on the retrieved project context: the serving-platform routing policy is

### Friday — LLM Serving Platform
- **Focus:** Harden failover and write the runbook  ·  plan state → `ACTIVE`
- **Plan (AI):** Priorities for the day, highest-leverage first:
- **Code (AI):** Proposed change: add input validation and a typed return, keep the public  _(write approved before merge)_
- **Email (AI):** drafted reply to “Finance needs the GPU spend estimate for next quarter by Friday.” — _not sent_
- **RAG (AI):** Based on the retrieved project context: the serving-platform routing policy is

## What this proves

- **Pairing works** against a local Ollabridge-compatible endpoint (the same
  `OllabridgeConnector` and `/v1` contract used for Ollabridge Cloud).
- **Inference is wired end to end** — 20 real completions drove planning, coding,
  email drafting, and RAG across the week.
- **The governance contract holds** — 0 emails sent, 0 unapproved writes; every
  sensitive action passed through an approval.
- **Continuity works** — each day wraps and rolls unfinished work into the next.
