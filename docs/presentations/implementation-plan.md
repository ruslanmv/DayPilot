# Implementation plan and feasibility (P00 spike result)

This turns the design in this folder into a build sequence for DayPilot, starting with a feasibility spike run on 2026-10-02 in a Linux worker (4 vCPU, no GPU).

## Feasibility: what the spike proved

| Question | Result | Evidence |
|---|---|---|
| Can JavaScript produce a native, editable PPTX with brand colours, fonts, a layout with footer and slide number, a native chart, a native table, editable shapes/connectors and speaker notes? | **Yes.** PptxGenJS 4.0.1 (MIT), pinned | 4-slide spike deck: chart is a real chart part with its series, table is a real table, flow boxes are shapes with text, notes are notes slides |
| Can the server render the actual exported file to PDF and slide images? | **Yes, after adding `libreoffice-impress`.** The base image had only `libreoffice-core`, which cannot load any document ("source file could not be loaded") | 4 slides to PDF in 2.7 s with an isolated user profile; `pdftoppm` gives per-slide PNGs ([render](assets/p00-spike-render.png)) |
| Are text-fit checks trustworthy? | **Only for metric-compatible fonts.** Without them LibreOffice substitutes DejaVu and widths differ. Installing `fonts-crosextra-carlito` (Calibri), `fonts-crosextra-caladea` (Cambria) and Liberation (Arial, Times New Roman, Courier New) makes the render match Office's metrics | `fc-match Calibri` → Carlito after install |
| Is the server able to run Node? | Yes: Node 22 is already required by the web build | |
| Licensing | PptxGenJS MIT, JSZip MIT/GPLv3 dual (MIT used), LibreOffice MPL, fonts OFL/Apache | |

Constraints confirmed: LibreOffice is an operational renderer, not proof of PowerPoint fidelity (the design already says so); a company font that is not installed must be reported, not silently substituted; importing an arbitrary existing `.pptx/.potx` with full fidelity is not attempted in R1 (design P11 needs its own spike).

**Worker requirements:** `node` 22, `libreoffice-impress`, `poppler-utils`, `fonts-liberation`, `fonts-crosextra-carlito`, `fonts-crosextra-caladea`. Missing pieces are detected at runtime and reported as a capability gap; the deck still exports, but it is never labelled "checked".

## What gets built now (R1 vertical slice, additive, flag-gated)

| Step | Delivers (design batch) | Gate |
|---|---|---|
| E1 Engine | `packages/presentation-engine`: DeckSpec/BrandKit/Template validation compatible with the draft schemas, a **composer** (storyline → positioned DeckSpec using curated layouts), the **compiler** (DeckSpec → native PPTX: layouts, theme colours and fonts written into the theme, sections, notes, stable object names), real font-metric text fitting, OOXML self-check (P01, P03) | The PR 19 fixture deck compiles; every native object present; no text below role minimums; deterministic semantic output |
| E2 Render and quality | Isolated render (PDF + PNG + contact sheet), per-slide checks: geometry/safe area/overlap, text fit, contrast, brand fonts/logo ratio, chart data equals the fact ledger, slide count, blank-render detection; a quality receipt bound to the PPTX hash (P04 part, P07) | Hard failures block "review ready"; receipt invalid after any edit |
| E3 Service | Companies, immutable brand-kit versions with logo assets (hash, type by bytes, size limits), curated templates, decks with CAS revisions and slide locks, runs with lease epoch fencing, artifacts with hashes, weekly series with idempotent occurrences per period, all workspace-scoped (P02, P04, P08, P09) | Cross-workspace/company denial tests; stale runs cannot publish; one occurrence per period |
| E4 AI | Storyline from a brief and sources through the workspace's own connected model (credits apply), strict JSON, never executable code; regenerate selected slides honouring locks (P06 part, P08) | Model output validated like any user input; no provider = deterministic outline from the sources |
| E5 UI | `#/presentations`: library, brand kit setup (colours, fonts, logo), wizard (purpose → sources incl. dmind map → brand → editable outline → generate), review with the actual rendered slides, notes, findings, revisions, downloads; weekly series "Prepare this week" (P06, P07 UI, P09) | Feature flag off by default; existing routes unchanged; E2E |
| E6 Evidence | Unit/integration/E2E tests, rendered sample decks for two fictional companies, docs and README | Every slide of the samples inspected visually |

Deferred, as the design requires: recurring schedules (P10, preview only), existing-template fidelity import (P11), external delivery (P12), Matrix proposals and MCP tools (P13), expert JavaScript sandbox (P14), the blind benchmark against other tools (P15). No claim of being better than any named product is made before that benchmark exists.

## Delivery status (branch `claude/presentations`)

| Step | Status | Evidence |
|---|---|---|
| E1 Engine | Done | `packages/presentation-engine`: 14 curated slide types, brand theme written into the file, real-font-metric fitting (Liberation/Carlito/Caladea widths), sections, notes, stable object names, alt text on charts/tables/diagrams. 13 engine checks; the PR 19 fixture deck compiles unchanged |
| E2 Render and quality | Done | LibreOffice → PDF → 1600-px PNGs in a private profile; blank-page and page-count checks; scene-graph checks for overflow, minimum sizes, contrast, overlap, off-slide, logo distortion, native objects, theme colours, fonts, footer, macros/external links, evidence; receipt bound to the PPTX SHA-256 |
| E3 Service | Done | Migration 0028 (9 additive tables); companies, immutable brand-kit versions with CAS activation, byte-checked logo uploads, decks with CAS revisions, slide locks, restore-as-new-revision, approval bound to the file hash, lease-epoch-fenced runs (a stale worker cannot publish), content-addressed artifacts, weekly series with one occurrence per period |
| E4 AI | Done | Storyline and per-slide rewrites on the workspace's own connected model; strict JSON, one bounded repair round, engine validation, numbers not present in the sources removed and reported; AI credits charged (3 per outline, 1 per slide); offline falls back to genre templates; dmind maps imported read-only as diagram slides |
| E5 UI | Done | `#/presentations` (feature-flagged nav entry after Diagrams): brand setup with preview, 4-step wizard, outline editor without JSON, review of the actual rendered slides with checks and notes, locks, AI rewrite, revisions, approval, PPTX/PDF download, weekly series |
| E6 Evidence | Done | Python: 20 presentation tests (+ migration test); browser E2E 11/11 including axe (no serious/critical); rendered sample decks inspected slide by slide (defects found and fixed: logo on dark cover, uneven KPI tiles, oversized panels, muted text contrast, motif over the logo) |

Visual QA of the actual renders drove these fixes; the gate now also catches unreadable muted colours and stretched logos automatically.

### Extensions (S1–S6)

| Step | Status | Evidence |
|---|---|---|
| S1 SVG logos | Done | `presentations/svg.py`: strict parser (no DOCTYPE/entities/processing instructions), allow-listed elements and attributes, only internal `#id` references, CSS filtered, size/depth/proportion limits; the cleaned SVG is kept and a 1200-px PNG (LibreOffice Draw) is what decks use. 29 tests including script, event handlers, foreignObject, external/`data:`/`javascript:` links, CSS `url()`/escapes, animation, XXE and billion-laughs |
| S2 Automatic weekly drafts | Done | Opt-in per series (`PUT /series/{id}/schedule`) and per server (`DAYPILOT_PRESENTATIONS_SCHEDULER=true`). Local day and time in the series time zone; a time skipped by a clock change runs at the first valid instant, a repeated time runs once; CAS claim on `next_run_at` so two workers never fire twice; catch-up window; one occurrence per period; notification on each draft. Drafts only — nothing is sent |
| S3 MCP | Done | `POST /v1/presentations/mcp` (Streamable HTTP, JSON-RPC 2.0, Origin check): nine workspace-scoped tools (list_brands, list_decks, get_deck, propose_outline, create_deck, revise_deck, regenerate_slides, prepare_weekly, export_deck). No tool approves, sends or deletes. Registered in `packages/mcp-contracts` and the MCP host |
| S4 Template import | Done | `.pptx/.potx` read with zip-bomb, part-count and XML-safety limits; the original is stored byte for byte; theme colours, fonts, slide size, footer and logo candidates extracted; a fidelity report says what is used and what is not reproduced (layout geometry, background pictures, SmartArt, media, embedded objects); rendered previews; “create brand from template” including its logo and non-16:9 sizes |
| S5 Expert sandbox | Done | Opt-in (`DAYPILOT_PRESENTATIONS_EXPERT=true`). A JavaScript builder writes slides with the PptxGenJS API on the branded masters. Runs as `nobody` with no-new-privs, in a fresh user + network namespace, under Node's permission model (read: engine and its input only; write: one output folder; no child processes/workers/addons), with CPU/process/file/size limits, a 60-s timeout and an empty environment. Then rendered and checked (off-slide geometry, brand fonts, palette, notes, empty slides, macros). Tests prove reading `/etc/passwd`, spawning processes, network access, writing outside and environment leaks all fail with the pre-check bypassed |
| S6 UI and evidence | Done | Template import with report, previews and logo choice; SVG logo upload; schedule editor with policy and next runs; expert builder panel with refusal reasons. Browser E2E 15/15 (axe clean) |

Still open: external sharing/delivery (P12) and the blind benchmark (P15). Rendering is LibreOffice-based; PowerPoint for Windows/Mac acceptance and a screen-reader review are still required before a release claim.
