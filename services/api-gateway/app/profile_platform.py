"""Server-owned AI profile, goals, and onboarding progress (Phase 1).

The backend is the single source of truth for the signed-in person's AI profile
and their first-run completion — the browser may cache a revision/ETag and a
draft, but never owns state. Ownership is derived from the authenticated session
(or, when session enforcement is off, a well-defined local owner resolved
server-side); a browser-supplied user/workspace id is never trusted.

Writes use optimistic concurrency: a stale ``If-Match`` revision returns
``409 profile_revision_conflict`` with the current value. Every category/consent
change, export, reset, and onboarding completion emits an audit event that lists
*changed field names only* — never the values.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import (
    AuditLog,
    CalendarAccount,
    KnowledgeSource,
    OnboardingProgress,
    User,
    UserAiProfile,
    UserProfileGoal,
    UserProfileObservation,
    WorkspaceMembership,
)

from . import identity
from .profile_schemas import (
    DEFAULT_CATEGORY_CONSENT,
    GoalCreate,
    GoalUpdate,
    ProfileUpdate,
)

LOCAL_OWNER_ID = "local-owner"
DEFAULT_WORKSPACE = "default"
REQUIRED_STEPS = ("welcome", "about_you", "review")


class ProfileConflict(Exception):
    """Raised on a stale If-Match; carries the current server revision + value."""

    def __init__(self, revision: int, current: dict[str, Any]) -> None:
        super().__init__("profile_revision_conflict")
        self.revision = revision
        self.current = current


class ProfileValidation(Exception):
    """Required-field failure on onboarding completion."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__("required_fields_missing")
        self.missing = missing


@dataclass(frozen=True)
class Owner:
    user_id: str
    workspace_id: str
    csrf_token: Optional[str]  # present only for a real cookie session


# --- ownership resolution ----------------------------------------------------

def resolve_owner(session: Session, token: Optional[str], require_session: bool) -> Owner:
    """Resolve (user, workspace) from the session cookie, or a well-defined local
    owner when session enforcement is disabled. Never accepts a client-supplied
    id, so object ids alone can never authorize access."""
    resolved = identity.resolve_session(session, token)
    if resolved is not None:
        user, auth_session = resolved
        return Owner(user.id, auth_session.workspace_id, auth_session.csrf_token)
    if require_session:
        raise PermissionError("not_authenticated")
    # Local-first: the canonical owner is the bootstrapped account (first user
    # with a password) + its primary workspace; else a stable synthetic owner.
    user = session.execute(
        select(User).where(User.password_hash.isnot(None)).order_by(User.created_at.asc())
    ).scalars().first()
    if user is not None:
        return Owner(user.id, _primary_workspace(session, user.id), None)
    return Owner(LOCAL_OWNER_ID, DEFAULT_WORKSPACE, None)


def _primary_workspace(session: Session, user_id: str) -> str:
    row = session.execute(
        select(WorkspaceMembership).where(WorkspaceMembership.user_id == user_id)
        .order_by(WorkspaceMembership.created_at.asc())
    ).scalars().first()
    return row.workspace_id if row else DEFAULT_WORKSPACE


# --- audit -------------------------------------------------------------------

def _audit(session: Session, owner: Owner, event_type: str, changed: list[str]) -> None:
    actor = owner.user_id if session.get(User, owner.user_id) is not None else None
    session.add(AuditLog(
        actor_user_id=actor,
        event_type=event_type,
        decision="recorded",
        # Field/category NAMES only — never the values, which may be personal.
        payload_json={"workspaceId": owner.workspace_id, "fields": sorted(changed)},
    ))


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


# --- profile CRUD ------------------------------------------------------------

def _get_profile(session: Session, owner: Owner) -> Optional[UserAiProfile]:
    return session.execute(
        select(UserAiProfile).where(
            UserAiProfile.user_id == owner.user_id,
            UserAiProfile.workspace_id == owner.workspace_id,
        )
    ).scalar_one_or_none()


def serialize_profile(row: Optional[UserAiProfile]) -> dict[str, Any]:
    if row is None:
        return {
            "revision": 0, "schemaVersion": 1, "exists": False,
            "timezone": None, "locale": None, "preferredName": None, "pronouns": None,
            "useCases": [], "schedule": {}, "planning": {}, "communication": {},
            "accessibility": {}, "boundaries": {},
            "categoryConsent": dict(DEFAULT_CATEGORY_CONSENT),
            "reviewedAt": None, "updatedAt": None,
        }
    consent = {**DEFAULT_CATEGORY_CONSENT, **(row.category_consent_json or {})}
    return {
        "revision": row.revision, "schemaVersion": row.schema_version, "exists": True,
        "timezone": row.timezone, "locale": row.locale,
        "preferredName": row.preferred_name, "pronouns": row.pronouns,
        "useCases": row.use_cases_json or [],
        "schedule": row.schedule_json or {},
        "planning": row.planning_json or {},
        "communication": row.communication_json or {},
        "accessibility": row.accessibility_json or {},
        "boundaries": row.boundaries_json or {},
        "categoryConsent": consent,
        "reviewedAt": _iso(row.reviewed_at), "updatedAt": _iso(row.updated_at),
    }


# Camel-cased payload keys (the API speaks camelCase) → ORM columns. Nested
# category documents are stored as camelCase JSON exactly as validated.
_FIELD_MAP = {
    "timezone": "timezone", "locale": "locale",
    "preferredName": "preferred_name", "pronouns": "pronouns",
    "useCases": "use_cases_json", "schedule": "schedule_json",
    "planning": "planning_json", "communication": "communication_json",
    "accessibility": "accessibility_json", "boundaries": "boundaries_json",
}


def apply_profile_update(
    session: Session, owner: Owner, update: ProfileUpdate, if_match: Optional[str],
) -> dict[str, Any]:
    """Merge the provided (set) fields, bumping the revision. A stale If-Match on
    an existing profile raises ProfileConflict."""
    row = _get_profile(session, owner)
    provided = update.model_dump(exclude_unset=True, mode="json", by_alias=True)

    if row is None:
        row = UserAiProfile(user_id=owner.user_id, workspace_id=owner.workspace_id, revision=1)
        session.add(row)
    else:
        if if_match is None or _as_int(if_match) != row.revision:
            raise ProfileConflict(row.revision, serialize_profile(row))
        row.revision += 1

    changed: list[str] = []
    for key, value in provided.items():
        if key == "categoryConsent":
            merged = {**(row.category_consent_json or {}), **(value or {})}
            row.category_consent_json = merged
            changed.append("categoryConsent")
            continue
        col = _FIELD_MAP.get(key)
        if col is None:
            continue
        setattr(row, col, value)
        changed.append(key)

    session.flush()
    _audit(session, owner, "profile.updated", changed)
    session.flush()
    return serialize_profile(row)


def _as_int(v: str) -> int:
    try:
        return int(str(v).strip().strip('"'))
    except (TypeError, ValueError):
        return -1


def reset_learned(session: Session, owner: Owner) -> dict[str, Any]:
    """Delete confirmed + suggested observations (a one-click "forget what you
    learned"). Rejected rows are kept so their suppression still holds, and the
    reset is audited."""
    rows = session.execute(
        select(UserProfileObservation).where(
            UserProfileObservation.user_id == owner.user_id,
            UserProfileObservation.workspace_id == owner.workspace_id,
            UserProfileObservation.state.in_(("suggested", "confirmed")),
        )
    ).scalars().all()
    for row in rows:
        session.delete(row)
    _audit(session, owner, "profile.learned_reset", ["observations"])
    session.flush()
    return {"reset": True, "removed": len(rows)}


# --- observations (consented learning) ---------------------------------------

_OBS_CATEGORIES = {"schedule", "planning", "communication", "identity", "boundaries", "goals"}


def _serialize_observation(o: UserProfileObservation) -> dict[str, Any]:
    return {
        "id": o.id, "category": o.category, "value": o.value_json or {},
        "sourceType": o.source_type, "confidence": o.confidence,
        "state": o.state, "observedAt": _iso(o.observed_at), "expiresAt": _iso(o.expires_at),
    }


def _obs_expired(o: UserProfileObservation) -> bool:
    if o.expires_at is None:
        return False
    exp = o.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp < datetime.now(timezone.utc)


def list_observations(session: Session, owner: Owner, state: Optional[str] = None) -> dict[str, Any]:
    stmt = select(UserProfileObservation).where(
        UserProfileObservation.user_id == owner.user_id,
        UserProfileObservation.workspace_id == owner.workspace_id,
    )
    if state:
        stmt = stmt.where(UserProfileObservation.state == state)
    rows = session.execute(stmt.order_by(UserProfileObservation.observed_at.desc())).scalars().all()
    return {"observations": [_serialize_observation(o) for o in rows]}


def record_observation(
    session: Session, owner: Owner, category: str, value: dict[str, Any], *,
    source_type: str = "inferred", source_ref: Optional[str] = None,
    confidence: float = 0.5, ttl_days: Optional[int] = 90,
) -> Optional[dict[str, Any]]:
    """Record a learned SUGGESTION (never durable on its own). Suppressed when an
    equivalent (category, value) was previously rejected, so a rejection is not
    re-surfaced. Returns None when suppressed or the category is unknown."""
    if category not in _OBS_CATEGORIES:
        return None
    existing = session.execute(
        select(UserProfileObservation).where(
            UserProfileObservation.user_id == owner.user_id,
            UserProfileObservation.workspace_id == owner.workspace_id,
            UserProfileObservation.category == category,
        )
    ).scalars().all()
    for o in existing:
        if o.value_json == value and o.state in ("rejected", "suggested", "confirmed"):
            return None  # already known or explicitly rejected → do not duplicate
    expires = datetime.utcnow() + timedelta(days=ttl_days) if ttl_days else None
    obs = UserProfileObservation(
        user_id=owner.user_id, workspace_id=owner.workspace_id, category=category,
        value_json=value, source_type=source_type, source_ref=source_ref,
        confidence=confidence, expires_at=expires, state="suggested",
    )
    session.add(obs)
    session.flush()
    return _serialize_observation(obs)


def _owned_observation(session: Session, owner: Owner, obs_id: str) -> Optional[UserProfileObservation]:
    o = session.get(UserProfileObservation, obs_id)
    if o is None or o.user_id != owner.user_id or o.workspace_id != owner.workspace_id:
        return None
    return o


def decide_observation(session: Session, owner: Owner, obs_id: str, decision: str) -> Optional[dict[str, Any]]:
    o = _owned_observation(session, owner, obs_id)
    if o is None:
        return None
    o.state = "confirmed" if decision == "confirm" else "rejected"
    session.flush()
    _audit(session, owner, "profile.observation_" + o.state, [o.category])
    session.flush()
    return _serialize_observation(o)


def export_profile(session: Session, owner: Owner) -> dict[str, Any]:
    row = _get_profile(session, owner)
    goals = list_goals(session, owner)
    _audit(session, owner, "profile.exported", ["profile", "goals"])
    session.flush()
    return {
        "profile": serialize_profile(row),
        "goals": goals["goals"],
        "exportedAt": datetime.utcnow().isoformat(),
    }


# --- goals -------------------------------------------------------------------

def _serialize_goal(g: UserProfileGoal) -> dict[str, Any]:
    return {
        "id": g.id, "title": g.title, "detail": g.detail, "status": g.status,
        "priority": g.priority, "reviewAt": _iso(g.review_at),
        "createdAt": _iso(g.created_at), "updatedAt": _iso(g.updated_at),
    }


def list_goals(session: Session, owner: Owner) -> dict[str, Any]:
    rows = session.execute(
        select(UserProfileGoal).where(
            UserProfileGoal.user_id == owner.user_id,
            UserProfileGoal.workspace_id == owner.workspace_id,
        ).order_by(UserProfileGoal.priority.asc(), UserProfileGoal.created_at.asc())
    ).scalars().all()
    return {"goals": [_serialize_goal(g) for g in rows]}


def create_goal(session: Session, owner: Owner, body: GoalCreate) -> dict[str, Any]:
    active = session.execute(
        select(UserProfileGoal).where(
            UserProfileGoal.user_id == owner.user_id,
            UserProfileGoal.workspace_id == owner.workspace_id,
            UserProfileGoal.status == "active",
        )
    ).scalars().all()
    # The product asks for "up to three current outcomes"; extra goals land as
    # 'upcoming' rather than being rejected, so nothing the user typed is lost.
    status = "active" if len(active) < 3 else "upcoming"
    goal = UserProfileGoal(
        user_id=owner.user_id, workspace_id=owner.workspace_id,
        title=body.title, detail=body.detail, priority=body.priority,
        status=status, review_at=_parse_dt(body.review_at),
    )
    session.add(goal)
    session.flush()
    _audit(session, owner, "profile.goal_created", ["goal"])
    session.flush()
    return _serialize_goal(goal)


def _owned_goal(session: Session, owner: Owner, goal_id: str) -> Optional[UserProfileGoal]:
    g = session.get(UserProfileGoal, goal_id)
    if g is None or g.user_id != owner.user_id or g.workspace_id != owner.workspace_id:
        return None
    return g


def update_goal(session: Session, owner: Owner, goal_id: str, body: GoalUpdate) -> Optional[dict[str, Any]]:
    g = _owned_goal(session, owner, goal_id)
    if g is None:
        return None
    provided = body.model_dump(exclude_unset=True)
    for key in ("title", "detail", "status", "priority"):
        if key in provided and provided[key] is not None:
            setattr(g, key, provided[key])
    if "review_at" in provided:
        g.review_at = _parse_dt(provided["review_at"])
    session.flush()
    _audit(session, owner, "profile.goal_updated", list(provided.keys()))
    session.flush()
    return _serialize_goal(g)


def delete_goal(session: Session, owner: Owner, goal_id: str) -> bool:
    g = _owned_goal(session, owner, goal_id)
    if g is None:
        return False
    session.delete(g)
    _audit(session, owner, "profile.goal_deleted", ["goal"])
    session.flush()
    return True


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


# --- onboarding --------------------------------------------------------------

def _get_progress(session: Session, owner: Owner) -> Optional[OnboardingProgress]:
    return session.execute(
        select(OnboardingProgress).where(
            OnboardingProgress.user_id == owner.user_id,
            OnboardingProgress.workspace_id == owner.workspace_id,
        )
    ).scalar_one_or_none()


def _get_or_create_progress(session: Session, owner: Owner) -> OnboardingProgress:
    row = _get_progress(session, owner)
    if row is None:
        row = OnboardingProgress(user_id=owner.user_id, workspace_id=owner.workspace_id)
        session.add(row)
        session.flush()
    return row


def _capability_status(session: Session, owner: Owner) -> dict[str, Any]:
    """Compute integration completion from AUTHORITATIVE resource state — never a
    stored 'I typed a mailbox' flag. Each block is defensive: a missing/failed
    integration must not break the onboarding view."""
    provider = {"connected": False}
    try:
        from . import providers_platform
        pstat = providers_platform.status(session, owner.workspace_id)
        provider = {"connected": pstat.get("active") is not None, "active": pstat.get("active")}
    except Exception:  # noqa: BLE001
        pass

    mail = {"connected": False}
    try:
        from . import mail_setup
        mstat = mail_setup.mailbox_status(session, owner.workspace_id)
        mail = {"connected": bool(mstat.get("connected"))}
    except Exception:  # noqa: BLE001
        pass

    calendar = {"connected": False}
    try:
        rows = session.execute(
            select(CalendarAccount).where(CalendarAccount.user_id == owner.user_id)
        ).scalars().all()
        calendar = {"connected": any(a.sync_state in ("connected", "enabled", "active") for a in rows)}
    except Exception:  # noqa: BLE001
        pass

    knowledge = {"connected": False, "count": 0}
    try:
        rows = session.execute(
            select(KnowledgeSource).where(KnowledgeSource.workspace_id == owner.workspace_id)
        ).scalars().all()
        knowledge = {"connected": len(rows) > 0, "count": len(rows)}
    except Exception:  # noqa: BLE001
        pass

    return {"provider": provider, "mail": mail, "calendar": calendar, "knowledge": knowledge}


def _completeness(profile: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    if not profile.get("timezone"):
        missing.append("timezone")
    if not profile.get("useCases"):
        missing.append("useCases")
    return {
        "requiredComplete": len(missing) == 0,
        "missing": missing,
        "hasSchedule": bool(profile.get("schedule")),
        "hasCommunication": bool(profile.get("communication")),
        "reviewed": profile.get("reviewedAt") is not None,
    }


def onboarding_view(session: Session, owner: Owner) -> dict[str, Any]:
    """Single view model: progress + profile completeness + capability status, so
    the UI decides whether to open the wizard without racing several requests."""
    row = _get_progress(session, owner)
    profile = serialize_profile(_get_profile(session, owner))
    return {
        "flowVersion": row.flow_version if row else 1,
        "status": row.status if row else "not_started",
        "currentStep": row.current_step if row else "welcome",
        "completedSteps": (row.completed_steps_json or []) if row else [],
        "dismissedAt": _iso(row.dismissed_at) if row else None,
        "completedAt": _iso(row.completed_at) if row else None,
        "profile": {**profile, "completeness": _completeness(profile)},
        "capabilities": _capability_status(session, owner),
    }


def patch_onboarding(
    session: Session, owner: Owner, *,
    current_step: Optional[str] = None,
    completed_steps: Optional[list[str]] = None,
    dismissed: Optional[bool] = None,
) -> dict[str, Any]:
    """Save navigation/dismissal only. Never marks the flow completed — that is a
    validated action through /complete."""
    row = _get_or_create_progress(session, owner)
    if row.status == "not_started":
        row.status = "in_progress"
    if current_step is not None:
        row.current_step = current_step
    if completed_steps is not None:
        row.completed_steps_json = sorted(set(completed_steps))
    if dismissed:
        row.dismissed_at = datetime.utcnow()
    session.flush()
    return onboarding_view(session, owner)


def complete_onboarding(session: Session, owner: Owner) -> dict[str, Any]:
    """Validate the required minimum + record the review. Idempotent: completing
    an already-complete flow returns the same state without error."""
    profile_row = _get_profile(session, owner)
    profile = serialize_profile(profile_row)
    completeness = _completeness(profile)
    if not completeness["requiredComplete"]:
        raise ProfileValidation(completeness["missing"])

    row = _get_or_create_progress(session, owner)
    already = row.status == "completed"
    row.status = "completed"
    if row.completed_at is None:
        row.completed_at = datetime.utcnow()
    if "review" not in (row.completed_steps_json or []):
        row.completed_steps_json = sorted(set((row.completed_steps_json or []) + ["review"]))
    if profile_row is not None and profile_row.reviewed_at is None:
        profile_row.reviewed_at = datetime.utcnow()
    session.flush()
    if not already:
        _audit(session, owner, "onboarding.completed", ["status", "reviewed_at"])
        session.flush()
    return onboarding_view(session, owner)


def import_legacy(session: Session, owner: Owner, fields: dict[str, Any]) -> dict[str, Any]:
    """One-time migration of SAFE legacy ``daypilot.profile`` fields into the
    server profile. Only allowlisted, non-secret keys are honored; anything
    resembling a credential is ignored. Existing declared values win, so an
    import never overwrites something the user already set on the server."""
    row = _get_profile(session, owner)
    if row is None:
        row = UserAiProfile(user_id=owner.user_id, workspace_id=owner.workspace_id, revision=1)
        session.add(row)
    changed: list[str] = []
    tz = fields.get("timezone")
    if tz and not row.timezone:
        try:
            from .profile_schemas import validate_timezone
            row.timezone = validate_timezone(tz)
            changed.append("timezone")
        except ValueError:
            pass
    name = fields.get("preferredName") or fields.get("name")
    if name and not row.preferred_name:
        row.preferred_name = str(name)[:120]
        changed.append("preferred_name")
    session.flush()
    if changed:
        _audit(session, owner, "profile.legacy_imported", changed)
        session.flush()
    return {"imported": changed, "profile": serialize_profile(row)}
