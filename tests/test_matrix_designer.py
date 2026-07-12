"""Tests for Matrix Designer planner + bundle intake + design review (B8)."""
from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from daypilot_orchestrator.design.matrix_designer_adapter import MatrixDesignerAdapter

client = TestClient(app)


def _ws() -> str:
    return "ws-" + uuid.uuid4().hex[:8]


BUNDLE_PAYLOAD = {
    "bundleId": "bundle-1",
    "title": "Platformer Game",
    "framework": "Phaser",
    "visualTarget": "16-bit pixel art",
    "architecture": "entity-component system",
    "acceptanceCriteria": ["playable level", "score HUD"],
    "batches": [
        {"id": "1", "title": "Project scaffold", "acceptance": ["builds"]},
        {"id": "2", "title": "Player controller", "dependsOn": ["1"], "acceptance": ["moves"]},
        {"id": "3", "title": "Level design", "dependsOn": ["2"]},
    ],
}

REVIEW_PAYLOAD = {
    "reviewId": "rev-1",
    "score": 68,
    "findings": [
        {"severity": "major", "area": "contrast", "note": "Low contrast on nav labels"},
        {"severity": "minor", "area": "spacing", "note": "Tighten card padding"},
    ],
    "suggestions": ["Raise text contrast to WCAG AA"],
}


def _adapter(payload: dict) -> MatrixDesignerAdapter:
    return MatrixDesignerAdapter(
        base_url="http://md.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    )


# --- Adapter normalization --------------------------------------------------

def test_submit_bundle_normalizes():
    bundle = _adapter(BUNDLE_PAYLOAD).submit_bundle("a platformer", "phaser blueprint")
    assert bundle.title == "Platformer Game"
    assert len(bundle.batches) == 3
    assert bundle.batches[1].depends_on == ["1"]


def test_review_grades_from_score():
    review = _adapter(REVIEW_PAYLOAD).review_artifact("dashboard.png", "ui")
    assert review.score == 68
    assert review.grade == "C"
    assert any(f.severity == "major" for f in review.findings)


# --- Gateway intake + review (patched adapter) ------------------------------

@pytest.fixture()
def patched_designer(monkeypatch):
    from app.routers import design as design_router

    def fake_bundle(idea="", blueprint=""):
        return _adapter(BUNDLE_PAYLOAD).submit_bundle(idea, blueprint)

    def fake_review(target="", kind="ui", context=""):
        return _adapter(REVIEW_PAYLOAD).review_artifact(target, kind, context)

    class FakeAdapter:
        submit_bundle = staticmethod(fake_bundle)
        review_artifact = staticmethod(fake_review)

    monkeypatch.setattr(design_router, "matrix_designer_from_env", lambda: FakeAdapter())


def test_bundle_intake_creates_project_and_ordered_tasks(patched_designer):
    ws = _ws()
    resp = client.post("/v1/design/bundles", json={"idea": "a platformer", "workspaceId": ws})
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["bundle"]["batches"]) == 3
    intake = body["intake"]
    assert intake["batches"] == 3
    assert len(intake["taskIds"]) == 3

    # The batch tasks are scheduled coding blocks on the new project.
    tasks = client.get(f"/v1/tasks?workspaceId={ws}&limit=50").json()["items"]
    design_tasks = [t for t in tasks if t["source"] == "design_bundle"]
    assert len(design_tasks) == 3
    assert all(t["executor"] == "GitPilot" for t in design_tasks)
    # Dependent batches start blocked.
    assert any(t["status"] == "blocked" for t in design_tasks)


def test_design_review_attaches_findings_and_raises_blocker(patched_designer):
    ws = _ws()
    resp = client.post(
        "/v1/design/review",
        json={"target": "dashboard.png", "kind": "ui", "workspaceId": ws},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["grade"] == "C"
    assert len(body["findings"]) == 2

    # A major finding raises a blocker event on the Today stream.
    events = client.get(f"/v1/events?workspaceId={ws}").json()["items"]
    assert any(e["type"] == "blocker.raised" for e in events)
