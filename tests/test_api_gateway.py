from fastapi.testclient import TestClient

from app.main import app


def test_api_gateway_health_includes_service_map():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "orchestrator" in payload["services"]
