# Quality standard and evaluation

Quality means a useful story, correct evidence, faithful branding, readable composition and editable outputs. Attractive imagery cannot compensate for wrong facts or clipped labels. All numeric thresholds below are proposed product targets to calibrate on real company samples; they are not certifications or measured current performance.

## Editorial rules

Every slide has a purpose, an audience-relevant title, a justified visual and an expected takeaway/action. Weekly reports distinguish observation, comparison, risk and recommendation. Avoid invented statistics, filler sections, decorative charts and ungrounded confident headlines. Speaker notes explain the evidence and give the presenter a useful narrative without repeating every visible word.

Outline review checks requested scope, duration, exact/range count including cover/appendix, source coverage and narrative pacing. A title asserting a result needs a mapped claim in the fact ledger. A conceptual recommendation uses a clear recommendation/assumption label. The compiler cannot invent a value to satisfy layout density.

## Visual composition

Company rules and existing-template fidelity take precedence over generic defaults. For new 16:9 templates, start with these guidelines and validate projected readability:

| Property | Starting standard | Validation |
| --- | --- | --- |
| Slide size | 13.333 × 7.5 inches; other sizes remain supported and pinned | Exact kit/template/spec agreement |
| Safe area | 0.5-inch content margin; approved full-bleed assets/backgrounds exempt | Normalized bounding boxes and layout-specific exclusions |
| Typography | Deck title ~42 pt, slide title ≥32 pt, body ≥18 pt, data labels normally ≥16 pt, footnotes ≥12 pt | Brand/font policy, rendered legibility; no automatic shrink below a role minimum |
| Text density | Layout-defined line/word budget; concise claim-oriented copy | Shorten/split with content approval; never drop evidence silently |
| Alignment | Shared anchors and consistent gutter rhythm | Geometry against layout anchors; permitted optical correction |
| Contrast | Target WCAG AA-like text contrast: 4.5:1 ordinary text, 3:1 large text | Palette checks plus rendered backgrounds; Office review remains required |
| Logos | Original proportions, approved variant/clear space/minimum size | Asset digest and ratio; no AI reconstruction |
| Charts | Native, labeled units/period/series, meaningful axes; no decorative 3D | Data ledger equality, tick/label visibility and appropriate baseline |
| Tables | Native cells with concise headers, readable row spacing | Header semantics and text fit; overflow requires explicit split |
| Diagrams | Native labeled nodes/connectors with readable direction and grouping | Node/edge provenance, no disconnected or hidden semantics |
| Images | Rights/provenance, deliberate crop, sufficient effective resolution | Avoid unintended stretching, cut-off focal subjects or pixelation |

Use varied layouts: editorial title/evidence, large chart, concise table, image-led explanation, process/architecture diagram, decision comparison and summary. Let the evidence determine the visual. Brand consistency does not require every slide to be a card grid. Limit palette and decoration; preserve whitespace.

Bounding boxes live in normalized slide coordinates; compute physical sizes and font metrics in the compiler. Geometry checks reject off-slide content and incidental overlap. Backgrounds, image overlays and containing groups declare permitted overlap explicitly. Text fit uses the actual font metrics, line breaks and role constraints. Diagrams include connector routes and label boxes, not merely node positions.

## Evidence, numerical correctness and freshness

Maintain a fact ledger for quantitative claims: source snapshot ID/hash, exact locator, metric ID, unit, definition, period, numerator/denominator and permitted transformation. Charts/tables/visible assertions link to ledger entries. Check exported native data against the ledger, including percentages, totals, rounding and date labels. Source snapshots are immutable; evidence review does not execute a fresh query that changes the numbers under a rendered slide.

Computed changes require comparable definitions and periods. When denominators are zero/missing, display an explicit unavailable comparison rather than an invented growth rate. Dates/timezones and currency conversions must be stated. Contradictory sources require review. Missing data remains missing. A model/vision score cannot prove factual accuracy; use deterministic validations and source inspection.

Notes carry relevant citations and reporting cutoff with locators the authorized presenter can resolve. Redact restricted source details for a different audience via an explicit derivative revision and re-review. A source-permission check and outbound audience check are separate obligations.

## Actual-file review and repair

1. Export native PPTX and record its digest. Inspect OOXML structure/object types, notes, chart series and required editable objects.
2. Render that PPTX using the pinned renderer/fonts into PDF, slide PNGs and a contact sheet. For a new 16:9 kit, target at least 1600 × 900 pixels for slide inspection. Other ratios preserve their dimensions. High-resolution exports can be generated separately.
3. Run geometry/text/evidence/brand checks. Compare expected element coverage against rendered output using bounded image/OCR checks where useful. OCR absence is a finding, not a reason to erase source content.
4. Inspect **every** slide, including title, footers, notes/source panels, charts and diagrams. Review the contact sheet for story pacing, consistency and visual monotony. Automated visual models may propose findings; manual review remains part of company-template activation and release acceptance.
5. Produce a repair patch against the exact candidate revision. Allow up to three automatic repair cycles within a cost/time budget. Preserve locked objects and semantic facts. Each changed export must be rendered and checked again.
6. If hard failures remain, return an actionable failed candidate with its prior revision available. If checks pass, mark review-ready and attach a quality receipt. User approval binds that receipt and artifact. Changed bytes, fonts, template or content invalidate the binding.

No claim of visual approval may be based only on the JavaScript source, an HTML preview, a single thumbnail or a previous revision's render. Visual inspection proof records who/which checker reviewed each slide, renderer and output hashes, versions and findings. Automated slide review is not equivalent to a human attestation.

## Findings and release gates

| Severity | Examples | Behavior |
| --- | --- | --- |
| Hard failure | Missing/unverified quantitative evidence; incorrect arithmetic; required native object rasterized; clipping/hiding essential text; missing logo/unauthorized font; cross-company content; unsupported original-template promise; corrupt PPTX | Block verified review/distribution; corrective revision required |
| Reviewer decision | Explicit source conflict; intentional dense regulated table; acknowledged nonessential visual overlap; approved historical metric with clear label | Designated reviewer may accept a narrowly scoped, recorded override; never rewrite evidence |
| Warning | Minor spacing inconsistency, optional decorative crop, long notes, redundant section phrasing | Visible improvement suggestion; track recurrence |
| Operational failure | Unavailable renderer/provider, revoked source, expired lease, budget exhaustion | Stop candidate run; do not mark ready or replace existing approved output |

A receipt summarizes required checks and slide coverage; it does not collapse factual correctness into a single beauty score. All hard gates must pass independently. Share/review approval cannot be forged by editing a client-provided JSON document.

## Accessibility and compatibility

Use unique descriptive slide titles, a logical object reading order, alt text for meaningful images/charts, table headers, readable type and adequate contrast. Convey status through text/shapes as well as color. Decorative objects should not interrupt reading order. Provide a readable text/notes alternative in the DayPilot review UI. Validate keyboard and screen-reader operation there separately from exported-file accessibility.

Automated OOXML checks cover supported structural properties; release QA also uses PowerPoint Accessibility Checker and representative screen-reader review. Verify that the chosen adapter can emit every required property before promising it. Native chart data alone does not guarantee accessible interpretation: include a concise description or a data table where appropriate.

| Consumer | Acceptance scope |
| --- | --- |
| PowerPoint Windows | Open without repair; edit text/chart/table/diagram; notes, fonts, reading order and save round-trip |
| PowerPoint Mac | Same representative corpus; font substitution and chart differences recorded |
| PowerPoint Web | Import/open/edit and rendering smoke checks; unsupported feature disclosure |
| LibreOffice | Deterministic operational render and basic edit checks; not a substitute for PowerPoint fidelity testing |
| PDF viewer | Export readability, pagination, links and selectable text where supported; no editability claim |
| Google Slides/Keynote | Optional compatibility tier after explicit import tests; not required for first-release fidelity promise |

Keep a versioned regression corpus covering long text, multilingual/RTL/CJK glyphs, transparent logos, custom aspect ratios, tables, sparse/missing chart data, diagrams and existing-template edge cases. Record consumer versions/date; do not imply identical pixels across all office applications.

## Competitive benchmark

The objective is to outperform alternatives in measurable user outcomes. “Better than Manus” becomes a hypothesis evaluated on a common, authorized corpus; no superiority claim ships before results exist.

Use at least 30 briefs across weekly reporting, executive decisions, client proposals, technical architecture and training. Include three distinct fictional/authorized company kits, low/high content density, multilingual samples, real permitted template edge cases and both complete/missing-data sources. Reserve a held-out set. Give each tool the same source material, branding, slide count, time/budget and user interactions. Record tool/version/date and any manual assistance. Do not invent competitor scores or upload company-confidential material without authorization.

Randomize deck order and hide tool names. At least three reviewers score independently; include a presentation designer, business presenter and data/technical reviewer. Counterbalance presentation order, record disagreements and use confidence intervals. First apply hard correctness/editability gates; then compare these dimensions:

| Dimension | Proposed weight | Evidence |
| --- | --- | --- |
| Narrative usefulness | 20% | Decision clarity, audience relevance, pacing |
| Visual readability | 20% | Layout, projected legibility, hierarchy, whitespace |
| Brand fidelity | 15% | Company rules, original logos, template match |
| Evidence integrity | 20% | Claims, numerical checks, sources, freshness |
| Editable usefulness | 15% | Timed text/chart/table/diagram edits and save round-trip |
| Accessibility | 10% | Structural checks and human/Office review |

Provisional release targets: no critical factual/brand/privacy failures; required native objects 100% editable in acceptance samples; mean human score ≥4.5/5; median correction time ≤5 minutes for a routine 8–12-slide weekly draft. A superiority claim requires statistically supported improvement on the agreed weighted score without reduced correctness, plus lower correction effort at comparable cost. If the baseline already meets a ceiling, report parity and the workflow improvement. Publish corpus/limitations and measured results, not a slogan.

Instrument real weekly usage with opt-in, privacy-preserving counts: first-draft acceptance, minutes to approve, edits by type, retained locks, brand exceptions, freshness gaps and weekly repeat usage. Revisit thresholds based on observed deck complexity. Do not train on company inputs without a separate policy and authorization.
