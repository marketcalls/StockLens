"""Signup, login, logout and the current session."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.auth.deps import current_user, export_limit_for, require_user, row_cap_for
from app.auth.models import Role
from app.auth.security import COOKIE_NAME, issue_token
from app.auth.service import (
    SignupError,
    authenticate,
    create_user,
    public_user,
    record_audit,
)
from app.auth.service import (
    change_password as change_password_service,
)
from app.config import get_settings
from app.db.engine import get_engine
from app.security.ratelimit import AUTH, READ, SIGNUP, limit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=1024)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=1024)


def _set_session(response: Response, user: dict[str, Any]) -> None:
    settings = get_settings()
    token = issue_token(user["id"], Role(user["role"]))
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.jwt_expiry_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


@router.post(
    "/signup",
    status_code=201,
    dependencies=[Depends(limit(AUTH)), Depends(limit(SIGNUP))],
)
def signup(request: SignupRequest, response: Response) -> dict[str, Any]:
    """Create an account. Always at the USER role - see auth/service.py."""
    try:
        user = create_user(
            get_engine(),
            request.email,
            request.password,
            display_name=request.display_name,
        )
    except SignupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _set_session(response, user)
    return {"user": public_user(user), "limits": _limits(Role(user["role"]))}


@router.post("/login", dependencies=[Depends(limit(AUTH))])
def login(request: LoginRequest, response: Response) -> dict[str, Any]:
    user = authenticate(get_engine(), request.email, request.password)
    if user is None:
        # One message for a wrong password, a missing account and a suspended
        # one, so the response cannot be used to discover who has an account.
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    _set_session(response, user)
    record_audit(get_engine(), actor_id=user["id"], action="user.login")
    return {"user": public_user(user), "limits": _limits(Role(user["role"]))}


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "signed out"}


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=1, max_length=1024)


@router.post("/password", dependencies=[Depends(limit(AUTH))])
def change_password(
    request: PasswordChange, user: dict[str, Any] = Depends(require_user)
) -> dict[str, str]:
    """Change your own password.

    Rate limited with the login bucket: this endpoint verifies a password, so
    left open it is a way to test guesses against a session you already hold.
    """
    try:
        change_password_service(
            get_engine(),
            user_id=user["id"],
            current_password=request.current_password,
            new_password=request.new_password,
        )
    except SignupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "password changed"}


@router.get("/me", dependencies=[Depends(limit(READ))])
def me(user: dict[str, Any] | None = Depends(current_user)) -> dict[str, Any]:
    """Who am I, and what may I do. Safe to call anonymously."""
    role = Role(user["role"]) if user else Role.PUBLIC
    return {
        "user": public_user(user) if user else None,
        "role": role.label,
        "limits": _limits(role),
    }


def _limits(role: Role) -> dict[str, Any]:
    cap = row_cap_for(role)
    return {
        "screener_row_cap": cap,
        "screener_rows_unlimited": cap is None,
        "export_row_limit": export_limit_for(role),
        "can_save_screens": role >= Role.USER,
        "can_use_watchlists": role >= Role.USER,
        "can_export": role >= Role.USER,
        "can_admin": role >= Role.ADMIN,
        "can_manage_platform": role >= Role.SUPER_ADMIN,
        # Every administrative surface - console, people, diagnostics, status -
        # is Super Admin only. Kept separate from can_admin so the two can
        # diverge again without hunting through the front end.
        "can_see_admin_area": role >= Role.SUPER_ADMIN,
    }


@router.get("/limits")
def limits(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return _limits(Role(user["role"]))
