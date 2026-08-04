"""Consented learning — observations lifecycle + context precedence (P4).

No silent memory: an observation is only a suggestion until the user confirms
it; only confirmed, non-expired observations enter the context projection;
declared profile values always outrank a confirmed observation; rejections
suppress repeat suggestions; and the learned-reset deletes confirmed/suggested
rows (keeping rejections so their suppression holds).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import profile_platform as pp
from daypilot_knowledge.db import UserAiProfile, UserProfileObservation, session_scope
from daypilot_orchestrator.profile.context_builder import build_projection


def _owner() -> pp.Owner:
    return pp.Owner(user_id=f"u-{uuid.uuid4().hex}", workspace_id=f"ws-{uuid.uuid4().hex[:8]}", csrf_token=None)


def _seed_profile(owner: pp.Owner, **cols) -> None:
    with session_scope() as s:
        s.add(UserAiProfile(user_id=owner.user_id, workspace_id=owner.workspace_id, revision=1, **cols))


# --- lifecycle ---------------------------------------------------------------

def test_observation_suggested_then_confirmed_and_reject_suppresses():
    owner = _owner()
    with session_scope() as s:
        rec = pp.record_observation(s, owner, "communication", {"tone": "direct"})
        assert rec["state"] == "suggested"
        oid = rec["id"]
    # A duplicate suggestion is suppressed (not re-created).
    with session_scope() as s:
        assert pp.record_observation(s, owner, "communication", {"tone": "direct"}) is None
    # Confirm it.
    with session_scope() as s:
        assert pp.decide_observation(s, owner, oid, "confirm")["state"] == "confirmed"
    # Reject a different suggestion, then re-suggesting the rejected value is suppressed.
    with session_scope() as s:
        rec2 = pp.record_observation(s, owner, "planning", {"focusMinutes": 120})
        pid = rec2["id"]
    with session_scope() as s:
        assert pp.decide_observation(s, owner, pid, "reject")["state"] == "rejected"
    with session_scope() as s:
        assert pp.record_observation(s, owner, "planning", {"focusMinutes": 120}) is None


def test_observation_ownership_isolated():
    a, b = _owner(), _owner()
    with session_scope() as s:
        oid = pp.record_observation(s, a, "communication", {"tone": "formal"})["id"]
    with session_scope() as s:
        assert pp.decide_observation(s, b, oid, "confirm") is None  # not B's to touch


# --- context precedence ------------------------------------------------------

def test_only_confirmed_observations_enter_context():
    owner = _owner()
    _seed_profile(owner, timezone="UTC", category_consent_json={})
    with session_scope() as s:
        # A suggested (unconfirmed) communication observation must NOT appear.
        pp.record_observation(s, owner, "communication", {"tone": "direct"})
    with session_scope() as s:
        proj = build_projection(s, workspace_id=owner.workspace_id, user_id=owner.user_id, purpose="drafting").to_dict()
    assert "communication" not in proj  # unconfirmed → excluded


def test_confirmed_observation_fills_gap_but_declared_wins():
    owner = _owner()
    # Declared communication has a tone; planning is absent.
    _seed_profile(owner, communication_json={"tone": "formal"})
    with session_scope() as s:
        c = pp.record_observation(s, owner, "communication", {"tone": "direct", "detail": "concise"})
        pl = pp.record_observation(s, owner, "planning", {"focusMinutes": 90})
        pp.decide_observation(s, owner, c["id"], "confirm")
        pp.decide_observation(s, owner, pl["id"], "confirm")
    with session_scope() as s:
        proj = build_projection(s, workspace_id=owner.workspace_id, user_id=owner.user_id, purpose="planning").to_dict()
    # Planning was absent → observation fills it, tagged observed.
    assert proj["planning"]["focusMinutes"] == 90
    assert proj["provenance"]["planning"] == "observed"
    # Drafting: declared tone wins over the observed tone; observed 'detail' fills the gap.
    with session_scope() as s:
        draft = build_projection(s, workspace_id=owner.workspace_id, user_id=owner.user_id, purpose="drafting").to_dict()
    assert draft["communication"]["tone"] == "formal"  # declared precedence
    assert draft["communication"].get("detail") == "concise"  # observed gap-fill
    assert draft["provenance"]["communication"] == "declared"  # declared populated it first


def test_expired_confirmed_observation_never_enters_context():
    owner = _owner()
    _seed_profile(owner)
    with session_scope() as s:
        o = UserProfileObservation(
            user_id=owner.user_id, workspace_id=owner.workspace_id, category="planning",
            value_json={"focusMinutes": 45}, state="confirmed",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        s.add(o)
    with session_scope() as s:
        proj = build_projection(s, workspace_id=owner.workspace_id, user_id=owner.user_id, purpose="planning").to_dict()
    assert "planning" not in proj  # expired → ignored


def test_consent_off_excludes_observed_category():
    owner = _owner()
    _seed_profile(owner, category_consent_json={"planning": False})
    with session_scope() as s:
        o = pp.record_observation(s, owner, "planning", {"focusMinutes": 30})
        pp.decide_observation(s, owner, o["id"], "confirm")
    with session_scope() as s:
        proj = build_projection(s, workspace_id=owner.workspace_id, user_id=owner.user_id, purpose="planning").to_dict()
    assert "planning" not in proj  # consent off → not even a confirmed observation


# --- reset -------------------------------------------------------------------

def test_reset_learned_deletes_confirmed_and_suggested_keeps_rejected():
    owner = _owner()
    with session_scope() as s:
        a = pp.record_observation(s, owner, "communication", {"tone": "direct"})
        b = pp.record_observation(s, owner, "planning", {"focusMinutes": 60})
        pp.decide_observation(s, owner, a["id"], "confirm")
        pp.decide_observation(s, owner, b["id"], "reject")
    with session_scope() as s:
        out = pp.reset_learned(s, owner)
    assert out["removed"] == 1  # the confirmed one; the rejected stays
    with session_scope() as s:
        remaining = s.execute(
            select(UserProfileObservation).where(UserProfileObservation.user_id == owner.user_id)
        ).scalars().all()
    assert len(remaining) == 1 and remaining[0].state == "rejected"
