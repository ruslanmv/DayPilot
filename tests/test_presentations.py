"""Presentations: brand kits, native decks built and rendered from the actual file, revisions,
locks, approval binding, weekly series idempotency and tenant isolation."""

import struct
import uuid
import zlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.presentations import render, weekly

RENDER = render.capabilities()["ready"]


@pytest.fixture(autouse=True)
def flag(monkeypatch, tmp_path):
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS", "true")
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS_DIR", str(tmp_path / "store"))


def png(w=300, h=100, rgb=(11, 60, 93)):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def ws():
    return {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}


def setup_company(c, h, logo=True):
    co = c.post("/v1/presentations/companies", json={"name": "Northwind (fictional)"}, headers=h).json()
    body = {"palette": {"primary": "#0B3C5D", "accent": "#E07A1F"}, "headingFont": "Cambria", "bodyFont": "Calibri", "footerText": "Northwind · FICTIONAL"}
    if logo:
        a = c.post(f"/v1/presentations/companies/{co['id']}/assets", files={"file": ("logo.png", png(), "image/png")}, headers=h)
        assert a.status_code == 201, a.text
        body["logoAssetId"] = a.json()["id"]
    k = c.post(f"/v1/presentations/companies/{co['id']}/brand-kits", json=body, headers=h)
    assert k.status_code == 201, k.text
    return co["id"], k.json()


def starter(c, h, genre="weekly_update", topic="Team delivery"):
    r = c.post("/v1/presentations/starter", json={"genre": genre, "topic": topic, "periodLabel": "Week 39"}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["storyline"]


def story():
    return {
        "schema_version": "daypilot.storyline/v1", "title": "Weekly review",
        "slides": [
            {"id": "cover", "type": "cover", "title": "Weekly review", "subtitle": "Status and one decision", "kicker": "Week 39"},
            {"id": "numbers", "type": "kpis", "title": "The week in numbers", "kpis": [{"value": "25", "label": "Items delivered", "delta": "+4"}, {"value": "3.2 d", "label": "Cycle time"}]},
            {"id": "chart", "type": "chart", "title": "Delivered per day", "chart": {"type": "column", "unit": "items", "categories": ["Mon", "Tue", "Wed"], "series": [{"name": "Delivered", "values": [4, None, 6]}]}},
            {"id": "risks", "type": "table", "title": "Risks", "headers": ["Risk", "Owner"], "rows": [["API change", "Platform"]]},
            {"id": "close", "type": "closing", "title": "Next week", "next_steps": ["Ship the adapter"]},
        ],
    }


def test_disabled_by_default_except_capabilities(monkeypatch):
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS", "false")
    c, h = TestClient(app), ws()
    assert c.get("/v1/presentations/capabilities").json()["enabled"] is False
    assert c.get("/v1/presentations/companies", headers=h).status_code == 404


def test_brand_kit_versions_are_immutable_and_activation_is_explicit():
    c, h = TestClient(app), ws()
    cid, first = setup_company(c, h)
    assert first["version"] == 1 and first["active"] is True
    assert first["kit"]["logos"][0]["aspect_ratio"] == 3 and first["kit"]["typography"]["slide_title"]["family"] == "Cambria"
    second = c.post(f"/v1/presentations/companies/{cid}/brand-kits", json={"palette": {"primary": "#2C5F2D"}}, headers=h).json()
    assert second["version"] == 2 and second["active"] is False
    stale = c.post(f"/v1/presentations/companies/{cid}/brand-kits/2/activate", json={"expectedActiveVersion": 2}, headers=h)
    assert stale.status_code == 409
    assert c.post(f"/v1/presentations/companies/{cid}/brand-kits/2/activate", json={"expectedActiveVersion": 1}, headers=h).json()["activeBrandVersion"] == 2
    bad = c.post(f"/v1/presentations/companies/{cid}/brand-kits", json={"palette": {"primary": "blue"}}, headers=h)
    assert bad.status_code == 422 and "palette.primary" in str(bad.json())


def test_uploads_are_checked_by_their_bytes():
    c, h = TestClient(app), ws()
    co = c.post("/v1/presentations/companies", json={"name": "A"}, headers=h).json()
    for name, data in (("x.png", b"not an image"), ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>"), ("big.png", b"\x89PNG" + b"0" * 5_000_001)):
        assert c.post(f"/v1/presentations/companies/{co['id']}/assets", files={"file": (name, data, "image/png")}, headers=h).status_code == 422
    one = c.post(f"/v1/presentations/companies/{co['id']}/assets", files={"file": ("a.png", png(), "image/png")}, headers=h).json()
    two = c.post(f"/v1/presentations/companies/{co['id']}/assets", files={"file": ("b.png", png(), "image/png")}, headers=h).json()
    assert one["id"] == two["id"] and one["width"] == 300  # same bytes, same asset


def test_deck_is_built_rendered_checked_and_downloadable():
    c, h = TestClient(app), ws()
    cid, _ = setup_company(c, h)
    r = c.post("/v1/presentations/decks", json={"companyId": cid, "storyline": story()}, headers=h)
    assert r.status_code == 202, r.text
    deck = c.get(f"/v1/presentations/decks/{r.json()['id']}", headers=h).json()
    head = deck["head"]
    assert head["run"]["status"] == "succeeded", head
    assert head["slideCount"] == 5 and head["files"]["pptx"]
    if RENDER:
        assert head["state"] == "review_ready", head["findings"]
        assert head["quality"]["status"] == "passed" and head["files"]["pdf"] and head["files"]["slides"] == 5
        img = c.get(f"/v1/presentations/decks/{deck['id']}/revisions/1/files/png?slide=2", headers=h)
        assert img.status_code == 200 and img.content[:4] == b"\x89PNG"
    else:
        assert head["quality"]["status"] == "unverified"
    f = c.get(f"/v1/presentations/decks/{deck['id']}/revisions/1/files/pptx", headers=h)
    assert f.status_code == 200 and f.content[:2] == b"PK" and "-draft.pptx" in f.headers["content-disposition"]
    assert any(n["id"] == "chart" and "Mon" in n["notes"] for n in head["notes"])


def test_quality_failure_is_reported_and_cannot_be_approved():
    c, h = TestClient(app), ws()
    cid, _ = setup_company(c, h)
    s = story()
    s["slides"][1]["kpis"][0]["label"] = "An extremely long label that goes on and on " * 1
    s["slides"].insert(1, {"id": "dense", "type": "bullets", "title": "Too much", "takeaway": "x" * 190, "bullets": ["word " * 39 + "end"] * 7})
    d = c.post("/v1/presentations/decks", json={"companyId": cid, "storyline": s}, headers=h).json()
    head = c.get(f"/v1/presentations/decks/{d['id']}", headers=h).json()["head"]
    assert head["state"] == "failed" and any(f["code"] == "text_overflow" for f in head["findings"])
    sha = head["pptxSha256"]
    assert c.post(f"/v1/presentations/decks/{d['id']}/revisions/1/approve", json={"pptxSha256": sha}, headers=h).status_code == 409


def test_invalid_storylines_are_refused_with_reasons():
    c, h = TestClient(app), ws()
    cid, _ = setup_company(c, h, logo=False)
    bad = {"schema_version": "daypilot.storyline/v1", "title": "x", "slides": [{"type": "chart", "title": "c", "chart": {"type": "pie", "categories": ["a"], "series": [{"name": "s", "values": [1]}]}}]}
    r = c.post("/v1/presentations/decks", json={"companyId": cid, "storyline": bad}, headers=h)
    assert r.status_code == 422 and "chart.type" in str(r.json())


def test_revisions_cas_locks_restore_and_approval_binding():
    c, h = TestClient(app), ws()
    cid, _ = setup_company(c, h, logo=False)
    d = c.post("/v1/presentations/decks", json={"companyId": cid, "storyline": story()}, headers=h).json()
    did = d["id"]
    assert c.post(f"/v1/presentations/decks/{did}/locks", json={"locks": ["numbers", "ghost"], "expectedRevision": 1}, headers=h).json()["locks"] == ["numbers"]
    s2 = story()
    s2["slides"][1]["kpis"][0]["value"] = "26"
    locked = c.post(f"/v1/presentations/decks/{did}/revisions", json={"storyline": s2, "expectedRevision": 1}, headers=h)
    assert locked.status_code == 409 and "locked" in locked.json()["detail"]
    s3 = story()
    s3["slides"][4]["next_steps"] = ["Ship it", "Tell customers"]
    ok = c.post(f"/v1/presentations/decks/{did}/revisions", json={"storyline": s3, "expectedRevision": 1, "locks": ["numbers"]}, headers=h)
    assert ok.status_code == 202 and ok.json()["headRevision"] == 2
    stale = c.post(f"/v1/presentations/decks/{did}/revisions", json={"storyline": s3, "expectedRevision": 1}, headers=h)
    assert stale.status_code == 409
    full = c.get(f"/v1/presentations/decks/{did}", headers=h).json()
    assert [r["revision"] for r in full["revisions"]] == [2, 1]
    r1 = c.get(f"/v1/presentations/decks/{did}/revisions/1", headers=h).json()
    assert r1["storyline"]["slides"][4]["next_steps"] == ["Ship the adapter"]  # history untouched
    restored = c.post(f"/v1/presentations/decks/{did}/restore", json={"revision": 1, "expectedRevision": 2}, headers=h).json()
    assert restored["headRevision"] == 3
    if RENDER:
        head = c.get(f"/v1/presentations/decks/{did}", headers=h).json()["head"]
        assert c.post(f"/v1/presentations/decks/{did}/revisions/3/approve", json={"pptxSha256": "0" * 64}, headers=h).status_code == 409
        a = c.post(f"/v1/presentations/decks/{did}/revisions/3/approve", json={"pptxSha256": head["pptxSha256"]}, headers=h)
        assert a.status_code == 200 and a.json()["state"] == "approved"
        f = c.get(f"/v1/presentations/decks/{did}/revisions/3/files/pptx", headers=h)
        assert "-draft" not in f.headers["content-disposition"]


def test_stale_worker_cannot_publish():
    from app.db import _get_sessionmaker
    from app.presentations import worker
    from daypilot_knowledge.db.models import PresentationRun

    c, h = TestClient(app), ws()
    cid, _ = setup_company(c, h, logo=False)
    d = c.post("/v1/presentations/decks", json={"companyId": cid, "storyline": story()}, headers=h).json()
    with _get_sessionmaker()() as s:
        run = PresentationRun(workspace_id=h["X-Workspace-Id"], deck_id=d["id"], revision=1, status="queued", phase="queued", epoch=0, attempts=0)
        s.add(run)
        s.commit()
        epoch = worker.claim(s, run.id)
        assert epoch == 1 and worker.claim(s, run.id) is None  # a live lease cannot be taken twice
        s.query(PresentationRun).filter_by(id=run.id).update({"epoch": 2})  # someone else took over
        s.commit()
        assert worker._phase(s, run.id, epoch, "export") is False
        s.query(PresentationRun).filter_by(id=run.id).update({"status": "cancelled"})
        s.commit()
        assert worker.build(s, run.id) == "cancelled"


def test_tenant_isolation():
    c, h = TestClient(app), ws()
    other = ws()
    cid, kit = setup_company(c, h)
    d = c.post("/v1/presentations/decks", json={"companyId": cid, "storyline": story()}, headers=h).json()
    asset = kit["kit"]["logos"][0]["asset_id"]
    for path in (f"/v1/presentations/decks/{d['id']}", f"/v1/presentations/decks/{d['id']}/revisions/1", f"/v1/presentations/decks/{d['id']}/revisions/1/files/pptx", f"/v1/presentations/assets/{asset}"):
        assert c.get(path, headers=other).status_code == 404
    assert c.post("/v1/presentations/decks", json={"companyId": cid, "storyline": story()}, headers=other).status_code == 404
    assert c.post(f"/v1/presentations/companies/{cid}/brand-kits", json={}, headers=other).status_code == 404
    assert c.get("/v1/presentations/decks", headers=other).json()["items"] == []


def test_genre_starters_all_build():
    c, h = TestClient(app), ws()
    cid, _ = setup_company(c, h, logo=False)
    genres = [g["id"] for g in c.get("/v1/presentations/capabilities").json()["genres"]]
    assert len(genres) == 8
    for g in genres:
        r = c.post("/v1/presentations/decks", json={"companyId": cid, "storyline": starter(c, h, g, f"Topic for {g}")}, headers=h)
        assert r.status_code == 202, (g, r.text)
        head = c.get(f"/v1/presentations/decks/{r.json()['id']}", headers=h).json()["head"]
        assert head["run"]["status"] == "succeeded" and not [f for f in head["findings"] if f["severity"] == "hard"], (g, head["findings"])


def test_weekly_series_is_idempotent_and_never_carries_numbers_forward():
    c, h = TestClient(app), ws()
    cid, _ = setup_company(c, h, logo=False)
    s = c.post("/v1/presentations/series", json={"companyId": cid, "name": "Weekly", "timezone": "Europe/Rome", "storyline": story()}, headers=h)
    assert s.status_code == 201, s.text
    sid = s.json()["id"]
    at = datetime(2026, 9, 28, 7, 0, tzinfo=timezone.utc).isoformat()
    a = c.post(f"/v1/presentations/series/{sid}/prepare", json={"at": at}, headers=h).json()
    b = c.post(f"/v1/presentations/series/{sid}/prepare", json={"at": at}, headers=h).json()
    assert a["created"] is True and b["created"] is False and a["deck"]["id"] == b["deck"]["id"]
    assert a["period"]["key"] == "2026-W39-Europe-Rome" and a["period"]["start"] == "2026-09-20T22:00:00Z"
    r1 = c.get(f"/v1/presentations/decks/{a['deck']['id']}/revisions/1", headers=h).json()["storyline"]
    kpis = next(x for x in r1["slides"] if x["type"] == "kpis")["kpis"]
    assert all(k["value"] == "—" and "delta" not in k for k in kpis)
    chart = next(x for x in r1["slides"] if x["type"] == "chart")["chart"]
    assert chart["series"][0]["values"] == [None, None, None]
    assert next(x for x in r1["slides"] if x["type"] == "cover")["kicker"].startswith("Week 39")
    nxt = c.post(f"/v1/presentations/series/{sid}/prepare", json={"at": datetime(2026, 10, 5, 7, 0, tzinfo=timezone.utc).isoformat()}, headers=h).json()
    assert nxt["created"] and nxt["period"]["key"] == "2026-W40-Europe-Rome" and nxt["deck"]["id"] != a["deck"]["id"]
    assert c.post(f"/v1/presentations/series/{sid}/pause", headers=h).json()["paused"] is True
    assert c.post(f"/v1/presentations/series/{sid}/prepare", json={}, headers=h).status_code == 409


def test_periods_respect_timezones_and_dst():
    # 26 Oct-1 Nov 2026 in Rome starts after the change back to CET (+01:00): local midnight is 23:00Z.
    p = weekly.period("previous_full_week", "Europe/Rome", 0, datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc))
    assert p["key"] == "2026-W44-Europe-Rome"
    assert p["start"] == "2026-10-25T23:00:00Z" and p["end_exclusive"] == "2026-11-01T23:00:00Z"
    # The week that contains the change is 7 days plus one hour long.
    q = weekly.period("previous_full_week", "Europe/Rome", 0, datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc))
    assert q["start"] == "2026-10-18T22:00:00Z" and q["end_exclusive"] == "2026-10-25T23:00:00Z"
    with pytest.raises(ValueError):
        weekly.period("previous_full_week", "Mars/Olympus")
    with pytest.raises(ValueError):
        weekly.period("monthly", "UTC")
    sunday = weekly.period("current_week", "America/New_York", 6, datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc))
    assert sunday["start"] == "2026-03-08T05:00:00Z"  # local midnight on the DST-change Sunday is still EST
