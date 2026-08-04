"""AI profile, goals, and onboarding — durable server-owned foundation (Phase 1).

Exercises the real backend contract: ownership is derived server-side (never a
client-supplied id), cookie-authenticated writes require CSRF, profile writes
use optimistic concurrency (If-Match/revision), validation rejects unknown
fields / invalid timezones / overlapping windows / oversized text, goals are
tenant-isolated, onboarding completion is validated + idempotent, export leaks
no secrets, and every change records an audit event that lists field NAMES only.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import identity
from app import profile_platform as pp
from app.main import app
from daypilot_knowledge.db import (
    AuditLog,
    User,
    WorkspaceMembership,
    create_engine_from_settings,
    session_scope,
)

client = TestClient(app)
ENGINE = create_engine_from_settings()


# --- helpers -----------------------------------------------------------------

def _owner() -> pp.Owner:
    """A distinct tenant-scoped owner for direct platform-level tests."""
    return pp.Owner(user_id=f"u-{uuid.uuid4().hex}", workspace_id=f"ws-{uuid.uuid4().hex[:8]}", csrf_token=None)


def _logged_in_client() -> tuple[TestClient, str]:
    """A fresh member user in their own workspace, logged in. Returns (client, csrf)."""
    email = f"profile-{uuid.uuid4().hex[:8]}@example.com"
    ws = f"ws-{uuid.uuid4().hex[:8]}"
    with session_scope(ENGINE) as s:
        u = User(email=email, display_name="P", role="owner",
                 password_hash=identity.hash_password("a-strong-password"))
        s.add(u)
        s.flush()
        s.add(WorkspaceMembership(user_id=u.id, workspace_id=ws, role="owner"))
    c = TestClient(app)
    r = c.post("/v1/auth/local/login", json={"email": email, "password": "a-strong-password"})
    assert r.status_code == 200
    return c, c.cookies.get("dp_csrf")


# --- profile CRUD + optimistic concurrency -----------------------------------

def test_profile_put_creates_then_patch_bumps_revision():
    c, csrf = _logged_in_client()
    h = {"X-CSRF-Token": csrf}
    empty = c.get("/v1/profile/ai").json()
    assert empty["exists"] is False and empty["revision"] == 0

    put = c.put("/v1/profile/ai", headers=h, json={
        "timezone": "Europe/Paris",
        "useCases": ["plan_day", "manage_projects"],
        "planning": {"focusMinutes": 90},
    })
    assert put.status_code == 200
    body = put.json()
    assert body["revision"] == 1 and body["timezone"] == "Europe/Paris"
    assert body["planning"]["focusMinutes"] == 90

    patched = c.patch("/v1/profile/ai", headers={**h, "If-Match": '"1"'},
                      json={"locale": "fr-FR"}).json()
    assert patched["revision"] == 2 and patched["locale"] == "fr-FR"
    # Earlier fields survive the partial merge.
    assert patched["timezone"] == "Europe/Paris"


def test_stale_if_match_conflicts_with_current_value():
    c, csrf = _logged_in_client()
    h = {"X-CSRF-Token": csrf}
    c.put("/v1/profile/ai", headers=h, json={"timezone": "UTC"})
    # Revision is now 1; a write claiming an older revision must 409.
    resp = c.patch("/v1/profile/ai", headers={**h, "If-Match": '"0"'}, json={"locale": "en-US"})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "profile_revision_conflict"
    assert detail["revision"] == 1 and detail["current"]["timezone"] == "UTC"


def test_missing_if_match_on_existing_profile_conflicts():
    c, csrf = _logged_in_client()
    h = {"X-CSRF-Token": csrf}
    c.put("/v1/profile/ai", headers=h, json={"timezone": "UTC"})
    assert c.patch("/v1/profile/ai", headers=h, json={"locale": "en-US"}).status_code == 409


# --- validation --------------------------------------------------------------

def test_validation_rejects_unknown_and_malformed_fields():
    c, csrf = _logged_in_client()
    h = {"X-CSRF-Token": csrf}
    assert c.put("/v1/profile/ai", headers=h, json={"unknownField": 1}).status_code == 422
    assert c.put("/v1/profile/ai", headers=h, json={"timezone": "Not/AZone"}).status_code == 422
    assert c.put("/v1/profile/ai", headers=h, json={"useCases": ["not_a_real_use_case"]}).status_code == 422
    # Overlapping windows on the same day.
    overlap = c.put("/v1/profile/ai", headers=h, json={"schedule": {"workingWindows": [
        {"days": [1], "start": "09:00", "end": "12:00"},
        {"days": [1], "start": "11:00", "end": "17:00"},
    ]}})
    assert overlap.status_code == 422
    # Inverted window.
    assert c.put("/v1/profile/ai", headers=h, json={"schedule": {"workingWindows": [
        {"days": [1], "start": "18:00", "end": "09:00"}]}}).status_code == 422
    # Oversized free-form text.
    assert c.put("/v1/profile/ai", headers=h, json={
        "boundaries": {"notes": "x" * 5000}}).status_code == 422


# --- CSRF --------------------------------------------------------------------

def test_cookie_write_requires_csrf():
    c, csrf = _logged_in_client()
    # No CSRF header on a cookie-authenticated write → rejected.
    assert c.put("/v1/profile/ai", json={"timezone": "UTC"}).status_code == 403
    assert c.put("/v1/profile/ai", headers={"X-CSRF-Token": "wrong"},
                 json={"timezone": "UTC"}).status_code == 403
    # Correct token passes.
    assert c.put("/v1/profile/ai", headers={"X-CSRF-Token": csrf},
                 json={"timezone": "UTC"}).status_code == 200


# --- goals + tenant isolation ------------------------------------------------

def test_goals_crud_and_extra_goals_go_upcoming():
    c, csrf = _logged_in_client()
    h = {"X-CSRF-Token": csrf}
    ids = []
    for i in range(4):
        r = c.post("/v1/profile/goals", headers=h, json={"title": f"Goal {i}", "priority": 1})
        assert r.status_code == 201
        ids.append(r.json()["id"])
    goals = c.get("/v1/profile/goals").json()["goals"]
    statuses = [g["status"] for g in goals]
    assert statuses.count("active") == 3 and statuses.count("upcoming") == 1

    # Patch + delete round-trip.
    assert c.patch(f"/v1/profile/goals/{ids[0]}", headers=h,
                   json={"status": "archived"}).json()["status"] == "archived"
    assert c.delete(f"/v1/profile/goals/{ids[1]}", headers=h).status_code == 204
    assert c.delete(f"/v1/profile/goals/{ids[1]}", headers=h).status_code == 404


def test_goal_ownership_is_isolated_by_id():
    # Platform-level IDOR check: owner B cannot touch owner A's goal by id.
    from app.profile_schemas import GoalCreate, GoalUpdate
    a, b = _owner(), _owner()
    with session_scope(ENGINE) as s:
        goal = pp.create_goal(s, a, GoalCreate(title="A's private goal"))
        gid = goal["id"]
    with session_scope(ENGINE) as s:
        assert pp.update_goal(s, b, gid, GoalUpdate(title="hijack")) is None
        assert pp.delete_goal(s, b, gid) is False
        # A still owns it, untouched.
        assert pp.update_goal(s, a, gid, GoalUpdate(title="renamed"))["title"] == "renamed"


# --- onboarding --------------------------------------------------------------

def test_onboarding_view_reports_not_started_and_capabilities():
    c, _ = _logged_in_client()
    view = c.get("/v1/onboarding").json()
    assert view["status"] == "not_started"
    assert view["profile"]["completeness"]["requiredComplete"] is False
    caps = view["capabilities"]
    assert set(caps) == {"provider", "mail", "calendar", "knowledge"}
    assert caps["provider"]["connected"] is False


def test_onboarding_complete_requires_minimum_then_is_idempotent():
    c, csrf = _logged_in_client()
    h = {"X-CSRF-Token": csrf}
    # Missing timezone + use cases → refused with the missing list.
    fail = c.post("/v1/onboarding/complete", headers=h)
    assert fail.status_code == 422
    assert set(fail.json()["detail"]["missing"]) == {"timezone", "useCases"}

    c.put("/v1/profile/ai", headers=h, json={"timezone": "UTC", "useCases": ["plan_day"]})
    done = c.post("/v1/onboarding/complete", headers=h)
    assert done.status_code == 200
    body = done.json()
    assert body["status"] == "completed" and body["completedAt"]
    assert body["profile"]["reviewedAt"] is not None
    # Idempotent: completing again does not error and keeps the same completedAt.
    again = c.post("/v1/onboarding/complete", headers=h).json()
    assert again["status"] == "completed" and again["completedAt"] == body["completedAt"]


def test_onboarding_patch_saves_navigation_but_never_completes():
    c, csrf = _logged_in_client()
    h = {"X-CSRF-Token": csrf}
    view = c.patch("/v1/onboarding", headers=h,
                   json={"currentStep": "how_you_work", "completedSteps": ["welcome", "about_you"]}).json()
    assert view["status"] == "in_progress" and view["currentStep"] == "how_you_work"
    assert view["completedSteps"] == ["about_you", "welcome"]
    # Dismissing records a timestamp but keeps status in_progress (not completed).
    dismissed = c.patch("/v1/onboarding", headers=h, json={"dismissed": True}).json()
    assert dismissed["dismissedAt"] is not None and dismissed["status"] != "completed"


# --- export + audit redaction ------------------------------------------------

def test_export_returns_profile_and_goals_without_secrets():
    c, csrf = _logged_in_client()
    h = {"X-CSRF-Token": csrf}
    c.put("/v1/profile/ai", headers=h, json={"timezone": "Europe/Berlin", "preferredName": "Sam"})
    c.post("/v1/profile/goals", headers=h, json={"title": "Ship it"})
    raw = c.get("/v1/profile/ai/export")
    assert raw.status_code == 200
    data = raw.json()
    assert data["profile"]["timezone"] == "Europe/Berlin"
    assert data["goals"][0]["title"] == "Ship it"
    text = raw.text
    assert "password" not in text and "secret" not in text and "csrf" not in text.lower()


def test_audit_records_field_names_not_values():
    owner = _owner()
    from app.profile_schemas import ProfileUpdate
    with session_scope(ENGINE) as s:
        pp.apply_profile_update(s, owner, ProfileUpdate.model_validate(
            {"timezone": "Asia/Tokyo", "preferredName": "Kenji"}), None)
    with session_scope(ENGINE) as s:
        rows = s.execute(
            select(AuditLog).where(AuditLog.event_type == "profile.updated")
        ).scalars().all()
        payloads = [r.payload_json for r in rows]
    # At least one audit row lists the changed field NAMES.
    assert any("timezone" in p.get("fields", []) for p in payloads)
    # The personal VALUES never appear in any audit payload.
    blob = str(payloads)
    assert "Asia/Tokyo" not in blob and "Kenji" not in blob


def test_observation_endpoints_confirm_reject_and_reset():
    c, csrf = _logged_in_client()
    h = {"X-CSRF-Token": csrf}
    rec = c.post("/v1/profile/ai/observations", headers=h,
                 json={"category": "communication", "value": {"tone": "direct"}})
    assert rec.status_code == 201 and rec.json()["recorded"] is True
    oid = rec.json()["observation"]["id"]
    # Duplicate is suppressed, not an error.
    dup = c.post("/v1/profile/ai/observations", headers=h,
                 json={"category": "communication", "value": {"tone": "direct"}})
    assert dup.json()["recorded"] is False
    # Suggested list shows it; confirm moves it to confirmed.
    assert any(o["id"] == oid for o in c.get("/v1/profile/ai/observations?state=suggested").json()["observations"])
    assert c.post(f"/v1/profile/ai/observations/{oid}/confirm", headers=h).json()["state"] == "confirmed"
    # Reset removes the confirmed observation.
    assert c.delete("/v1/profile/ai/learned", headers=h).json()["removed"] >= 1


def test_legacy_import_only_honors_safe_fields():
    owner = _owner()
    with session_scope(ENGINE) as s:
        out = pp.import_legacy(s, owner, {
            "timezone": "America/New_York", "name": "Legacy Sam",
            "apiKey": "sk-should-be-ignored", "password": "nope",
        })
    assert "timezone" in out["imported"] and "preferred_name" in out["imported"]
    assert out["profile"]["timezone"] == "America/New_York"
    # Nothing resembling a credential was imported.
    assert "sk-should-be-ignored" not in str(out)
