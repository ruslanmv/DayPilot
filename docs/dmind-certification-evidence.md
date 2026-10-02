# dmind certification evidence (batch B9)

Recorded on branch `claude/dmind-batches`; a sandbox (4 vCPU, no GPU, headless Chromium), so figures are indicative.

| Gate | Result |
|---|---|
| DayPilot Python suite (whole repo) | 879 passed |
| DayPilot `ruff check .` | clean |
| `tests/ui/dmind-modules.mjs` | 443 checks passed (zip, bundle, archive corpus, patches, handoff, OPML/XMind import) |
| `tests/ui/dmind.mjs` | 135 checks incl. shared contract corpus |
| Type check (`ui-bridge`, `tsc --noEmit`) | clean |
| Browser E2E (`make dmind-e2e`, incl. axe: no serious/critical violations in the editor; phone width without horizontal scroll) | 32/32 passed |
| Matrix Designer pytest | 277 passed + B8 handoff (44) ; `ruff check` clean |
| Migrations on PostgreSQL 16 | upgrade to head `0026_dmind_shares`; downgrade to 0025 and to 0023 and back both succeed |
| dmind API suites against PostgreSQL 16 (diagrams, workspace, sharing, concurrency) | 43 passed |
| Cross-repo parity | schema, fixture, contract, archive, patch and handoff corpora pinned by digest in both repositories; TS and Python writers byte-identical for bundles |

Rollback: every migration (0024-0026) is additive and its downgrade restores the exact prior schema (tested on SQLite and PostgreSQL). Features that expose data are off by default (`DAYPILOT_DMIND_URL_FETCH`, `DAYPILOT_DMIND_SHARING`).

Known gaps, stated plainly: the 45 fps pan/zoom target at 1000 topics is not certified (open 175 ms, edit p95 45 ms, drag about 28 ms per move); no manual screen-reader review and only Chromium was exercised, so WCAG 2.2 AA and cross-browser claims are not made; the public share endpoint has no built-in rate limit; B5 server-side asset storage, B7 per-diagram ACLs/comments/management UI and the B8 editor panel are not built; `tests/ui/smoke.mjs` needs `playwright-core`, which is not installed here.
