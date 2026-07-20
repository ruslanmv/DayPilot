"""Identity & login API (Batch 1).

Cookie-based server sessions: login sets an HttpOnly `dp_session` cookie and a
readable CSRF cookie; cookie-authenticated writes must echo the CSRF token in
an `X-CSRF-Token` header (double-submit). Identity is separate from AI-provider
activation. Auth is opt-in via DAYPILOT_REQUIRE_SESSION so the local-first dev
default keeps working.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import identity
from ..db import get_session

router = APIRouter(prefix="/v1/auth", tags=["auth"])

COOKIE = identity.COOKIE_NAME
CSRF_COOKIE = "dp_csrf"


def _require_session() -> bool:
    return os.getenv("DAYPILOT_REQUIRE_SESSION", "false").lower() == "true"


def _secure_cookies() -> bool:
    # Secure cookies in production; relaxed for http://localhost dev.
    return os.getenv("DAYPILOT_COOKIE_SECURE", "false").lower() == "true"


class BootstrapBody(BaseModel):
    email: str
    password: str
    displayName: str = ""
    workspaceName: str = "My workspace"


class LoginBody(BaseModel):
    email: str
    password: str


def _set_session_cookies(response: Response, token: str, csrf: str) -> None:
    secure = _secure_cookies()
    max_age = int(identity.SESSION_TTL.total_seconds())
    response.set_cookie(COOKIE, token, httponly=True, secure=secure, samesite="lax",
                        max_age=max_age, path="/")
    # CSRF cookie is readable by JS so the SPA can echo it back (double-submit).
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=secure, samesite="lax",
                        max_age=max_age, path="/")


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.get("/config")
def config(session: Session = Depends(get_session)) -> dict[str, Any]:
    """What the login UI needs before rendering: whether auth is required and
    whether the first owner still needs to be created."""
    return {
        "authRequired": _require_session(),
        "bootstrapRequired": identity.bootstrap_required(session),
        "cloudLoginAvailable": False,  # wired in Batch 2 (server-owned Cloud auth)
        "ssoAvailable": False,
    }


@router.post("/bootstrap", status_code=201)
def bootstrap(body: BootstrapBody, response: Response, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        identity.bootstrap(session, body.email, body.password, body.displayName, body.workspaceName)
    except PermissionError:
        raise HTTPException(status_code=409, detail="bootstrap_already_done")
    except ValueError:
        raise HTTPException(status_code=422, detail="weak_password")
    # Log the new owner straight in.
    result = identity.local_login(session, body.email, body.password)
    _set_session_cookies(response, result["token"], result["csrf"])
    return {"user": result["user"]}


@router.post("/local/login")
def local_login(body: LoginBody, response: Response, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        result = identity.local_login(session, body.email, body.password)
    except PermissionError as exc:
        code = str(exc)
        status = 429 if code == "account_locked" else 401
        raise HTTPException(status_code=status, detail=code)
    _set_session_cookies(response, result["token"], result["csrf"])
    return {"user": result["user"]}


def current_user(
    session: Session = Depends(get_session),
    dp_session: str | None = Cookie(default=None),
) -> tuple[Any, Any]:
    resolved = identity.resolve_session(session, dp_session)
    if resolved is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return resolved


@router.get("/me")
def me(current: tuple = Depends(current_user)) -> dict[str, Any]:
    user, auth_session = current
    return {"user": identity.me(user, auth_session.workspace_id)}


def _check_csrf(request: Request, auth_session: Any, x_csrf_token: str | None) -> None:
    if not x_csrf_token or x_csrf_token != auth_session.csrf_token:
        raise HTTPException(status_code=403, detail="csrf_failed")


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    dp_session: str | None = Cookie(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> dict[str, Any]:
    resolved = identity.resolve_session(session, dp_session)
    if resolved is not None:
        _check_csrf(request, resolved[1], x_csrf_token)
        identity.logout(session, dp_session)
    _clear_session_cookies(response)
    return {"loggedOut": True}


@router.post("/logout-all")
def logout_all(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    current: tuple = Depends(current_user),
    x_csrf_token: str | None = Header(default=None),
) -> dict[str, Any]:
    user, auth_session = current
    _check_csrf(request, auth_session, x_csrf_token)
    count = identity.logout_all(session, user.id)
    _clear_session_cookies(response)
    return {"revoked": count}
