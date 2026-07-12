"""Phase 5 — private integration platform (batch I9/I10).

Proves the completion criteria: an integration can be built outside the core
(via manifest + SDK contract), installed through a manifest, tested and
classified by DayPilot's conformance suite, and curated by tier — all without
changing the core application.
"""
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from daypilot_orchestrator.integrations import sdk
from daypilot_orchestrator.integrations.certification import run_conformance
from daypilot_orchestrator.integrations.manifest import list_catalog, register_manifest, validate_manifest
from daypilot_orchestrator.integrations.provider import (
    AuthType,
    Capability,
    CapabilityKind,
    ConnectionStatus,
    IntegrationError,
    IntegrationHealth,
)

client = TestClient(app)

GOOD_MANIFEST = {
    "id": "acme-widgets", "name": "Acme Widgets", "version": "1.2.0",
    "publisher": "Acme Corp", "transport": "streamable-http",
    "capabilities": ["widget.read", "widget.update"], "events": ["widget.updated"], "risk": "medium",
}


class GoodProbe:
    """A well-behaved out-of-core integration built against the SDK contract."""
    provider = "acme-widgets"
    auth_type = AuthType.API_KEY

    def __init__(self) -> None:
        self._connected = False

    def connect(self, credentials: dict[str, Any]) -> None:
        if not credentials.get("token"):
            raise IntegrationError("missing token")
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def list_capabilities(self) -> list[Capability]:
        return [
            Capability("widget.read", CapabilityKind.READ, "Read widgets."),
            Capability("widget.update", CapabilityKind.WRITE, "Update a widget."),
        ]

    def execute(self, action: str, payload: Any) -> Any:
        return {"ok": True}

    def get_health(self) -> IntegrationHealth:
        # Never echoes the credential into detail.
        return IntegrationHealth(ConnectionStatus.CONNECTED, "ok")


class LeakyProbe(GoodProbe):
    """A non-conformant integration that leaks the credential into health."""
    def get_health(self) -> IntegrationHealth:
        return IntegrationHealth(ConnectionStatus.CONNECTED, "connected with token CANARY-SECRET-TOKEN-abc123")


def test_manifest_validation():
    assert validate_manifest(GOOD_MANIFEST) == (True, [])
    bad = {**GOOD_MANIFEST, "version": "1.2", "transport": "carrier-pigeon", "capabilities": []}
    ok, errors = validate_manifest(bad)
    assert ok is False
    assert any("semver" in e for e in errors)
    assert any("transport" in e for e in errors)
    assert any("capabilities" in e for e in errors)


def test_curated_catalog_has_tiers():
    catalog = list_catalog()
    tiers = {e["tier"] for e in catalog}
    assert {"verified", "certified", "private"} <= tiers
    verified = {e["id"] for e in list_catalog("verified")}
    assert {"slack", "github", "google-calendar"} <= verified


def test_conformance_passes_for_a_good_integration():
    report = run_conformance(GOOD_MANIFEST, GoodProbe())
    assert report["passed"] is True
    names = {c["name"] for c in report["checks"]}
    assert {"manifest_valid", "capabilities_classified", "auth_works",
            "disconnect_works", "no_credential_leak"} <= names


def test_conformance_fails_on_credential_leak():
    report = run_conformance(GOOD_MANIFEST, LeakyProbe())
    assert report["passed"] is False
    leak = next(c for c in report["checks"] if c["name"] == "no_credential_leak")
    assert leak["ok"] is False


def test_conformance_fails_on_manifest_mismatch():
    mismatch = {**GOOD_MANIFEST, "capabilities": ["widget.read", "widget.delete"]}  # delete not exposed
    report = run_conformance(mismatch, GoodProbe())
    match = next(c for c in report["checks"] if c["name"] == "capabilities_match_manifest")
    assert match["ok"] is False


def test_install_lifecycle_via_api():
    # Install a new manifest — starts experimental, not certified.
    r = client.post("/v1/catalog/install", json={"manifest": GOOD_MANIFEST, "tier": "experimental"})
    assert r.status_code == 201, r.text
    assert r.json()["certified"] is False
    # It appears in the catalog.
    listed = client.get("/v1/catalog").json()["catalog"]
    assert any(e["id"] == "acme-widgets" for e in listed)
    # A malformed manifest is rejected.
    bad = client.post("/v1/catalog/install", json={"manifest": {"id": "x"}})
    assert bad.status_code == 400


def test_certify_registered_provider():
    # The built-in `reference` provider certifies against its manifest.
    register_manifest({
        "id": "reference", "name": "Reference", "version": "1.0.0", "publisher": "DayPilot",
        "transport": "native", "capabilities": ["echo.read", "echo.write"],
        "events": [], "risk": "low",
    }, tier="experimental")
    r = client.post("/v1/catalog/reference/certify")
    assert r.status_code == 200, r.text
    assert r.json()["certified"] is True


def test_sdk_surface_is_importable():
    # An out-of-core builder imports everything they need from one module.
    for name in ("IntegrationProvider", "IntegrationManifest", "Capability",
                 "CapabilityKind", "run_conformance", "validate_manifest"):
        assert hasattr(sdk, name)
