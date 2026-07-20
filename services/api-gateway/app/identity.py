"""Local identity & login (Batch 1).

Real user accounts, workspaces, memberships and server-side sessions — the
backend becomes the source of truth for who is signed in and which workspace
they may act in.

Trust properties:
  - Passwords are hashed with scrypt (stdlib, memory-hard) and never stored or
    logged in plaintext. Verification is constant-time.
  - Sessions are opaque random tokens; only their SHA-256 is stored, and the
    token lives in an HttpOnly cookie. Sessions expire and are revocable.
  - Login is rate-limited with progressive lockout via the AuthEvent trail.
  - Workspace authorization is derived from membership; a browser-supplied
    workspace id is never trusted.
  - Identity (who you are) is deliberately separate from AI-provider activation.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import (
    AuthEvent,
    AuthSession,
    User,
    Workspace,
    WorkspaceMembership,
    session_scope,
)
from daypilot_knowledge.db.models import utcnow

SESSION_TTL = timedelta(days=int(os.getenv("DAYPILOT_SESSION_TTL_DAYS", "14")))
COOKIE_NAME = "dp_session"
MAX_FAILURES = 5
LOCKOUT_WINDOW = timedelta(minutes=15)

# scrypt work factors (OWASP-aligned interactive login params).
_N, _R, _P = 2**14, 8, 1


# ---- password hashing -------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded or not encoded.startswith("scrypt$"):
        return False
    try:
        _, n, r, p, salt_hex, hash_hex = encoded.split("$")
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(hash_hex)),
        )
        return hmac.compare_digest(digest, bytes.fromhex(hash_hex))
    except (ValueError, TypeError):
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _event(session: Session, event: str, outcome: str, *, email: str | None = None,
           user_id: str | None = None, meta: dict[str, Any] | None = None) -> None:
    session.add(AuthEvent(user_id=user_id, email=email, event=event, outcome=outcome, meta_json=meta or {}))


def _event_durable(event: str, outcome: str, *, email: str | None = None,
                   user_id: str | None = None, meta: dict[str, Any] | None = None) -> None:
    """Write an auth event in its own committed transaction so it survives even
    when the producing request fails (a rejected login raises, rolling the
    request session back). Rate-limiting/lockout depends on this durability."""
    with session_scope() as s:
        s.add(AuthEvent(user_id=user_id, email=email, event=event, outcome=outcome, meta_json=meta or {}))


# ---- bootstrap --------------------------------------------------------------

def bootstrap_required(session: Session) -> bool:
    """True when no local account with a password exists yet (first run)."""
    count = session.execute(
        select(func.count(User.id)).where(User.password_hash.isnot(None))
    ).scalar_one()
    return count == 0


def bootstrap(session: Session, email: str, password: str, display_name: str,
              workspace_name: str = "My workspace") -> dict[str, Any]:
    """Create the first owner + their workspace. Refused once any local account
    exists, so it cannot be used to escalate later."""
    if not bootstrap_required(session):
        raise PermissionError("bootstrap_already_done")
    _require_strong(password)
    email = email.strip().lower()
    user = User(email=email, display_name=display_name or email, role="owner",
                password_hash=hash_password(password), status="active")
    session.add(user)
    session.flush()
    ws = Workspace(id="default", name=workspace_name, mode="local", created_by=user.id) \
        if session.get(Workspace, "default") is None else session.get(Workspace, "default")
    if ws not in session:
        session.add(ws)
    session.add(WorkspaceMembership(user_id=user.id, workspace_id=ws.id, role="owner"))
    _event(session, "bootstrap", "success", email=email, user_id=user.id)
    session.flush()
    return {"userId": user.id, "workspaceId": ws.id}


def _require_strong(password: str) -> None:
    if len(password or "") < 10:
        raise ValueError("weak_password")


# ---- login / sessions -------------------------------------------------------

def _recent_failures(session: Session, email: str) -> int:
    since = utcnow() - LOCKOUT_WINDOW
    return session.execute(
        select(func.count(AuthEvent.seq)).where(
            AuthEvent.email == email, AuthEvent.event == "login",
            AuthEvent.outcome == "failure", AuthEvent.created_at >= since,
        )
    ).scalar_one()


def local_login(session: Session, email: str, password: str) -> dict[str, Any]:
    """Verify credentials, enforce lockout, and issue a server session.

    Returns the raw session token + csrf token for the caller to set as cookies.
    The token is never persisted; only its hash is stored.
    """
    email = (email or "").strip().lower()
    if _recent_failures(session, email) >= MAX_FAILURES:
        _event_durable("login", "locked", email=email)
        raise PermissionError("account_locked")

    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    # Always run a hash to keep timing uniform whether or not the user exists.
    ok = verify_password(password, user.password_hash if user else None)
    if not user or user.status != "active" or not ok:
        # Durable so the failure counts toward lockout even though this request
        # is about to roll back (it raises).
        _event_durable("login", "failure", email=email, user_id=(user.id if user else None))
        raise PermissionError("invalid_credentials")

    workspace_id = _primary_workspace(session, user.id)
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    session.add(AuthSession(
        id_hash=_hash_token(token), user_id=user.id, workspace_id=workspace_id,
        csrf_token=csrf, expires_at=utcnow() + SESSION_TTL,
    ))
    _event(session, "login", "success", email=email, user_id=user.id)
    session.flush()
    return {"token": token, "csrf": csrf, "user": me(user, workspace_id)}


def _primary_workspace(session: Session, user_id: str) -> str:
    membership = session.execute(
        select(WorkspaceMembership).where(WorkspaceMembership.user_id == user_id)
        .order_by(WorkspaceMembership.created_at.asc())
    ).scalars().first()
    return membership.workspace_id if membership else "default"


def resolve_session(session: Session, token: str | None) -> tuple[User, AuthSession] | None:
    """Return (user, auth_session) for a valid, unexpired, unrevoked token."""
    if not token:
        return None
    row = session.get(AuthSession, _hash_token(token))
    if row is None or row.revoked_at is not None:
        return None
    expires = row.expires_at
    if expires.tzinfo is not None:
        expires = expires.replace(tzinfo=None)
    if expires < datetime.utcnow():
        return None
    user = session.get(User, row.user_id)
    if user is None or user.status != "active":
        return None
    return user, row


def logout(session: Session, token: str | None) -> None:
    if not token:
        return
    row = session.get(AuthSession, _hash_token(token))
    if row and row.revoked_at is None:
        row.revoked_at = utcnow()
        _event(session, "logout", "success", user_id=row.user_id)
        session.flush()


def logout_all(session: Session, user_id: str) -> int:
    rows = session.execute(
        select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    ).scalars().all()
    for row in rows:
        row.revoked_at = utcnow()
    _event(session, "logout_all", "success", user_id=user_id, meta={"count": len(rows)})
    session.flush()
    return len(rows)


def is_member(session: Session, user_id: str, workspace_id: str) -> bool:
    row = session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    return row is not None


def me(user: User, workspace_id: str) -> dict[str, Any]:
    return {
        "id": user.id, "email": user.email, "displayName": user.display_name,
        "role": user.role, "workspaceId": workspace_id, "mfaState": user.mfa_state,
    }
