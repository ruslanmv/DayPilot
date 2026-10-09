"""Local integration configuration must survive a gateway restart."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys

from daypilot_orchestrator.integrations.credentials import FileCredentialStore


def test_credentials_are_readable_by_a_new_process(tmp_path):
    directory = tmp_path / "credentials"
    secret = {"base_url": "http://localhost:8000", "api_key": "test-value",
              "account_ref": "user:42", "prefs": {"autoSync": True}}
    FileCredentialStore(directory).put("homepilot:connection", secret)
    # Start a real interpreter using the default store, rather than testing a
    # second in-memory object in the same gateway process.
    result = subprocess.run(
        [sys.executable, "-c", "from daypilot_orchestrator.integrations.credentials import credential_store; "
         "import json; print(json.dumps(credential_store().get('homepilot:connection')))"],
        env={**os.environ, "DAYPILOT_CREDENTIALS_DIR": str(directory),
             "PYTHONPATH": "services/orchestrator"},
        check=True, text=True, capture_output=True,
    )
    assert json.loads(result.stdout) == secret


def test_local_secret_files_are_private_and_do_not_use_reference_as_a_path(tmp_path):
    directory = tmp_path / "credentials"
    store = FileCredentialStore(directory)
    store.put("../connection", {"api_key": "test-value"})
    files = list(directory.iterdir())
    assert len(files) == 1 and files[0].suffix == ".json"
    assert store.get("../connection") == {"api_key": "test-value"}
    if os.name == "posix":
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(files[0].stat().st_mode) == 0o600


def test_updating_and_revoking_one_connection_preserves_other_connections(tmp_path):
    store = FileCredentialStore(tmp_path / "credentials")
    store.put("one", {"api_key": "old-value"})
    store.put("two", {"api_key": "other-value"})
    store.put("one", {"api_key": "new-value"})
    assert FileCredentialStore(store.directory).get("one") == {"api_key": "new-value"}
    assert store.get("two") == {"api_key": "other-value"}
    store.delete("one")
    store.delete("one")
    assert not store.has("one") and store.get("one") == {}
    assert store.has("two") and store.get("two") == {"api_key": "other-value"}


def test_homepilot_uses_the_saved_address_and_account_after_restart(tmp_path, monkeypatch):
    from app import homepilot_platform as hp
    from daypilot_knowledge.db import IntegrationConnection
    from daypilot_orchestrator.integrations import credentials

    directory = tmp_path / "credentials"
    reference = "homepilot:restart-test"
    FileCredentialStore(directory).put(reference, {
        "base_url": "http://localhost:8000", "api_key": "test-value",
        "account_ref": "user:42", "account_label": "Test account",
    })
    monkeypatch.setenv("DAYPILOT_CREDENTIALS_DIR", str(directory))
    monkeypatch.setattr(credentials, "_store", None)
    row = IntegrationConnection(id="restart-test", workspace_id="default", provider="homepilot")
    client = hp._client_for(row)
    assert client.base_url == "http://localhost:8000"
    assert client.api_key == "test-value"
    assert hp._secret(row.id)["account_ref"] == "user:42"


def test_a_previously_lost_connection_requires_reconnect_instead_of_using_another_server(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app import homepilot_platform as hp
    from daypilot_knowledge.db import IntegrationConnection, create_engine_from_settings, session_scope
    from daypilot_orchestrator.integrations import credentials

    monkeypatch.setenv("DAYPILOT_CREDENTIALS_DIR", str(tmp_path / "empty"))
    monkeypatch.setattr(credentials, "_store", None)
    row = IntegrationConnection(id="lost-test", workspace_id="default", provider="homepilot", status="connected")
    assert hp._client_for(row) is None
    public = hp._public(row)
    assert public["status"] == "unconfigured"
    assert "Reconnect HomePilot" in public["lastError"]
    with session_scope(create_engine_from_settings()) as session:
        row.workspace_id = "lost-connection-test"
        session.add(row)
    with TestClient(app) as gateway:
        status = gateway.get("/v1/homepilot/setup/status?workspaceId=lost-connection-test").json()
        assert status["connectionState"] == "not_connected"
        assert "Reconnect HomePilot" in status["connection"]["lastError"]
