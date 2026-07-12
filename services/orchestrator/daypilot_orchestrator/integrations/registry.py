"""Integration provider registry (batch I0).

Maps a provider name to a factory. New integrations register here (or, later,
via a manifest in Phase 5) without the core needing to import them directly.
"""
from __future__ import annotations

from typing import Callable

from .provider import IntegrationProvider

ProviderFactory = Callable[[], IntegrationProvider]

_FACTORIES: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    _FACTORIES[name] = factory


def build_provider(name: str) -> IntegrationProvider:
    if name not in _FACTORIES:
        raise KeyError(f"Unknown integration provider '{name}'")
    return _FACTORIES[name]()


def available_providers() -> list[str]:
    return sorted(_FACTORIES)


def is_registered(name: str) -> bool:
    return name in _FACTORIES


# Register built-in providers on import.
from .providers import reference as _reference  # noqa: E402,F401  (side-effect: registers)
from .providers import extra as _extra  # noqa: E402,F401  (side-effect: registers github, calendar)
from .providers.slack import adapter as _slack  # noqa: E402,F401  (side-effect: registers)
