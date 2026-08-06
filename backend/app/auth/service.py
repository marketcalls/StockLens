"""Account operations. No HTTP here, so the rules are testable directly."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, func, select

from app.auth.models import Role, app_user, audit_log
from app.auth.security import (
    hash_password,
    needs_rehash,
    normalise_email,
    password_problem,
    verify_password,
)


class SignupError(ValueError):
    pass


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def record_audit(
    engine: Engine,
    *,
    actor_id: int | None,
    action: str,
    target: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            audit_log.insert().values(
                actor_id=actor_id,
                action=action,
                target=target,
                detail=json.dumps(detail) if detail else None,
                created_at=utcnow(),
            )
        )


def user_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(app_user)).scalar_one()


def get_user_by_email(engine: Engine, email: str) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = (
            conn.execute(select(app_user).where(app_user.c.email == normalise_email(email)))
            .mappings()
            .first()
        )
    return dict(row) if row else None


def get_user(engine: Engine, user_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(select(app_user).where(app_user.c.id == user_id)).mappings().first()
    return dict(row) if row else None


def create_user(
    engine: Engine,
    email: str,
    password: str,
    *,
    display_name: str | None = None,
    role: Role = Role.USER,
) -> dict[str, Any]:
    """Create an account. Self-service signup always passes Role.USER.

    There is deliberately no path from a web form to any elevated role: the
    first Super Admin is made by the CLI, and every later one by an existing
    Super Admin.
    """
    email = normalise_email(email)
    if not email or "@" not in email:
        raise SignupError("Enter a valid email address")

    problem = password_problem(password)
    if problem:
        raise SignupError(problem)

    if get_user_by_email(engine, email) is not None:
        raise SignupError("An account with that email already exists")

    with engine.begin() as conn:
        result = conn.execute(
            app_user.insert().values(
                email=email,
                password_hash=hash_password(password),
                display_name=(display_name or email.split("@")[0]).strip(),
                role=int(role),
                is_active=True,
                email_verified=False,
                created_at=utcnow(),
            )
        )
        user_id = result.inserted_primary_key[0]

    record_audit(
        engine, actor_id=user_id, action="user.created", target=email, detail={"role": role.label}
    )
    created = get_user(engine, user_id)
    assert created is not None
    return created


def authenticate(engine: Engine, email: str, password: str) -> dict[str, Any] | None:
    """Return the user, or None. Never says which half was wrong."""
    user = get_user_by_email(engine, email)
    if user is None:
        # Hash anyway so a missing account and a wrong password take a similar
        # amount of time, and the response cannot be used to enumerate emails.
        hash_password(password)
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    if not user["is_active"]:
        return None

    updates: dict[str, Any] = {"last_login_at": utcnow()}
    if needs_rehash(user["password_hash"]):
        updates["password_hash"] = hash_password(password)
    with engine.begin() as conn:
        conn.execute(app_user.update().where(app_user.c.id == user["id"]).values(**updates))
    return {**user, **updates}


def set_role(engine: Engine, *, actor_id: int, user_id: int, role: Role) -> dict[str, Any]:
    user = get_user(engine, user_id)
    if user is None:
        raise ValueError(f"No user with id {user_id}")
    with engine.begin() as conn:
        conn.execute(app_user.update().where(app_user.c.id == user_id).values(role=int(role)))
    record_audit(
        engine,
        actor_id=actor_id,
        action="user.role_changed",
        target=user["email"],
        detail={"from": Role(user["role"]).label, "to": role.label},
    )
    updated = get_user(engine, user_id)
    assert updated is not None
    return updated


def set_active(engine: Engine, *, actor_id: int, user_id: int, active: bool) -> None:
    with engine.begin() as conn:
        conn.execute(app_user.update().where(app_user.c.id == user_id).values(is_active=active))
    record_audit(
        engine,
        actor_id=actor_id,
        action="user.activated" if active else "user.suspended",
        target=str(user_id),
    )


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    """The shape sent to a client. Never includes the password hash."""
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": Role(user["role"]).label,
        "role_level": user["role"],
        "is_active": bool(user["is_active"]),
        "email_verified": bool(user["email_verified"]),
        "created_at": user["created_at"],
        "last_login_at": user.get("last_login_at"),
    }
