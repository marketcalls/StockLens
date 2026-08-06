"""User administration.

The rules that matter here are the ones that stop an administrator locking
everyone out, including themselves. They live in this module rather than in the
routes so a script or an agent cannot go around them.

Accounts are deactivated, never deleted. A deleted account takes its audit trail
with it, and the audit log is the record of who changed what.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, func, or_, select

from app.auth.models import Role, app_user, audit_log, saved_screen, watchlist
from app.auth.security import email_problem, normalise_email
from app.auth.service import public_user, record_audit
from app.db.engine import get_engine
from app.services.errors import Conflict, Forbidden, NotFound

# How many audit entries a user detail view carries.
AUDIT_PAGE = 25


def _engine(engine: Engine | None = None) -> Engine:
    return engine or get_engine()


def _row(conn, user_id: int) -> dict[str, Any]:
    row = conn.execute(select(app_user).where(app_user.c.id == user_id)).mappings().first()
    if row is None:
        raise NotFound(f"No account with the id {user_id}", user_id=user_id)
    return dict(row)


def _super_admin_count(conn, *, active_only: bool = True) -> int:
    query = (
        select(func.count()).select_from(app_user).where(app_user.c.role == int(Role.SUPER_ADMIN))
    )
    if active_only:
        query = query.where(app_user.c.is_active.is_(True))
    return conn.execute(query).scalar_one()


def _assert_may_manage(actor: dict[str, Any], target: dict[str, Any]) -> None:
    """An admin may not act on a super admin, nor grant what they do not hold.

    Without this an admin could promote themselves, which makes the two roles
    the same role.
    """
    if actor["role"] < int(Role.ADMIN):
        raise Forbidden("Managing accounts requires administrator access")
    if target["role"] >= int(Role.SUPER_ADMIN) and actor["role"] < int(Role.SUPER_ADMIN):
        raise Forbidden(
            "Only a super administrator can act on another super administrator",
            target_role=Role(target["role"]).label,
        )


def listing(
    *,
    term: str | None = None,
    role: str | None = None,
    include_inactive: bool = True,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Every account, with what each one owns."""
    db = _engine(engine)
    with db.connect() as conn:
        query = select(app_user)
        if term:
            like = f"%{term.strip().lower()}%"
            query = query.where(
                or_(
                    func.lower(app_user.c.email).like(like),
                    func.lower(func.coalesce(app_user.c.display_name, "")).like(like),
                )
            )
        if role:
            match = next((r for r in Role if r.label == role), None)
            if match is None:
                raise NotFound(
                    f"No role called {role!r}",
                    role=role,
                    known=[r.label for r in Role if r is not Role.PUBLIC],
                )
            query = query.where(app_user.c.role == int(match))
        if not include_inactive:
            query = query.where(app_user.c.is_active.is_(True))

        rows = conn.execute(query.order_by(app_user.c.id)).mappings().all()

        screens = dict(
            conn.execute(
                select(saved_screen.c.user_id, func.count()).group_by(saved_screen.c.user_id)
            ).all()
        )
        lists = dict(
            conn.execute(
                select(watchlist.c.user_id, func.count()).group_by(watchlist.c.user_id)
            ).all()
        )
        super_admins = _super_admin_count(conn)

    users = []
    for row in rows:
        user = public_user(dict(row))
        user["is_active"] = bool(row["is_active"])
        user["created_at"] = row["created_at"]
        user["last_login_at"] = row["last_login_at"]
        user["saved_screens"] = screens.get(row["id"], 0)
        user["watchlists"] = lists.get(row["id"], 0)
        users.append(user)

    return {
        "total": len(users),
        "users": users,
        # The console needs this to explain why the last super admin cannot be
        # demoted, rather than only refusing.
        "active_super_admins": super_admins,
    }


def detail(user_id: int, *, engine: Engine | None = None) -> dict[str, Any]:
    """One account, what it owns, and what has been done to it."""
    db = _engine(engine)
    with db.connect() as conn:
        row = _row(conn, user_id)
        screens = (
            conn.execute(
                select(saved_screen.c.id, saved_screen.c.name, saved_screen.c.query)
                .where(saved_screen.c.user_id == user_id)
                .order_by(saved_screen.c.updated_at.desc())
            )
            .mappings()
            .all()
        )
        lists = (
            conn.execute(
                select(watchlist.c.id, watchlist.c.name).where(watchlist.c.user_id == user_id)
            )
            .mappings()
            .all()
        )
        # Both what they did and what was done to them.
        trail = (
            conn.execute(
                select(audit_log)
                .where(
                    or_(
                        audit_log.c.actor_id == user_id,
                        audit_log.c.target == str(user_id),
                    )
                )
                .order_by(audit_log.c.created_at.desc())
                .limit(AUDIT_PAGE)
            )
            .mappings()
            .all()
        )

    user = public_user(row)
    user["is_active"] = bool(row["is_active"])
    user["created_at"] = row["created_at"]
    user["last_login_at"] = row["last_login_at"]
    return {
        "user": user,
        "saved_screens": [dict(s) for s in screens],
        "watchlists": [dict(w) for w in lists],
        "audit": [dict(a) for a in trail],
    }


def change_role(
    actor: dict[str, Any], user_id: int, role: str, *, engine: Engine | None = None
) -> dict[str, Any]:
    """Move an account to another role, refusing the changes that lock people out."""
    match = next((r for r in Role if r.label == role), None)
    if match is None or match is Role.PUBLIC:
        raise NotFound(
            f"No role called {role!r}",
            role=role,
            known=[r.label for r in Role if r is not Role.PUBLIC],
        )

    db = _engine(engine)
    with db.connect() as conn:
        target = _row(conn, user_id)
        _assert_may_manage(actor, target)

        if int(match) > actor["role"]:
            raise Forbidden(
                "You cannot grant a role above your own",
                requested=role,
                yours=Role(actor["role"]).label,
            )
        if actor["id"] == user_id and int(match) < actor["role"]:
            # Demoting yourself is how an administrator accidentally locks
            # themselves out of the console mid-task.
            raise Conflict("You cannot lower your own role. Ask another administrator.")
        if (
            target["role"] == int(Role.SUPER_ADMIN)
            and int(match) < int(Role.SUPER_ADMIN)
            and _super_admin_count(conn) <= 1
        ):
            raise Conflict(
                "That is the only active super administrator. Promote another one first.",
                user_id=user_id,
            )

    with db.begin() as conn:
        conn.execute(app_user.update().where(app_user.c.id == user_id).values(role=int(match)))
    record_audit(
        db,
        actor_id=actor["id"],
        action="user.role",
        target=str(user_id),
        detail={"from": Role(target["role"]).label, "to": role},
    )
    return detail(user_id, engine=db)


def set_active(
    actor: dict[str, Any], user_id: int, active: bool, *, engine: Engine | None = None
) -> dict[str, Any]:
    """Suspend or restore an account.

    Accounts are never deleted - the audit log refers to them, and a deleted
    account makes its own history unreadable.
    """
    db = _engine(engine)
    with db.connect() as conn:
        target = _row(conn, user_id)
        _assert_may_manage(actor, target)

        if actor["id"] == user_id and not active:
            raise Conflict("You cannot deactivate your own account.")
        if not active and target["role"] == int(Role.SUPER_ADMIN) and _super_admin_count(conn) <= 1:
            raise Conflict(
                "That is the only active super administrator. Promote another one first.",
                user_id=user_id,
            )

    with db.begin() as conn:
        conn.execute(app_user.update().where(app_user.c.id == user_id).values(is_active=active))
    record_audit(
        db,
        actor_id=actor["id"],
        action="user.activate" if active else "user.deactivate",
        target=str(user_id),
    )
    return detail(user_id, engine=db)


def invite(
    actor: dict[str, Any],
    email: str,
    role: str = "user",
    *,
    display_name: str | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Create an account for someone else, with a one-time password to hand over.

    There is no mail server in a self-hosted install, so the password is returned
    once, here, and never again - it is stored only as a hash.
    """
    import secrets

    problem = email_problem(email)
    if problem:
        raise Conflict(problem, email=email)

    match = next((r for r in Role if r.label == role), None)
    if match is None or match is Role.PUBLIC:
        raise NotFound(f"No role called {role!r}", role=role)
    if actor["role"] < int(Role.ADMIN):
        raise Forbidden("Creating accounts requires administrator access")
    if int(match) > actor["role"]:
        raise Forbidden("You cannot grant a role above your own", requested=role)

    from app.auth.service import SignupError, create_user

    password = secrets.token_urlsafe(12)
    try:
        user = create_user(
            _engine(engine),
            email=normalise_email(email),
            password=password,
            role=match,
            display_name=display_name,
        )
    except SignupError as exc:
        raise Conflict(str(exc), email=email) from exc

    record_audit(
        _engine(engine),
        actor_id=actor["id"],
        action="user.invite",
        target=str(user["id"]),
        detail={"role": role},
    )
    return {
        "user": public_user(user),
        # Shown once. Nothing can recover it afterwards.
        "one_time_password": password,
    }


def roles() -> list[dict[str, Any]]:
    """The roles that can be assigned, and what each one gets."""
    return [
        {"value": r.label, "rank": int(r), "label": r.label.replace("_", " ").title()}
        for r in Role
        if r is not Role.PUBLIC
    ]


def stats(*, engine: Engine | None = None) -> dict[str, Any]:
    """Headline counts for the console."""
    with _engine(engine).connect() as conn:
        by_role = dict(
            conn.execute(select(app_user.c.role, func.count()).group_by(app_user.c.role)).all()
        )
        inactive = conn.execute(
            select(func.count()).select_from(app_user).where(app_user.c.is_active.is_(False))
        ).scalar_one()
        total = conn.execute(select(func.count()).select_from(app_user)).scalar_one()
    return {
        "total": total,
        "inactive": inactive,
        "by_role": {Role(rank).label: count for rank, count in by_role.items()},
    }
