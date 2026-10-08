# Development plan and acceptance criteria

This design PR is additive documentation only. It does not add dependencies, migrations, runtime jobs, routes or enabled schedules. Implementation should proceed through small reviewable PRs, each with its own acceptance evidence. Feature flags default off. Existing DayPilot behavior remains available throughout.

## Release slices

**R1 — Useful weekly drafts:** branded curated templates, short wizard, permission-scoped sources, editable native slides, PPTX/actual render review, immutable revisions and manual weekly preparation. This is the first genuinely usable product.

**R2 — Reliable team workflow:** deeper editor/locks, approved company-template fidelity, source freshness, recurring draft preparation, reviewer roles and explicitly authorized sharing. Turn on recurrence only after recovery/idempotency gates.

**R3 — Advanced authoring:** richer genres, native dmind systems diagrams, Matrix proposals, reproducible source bundles and optional sandboxed expert JavaScript. Competitive evaluation continues across releases; a comparison claim is gated by results.

## Implementation batches

Estimates are planning ranges in engineer-weeks, not commitments. Dependency work can overlap; gates cannot be skipped. A two-engineer team with part-time presentation design, product and QA should plan roughly 14–22 calendar weeks for R1/R2, with advanced fidelity/expert-mode scope potentially extending this. A first curated-template vertical slice should demonstrate real native export/render before expanding the roadmap.

| Batch | Deliverable and likely files | Dependencies | Estimate | Acceptance evidence |
| --- | --- | --- | --- | --- |
| P00 | Capability spike: native chart/table/diagram/text/notes, actual PPTX render, custom fonts and brand logos; compare complex imported master | None | 1–2 | Real corpus opened/edited in PowerPoint; supported/unsupported capabilities documented; choose renderer and import strategy |
| P01 | Production contracts/semantic validators derived from `schemas/`; compiler interface and resource budgets | P00 | 1 | Fixtures + negative cases; IDs/units/fonts/counts/geometry checked; client cannot supply approval authority |
| P02 | Company grants, immutable kit/template/assets and scoped artifact abstraction; new additive database migration | P01 | 1–2 | Cross-company denials; original asset bytes/hash retained; immutable versions and active-pointer CAS |
| P03 | `packages/presentation-engine/` compiler and curated editorial/chart/table/diagram layouts | P00–P02 | 2–3 | Native editability in exported corpus; brand tokens/ratios/notes; deterministic semantic outputs; no screenshot decks |
| P04 | Isolated export/render worker, phase budgets, run lease/fencing, staging/publish transactions | P02–P03 | 1–2 | Crash/retry/cancel/stale-worker drills; actual PPTX renders; no prior-head loss or duplicate publication |
| P05 | Source snapshot adapters: text/Markdown and existing granted Documents first; PDF/DOCX/spreadsheets/pptx extraction iteratively | P01–P02 | 1–2 | Permissions rechecked; prompt injection treated as source text; typed facts/locators/freshness; bounded hostile inputs |
| P06 | Feature-flagged library + wizard + company/template setup; gateway and async progress | P02–P05 | 2 | New route without shell regressions; topic/source/brand/outline flow; budgets and meaningful errors; mobile review |
| P07 | Quality service and per-slide review UI: fact/geometry/brand/native-object checks, actual render, receipts, bounded repairs | P03–P06 | 2 | Every slide coverage; hard failures block ready/distribution; locks/facts survive repair; no receipt reuse after edits |
| P08 | Revision editor, outline/content/layout patches, selected regeneration, human locks and restore-as-new-revision | P06–P07 | 1–2 | Concurrent-edit conflicts; stale AI patch rejection; version history/downloads; original imports untouched |
| P09 | Manual weekly recipes, reporting windows/cutoffs, comparable metrics and previous-deck delta | P05, P08 | 1 | Same-period replays converge; missing values remain gaps; exact recipe/source pins; no old facts relabeled current |
| P10 | Opt-in recurring draft scheduler, timezone/DST preview, pause/cancel/catch-up and owner notification proposal | P04, P09 | 1–2 | DST gap/fold, downtime and duplicate-worker drills; draft-only outputs; no schedule enabled by default |
| P11 | Existing-template fidelity import, master/placeholder mapping, edited-copy preservation/branching and explicit normalized replacement path | P00, P02, P07 | 2–4 | Real company templates compared slide-by-slide; original retained; unsupported content disclosed; no silent flattening |
| P12 | Exact-artifact reviews, scoped private share links, expiry/revocation, approved delivery adapter and audit | P07–P10 | 1–2 | Recipient/hash changes invalidate approval; authorization on thumbnails/downloads; delivery ambiguity reconciled |
| P13 | Native dmind revision import, optional Matrix snapshot proposals and permission-scoped MCP tools | P03, P08 | 1–2 | Native diagram edits; source graph unchanged; no design intake/coding/task side effects; MCP follows approval contracts |
| P14 | Reproducible JS source bundle and opt-in expert-code sandbox | P04, P08 | 2–3 | Sandbox escape/resource/network probes; no credentials; reviewed code generates candidate only; reproducibility manifest |
| P15 | Held-out benchmark, office compatibility/accessibility corpus, pilot telemetry and release documentation | P07 onward | 1–2 + ongoing QA | Hard gates and blind review targets; measured correction time; no unsupported superiority statements |

Each estimate includes focused implementation validation; imported-template variability and licensed fonts can materially change effort. Do not sum all rows as a fixed deadline. R1 requires P00–P09 and its P15 subset; P08 can initially ship content/lock/selected-regeneration operations rather than a full freeform canvas. R2 adds P10–P12; R3 adds P13–P14. Real brand assets and authorized source examples are external inputs to a company pilot, not blockers for a fictional-template prototype.

## Acceptance scenarios

1. **Company consistency:** Activate two fictional/authorized company kits. Generate from the same brief. Each uses its own approved logos, colors, fonts and footers. No mixed-company assets appear. Updating a kit creates a version and leaves both old exports intact.
2. **Weekly update:** Prepare an 8–12-slide report with a native trend chart and status table. Exact count includes all slides. Notes contain reporting window and evidence. Edit a chart series in PowerPoint and save successfully.
3. **Human control:** Lock a slide's conclusion and layout. Regenerate two other slides. The locked objects and prior revision are unchanged. A concurrent human edit produces a conflict rather than overwritten content.
4. **Quality failure:** Supply an unsupported font, overly long title and contradictory metric. Show findings and candidate status. No approved/review-ready artifact is falsely published. Fixing the content requires a new export/render/receipt.
5. **Template fidelity:** Import a real `.potx`/`.pptx`, retain the original, map supported masters/placeholders, generate varied sample content and compare actual exports. Unknown objects either preserve with proof or require an explicit normalized variant. Do not market unsupported universal round-trip editing.
6. **Weekly reliability:** Manual/scheduled same-period requests and worker retries produce one occurrence. Source snapshots and recipe remain frozen; reruns create revisions. DST, pause, source revocation and crash recovery cannot cause stale publication or duplicate sends.
7. **Privacy:** A member of company A cannot fetch company B's logo, thumbnail, citation, PPTX or share link by guessing an ID. Expert code cannot read host files, use network or access provider credentials.
8. **Delivery:** Propose sharing an approved revision to named recipients. A change in recipients, template, source redaction, quality receipt or PPTX hash invalidates the proposal. A retry after an ambiguous provider response reconciles rather than blindly resends.
9. **System explanation:** Import an approved dmind graph revision into a technical deck. Nodes/connectors remain native editable objects with source references. The original graph and project tasks remain unchanged.
10. **Usability:** A presenter chooses a saved series and prepares a new weekly draft without re-entering brand rules. The actual rendered deck is readable, useful and reviewable; a mobile reviewer can read notes and approve with the right role.

## Validation strategy

Use meaningful boundary/invariant checks rather than snapshots that merely repeat compiler internals. Validate permission matrices, source revocation, revision CAS/locks, lease fencing, idempotency, delivery binding and hostile import limits. Render regression samples for representative templates/content rather than every trivial UI edit. Inspect actual exported objects and consumer edits, not only XML shape counts.

Quality corpus covers overflow, mixed languages, custom fonts, transparent logos, alternate aspect ratios, missing/zero chart values, large tables, connector routes and unsupported imports. Source fixtures include conflicting values and stale reporting windows. UI checks cover keyboard navigation, focus management, small screens, async recovery and shell route regression. Performance tests run in declared hardware/worker conditions and measure total cost/latency as well as render quality.

Initial service goals to calibrate: a routine 10-slide supplied-data deck exports/renders/checks in ≤120 seconds at p95 on a declared worker configuration, excluding source ingest/provider waiting; user cancellation acknowledged within five seconds; no queue/worker memory growth during repeated series runs. Publish measurements and adjust capacity budgets after the spike, rather than presenting these targets as achieved.

## Rollout and recovery

1. Merge the reviewed design separately from runtime changes. Choose runtime version, import support and storage policy in P00.
2. Add nullable/new presentation tables with the next unused migration ID; never modify applied historical migrations. Back up representative environments and validate forward migration with existing DayPilot data. There is no destructive schema downgrade in a rollback.
3. Ship feature flags off; enable company setup and supplied-data curated-template generation for internal workspaces. Keep all presentation jobs in an isolated worker pool. Missing renderer capability is explicit.
4. Enable R1 for a small company pilot after brand sample approval and per-slide quality gates. Run manual weekly drafts for several reporting periods; measure correction effort and regressions.
5. Enable recurrence per series only after P10 recovery tests. Enable share/send adapters separately after exact-scope approval tests. No existing user receives a new schedule or public link on upgrade.
6. Expand template fidelity/advanced code by capability and company opt-in. Publish known font/object/consumer limitations and measured benchmark results.
7. Roll back by disabling the presentation UI/routes that create new runs, pausing new series jobs and stopping isolated workers. Keep authorized access to existing artifact downloads/history where possible. Preserve all rows/assets/originals; do not remove unrelated queues or revert other DayPilot behavior.

Document ownership: a product owner approves story/workflow requirements, a presentation designer approves layouts/brand samples, engineering owns compiler/contracts/leases, QA owns consumer/accessibility evidence, and company administrators own asset rights/template activation. These are proposed responsibilities, not recipients or assignments created by this PR.

## Requirement traceability

| User goal | Design/implementation | Gate |
| --- | --- | --- |
| Additive, non-destructive DayPilot feature | Dedicated scope, immutable assets/revisions, flag-off rollout; P02/P04/P08 | Original inputs and existing modules preserved; rollback drill |
| High presentation quality | Actual-file render, evidence/geometry review, repair; P03/P07/P15 | Every slide reviewed, no hard failures, held-out human scores |
| JavaScript authoring with Claude Code/Codex | Data-first compiler, source bundle, optional sandbox; P03/P14 | Native editable export; no arbitrary code in shared process |
| PowerPoint plus companion formats | Renderer adapter, PPTX/PDF/PNG/source bundle; P03/P04 | Office open/edit/save and actual-render corpus |
| Company colors/logos/templates | Company grants, versioned kits, fidelity import; P02/P06/P11 | Original asset hashes, correct fonts/palette/masters, sample approval |
| Presentation every week | Saved recipe/manual draft then opt-in recurrence; P09/P10 | Correct period/freshness/DST, one occurrence, draft-only recovery |
| Industry-leading outcome | Measured blind comparison and correction effort; P15 | Supported claims only; comparable budgets and source corpus |
| dmind/Matrix compatibility | Approved snapshots/native diagram adapter; P13 | No source graph edits or project/task creation |

## Design package verification

The checked-in schemas and fictional fixtures are review tools. Run `python docs/presentations/validate_contracts.py` with Python 3.11+ and `jsonschema` installed. It checks Draft 2020-12 schema validity, fixture shape, semantic relationships, metric consistency, geometry, timezone/cadence fields, branding references and rejection probes. It does not implement or validate a production renderer, scheduler, authorization service or delivered PowerPoint file.
