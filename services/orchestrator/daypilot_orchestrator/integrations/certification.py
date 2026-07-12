"""Integration conformance / certification checks (batch I10).

Before an integration can be enabled it must pass a fixed set of checks. A
"probe" is any object satisfying the IntegrationProvider contract; the checks
exercise it against a manifest without trusting either. This lets internal or
third-party teams build integrations outside the core repo and have DayPilot
test and classify them safely.
"""
from __future__ import annotations

from typing import Any

from ..security.secrets import redact
from .manifest import VALID_TRANSPORTS, validate_manifest
from .provider import CapabilityKind

# A canary secret the probe is fed; it must never surface in health/detail text.
_CANARY = "CANARY-SECRET-TOKEN-abc123"


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def run_conformance(manifest: dict[str, Any], probe: Any, credentials: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the certification suite. Returns {"passed": bool, "checks": [...]}. The
    probe is connected with a canary credential and disconnected again; failures
    are recorded, never raised."""
    checks: list[dict[str, Any]] = []
    creds = credentials or {"token": _CANARY, "bot_token": _CANARY, "access_token": _CANARY}

    ok, errors = validate_manifest(manifest)
    checks.append(_check("manifest_valid", ok, "; ".join(errors)))
    checks.append(_check("transport_supported", manifest.get("transport") in VALID_TRANSPORTS,
                         str(manifest.get("transport"))))
    checks.append(_check("scopes_documented", bool(manifest.get("capabilities")),
                         "manifest must declare capabilities"))

    # Capabilities are all classified read/write/destructive.
    try:
        caps = list(probe.list_capabilities())
        classified = all(isinstance(getattr(c, "kind", None), CapabilityKind) for c in caps)
        checks.append(_check("capabilities_classified", bool(caps) and classified, ""))
        # Manifest capability ids should match what the probe exposes.
        probe_ids = {c.id for c in caps}
        declared = set(manifest.get("capabilities", []))
        checks.append(_check("capabilities_match_manifest", declared <= probe_ids,
                             f"declared-not-exposed: {sorted(declared - probe_ids)}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("capabilities_classified", False, str(exc)))
        checks.append(_check("capabilities_match_manifest", False, str(exc)))

    # Auth works, health reports, disconnect works, and no credential leaks.
    leak_free = True
    try:
        probe.connect(creds)
        checks.append(_check("auth_works", True, ""))
        health = probe.get_health()
        detail = getattr(health, "detail", "")
        leak_free = _CANARY not in redact(str(detail)) and _CANARY not in str(getattr(health, "as_dict", lambda: {})())
        checks.append(_check("health_reports", getattr(health, "status", None) is not None, ""))
        probe.disconnect()
        checks.append(_check("disconnect_works", True, ""))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("auth_works", False, str(exc)))
        checks.append(_check("disconnect_works", False, str(exc)))

    checks.append(_check("no_credential_leak", leak_free, "credential surfaced in health output" if not leak_free else ""))

    passed = all(c["ok"] for c in checks)
    return {"passed": passed, "checks": checks}
