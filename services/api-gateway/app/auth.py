"""Authentication and workspace membership (batch B11).

Local-first by default: with no tokens configured, every request runs as the
default workspace owner, so a single-user desktop install needs no login. When
DAYPILOT_AUTH_ENABLED=true and DAYPILOT_AUTH_TOKENS is set, a bearer token is
required and mapped to a role — the same code path serves team deployments.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    workspace_id: str = "default"


DEFAULT_OWNER = Principal(subject="local-owner", role="owner")


def _auth_enabled() -> bool:
    return os.getenv("DAYPILOT_AUTH_ENABLED", "false").lower() == "true"


def _token_map() -> dict[str, str]:
    # "tokenA:owner,tokenB:reviewer"
    raw = os.getenv("DAYPILOT_AUTH_TOKENS", "")
    out: dict[str, str] = {}
    for pair in raw.split(","):
        if ":" in pair:
            token, role = pair.split(":", 1)
            out[token.strip()] = role.strip()
    return out


def get_principal(authorization: str | None = Header(default=None)) -> Principal:
    """FastAPI dependency resolving the caller's identity + role."""
    if not _auth_enabled():
        return DEFAULT_OWNER
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    role = _token_map().get(token)
    if role is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return Principal(subject=f"token:{token[:6]}…", role=role)
