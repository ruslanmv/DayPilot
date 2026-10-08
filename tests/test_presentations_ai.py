"""Presentations AI: own-model outline and slide rewrites, number grounding, locks, credits, offline."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.presentations import ai
from app.routers import presentations as P
from test_presentations import setup_company, story


@pytest.fixture(autouse=True)
def flag(monkeypatch, tmp_path):
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS", "true")
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS_DIR", str(tmp_path / "store"))


class Fake:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def generate_messages(self, messages, task="x", **kw):
        self.calls.append(messages)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return {"text": r if isinstance(r, str) else json.dumps(r)}


def ws():
    return {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}


def model_story(n=4, kpi="25", chart=(4, 5, 99)):
    slides = [
        {"id": "cover", "type": "cover", "title": "Delivery review", "kicker": "W39"},
        {"id": "nums", "type": "kpis", "title": "Numbers", "kpis": [{"value": kpi, "label": "Delivered", "delta": "+7 vs last week"}]},
        {"id": "trend", "type": "chart", "title": "Per day", "chart": {"type": "column", "title": "Per day", "unit": "items", "categories": ["Mon", "Tue", "Wed"], "series": [{"name": "Done", "values": list(chart)}]}},
        {"id": "next", "type": "closing", "title": "Next", "next_steps": ["Ship"]},
    ]
    return {"title": "Delivery review", "slides": slides[:n]}


def test_offline_outline_uses_the_template_and_costs_nothing(monkeypatch):
    monkeypatch.setattr(P, "connector_for", lambda s, w: None)
    c, h = TestClient(app), ws()
    r = c.post("/v1/presentations/outline", json={"genre": "executive_update", "brief": "Pricing change"}, headers=h).json()
    assert r["mode"] == "template" and r["storyline"]["title"] == "Pricing change" and "not connected" in r["message"]


def test_model_outline_keeps_sourced_numbers_and_removes_invented_ones(monkeypatch):
    fake = Fake(model_story())
    monkeypatch.setattr(P, "connector_for", lambda s, w: fake)
    c, h = TestClient(app), ws()
    r = c.post("/v1/presentations/outline", json={"genre": "weekly_update", "brief": "Weekly delivery", "slideCount": 4, "sources": "Delivered: 25 items. Monday 4, Tuesday 5, Wednesday 6."}, headers=h).json()
    s = r["storyline"]
    assert r["mode"] == "model"
    assert s["slides"][1]["kpis"][0]["value"] == "25" and "delta" not in s["slides"][1]["kpis"][0]  # +7 is not in the sources
    assert s["slides"][2]["chart"]["series"][0]["values"] == [4, 5, None]  # 99 was invented
    assert any("99" in x for x in r["removedNumbers"])
    user = fake.calls[0][-1]["content"]
    assert "UNTRUSTED" in user and "Exactly 4 slides" in user and fake.calls[0][0]["role"] == "system"


def test_no_sources_means_no_numbers(monkeypatch):
    monkeypatch.setattr(P, "connector_for", lambda s, w: Fake(model_story()))
    c, h = TestClient(app), ws()
    s = c.post("/v1/presentations/outline", json={"brief": "Weekly", "slideCount": 4}, headers=h).json()["storyline"]
    assert s["slides"][1]["kpis"][0]["value"] == "—" and s["slides"][2]["chart"]["series"][0]["values"] == [None, None, None]


def test_invalid_reply_gets_one_repair_round_then_a_clear_error(monkeypatch):
    bad = {"title": "x", "slides": [{"id": "a", "type": "pie", "title": "x"}] * 4}
    monkeypatch.setattr(P, "connector_for", lambda s, w: Fake(bad, model_story()))
    c, h = TestClient(app), ws()
    assert c.post("/v1/presentations/outline", json={"brief": "x", "slideCount": 4}, headers=h).status_code == 200
    monkeypatch.setattr(P, "connector_for", lambda s, w: Fake(bad, bad))
    r = c.post("/v1/presentations/outline", json={"brief": "x", "slideCount": 4}, headers=h)
    assert r.status_code == 422 and "not usable" in r.json()["detail"]
    monkeypatch.setattr(P, "connector_for", lambda s, w: Fake("not json"))
    assert c.post("/v1/presentations/outline", json={"brief": "x", "slideCount": 4}, headers=h).status_code == 422
    monkeypatch.setattr(P, "connector_for", lambda s, w: Fake(model_story(3), model_story(3)))
    r = c.post("/v1/presentations/outline", json={"brief": "x", "slideCount": 4}, headers=h)
    assert r.status_code == 422 and "instead of 4" in r.json()["detail"]
    monkeypatch.setattr(P, "connector_for", lambda s, w: Fake(RuntimeError("down")))
    r = c.post("/v1/presentations/outline", json={"brief": "x", "slideCount": 4}, headers=h)
    assert r.status_code == 422 and "couldn't reach" in r.json()["detail"] and "down" not in r.text


def test_regenerate_rewrites_only_selected_unlocked_slides(monkeypatch):
    c, h = TestClient(app), ws()
    cid, _ = setup_company(c, h, logo=False)
    d = c.post("/v1/presentations/decks", json={"companyId": cid, "storyline": story()}, headers=h).json()
    c.post(f"/v1/presentations/decks/{d['id']}/locks", json={"locks": ["numbers"], "expectedRevision": 1}, headers=h)
    new_close = {"id": "close", "type": "closing", "title": "Next week, sharper", "next_steps": ["Ship the adapter", "Tell 3 customers"]}
    monkeypatch.setattr(P, "connector_for", lambda s, w: Fake({"slides": [new_close]}))
    r = c.post(f"/v1/presentations/decks/{d['id']}/regenerate", json={"slideIds": ["close"], "instruction": "Make it sharper", "expectedRevision": 1}, headers=h)
    assert r.status_code == 202, r.text
    rev = c.get(f"/v1/presentations/decks/{d['id']}/revisions/2", headers=h).json()
    assert rev["author"] == "model" and rev["locks"] == ["numbers"]
    slides = {s["id"]: s for s in rev["storyline"]["slides"]}
    assert slides["close"]["title"] == "Next week, sharper" and slides["numbers"] == story()["slides"][1]
    monkeypatch.setattr(P, "connector_for", lambda s, w: Fake({"slides": []}))
    locked = c.post(f"/v1/presentations/decks/{d['id']}/regenerate", json={"slideIds": ["numbers"], "expectedRevision": 2}, headers=h)
    assert locked.status_code == 422 and "Locked" in locked.json()["detail"]
    monkeypatch.setattr(P, "connector_for", lambda s, w: Fake({"slides": [new_close, {"id": "extra", "type": "statement", "title": "x", "statement": "y"}]}))
    assert c.post(f"/v1/presentations/decks/{d['id']}/regenerate", json={"slideIds": ["close"], "expectedRevision": 2}, headers=h).status_code == 422
    monkeypatch.setattr(P, "connector_for", lambda s, w: None)
    assert c.post(f"/v1/presentations/decks/{d['id']}/regenerate", json={"slideIds": ["close"], "expectedRevision": 2}, headers=h).status_code == 409


def test_credits_are_charged_for_model_work_and_refunded_on_failure(monkeypatch):
    monkeypatch.setenv("DAYPILOT_AI_CREDITS", "true")
    monkeypatch.setenv("DAYPILOT_AI_MONTHLY_CREDITS", "4")
    c, h = TestClient(app), ws()
    monkeypatch.setattr(P, "connector_for", lambda s, w: Fake(model_story()))
    r = c.post("/v1/presentations/outline", json={"brief": "x", "slideCount": 4}, headers=h).json()
    assert r["credits"] == {"charged": 3, "balance": 1}
    monkeypatch.setattr(P, "connector_for", lambda s, w: Fake("garbage"))
    monkeypatch.setenv("DAYPILOT_AI_MONTHLY_CREDITS", "4")
    assert c.post("/v1/presentations/outline", json={"brief": "x", "slideCount": 4}, headers=h).status_code == 402  # 1 left, needs 3
    assert c.get("/v1/diagrams/assist/credits", headers=h).json()["balance"] == 1


def test_a_dmind_map_becomes_an_editable_diagram_slide_without_changing_the_map(monkeypatch):
    monkeypatch.setattr(P, "connector_for", lambda s, w: None)
    c, h = TestClient(app), ws()
    doc = {"schema_version": "dmind/v1", "id": "x", "title": "Order flow", "kind": "flowchart",
           "nodes": [{"id": "root", "label": "Order"}] + [{"id": f"n{i}", "label": f"Step {i}"} for i in range(12)],
           "edges": [{"id": f"e{i}", "source": "root" if i == 0 else f"n{i - 1}", "target": f"n{i}", "kind": "flow"} for i in range(12)]}
    did = c.post("/v1/diagrams", json={"document": doc}, headers=h).json()["id"]
    before = c.get(f"/v1/diagrams/{did}", headers=h).json()
    s = c.post("/v1/presentations/outline", json={"genre": "training", "brief": "Ordering", "diagramId": did}, headers=h).json()["storyline"]
    m = next(x for x in s["slides"] if x["type"] == "diagram" and x["id"] == "map")
    assert len(m["nodes"]) == 8 and m["nodes"][0]["label"] == "Order" and "read-only" in m["notes"]
    assert c.get(f"/v1/diagrams/{did}", headers=h).json() == before
    assert c.post("/v1/presentations/outline", json={"brief": "x", "diagramId": did}, headers=ws()).status_code == 404


def test_grounding_unit():
    s = {"slides": [{"kpis": [{"value": "98.6%", "label": "x"}, {"value": "1,234", "label": "y"}, {"value": "Flat", "label": "z"}]}]}
    removed = ai.ground(s, "Rate 98.6 percent; total 1234")
    assert removed == [] and s["slides"][0]["kpis"][2]["value"] == "Flat"
    removed = ai.ground(s, "nothing")
    assert len(removed) == 2
