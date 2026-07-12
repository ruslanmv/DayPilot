"""DayPilot Integration SDK (batch I10).

The stable surface an internal or third-party team imports to build an
integration **outside** the core repo. It re-exports the provider contract, the
manifest type, the permission/capability vocabulary, and the conformance runner
so a builder can self-test before submitting to the catalog. Nothing here reaches
into DayPilot internals.
"""
from __future__ import annotations

from .certification import run_conformance
from .manifest import IntegrationManifest, validate_manifest
from .provider import (
    AuthType,
    Capability,
    CapabilityKind,
    ConnectionStatus,
    IntegrationHealth,
    IntegrationProvider,
)

__all__ = [
    "AuthType",
    "Capability",
    "CapabilityKind",
    "ConnectionStatus",
    "IntegrationHealth",
    "IntegrationManifest",
    "IntegrationProvider",
    "run_conformance",
    "validate_manifest",
]
