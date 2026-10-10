"""The production static mount serves HTTP and safely rejects WebSocket upgrades."""
from __future__ import annotations

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.webserve import mount_web


@pytest.fixture
def web_app(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html>DayPilot</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('DayPilot')")
    monkeypatch.setenv("DAYPILOT_WEB_DIST", str(tmp_path))
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.websocket("/live")
    async def live(socket: WebSocket):
        await socket.accept()
        await socket.send_text("connected")
        await socket.close()

    mount_web(app)
    return app


@pytest.mark.parametrize("path", ["/", "/assets/app.js", "/stale-vite-hmr"])
def test_static_mount_rejects_websockets_without_crashing(web_app, path):
    with TestClient(web_app) as client:
        with pytest.raises(WebSocketDisconnect) as rejected:
            with client.websocket_connect(path):
                pytest.fail("The static mount must not accept WebSockets")
        assert rejected.value.code == 1008
        # An unsupported upgrade must leave HTTP serving usable.
        assert client.get("/").text == "<html>DayPilot</html>"
        assert client.get("/api/health").json() == {"ok": True}


def test_http_static_files_and_api_routes_still_work(web_app):
    with TestClient(web_app) as client:
        assert client.get("/").text == "<html>DayPilot</html>"
        assert client.get("/assets/app.js").text == "console.log('DayPilot')"
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/health").json() == {"ok": True}
        assert client.get("/api/health").json() == {"ok": True}


def test_registered_websocket_routes_take_precedence(web_app):
    with TestClient(web_app) as client:
        with client.websocket_connect("/live") as socket:
            assert socket.receive_text() == "connected"


# --- Echo Show display mode (/echo) -------------------------------------------


@pytest.fixture
def echo_app(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html>DayPilot</html>")
    (tmp_path / "echo").mkdir()
    (tmp_path / "echo" / "index.html").write_text("<html>Echo</html>")
    monkeypatch.setenv("DAYPILOT_WEB_DIST", str(tmp_path))
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"ok": True}

    mount_web(app)
    return app


@pytest.mark.parametrize("path", ["/echo", "/echo/"])
def test_echo_page_is_served_at_both_addresses_without_a_redirect(echo_app, path):
    # StaticFiles would redirect /echo to an absolute http:// URL behind a TLS proxy.
    with TestClient(echo_app) as client:
        res = client.get(path, follow_redirects=False)
        assert res.status_code == 200
        assert res.text == "<html>Echo</html>"
        assert res.headers["cache-control"] == "no-cache"
        assert client.head(path, follow_redirects=False).status_code == 200


def test_echo_leaves_the_console_and_the_api_as_they_were(echo_app):
    with TestClient(echo_app) as client:
        assert client.get("/").text == "<html>DayPilot</html>"
        assert client.get("/api/health").json() == {"ok": True}
        assert client.get("/echo/index.html").text == "<html>Echo</html>"


def test_without_an_echo_build_nothing_new_is_routed(web_app):
    with TestClient(web_app) as client:
        assert client.get("/echo", follow_redirects=False).status_code == 404
        assert client.get("/").text == "<html>DayPilot</html>"
