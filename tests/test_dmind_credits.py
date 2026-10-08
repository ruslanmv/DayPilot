"""AI credits: metered use of the workspace's own models, atomic, refunded on failure, owner-granted."""

import json
import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from app import ai_credits as credits
from app.db import _get_sessionmaker
from app.main import app
from app.routers import diagram_assist
from daypilot_knowledge.db.models import AiCreditAccount, AiCreditEvent


def doc():
    return {
        "schema_version": "dmind/v1", "id": "m", "title": "T", "kind": "mindmap",
        "nodes": [{"id": "root", "label": "Root"}], "edges": [],
    }


class Fake:
    def __init__(self, reply):
        self.reply = reply

    def generate_messages(self, messages, task="x", **kw):
        if isinstance(self.reply, Exception):
            raise self.reply
        return {"text": json.dumps(self.reply)}


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("DAYPILOT_AI_CREDITS", "true")
    monkeypatch.setenv("DAYPILOT_AI_MONTHLY_CREDITS", "5")
    ws = {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    return TestClient(app), ws, monkeypatch


def use(mp, reply):
    mp.setattr(diagram_assist, "provider", lambda s, w: Fake(reply))


def chat(c, h, prompt="x", **kw):
    return c.post("/v1/diagrams/assist", json={"action": "chat", "document": doc(), "prompt": prompt, **kw}, headers=h)


def balance(c, h):
    return c.get("/v1/diagrams/assist/credits", headers=h).json()["balance"]


def test_off_by_default_means_unmetered(monkeypatch):
    monkeypatch.delenv("DAYPILOT_AI_CREDITS", raising=False)
    c, h = TestClient(app), {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    use(monkeypatch, {"message": "ok"})
    r = chat(c, h)
    assert r.status_code == 200 and "credits" not in r.json()
    assert c.get("/v1/diagrams/assist/credits", headers=h).json()["enabled"] is False


def test_each_action_costs_credits_and_the_ledger_records_it(env):
    c, h, mp = env
    use(mp, {"message": "ok"})
    assert balance(c, h) == 5
    r = chat(c, h)
    assert r.json()["credits"] == {"charged": 1, "balance": 4}
    r = c.post("/v1/diagrams/assist", json={"action": "reorganize", "document": doc()}, headers=h)
    assert r.json()["credits"]["charged"] == 2 and balance(c, h) == 2
    s = c.get("/v1/diagrams/assist/credits", headers=h).json()
    assert [e["kind"] for e in s["recent"][:2]] == ["use", "use"] and s["monthlyAllowance"] == 5
    assert "x" not in json.dumps(s["recent"]).replace("amount", "")  # no prompt text anywhere in the ledger


def test_running_out_blocks_before_any_model_call(env):
    c, h, mp = env
    calls = []
    mp.setattr(diagram_assist, "provider", lambda s, w: type("F", (), {"generate_messages": lambda self, *a, **k: calls.append(1) or {"text": "{}"}})())
    for _ in range(5):
        assert chat(c, h).status_code == 200
    r = chat(c, h)
    assert r.status_code == 402 and "Not enough AI credits" in r.json()["detail"] and len(calls) == 5
    assert balance(c, h) == 0


def test_failures_and_no_provider_do_not_cost_credits(env):
    c, h, mp = env
    use(mp, RuntimeError("down"))
    assert chat(c, h).status_code == 422 and balance(c, h) == 5
    use(mp, "{bad")
    mp.setattr(diagram_assist, "provider", lambda s, w: Fake({"ops": [{"op": "drop"}]}))
    assert chat(c, h).status_code == 422 and balance(c, h) == 5
    mp.setattr(diagram_assist, "provider", lambda s, w: None)
    r = chat(c, h)
    assert r.json()["mode"] == "offline" and r.json()["credits"]["charged"] == 0 and balance(c, h) == 5
    # invalid input is rejected before any charge
    assert c.post("/v1/diagrams/assist", json={"action": "grow", "document": doc()}, headers=h).status_code == 422
    assert balance(c, h) == 5


def test_concurrent_requests_cannot_overspend(env):
    c, h, mp = env
    use(mp, {"message": "ok"})
    codes = []

    def go():
        codes.append(chat(TestClient(app), h).status_code)

    threads = [threading.Thread(target=go) for _ in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert codes.count(200) == 5 and codes.count(402) == 7 and balance(c, h) == 0


def test_owner_grants_and_sets_allowance_others_cannot(env):
    c, h, mp = env
    assert balance(c, h) == 5
    r = c.post("/v1/diagrams/assist/credits/grant", json={"amount": 20, "monthlyAllowance": 50}, headers=h)
    assert r.status_code == 200 and r.json()["balance"] == 25 and r.json()["monthlyAllowance"] == 50
    for bad in ({"amount": -1}, {"amount": 10**7}, {"monthlyAllowance": -5}):
        assert c.post("/v1/diagrams/assist/credits/grant", json=bad, headers=h).status_code == 422
    mp.setattr(diagram_assist, "access_role", lambda request, session: ("w", "operator"))
    assert c.post("/v1/diagrams/assist/credits/grant", json={"amount": 5}, headers=h).status_code == 403
    mp.setenv("DAYPILOT_AI_CREDITS", "false")
    mp.setattr(diagram_assist, "access_role", lambda request, session: ("w", "owner"))
    assert c.post("/v1/diagrams/assist/credits/grant", json={"amount": 5}, headers=h).status_code == 409


def test_new_month_refills_to_the_allowance_but_never_reduces(env):
    c, h, mp = env
    use(mp, {"message": "ok"})
    for _ in range(5):
        chat(c, h)
    ws = h["X-Workspace-Id"]
    with _get_sessionmaker()() as s:
        s.get(AiCreditAccount, ws).period = "2000-01"
        s.commit()
    assert balance(c, h) == 5
    c.post("/v1/diagrams/assist/credits/grant", json={"amount": 40}, headers=h)
    with _get_sessionmaker()() as s:
        s.get(AiCreditAccount, ws).period = "2000-01"
        s.commit()
    assert balance(c, h) == 45  # carried-over purchases are kept
    with _get_sessionmaker()() as s:
        kinds = [e.kind for e in s.query(AiCreditEvent).filter_by(workspace_id=ws)]
    assert {"use", "refill", "grant"} <= set(kinds)


def test_costs_scale_with_selection_and_can_be_configured(env):
    c, h, mp = env
    assert credits.cost_for("refine", 1) == 1 and credits.cost_for("refine", 11) == 3 and credits.cost_for("chat", 50) == 1
    mp.setenv("DAYPILOT_AI_CREDIT_COSTS", json.dumps({"chat": 3, "grow": -1, "bogus": 5, "explain": True}))
    assert credits.cost_for("chat") == 3 and credits.cost_for("grow") == 1 and "bogus" not in credits.costs()
    mp.setenv("DAYPILOT_AI_CREDIT_COSTS", "not json")
    assert credits.cost_for("chat") == 1
    mp.setenv("DAYPILOT_AI_CREDIT_COSTS", json.dumps({"chat": 0}))
    use(mp, {"message": "free"})
    assert chat(c, h).json()["credits"]["charged"] == 0 and balance(c, h) == 5


def test_tenants_have_separate_balances(env):
    c, h, mp = env
    use(mp, {"message": "ok"})
    other = {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    chat(c, h)
    assert balance(c, h) == 4 and balance(c, other) == 5
