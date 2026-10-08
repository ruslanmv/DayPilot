# Draft input contracts

These schemas use JSON Schema Draft 2020-12. The `$id` URLs are logical identifiers under a reserved `.example` domain; no hosted schema service exists. `schema_version` governs future incompatible changes. Do not generate server migrations directly from these draft schemas.

| Schema | Purpose |
| --- | --- |
| [brand-kit.schema.json](brand-kit.schema.json) | Pinned company palette, typography, original-logo references, slide dimensions and chart/footer policy |
| [template.schema.json](template.schema.json) | Kit-bound layouts, placeholder geometry and explicit import fidelity status |
| [deck-spec.schema.json](deck-spec.schema.json) | Structured content, source snapshots/metrics, native elements, claims, locks, notes and slide count |
| [weekly-series.schema.json](weekly-series.schema.json) | Pinned recipe, source scope, calendar/timezone/cutoff policy and opt-in draft schedule |
| [generation-manifest.schema.json](generation-manifest.schema.json) | Reproducibility metadata and output/quality bindings |

Coordinates are normalized to the parent: slide elements/layout placeholders to the slide; diagram nodes to the diagram box. A bounds object requires `x + w ≤ 1` and `y + h ≤ 1` through semantic validation. Stable IDs survive content edits; cloning creates new IDs when object identity changes.

Dates include timezone offsets; periods are start-inclusive/end-exclusive. Weekday numbers follow ISO/Python convention here: Monday `0` through Sunday `6`. The API computes reporting periods server-side from IANA timezones; a client cannot bypass freshness checks by writing a period field.

In this draft fixture package, a reference digest is SHA-256 of UTF-8 JSON encoded with sorted object keys, separators `(',', ':')`, Python's default ASCII escaping and no non-finite numbers. The validator uses that exact encoder. Before production, adopt a single cross-language canonicalization algorithm (for example RFC 8785 with an audited implementation), update the contract/digest vectors, and verify TypeScript/Python parity. Never compare arbitrary pretty-printed file bytes to this logical digest. This draft encoder is not claimed to be RFC 8785.

JSON Schema validates shape, not authorization or quality. Additional production checks must cover IDs/references, bounds, text/font metrics, unit conversions/transformations, typed tables, asset bytes/rights, template capabilities, source grants/freshness, worker budgets, locks, exact artifact approval and schedule uniqueness. `workspace_id`/`company_id` are server-verified identities. The manifest is an audit output; submitting it never creates an approval or quality receipt. Native reading order/alt text/Office accessibility checks require adapter implementation beyond this data shape.

All examples set `fixture_only: true`. This flag marks fictional examples and must be rejected by production generation unless a dedicated demo mode is selected. It does not grant access or activate templates. `validate_contracts.py` intentionally requires fixture flags and disabled schedules; it is an example-package validator, not a universal validator for real decks.
