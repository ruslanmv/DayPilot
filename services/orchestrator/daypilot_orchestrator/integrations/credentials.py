"""Credential storage abstraction (batch I0).

Integration credentials are stored **outside** the database, keyed by connection
id. The default is an in-process store suitable for local-first single-user use;
production swaps in a managed backend (Vault / cloud secret manager / OS keyring)
via `set_credential_store`. Credentials never enter the DB, logs, traces, or
prompts — `redact()` covers any accidental leakage into surfaced text.
"""
from __future__ import annotations

from typing import Protocol


class CredentialStore(Protocol):
    def put(self, connection_id: str, secrets: dict[str, str]) -> None: ...
    def get(self, connection_id: str) -> dict[str, str]: ...
    def delete(self, connection_id: str) -> None: ...
    def has(self, connection_id: str) -> bool: ...


class InMemoryCredentialStore:
    """Default store. Process-local; not persisted. Fine for local-first use and
    for tests. Replace in production with a managed backend."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, str]] = {}

    def put(self, connection_id: str, secrets: dict[str, str]) -> None:
        self._data[connection_id] = dict(secrets)

    def get(self, connection_id: str) -> dict[str, str]:
        return dict(self._data.get(connection_id, {}))

    def delete(self, connection_id: str) -> None:
        self._data.pop(connection_id, None)

    def has(self, connection_id: str) -> bool:
        return connection_id in self._data


_store: CredentialStore = InMemoryCredentialStore()


def credential_store() -> CredentialStore:
    return _store


def set_credential_store(store: CredentialStore) -> None:
    """Swap the backend (e.g. Vault) at process start."""
    global _store
    _store = store
