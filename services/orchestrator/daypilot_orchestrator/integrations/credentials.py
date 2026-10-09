"""Credential storage abstraction (batch I0).

Integration credentials are stored **outside** the database, keyed by connection
id. The default is a private local file store that survives gateway restarts;
production can swap in a managed backend (Vault / cloud secret manager / OS keyring)
via `set_credential_store`. Credentials never enter the DB, logs, traces, or
prompts — `redact()` covers any accidental leakage into surfaced text.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol


class CredentialStore(Protocol):
    def put(self, connection_id: str, secrets: dict[str, Any]) -> None: ...
    def get(self, connection_id: str) -> dict[str, Any]: ...
    def delete(self, connection_id: str) -> None: ...
    def has(self, connection_id: str) -> bool: ...


class InMemoryCredentialStore:
    """Injectable ephemeral store for tests and explicitly temporary sessions."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def put(self, connection_id: str, secrets: dict[str, Any]) -> None:
        self._data[connection_id] = dict(secrets)

    def get(self, connection_id: str) -> dict[str, Any]:
        return dict(self._data.get(connection_id, {}))

    def delete(self, connection_id: str) -> None:
        self._data.pop(connection_id, None)

    def has(self, connection_id: str) -> bool:
        return connection_id in self._data


class FileCredentialStore:
    """Local secrets outside the application DB, with owner-only permissions.

    One atomic file per reference avoids overwriting other connections' secrets
    when several gateway processes write at once. A managed store can still be
    injected with set_credential_store().
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, connection_id: str) -> Path:
        return self.directory / (hashlib.sha256(connection_id.encode()).hexdigest() + ".json")

    def put(self, connection_id: str, secrets: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(dir=self.directory, prefix=".credential-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(secrets, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, self._path(connection_id))
        finally:
            Path(name).unlink(missing_ok=True)

    def get(self, connection_id: str) -> dict[str, Any]:
        try:
            return json.loads(self._path(connection_id).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def delete(self, connection_id: str) -> None:
        self._path(connection_id).unlink(missing_ok=True)

    def has(self, connection_id: str) -> bool:
        return self._path(connection_id).is_file()


_store: CredentialStore | None = None


def credential_store() -> CredentialStore:
    global _store
    if _store is None:
        _store = FileCredentialStore(Path(os.getenv("DAYPILOT_CREDENTIALS_DIR", "local_data/credentials")))
    return _store


def set_credential_store(store: CredentialStore) -> None:
    """Swap the backend (e.g. Vault) at process start."""
    global _store
    _store = store
