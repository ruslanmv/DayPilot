"""Matrix Designer: the design chain, bundle intake, and design review (B8).

DayPilot drives Matrix Designer over four endpoints — propose, adjust, design,
govern — and turns the result into scheduled work. These tests are the consumer
side of a contract mirrored in Matrix Designer's own `tests/test_daypilot_contract.py`:
the golden payloads below are the real service's responses, so a shape change there
fails here.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from daypilot_orchestrator.design.matrix_designer_adapter import (
    DesignerError,
    MatrixDesignerAdapter,
)

client = TestClient(app)


def _ws() -> str:
    return "ws-" + uuid.uuid4().hex[:8]


# --- Golden payloads: what Matrix Designer really returns --------------------

BLUEPRINTS_PAYLOAD = {
    "candidates": [
        {"id": "minimal", "tier": "Minimal", "title": "Minimal controlled blueprint",
         "summary": "Small controlled build package for: a task manager", "file_count": 29,
         "difficulty": "Easy", "estimate": "a weekend",
         "stack": ["Next.js", "FastAPI", "PostgreSQL"], "recommended": False},
        {"id": "standard", "tier": "Standard", "title": "Standard Matrix Bundle",
         "summary": "Recommended controlled blueprint for: a task manager", "file_count": 42,
         "difficulty": "Medium", "estimate": "about one week",
         "stack": ["Next.js", "FastAPI", "PostgreSQL"], "recommended": True},
        {"id": "production", "tier": "Production", "title": "Production controlled blueprint",
         "summary": "Hardened Matrix Bundle with release evidence", "file_count": 59,
         "difficulty": "Hard", "estimate": "about three weeks",
         "stack": ["Next.js", "FastAPI", "PostgreSQL"], "recommended": False},
    ],
    "details": {
        "standard": {
            "candidate_id": "standard",
            "overview": "This standard blueprint builds a task manager.",
            "batches": [
                {"id": "batch-01", "name": "Foundation", "purpose": "Scaffold, config, schema.",
                 "allowed_files": ["apps/web/**"], "depends_on": [],
                 "acceptance_criteria": ["builds", "app boots"],
                 "validation_checks": ["lint", "tests"], "must_not_change": []},
                {"id": "batch-02", "name": "Integrations", "purpose": "Endpoints and jobs.",
                 "allowed_files": ["services/api/**"], "depends_on": ["batch-01"],
                 "acceptance_criteria": ["endpoints respond"],
                 "validation_checks": ["tests"], "must_not_change": []},
            ],
        },
    },
    "matrix_rules": ["RMD-101: AI coders are workers, not architects."],
    "violations": [],
}

BUNDLE_PAYLOAD = {
    "schema_version": "matrix.designer.bundle/v1",
    "design_id": "dsn-a-task-manager-web-app",
    "project": "a-task-manager-web-app",
    "slug": "a-task-manager-web-app",
    "domain": "web-app",
    "quality_level": "standard",
    "source": {"idea": "a task manager web app for small teams"},
    "goal_analysis": {"real_goal": "a task manager web app for small teams",
                      "complexity": "medium"},
    "framework_decision": {"stack": ["Next.js", "FastAPI", "PostgreSQL"],
                           "rationale": "Recommended blueprint stack",
                           "deployment_target": "docker"},
    "architecture": {"routes": ["/", "/app"], "systems": ["Auth", "API", "UI system"]},
    "acceptance": {"functional": ["project builds, lints, boots", "core CRUD path works"],
                   "accessibility": ["keyboard navigable"]},
    "batch_roadmap": [
        {"id": "batch-01", "name": "Project scaffold", "purpose": "Builds, lints, app boots.",
         "allowed_files": ["src/**"], "acceptance": ["builds clean"], "depends_on": [],
         "new_features": [], "must_not_change": []},
        {"id": "batch-02", "name": "Data model + migrations", "purpose": "Schema applies.",
         "allowed_files": ["db/**"], "acceptance": ["migrations apply"],
         "depends_on": ["batch-01"], "new_features": [], "must_not_change": []},
        {"id": "batch-03", "name": "API / services", "purpose": "Endpoints respond.",
         "allowed_files": ["services/api/**"], "acceptance": ["endpoints respond"],
         "depends_on": ["batch-02"], "new_features": [], "must_not_change": []},
    ],
    "governance": {"validation_status": "approved"},
    "provenance": {"created_by": "matrix-designer", "ai_assisted": False,
                   "design_digest": "sha256:abc"},
}

REVIEW_PAYLOAD = {
    "review_id": "rev-dsn-a-task-manager-web-app",
    "target": "a-task-manager-web-app",
    "kind": "design-bundle",
    "status": "needs-repair",
    "score": 68,
    "findings": [
        {"severity": "high", "area": "DESIGN-005", "rule_id": "DESIGN-005",
         "note": "dependency cycle: batch-01 → batch-02 → batch-01"},
        {"severity": "medium", "area": "DESIGN-003", "rule_id": "DESIGN-003",
         "note": "batch b2 depends_on unknown 'ghost'"},
    ],
    "suggestions": ["DESIGN-005: The dependency graph is acyclic"],
    "schema_errors": [],
    "summary": "needs-repair: 0 schema errors, 2 rule violations",
}


def _adapter(payload: dict, expect_path: str | None = None) -> MatrixDesignerAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        if expect_path is not None:
            assert request.url.path == expect_path, f"called {request.url.path}"
        return httpx.Response(200, json=payload)

    return MatrixDesignerAdapter(
        base_url="http://md.test", transport=httpx.MockTransport(handler)
    )


# --- The paths the designer actually serves ---------------------------------

def test_each_step_calls_the_endpoint_the_designer_serves():
    """The whole chain 404s if these drift — this is what that regression looks like."""
    _adapter(BLUEPRINTS_PAYLOAD, "/design/blueprints").generate_blueprints("an idea")
    _adapter(BLUEPRINTS_PAYLOAD, "/design/refine").refine_design("an idea", "add auth")
    _adapter(BUNDLE_PAYLOAD, "/design/bundle").submit_bundle("an idea", candidate_id="standard")
    _adapter(REVIEW_PAYLOAD, "/design/review").review_bundle(BUNDLE_PAYLOAD, "target")


# --- Adapter normalization --------------------------------------------------

def test_blueprints_normalize_into_choosable_candidates():
    proposal = _adapter(BLUEPRINTS_PAYLOAD).generate_blueprints("a task manager")
    assert [c.id for c in proposal.candidates] == ["minimal", "standard", "production"]
    assert proposal.recommended.id == "standard"
    standard = proposal.candidates[1]
    assert standard.estimate == "about one week" and standard.file_count == 42
    # The roadmap preview travels with the candidate so the choice is informed.
    assert [b.id for b in standard.batches] == ["batch-01", "batch-02"]
    assert standard.batches[1].depends_on == ["batch-01"]
    assert standard.batches[0].acceptance == ["builds", "app boots"]


def test_submit_bundle_normalizes_the_design_bundle_document():
    bundle = _adapter(BUNDLE_PAYLOAD).submit_bundle("a task manager", candidate_id="standard")
    assert bundle.bundle_id == "dsn-a-task-manager-web-app"
    assert bundle.title == "a task manager web app for small teams"
    assert bundle.framework == "Next.js, FastAPI, PostgreSQL"
    assert bundle.architecture == "Auth, API, UI system"
    assert bundle.acceptance_criteria[0] == "project builds, lints, boots"
    assert bundle.validation_status == "approved"
    assert len(bundle.batches) == 3
    assert bundle.batches[1].depends_on == ["batch-01"]
    assert bundle.batches[1].description == "Schema applies."
    # Each batch keeps its own guardrail, so a build can be scoped to it.
    assert bundle.batches[2].allowed_files == ["services/api/**"]
    # The original document is kept — a review runs against it, not a lossy copy.
    assert bundle.document["schema_version"] == "matrix.designer.bundle/v1"


def test_a_flat_designer_response_still_schedules_correctly():
    """Tolerant by design: a different designer in front of this adapter still works."""
    flat = {"bundleId": "b-1", "title": "Platformer", "acceptanceCriteria": ["playable"],
            "batches": [{"id": "1", "title": "Scaffold", "acceptance": ["builds"]},
                        {"id": "2", "title": "Player", "dependsOn": ["1"]}]}
    bundle = _adapter(flat).submit_bundle("a platformer")
    assert bundle.title == "Platformer" and len(bundle.batches) == 2
    assert bundle.batches[1].depends_on == ["1"]


def test_review_maps_designer_severities_onto_blocking_severities():
    review = _adapter(REVIEW_PAYLOAD).review_bundle(BUNDLE_PAYLOAD, "dashboard")
    assert review.score == 68 and review.grade == "C"
    assert review.status == "needs-repair"
    # "high" from the designer's rule vocabulary must block in DayPilot's.
    assert [f.severity for f in review.findings] == ["major", "minor"]
    assert review.findings[0].area == "DESIGN-005"


def test_a_refusal_is_raised_not_returned_as_an_empty_plan():
    """The designer answers 200 with an error for refusals; that must not look like success."""
    adapter = _adapter({"error": "idea is required (non-empty).", "candidates": []})
    with pytest.raises(DesignerError):
        adapter.generate_blueprints("   ")
    with pytest.raises(DesignerError):
        _adapter(BUNDLE_PAYLOAD).review_bundle({}, "nothing")


# --- Gateway: the chain end to end (patched adapter) ------------------------

@pytest.fixture()
def patched_designer(monkeypatch):
    from app.routers import design as design_router

    class FakeAdapter:
        generate_blueprints = staticmethod(
            lambda idea, references=None, constraints=None:
            _adapter(BLUEPRINTS_PAYLOAD).generate_blueprints(idea, references, constraints)
        )
        refine_design = staticmethod(
            lambda idea, message, candidate_id="standard", constraints=None:
            _adapter(BLUEPRINTS_PAYLOAD).refine_design(idea, message, candidate_id, constraints)
        )
        submit_bundle = staticmethod(
            lambda idea, blueprint="", candidate_id="":
            _adapter(BUNDLE_PAYLOAD).submit_bundle(idea, blueprint, candidate_id)
        )
        review_bundle = staticmethod(
            lambda bundle, target="", kind="design-bundle":
            _adapter(REVIEW_PAYLOAD).review_bundle(bundle, target, kind)
        )

    monkeypatch.setattr(design_router, "matrix_designer_from_env", lambda: FakeAdapter())


def test_blueprints_endpoint_returns_plans_to_choose_from(patched_designer):
    body = client.post("/v1/design/blueprints", json={"idea": "a task manager"}).json()
    assert [c["id"] for c in body["candidates"]] == ["minimal", "standard", "production"]
    assert body["recommendedId"] == "standard"
    assert body["candidates"][1]["batches"][1]["dependsOn"] == ["batch-01"]


def test_refine_endpoint_adjusts_a_chosen_plan(patched_designer):
    resp = client.post(
        "/v1/design/refine",
        json={"idea": "a task manager", "message": "add SSO", "candidateId": "standard"},
    )
    assert resp.status_code == 200
    assert resp.json()["candidates"]


def test_bundle_intake_creates_project_and_ordered_tasks(patched_designer):
    ws = _ws()
    resp = client.post(
        "/v1/design/bundles",
        json={"idea": "a task manager", "candidateId": "standard", "workspaceId": ws},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["bundle"]["batches"]) == 3
    assert body["bundle"]["validationStatus"] == "approved"
    intake = body["intake"]
    assert intake["batches"] == 3 and len(intake["taskIds"]) == 3

    # The batch tasks are scheduled coding blocks on the new project.
    tasks = client.get(f"/v1/tasks?workspaceId={ws}&limit=50").json()["items"]
    design_tasks = [t for t in tasks if t["source"] == "design_bundle"]
    assert len(design_tasks) == 3
    assert all(t["executor"] == "GitPilot" for t in design_tasks)
    # Dependent batches start blocked; the first one can start now.
    assert any(t["status"] == "blocked" for t in design_tasks)
    assert any(t["status"] == "active" for t in design_tasks)


def test_design_review_attaches_findings_and_raises_blocker(patched_designer):
    ws = _ws()
    resp = client.post(
        "/v1/design/review",
        json={"bundle": BUNDLE_PAYLOAD, "target": "dashboard", "workspaceId": ws},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["grade"] == "C"
    assert len(body["findings"]) == 2

    # A major finding raises a blocker event on the Today stream.
    events = client.get(f"/v1/events?workspaceId={ws}").json()["items"]
    assert any(e["type"] == "blocker.raised" for e in events)


def test_review_from_an_idea_designs_the_bundle_first(patched_designer):
    resp = client.post("/v1/design/review", json={"idea": "a task manager", "workspaceId": _ws()})
    assert resp.status_code == 201
    assert resp.json()["findings"]


def test_review_without_a_bundle_or_an_idea_is_refused(patched_designer):
    assert client.post("/v1/design/review", json={"workspaceId": _ws()}).status_code == 400


def test_an_unreachable_designer_is_a_gateway_error_not_an_empty_plan(monkeypatch):
    """A design step that cannot reach the designer must fail loudly."""
    from app.routers import design as design_router

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(
        design_router, "matrix_designer_from_env",
        lambda: MatrixDesignerAdapter(
            base_url="http://md.test", transport=httpx.MockTransport(unreachable)
        ),
    )
    resp = client.post("/v1/design/blueprints", json={"idea": "a task manager"})
    assert resp.status_code == 502
