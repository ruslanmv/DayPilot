from daypilot_observability.traces import record_trace


def test_record_trace_returns_envelope():
    result = record_trace({"service": "test", "event_type": "unit", "payload": {"ok": True}})
    assert result["status"] == "recorded"
    assert result["event"]["service"] == "test"
