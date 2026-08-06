"""FastAPI dependencies for authentication and role checks.

Every route that needs a role uses `require_role`. No route implements its own
check, so the hierarchy lives in exactly one place.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request

from app.auth.models import Role
from app.auth.security import COOKIE_NAME, AuthError, decode_token
from app.auth.service import get_user
from app.db.engine import get_engine

# Rows a caller may retrieve from the screener, by role. Public gets a wall;
# everyone signed in gets the lot. See docs/prd/04-roles-and-access.md.
ROW_CAPS: dict[Role, int | None] = {
    Role.PUBLIC: 25,
    Role.USER: None,
    Role.ADMIN: None,
    Role.SUPER_ADMIN: None,
}

# Export ceilings per day, by role.
EXPORT_ROW_LIMITS: dict[Role, int] = {
    Role.PUBLIC: 0,
    Role.USER: 5000,
    Role.ADMIN: 5000,
    Role.SUPER_ADMIN: 1_000_000,
}


def current_user(request: Request) -> dict[str, Any] | None:
    """The signed-in user, or None. Never raises for an anonymous caller."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_token(token)
    except AuthError:
        return None
    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        return None
    user = get_user(get_engine(), user_id)
    if user is None or not user["is_active"]:
        return None
    return user


def current_role(user: dict[str, Any] | None = Depends(current_user)) -> Role:
    return Role(user["role"]) if user else Role.PUBLIC


def require_role(minimum: Role):
    """Dependency factory. Roles are hierarchical, so this is a >= test."""

    def dependency(user: dict[str, Any] | None = Depends(current_user)) -> dict[str, Any]:
        if user is None:
            raise HTTPException(status_code=401, detail="Sign in to do that")
        if Role(user["role"]) < minimum:
            raise HTTPException(
                status_code=403,
                detail=f"This needs the {minimum.label.replace('_', ' ')} role",
            )
        return user

    return dependency


require_user = require_role(Role.USER)
require_admin = require_role(Role.ADMIN)
require_super_admin = require_role(Role.SUPER_ADMIN)


def row_cap_for(role: Role) -> int | None:
    return ROW_CAPS.get(role, 25)


def export_limit_for(role: Role) -> int:
    return EXPORT_ROW_LIMITS.get(role, 0)
