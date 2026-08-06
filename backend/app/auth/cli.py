"""Account CLI.

The first Super Admin is made here, never through a web form:

    python -m app.auth.cli create-super-admin ops@example.com
    python -m app.auth.cli set-role ops@example.com admin
    python -m app.auth.cli list
"""

from __future__ import annotations

import argparse
import getpass
import sys

from app.auth.models import Role, create_auth
from app.auth.security import password_problem
from app.auth.service import (
    SignupError,
    create_user,
    get_user_by_email,
    public_user,
    set_role,
    user_count,
)
from app.db.engine import get_engine
from app.logging_setup import configure_logging


def _read_password(supplied: str | None) -> str:
    if supplied:
        return supplied
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        print("Passwords do not match.", file=sys.stderr)
        raise SystemExit(1)
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stocklens-auth")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-super-admin", help="Create the platform owner account")
    create.add_argument("email")
    create.add_argument("--password", help="Prompted for if omitted")
    create.add_argument("--name")

    role = sub.add_parser("set-role", help="Change an existing account's role")
    role.add_argument("email")
    role.add_argument("role", choices=[r.label for r in Role if r is not Role.PUBLIC])

    sub.add_parser("list", help="List accounts")

    args = parser.parse_args(argv)
    configure_logging()
    engine = get_engine()
    create_auth(engine)

    if args.command == "create-super-admin":
        password = _read_password(args.password)
        problem = password_problem(password)
        if problem:
            print(problem, file=sys.stderr)
            return 1
        try:
            user = create_user(
                engine,
                args.email,
                password,
                display_name=args.name,
                role=Role.SUPER_ADMIN,
            )
        except SignupError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Created super admin: {user['email']} (id {user['id']})")
        return 0

    if args.command == "set-role":
        user = get_user_by_email(engine, args.email)
        if user is None:
            print(f"No account for {args.email}", file=sys.stderr)
            return 1
        updated = set_role(
            engine, actor_id=user["id"], user_id=user["id"], role=Role.from_name(args.role)
        )
        print(f"{updated['email']} is now {Role(updated['role']).label}")
        return 0

    print(f"{user_count(engine)} accounts")
    from sqlalchemy import select

    from app.auth.models import app_user

    with engine.connect() as conn:
        for row in conn.execute(select(app_user).order_by(app_user.c.id)).mappings():
            info = public_user(dict(row))
            state = "" if info["is_active"] else "  [suspended]"
            print(f"  {info['id']:4d}  {info['email']:32s} {info['role']}{state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
