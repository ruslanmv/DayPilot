# Product experience and brand system

## Intent and boundaries

Presentations should feel like a guided design studio inside DayPilot: a short path to an understandable, visually polished deck with editable evidence. The tool serves recurring company updates, client reporting, sales proposals, technical design reviews and leadership decisions. The first release prioritizes weekly reports and executive updates; the layout system supports other genres without forcing the same structure on every deck.

Add a feature-flagged **Presentations** navigation entry and `#/presentations` route to desktop/mobile shells. Preserve existing navigation order and shortcut identities. The feature owns its library, creation flow and review surface. Brand management is available from its Templates view and a link in company settings. Rendering, extraction and model calls run as jobs so they cannot freeze the shell.

No existing project, task, diagram, document or source file changes as a side effect of deck generation. Linking an exported deck to a project adds a reference. Creating a task from a slide is a separate existing-workflow action. Downloading is permitted to authorized users; public sharing and outbound sending use distinct authorization.

## Main surfaces

| Surface | Contents | Primary actions |
| --- | --- | --- |
| Library | Drafts, review-ready decks, approved revisions, company/project, reporting period, recent jobs | Create, open, duplicate, archive, search, filter |
| Creation wizard | Brief, sources, brand/template, narrative outline | Select, inspect, propose outline, approve structure, generate |
| Deck review/editor | Filmstrip, actual PPTX slide preview, content/notes panel, source links, quality findings, revision history | Edit, reorder, lock, regenerate selected slides, compare, approve revision |
| Templates and brand kits | Company spaces, immutable brand versions, template previews, import fidelity reports | Upload originals, create draft kit, map layouts, review, activate version |
| Weekly series | Company, template/version, source scope, reporting window, cadence, owner, run history | Prepare this week, compare to last week, configure/pause recurrence |

Mobile supports wizard entry, review/notes, approvals and exports. Desktop adds detailed layout adjustments and template administration. Presentations on a phone retain the slide's aspect ratio and offer a readable text/notes view; they do not pretend a compressed canvas is an ideal editing surface.

## One-time company setup

1. Create a company profile inside the current workspace, or choose an existing profile. Company is a brand namespace; it is not a new authentication tenant.
2. Upload original logos and brand guidelines. Accept PNG/JPEG and sanitized SVG; retain originals and separate approved render variants. Specify logo variants for light/dark backgrounds, minimum size, clear space and preferred placement. Never redraw or recolor a real logo with generative AI.
3. Select brand colors, typography and font assets where rights permit. Check installed fonts, glyph coverage, approved substitutes, output licensing and contrast. A missing corporate font is an actionable issue, not an invisible substitution.
4. Upload a `.pptx` or `.potx` template, or choose an approved DayPilot layout collection and apply the brand. Offer two clearly named paths: **Match this existing template** and **Create a new template from these brand rules**.
5. Render every relevant source layout and inspect masters, placeholders, size, theme, required footers, image crops and chart styles. Preserve supplied aspect ratio. Map content roles such as title, chart, table, notes and section heading to supported placeholders.
6. Show a fidelity report: supported native content, retained master parts, unsupported animation/media/SmartArt, missing fonts and any raster fallback. Complex existing templates stay unapproved until the preservation spike succeeds or a person approves an explicit normalized replacement.
7. Generate a company sample collection with short/long titles, representative charts, tables, imagery and an architecture diagram. The owner reviews it and activates an immutable kit/template version.

A company kit contains palette roles, font policies, approved logo assets, slide sizes, layout references, chart/table styles, imagery rules, footer/confidentiality requirements and permitted variations. A template adds layout geometry, editable placeholder roles, density limits, required slides, genre rules and sample thumbnails. Multiple companies can coexist without mixing assets. Workspace permissions authorize access; company-level grants refine which brand content a member may use or edit.

Updating an active template creates a new version. Existing decks remain pinned to their original version. The UI offers an explicit rebrand preview for a new deck revision, including changes to all affected slides. No global template edit rewrites historical decks.

## Creation wizard

### Step 1: Purpose

Ask for topic, audience, outcome, language, target duration and either an exact slide count or a range. Suggested genres: weekly update, executive decision, client status, proposal, strategy, technical review and training. A deck may be created from a topic alone, but facts still need sources or explicit assumption labels.

Duration helps set density and speaker notes; it does not invent a required number of slides. An exact count includes cover and appendix. If the brief cannot fit, explain the conflict and ask the person to change scope/count. Never add slides silently.

### Step 2: Sources

Choose attachments or permitted DayPilot document/project/diagrams snapshots. Text, Markdown, PDF, DOCX, existing decks and spreadsheet extracts are supported through bounded extraction adapters as each ships. Show source versions, permissions, extraction previews, dates and freshness. Include/exclude individual sources before any provider request. URLs require an enabled fetch connector; no arbitrary authenticated-site retrieval is implied.

Define the reporting period and cutoff for weekly content. Show conflicting metrics, missing definitions, old snapshots and unresolved assumptions. The user chooses whether to obtain new data, leave a visible gap or include an explicitly labeled historical value. Null/missing never becomes zero. Claimed changes between weeks require comparable definitions, units and date ranges.

### Step 3: Brand and layout

Select company and an approved template version. Defaults come from the chosen series/project, not from whichever company was used last. Show actual template thumbnails. Optional presets adapt pacing and density while keeping the brand. Overrides outside the brand rules create a separate draft variant requiring review.

No company assets are currently supplied with this design. The examples are fictional technical fixtures. Production setup requires the company's original logos, approved colors/fonts and preferred deck references.

### Step 4: Storyline

Present an editable outline containing each slide's purpose, title, evidence, visual plan and intended audience action. A proposed sequence might be context, progress, evidence, risks, decision and next period. Omit sections without relevance or evidence. Preserve user-requested ordering.

The outline identifies sources behind claims and separates observed facts from assumptions or recommendations. A slide needs a reason to exist; generic filler slides and repeated slogans should fail editorial review. The person approves this outline before spending on full visual generation.

### Step 5: Generate and review

Show progress for source preparation, outline, composition, PowerPoint export, actual-file render and quality checks. Provide an estimated cost/budget before paid model or image generation. A local deterministic renderer can compose supplied structured content without AI; the product distinguishes this from an AI-written storyline.

The review screen uses the exported PPTX render. Every slide shows notes/source details and findings when selected. The user can rewrite, switch to an approved layout, replace an image, edit native chart data, reorder slides or regenerate a selection. AI changes arrive as a proposed patch against a base revision. Changed or locked human content requires conflict resolution.

Approval records the exact deck revision, template/brand versions and quality receipt. External sharing/sending uses its own action and approval where configured. Changes after approval invalidate approval for the new revision.

## Editorial and visual behavior

- One clear purpose per slide, varied compositions, consistent alignment and ample whitespace. Weekly dashboards may use structured tables, but every slide should not resemble a web UI card grid.
- Titles name the subject or state a supported finding. A chart finding must match its values and uncertainty. Speaker notes carry explanations that would overload the slide.
- Keep original brand rules and requested density first. In new templates, prefer large readable headings and body text; shorten or split content before reducing type size. Required data must remain present, even when moved to an agreed appendix.
- Native charts for quantitative comparisons/trends; native tables for exact records; native diagrams for editable systems/flows. Use approved photos/illustrations for conceptual content. Label generated imagery where a viewer might otherwise mistake it for documentary evidence.
- Notes include relevant source references, reporting date, presenter guidance and disclosed assumptions. Separate internal QA reports from audience-facing slide copy and notes.
- Prefer a limited, deliberate visual language. Brand-approved imagery can repeat when required; decorative repetition should not create monotonous decks.

## Weekly presentations

A weekly series is a saved reporting recipe. It pins company, brand/template versions, reporting window/cutoff, stable section IDs, permitted sources, audience, owner, quality policy and optional cadence. **Prepare this week** works without a schedule. Optional recurrence must be configured by the person and defaults to preparing a draft, never sending it.

The setup chooses an IANA timezone, local day/time, source window rules, source readiness deadline and review owner. For example, a fictional Europe/Rome series can prepare a Monday 08:30 draft for the previous complete week. This design does not create that schedule for the user.

Each occurrence:

1. Resolve a stable local reporting period and capture the recipe version plus source snapshots.
2. Compare current sources with the prior occurrence. Update new metrics and work completed; preserve still-relevant narrative as a proposed carry-forward. Identify stale or incompatible data.
3. Create a new deck lineage and apply the pinned brand. Stable section IDs make week-to-week comparisons possible even when layout/count changes.
4. Preserve locked reusable sections and explicitly period-bound human edits according to their carry-forward scope. Do not copy last week's metrics as this week's facts.
5. Render and check the exported PPTX; produce a changed-slides view, evidence differences and missing-input list.
6. Notify the owner inside DayPilot that a draft is ready or blocked. Delivery outside DayPilot requires a separate recipient-bound action.

One occurrence per `(series_id, recipe_version, period_key)` is idempotent. A user-requested regeneration creates a new revision inside that occurrence rather than another occurrence. Store actual planned/fired UTC timestamps and timezone database version. For daylight-saving gaps, move forward to the first valid local time; for repeated times, use the first occurrence. Display this policy before activation. Missed runs prepare at most the latest eligible period by default, with explicit historical backfill available. Pause/resume never publishes old drafts.

Changing the template or metric definitions in a series proposes a new recipe version. It takes effect on future occurrences; in-flight/historical occurrences retain their captured recipe. Reports must show comparability changes. Source permission revocation stops future extraction and cancels unpublished artifacts derived from newly inaccessible data according to retention policy.

## Non-destructive editing and preservation

- All imported originals are immutable assets; generated decks use new object keys and distinct filenames.
- Saving appends a deck revision using expected revision/CAS. Restore creates another revision. Archive hides a lineage while retaining authorized history.
- Human edits use stable slide/element IDs. Lock content, layout or both; AI patch requests honor these locks and cannot change required template fields.
- When the user edits the downloaded file in PowerPoint, **Import edited copy** creates a new branch. Reconcile supported slide/element IDs from custom metadata and semantic diffs. Unsupported edits remain in an opaque original artifact with a fidelity report. Never claim general lossless reverse engineering of arbitrary PPTX edits.
- A failed job leaves the latest successful revision and the draft specification available. Cancelled or stale jobs cannot make themselves current, approved or shared.

## Sharing and ownership

Owners manage kit/template activation, company access and retention. Editors create/revise decks. Reviewers approve a specific revision where membership policy allows. Viewers read permitted previews/downloads; they cannot change schedules or brand assets. Server authorization binds workspace and company grants independently of browser-supplied IDs.

Sharing offers restricted links with expiry/revocation, artifact-only PPTX/PDF downloads and optional connector-backed delivery. Review a redacted/export copy when sources contain restricted information. Download rights are explicit because a copied file cannot be revoked later. Approval snapshots include deck hash, artifact hash, audience/recipients and scope; a later edit or recipient change requires a new approval.
