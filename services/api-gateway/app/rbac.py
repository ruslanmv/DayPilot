"""Role-based access control (batch B11).

Roles are ranked; a route requires a minimum role. Enforced at the router layer
(and, for tool execution, at the MCP host). Local-first default principal is
owner, so single-user installs are unaffected.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException

from .auth import Principal, get_principal

# Higher rank = more privilege.
ROLE_RANK = {"read_only": 0, "reviewer": 1, "operator": 2, "owner": 3}


def require_role(minimum: str):
    """Dependency factory: require at least `minimum` role to proceed."""
    min_rank = ROLE_RANK.get(minimum, 99)

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if ROLE_RANK.get(principal.role, -1) < min_rank:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{principal.role}' lacks required role '{minimum}'.",
            )
        return principal

    return _dep


# Common gates.
require_reviewer = require_role("reviewer")
require_operator = require_role("operator")
require_owner = require_role("owner")
