"""Timed speaker scripts: time per slide adds up exactly, scripts fit their time, numbers are
grounded, locked slides are kept, and the timing reaches the PowerPoint notes and the script file."""

import io
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.presentations import talk
from app.routers import presentations as P
from test_presentations import setup_company, story
from test_presentations_ai import Fake


@pytest.fixture(autouse=True)
def flag(monkeypatch, tmp_path):
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS", "true")
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS_DIR", str(tmp_path / "store"))
    monkeypatch.setattr(P, "connector_for", lambda s, w: None)


def ws():
    return {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}


def deck(n):
    types = ["cover", "bullets", "chart", "statement", "kpis", "table", "quote", "closing"]
    return {"slides": [{"id": f"s{i}", "type": types[i % len(types)], "title": f"Slide {i}"} for i in range(n)]}


@pytest.mark.parametrize("minutes,n", [(3, 5), (3, 12), (5, 7), (5, 1), (10, 11), (15, 14), (15, 40), (1, 30), (2.5, 6)])
def test_slide_times_add_up_exactly_in_five_second_steps(minutes, n):
    p = talk.plan(deck(n), minutes)
    secs = [s["seconds"] for s in p["slides"]]
    assert sum(secs) == p["totalSeconds"] == round(minutes * 60 / 5) * 5
    assert all(s % 5 == 0 and (s >= 5 or p["totalSeconds"] < 5 * n) for s in secs)
    if p["totalSeconds"] < 20 * n:
        assert p["advice"]
    assert [s["start"] for s in p["slides"]] == [sum(secs[:i]) for i in range(n)]


def test_heavier_slides_get_more_time_and_pace_sets_the_word_budget():
    p = talk.plan(story(), 5)
    by = {s["id"]: s for s in p["slides"]}
    assert by["chart"]["seconds"] > by["cover"]["seconds"] and by["risks"]["seconds"] > by["close"]["seconds"]
    brisk, relaxed = talk.plan(story(), 5, "brisk"), talk.plan(story(), 5, "relaxed")
    assert brisk["slides"][2]["words"] > relaxed["slides"][2]["words"]
    assert by["chart"]["words"] == round(by["chart"]["seconds"] * 140 / 60)


def test_advice_for_too_many_or_too_few_slides():
    assert "seconds each" in " ".join(talk.plan(deck(20), 3)["advice"])
    tip = " ".join(talk.plan(deck(3), 15)["advice"])
    assert "keep the pace" in tip and "split" in tip
    assert talk.plan(deck(7), 5)["advice"] == []
    assert [talk.suggested_slides(m) for m in (3, 5, 15)] == [5, 7, 14]


def test_offline_script_is_composed_from_the_slides_and_fits_its_time():
    c, h = TestClient(app), ws()
    r = c.post("/v1/presentations/talk/script", json={"storyline": story(), "minutes": 3, "pace": "natural"}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["mode"] == "composed" and "not connected" in out["message"]
    s = out["storyline"]
    assert s["talk"] == {"minutes": 3, "wpm": 140, "pace": "natural"}
    assert sum(x["seconds"] for x in s["slides"]) == 180
    for sl, pl in zip(s["slides"], out["plan"]["slides"]):
        assert sl["script"] and talk.words(sl["script"]) <= pl["words"] * 1.15 + 12
    assert "25" in s["slides"][1]["script"]  # the KPI value is said, from the slide itself
    assert s["slides"][-1]["script"].endswith("questions.")


def test_model_script_is_grounded_trimmed_and_charged(monkeypatch):
    monkeypatch.setenv("DAYPILOT_AI_CREDITS", "true")
    monkeypatch.setenv("DAYPILOT_AI_MONTHLY_CREDITS", "10")
    s = story()
    long = " ".join(["We shipped the adapter and the team kept a steady rhythm all week."] * 40)
    reply = {"scripts": [
        {"id": "cover", "script": "Good morning. This is our weekly review. Revenue grew 37% this week."},
        {"id": "numbers", "script": "We delivered 25 items, four more than last week. Cycle time held at 3.2 days."},
        {"id": "chart", "script": long},
        {"id": "risks", "script": "**The API change** is the one risk. Platform owns it."},
        {"id": "close", "script": "Next week we ship the adapter. Questions?"},
    ]}
    fake = Fake(reply)
    monkeypatch.setattr(P, "connector_for", lambda s, w: fake)
    c, h = TestClient(app), ws()
    out = c.post("/v1/presentations/talk/script", json={"storyline": s, "minutes": 3, "pace": "natural", "audience": "Leadership"}, headers=h).json()
    by = {x["id"]: x for x in out["storyline"]["slides"]}
    plan = {x["id"]: x for x in out["plan"]["slides"]}
    assert out["mode"] == "model" and out["credits"]["charged"] == 2
    assert "37%" not in by["cover"]["script"] and any("37%" in x for x in out["removedNumbers"])  # invented figure
    assert "25 items" in by["numbers"]["script"]  # on the slide, so allowed
    assert talk.words(by["chart"]["script"]) <= plan["chart"]["words"] * 1.15  # trimmed at a sentence end
    assert "**" not in by["risks"]["script"]
    prompt = fake.calls[0][-1]["content"]
    assert "UNTRUSTED" in prompt and '"words":' in prompt and "Leadership" in prompt


def test_locked_slides_keep_their_script():
    s = story()
    s["slides"][1]["script"] = "My own words for the numbers."
    c, h = TestClient(app), ws()
    out = c.post("/v1/presentations/talk/script", json={"storyline": s, "minutes": 5, "locks": ["numbers"]}, headers=h).json()
    assert out["storyline"]["slides"][1]["script"] == "My own words for the numbers." and "numbers" not in out["written"]


def test_plan_endpoint_reports_fit_of_existing_scripts():
    s = story()
    s["slides"][0]["script"] = "Hi."
    c, h = TestClient(app), ws()
    p = c.post("/v1/presentations/talk/plan", json={"storyline": s, "minutes": 5}, headers=h).json()
    assert p["slides"][0]["fit"] == "short" and p["slides"][1]["fit"] == "missing" and p["totalSeconds"] == 300


@pytest.mark.parametrize("patch,why", [
    ({"talk": {"minutes": 0, "wpm": 140}}, "talk"),
    ({"talk": {"minutes": 5, "wpm": 400}}, "talk"),
    ({"slides": [{"id": "a", "type": "cover", "title": "A", "seconds": -5}]}, "seconds"),
    ({"slides": [{"id": "a", "type": "cover", "title": "A", "script": "x" * 4001}]}, "script"),
])
def test_engine_refuses_bad_timing(patch, why):
    c, h = TestClient(app), ws()
    cid, _ = setup_company(c, h)
    r = c.post("/v1/presentations/decks", json={"companyId": cid, "storyline": {**story(), **patch}}, headers=h)
    assert r.status_code == 422 and why in r.text


def test_timing_reaches_the_powerpoint_notes_and_the_script_file():
    c, h = TestClient(app), ws()
    cid, _ = setup_company(c, h)
    timed = c.post("/v1/presentations/talk/script", json={"storyline": story(), "minutes": 5}, headers=h).json()["storyline"]
    timed["slides"][1]["notes"] = "Pause after the first number."
    d = c.post("/v1/presentations/decks", json={"companyId": cid, "storyline": timed}, headers=h).json()
    head = c.get(f"/v1/presentations/decks/{d['id']}", headers=h).json()["head"]
    assert head["run"]["status"] == "succeeded", head
    pptx = c.get(f"/v1/presentations/decks/{d['id']}/revisions/1/files/pptx", headers=h).content
    z = zipfile.ZipFile(io.BytesIO(pptx))
    notes = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("ppt/notesSlides/notesSlide"))
    first = timed["slides"][0]
    assert f"[{talk.clock(first['seconds'])} on this slide · from 0:00 · " in notes
    assert f"from {talk.clock(first['seconds'])}" in notes and "Guidance: Pause after the first number." in notes
    md = c.get(f"/v1/presentations/decks/{d['id']}/revisions/1/script", headers=h)
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown") and "-r1-script.md" in md.headers["content-disposition"]
    text = md.text
    assert "Speaker script · 5:00" in text and "## 1. Weekly review — 0:00–" in text and timed["slides"][2]["script"] in text


def test_flag_off_hides_talk(monkeypatch):
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS", "false")
    c, h = TestClient(app), ws()
    assert c.post("/v1/presentations/talk/plan", json={"storyline": story(), "minutes": 5}, headers=h).status_code == 404


def test_weekly_carry_forward_drops_last_weeks_figures_from_the_script():
    from app.presentations import weekly

    s = story()
    s["slides"][1]["script"] = "We delivered 25 items. The team stayed focused. Cycle time was 3.2 days."
    nxt = weekly.carry_forward(s, {"start": "2026-10-05", "end_exclusive": "2026-10-12", "key": "2026-W41", "label": "Week 41"}, "Week 40")
    assert nxt["slides"][1]["script"] == "The team stayed focused."


def test_retiming_a_scripted_deck_keeps_every_word():
    c, h = TestClient(app), ws()
    first = c.post("/v1/presentations/talk/script", json={"storyline": story(), "minutes": 5}, headers=h).json()["storyline"]
    again = c.post("/v1/presentations/talk/script", json={"storyline": first, "minutes": 3, "keepExisting": True}, headers=h).json()
    assert again["mode"] == "kept" and again["written"] == []
    assert [s["script"] for s in again["storyline"]["slides"]] == [s["script"] for s in first["slides"]]
    assert sum(s["seconds"] for s in again["storyline"]["slides"]) == 180
