# dmind AI parity plan: what a thinking tool needs, simply

Goal: cover what people use an AI mind-mapping product for (prompt/file/link/image/voice in, an editable map, AI as co-editor, then action and sharing) while keeping dmind's strengths: an open `.dmind` format, offline-first, every AI change shown as a reviewable diff, untrusted-input handling, and a hand-off into DayPilot tasks and coding agents. Statuses below are for this branch.

## UX principles (what "simple" means here)

1. **One box to begin.** "What do you want to map?" accepts a sentence, pasted text, a link, a file, or a dictated note. Everything else is optional and appears after.
2. **Always a preview, never a surprise.** Nothing replaces the map until the person presses a button; every AI change is a list of differences with Apply and Discard, and Undo still works afterwards.
3. **Works without AI.** Templates, brainstorming modes, outline import, layouts, task breakdown from the map's own structure and the Gantt view need no provider. AI actions say plainly when no provider is connected and how to connect one.
4. **Act where you are.** Right-click or press `/` on a topic for Grow, Explain, Refine; the chat panel handles everything else.
5. **Small vocabulary.** Topic, map, preview, apply. No modes to learn.

## Capability map

| Need (as people describe it) | dmind now | This plan | Notes |
|---|---|---|---|
| Prompt, text, outline to map | Wizard (B0) | **C3** one-box start | offline outline parser or AI when connected |
| File, webpage, PDF, image to map | B3 extractors, OCR hook | kept; start box accepts them | YouTube transcripts are not fetched (no transcript source); paste the transcript |
| Chat to create/edit/refine a map | none | **C1 + C2** | chat returns reviewable patches |
| Brainstorming ideas, several modes | none | **C3** | SCAMPER, 5 Whys, pros/cons, six hats, questions, risks; deterministic scaffold, AI optional |
| Templates | none | **C3** | built-in gallery, no network |
| Image to map | OCR hook + outline | kept | |
| Voice to map | none | **C3** | browser speech recognition; audio never leaves the browser through DayPilot |
| Grow, explain, reorganize, refine (rewrite, translate, merge, expand, polish) | none | **C1 + C2** | per-topic actions, patch review |
| AI to-do, work breakdown | none | **C4** | tasks from the map structure; AI improves wording |
| Gantt planning | none | **C4** | start/duration per topic, dependencies from links, SVG chart |
| Push tasks to a task list | none | **C4** | creates DayPilot tasks after confirmation |
| Present | none | **C5** | step-through presentation of branches |
| Pitch video, image/sticker generation, background removal | none | **not built** | need image/video models and pipelines; out of scope, stated rather than faked |
| Use from AI tools (plugin, MCP, CLI/skills) | Matrix HTTP/MCP/CLI, `.dmind` bundles | **C6** | documented tool surface and a local validate/convert CLI |
| Open other formats | OPML/XMind import (B10) | kept | |
| Share and team | B7 read-only links | kept | |

## Batches

| Batch | Delivers | Gate |
|---|---|---|
| **C1 AI assist service** | `/v1/diagrams/assist`: generate, chat, grow, explain, reorganize, refine; strict patch parsing, bounded prompts, offline answers | model output can only become a valid, bounded patch; hostile map text cannot change the instructions; no provider yields a clear offline reply |
| **C2 AI in the editor** | chat panel, topic action menu, review-and-apply | apply only against the shown state; undo restores |
| **C3 Start simply** | one-box start, templates, brainstorm modes, voice | works with no provider; a template becomes a valid map |
| **C4 Tasks and Gantt** | task fields, breakdown, Gantt, push to tasks | dates validated; dependencies without cycles; confirm before creating tasks |
| **C5 Present** | full-screen walk-through | keyboard only, no network |
| **C6 Agent tools** | documented tool surface, CLI | validate/convert round-trip |

## Honest boundaries

AI quality depends on the connected provider; the service validates and bounds what comes back but cannot make a weak model insightful. Speech recognition depends on the browser. Features that require generating images or video are not attempted.
