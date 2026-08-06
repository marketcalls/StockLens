"""Account administration, and the rules that stop a lockout.

Everything here is about the ways an administrator can accidentally or
deliberately remove everyone's access, including their own.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from app.auth.models import Role, create_auth
from app.auth.service import create_user
from app.db.engine import build_engine
from app.db.models import create_all
from app.services import users
from app.services.errors import Conflict, Forbidden, NotFound


@pytest.fixture
def db(tmp_path) -> Engine:
    engine = build_engine(tmp_path / "users.db")
    raw = build_engine(tmp_path / "raw.db")
    create_all(engine, raw)
    create_auth(engine)
    return engine


def _make(db: Engine, email: str, role: Role) -> dict:
    return create_user(db, email=email, password="a-long-enough-password", role=role)


def test_the_only_super_admin_cannot_be_demoted(db: Engine) -> None:
    owner = _make(db, "owner@stocklens.local", Role.SUPER_ADMIN)
    spare = _make(db, "spare@stocklens.local", Role.SUPER_ADMIN)

    # Two exist, so demoting one is allowed.
    users.change_role(owner, spare["id"], "user", engine=db)
    assert users.listing(engine=db)["active_super_admins"] == 1

    # Owner is now the last one. Someone else with the rank must still be
    # refused - the guard is about how many remain, not about who is asking.
    another = _make(db, "another@stocklens.local", Role.SUPER_ADMIN)
    users.change_role(owner, another["id"], "user", engine=db)

    with pytest.raises(Conflict, match="only active super administrator"):
        users.change_role(owner | {"id": 999}, owner["id"], "user", engine=db)


def test_the_only_super_admin_cannot_be_deactivated(db: Engine) -> None:
    owner = _make(db, "owner@stocklens.local", Role.SUPER_ADMIN)
    spare = _make(db, "spare@stocklens.local", Role.SUPER_ADMIN)

    # Two active, so suspending one is allowed.
    users.set_active(owner, spare["id"], False, engine=db)
    assert users.listing(engine=db)["active_super_admins"] == 1

    # Owner is the last active one, and suspending it would leave nobody able
    # to run the console.
    with pytest.raises(Conflict, match="only active super administrator"):
        users.set_active(spare | {"is_active": True}, owner["id"], False, engine=db)


def test_you_cannot_lower_your_own_role(db: Engine) -> None:
    # The classic way to lock yourself out of the console mid-task.
    owner = _make(db, "owner@stocklens.local", Role.SUPER_ADMIN)
    _make(db, "spare@stocklens.local", Role.SUPER_ADMIN)

    with pytest.raises(Conflict, match="lower your own role"):
        users.change_role(owner, owner["id"], "user", engine=db)


def test_you_cannot_deactivate_yourself(db: Engine) -> None:
    owner = _make(db, "owner@stocklens.local", Role.SUPER_ADMIN)
    _make(db, "spare@stocklens.local", Role.SUPER_ADMIN)

    with pytest.raises(Conflict, match="deactivate your own"):
        users.set_active(owner, owner["id"], False, engine=db)


def test_an_admin_cannot_promote_themselves(db: Engine) -> None:
    # Without this the two roles are the same role.
    admin = _make(db, "admin@stocklens.local", Role.ADMIN)

    with pytest.raises(Forbidden, match="above your own"):
        users.change_role(admin, admin["id"], "super_admin", engine=db)


def test_an_admin_cannot_touch_a_super_admin(db: Engine) -> None:
    admin = _make(db, "admin@stocklens.local", Role.ADMIN)
    owner = _make(db, "owner@stocklens.local", Role.SUPER_ADMIN)

    with pytest.raises(Forbidden, match="super administrator"):
        users.change_role(admin, owner["id"], "user", engine=db)
    with pytest.raises(Forbidden, match="super administrator"):
        users.set_active(admin, owner["id"], False, engine=db)


def test_an_ordinary_user_cannot_manage_anyone(db: Engine) -> None:
    plain = _make(db, "plain@stocklens.local", Role.USER)
    other = _make(db, "other@stocklens.local", Role.USER)

    with pytest.raises(Forbidden):
        users.change_role(plain, other["id"], "admin", engine=db)


def test_a_super_admin_can_demote_another_when_one_remains(db: Engine) -> None:
    owner = _make(db, "owner@stocklens.local", Role.SUPER_ADMIN)
    other = _make(db, "other@stocklens.local", Role.SUPER_ADMIN)

    result = users.change_role(owner, other["id"], "admin", engine=db)
    assert result["user"]["role"] == "admin"


def test_deactivating_keeps_the_account_and_its_history(db: Engine) -> None:
    owner = _make(db, "owner@stocklens.local", Role.SUPER_ADMIN)
    target = _make(db, "target@stocklens.local", Role.USER)

    users.set_active(owner, target["id"], False, engine=db)
    detail = users.detail(target["id"], engine=db)
    assert detail["user"]["is_active"] is False
    assert any(a["action"] == "user.deactivate" for a in detail["audit"])


def test_a_role_change_is_recorded_with_both_ends(db: Engine) -> None:
    owner = _make(db, "owner@stocklens.local", Role.SUPER_ADMIN)
    target = _make(db, "target@stocklens.local", Role.USER)

    users.change_role(owner, target["id"], "admin", engine=db)
    entry = next(
        a for a in users.detail(target["id"], engine=db)["audit"] if a["action"] == "user.role"
    )
    assert "user" in entry["detail"] and "admin" in entry["detail"]


def test_an_unknown_role_is_named_rather_than_ignored(db: Engine) -> None:
    owner = _make(db, "owner@stocklens.local", Role.SUPER_ADMIN)
    target = _make(db, "target@stocklens.local", Role.USER)

    with pytest.raises(NotFound) as caught:
        users.change_role(owner, target["id"], "superuser", engine=db)
    assert "super_admin" in caught.value.context["known"]


def test_an_invite_returns_a_password_exactly_once(db: Engine) -> None:
    owner = _make(db, "owner@stocklens.local", Role.SUPER_ADMIN)
    result = users.invite(owner, "new@stocklens.local", "user", engine=db)

    assert result["one_time_password"]
    assert "password" not in result["user"], "the hash must never leave the server"
    # The account exists and can be found afterwards; the password cannot.
    assert "one_time_password" not in users.detail(result["user"]["id"], engine=db)


def test_listing_reports_what_each_account_owns(db: Engine) -> None:
    _make(db, "owner@stocklens.local", Role.SUPER_ADMIN)
    listing = users.listing(engine=db)
    assert listing["total"] == 1
    assert listing["active_super_admins"] == 1
    assert listing["users"][0]["saved_screens"] == 0


def test_listing_can_be_filtered_by_role_and_term(db: Engine) -> None:
    _make(db, "owner@stocklens.local", Role.SUPER_ADMIN)
    _make(db, "analyst@stocklens.local", Role.USER)

    assert users.listing(role="user", engine=db)["total"] == 1
    assert users.listing(term="analyst", engine=db)["total"] == 1
    assert users.listing(term="nobody", engine=db)["total"] == 0
