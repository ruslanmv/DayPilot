"""Guard against drift between Python API contracts and the TS shared-types.

Until the TS types are generated from the OpenAPI schema, this test keeps the
two hand-written sources of truth aligned for the pieces most likely to skew:
the Today Context event types and the pagination envelope.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED_TYPES = ROOT / "packages" / "shared-types" / "src" / "index.ts"


def _shared_types_source() -> str:
    return SHARED_TYPES.read_text(encoding="utf-8")


def test_event_types_match_python_source_of_truth():
    from app.events import EVENT_TYPES

    source = _shared_types_source()
    match = re.search(r"DayPilotEventType\s*=\s*([^\n]*(?:\n\s*\|[^\n]*)*)", source)
    assert match, "DayPilotEventType union not found in shared-types"
    ts_literals = set(re.findall(r"'([a-z_.]+)'", match.group(1)))
    assert ts_literals == set(EVENT_TYPES), (
        f"Event type drift: TS={sorted(ts_literals)} Python={sorted(EVENT_TYPES)}"
    )


def test_page_envelope_fields_present():
    source = _shared_types_source()
    # The Page<T> envelope must match the keys page_response() emits.
    assert "export type Page<T>" in source
    for field in ("items", "nextCursor", "hasMore", "limit"):
        assert field in source


def test_today_context_contract_present():
    source = _shared_types_source()
    assert "DayPilotTodayContext" in source
    for count_key in ("aiRunning", "approvals", "blockers", "projectsActive", "projectsNeedAttention"):
        assert count_key in source
