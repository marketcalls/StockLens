"""Account administration. Admin and above.

Thin wrappers over app/services/users, which holds the rules that stop an
administrator locking everyone out.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.deps import require_admin
from app.services import users

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


class RoleChange(BaseModel):
    role: str


class ActiveChange(BaseModel):
    active: bool


class Invite(BaseModel):
    email: str
    role: str = "user"
    display_name: str | None = Field(default=None, max_length=120)


@router.get("")
def list_users(
    q: str | None = None, role: str | None = None, include_inactive: bool = True
) -> dict[str, Any]:
    return users.listing(term=q, role=role, include_inactive=include_inactive)


@router.get("/roles")
def roles() -> dict[str, Any]:
    return {"roles": users.roles()}


@router.get("/stats")
def stats() -> dict[str, Any]:
    return users.stats()


@router.get("/{user_id}")
def user_detail(user_id: int) -> dict[str, Any]:
    return users.detail(user_id)


@router.patch("/{user_id}/role")
def change_role(
    user_id: int, request: RoleChange, actor: dict = Depends(require_admin)
) -> dict[str, Any]:
    return users.change_role(actor, user_id, request.role)


@router.patch("/{user_id}/active")
def set_active(
    user_id: int, request: ActiveChange, actor: dict = Depends(require_admin)
) -> dict[str, Any]:
    return users.set_active(actor, user_id, request.active)


@router.post("")
def invite(request: Invite, actor: dict = Depends(require_admin)) -> dict[str, Any]:
    """Create an account and return a one-time password to hand over.

    A self-hosted install has no mail server, so the password is shown once here
    and stored only as a hash.
    """
    return users.invite(actor, request.email, request.role, display_name=request.display_name)
