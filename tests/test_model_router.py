from daypilot_models.router import generate, route_model


def test_model_router_uses_mock_backend_by_default(monkeypatch):
    monkeypatch.setenv("DAYPILOT_MODEL_BACKEND", "mock")
    route = route_model("briefing")
    assert route["backend"] == "mock"
    result = generate("Summarize today", "briefing")
    assert result["backend"] == "mock"
    assert "mock response" in result["text"]
