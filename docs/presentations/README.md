# DayPilot Presentations

Status: implementation-ready design proposal. This PR adds design documents, draft contracts and examples. It does not enable the feature or schedule a presentation.

Implementation: an R1 vertical slice is built on branch `claude/presentations` (flag `DAYPILOT_PRESENTATIONS`, off by default); see [implementation plan and status](implementation-plan.md).

## Product outcome

Add **Presentations**, a dedicated DayPilot workspace for creating, reviewing and exporting company-branded, editable PowerPoint decks. A person supplies a brief, selects sources and chooses a company template. DayPilot proposes an outline, creates slides, renders the actual exported PowerPoint, checks every slide and presents a reviewable revision.

Weekly presentation series reuse the company's approved template and reporting structure, capture fresh source snapshots and prepare a new draft for each reporting period. Previous decks and human edits remain intact. Sharing or sending is a separate action.

## Core decisions

| Decision | Result |
| --- | --- |
| Company brand kits and versioned templates | Logos, colors, fonts, layouts, chart styles and required footers apply consistently across decks |
| Structured deck specification with JavaScript authoring | Claude Code, Codex or another configured provider can help produce content and layout instructions; an allowlisted compiler creates native `.pptx` objects |
| Editable evidence | Titles, body text, tables, charts and dmind diagrams remain editable; illustrations/photos remain image assets |
| Quality gate based on the exported file | Inspect rendered PPTX output, not just an HTML approximation; reject clipping, broken charts, missing fonts and logo distortion |
| Revisions and slide locks | Regenerate selected slides without overwriting approved content or the original source file |
| Weekly drafts with explicit review | Stable templates and section identities, fresh metrics, source cutoffs, comparison definitions, reminders and recovery |
| Measured quality | Blind benchmark, editability and correction-time metrics; no unsupported claim of superiority to Manus |

## Read the design

1. [Product experience and company templates](product-spec.md)
2. [Generation architecture, contracts, APIs and storage](technical-design.md)
3. [Visual quality, accessibility and competitive evaluation](quality-standard.md)
4. [Development batches, release gates and rollout](development-plan.md)
5. [Draft JSON Schemas](schemas/) and [fictional fixtures](examples/)
6. [Primary technical references](references.md)

The proposed default deployable renderer is PptxGenJS behind an adapter, with native OOXML export. An existing-deck fidelity adapter is a separate capability requiring a successful preservation spike. HTML is useful for interactive previews but is not the authoritative PowerPoint representation. The design does not equate a screenshot of a slide with an editable PowerPoint slide.

## First usable release

Company brand kit and curated master layouts; brief/source/outline wizard; editable text, native charts and tables; notes and citations; PPTX export; actual-file render and review; immutable revisions; manually requested weekly drafts. Recurring draft preparation follows after scheduling, worker recovery and source freshness gates pass.

The schemas are draft contracts for engineering review. JSON Schema handles shape constraints; referential integrity, brand rights, geometry, source validity, resource limits, workspace authorization and weekly idempotency also require semantic validation. A validated fixture is not proof that a production renderer or scheduler exists.
