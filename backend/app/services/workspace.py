"""Saved screens and watchlists.

Ownership is enforced here, not in the route: a caller that is not HTTP must get
the same guarantees. A screen belonging to someone else raises NotFound rather
than Forbidden, since Forbidden would confirm it exists.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from sqlalchemy import Engine, select

from app.auth.models import saved_screen, watchlist, watchlist_item
from app.auth.service import utcnow
from app.db.engine import get_engine
from app.screener.parser import QueryError
from app.screener.parser import parse as parse_query
from app.services.errors import Conflict, InvalidQuery, NotFound


def _engine(engine: Engine | None = None) -> Engine:
    return engine or get_engine()


def _screen_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "query": row["query"],
        "columns": json.loads(row["columns"]) if row["columns"] else None,
        "is_public": bool(row["is_public"]),
        "share_token": row["share_token"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_screens(user_id: int, *, engine: Engine | None = None) -> list[dict[str, Any]]:
    with _engine(engine).connect() as conn:
        rows = (
            conn.execute(
                select(saved_screen)
                .where(saved_screen.c.user_id == user_id)
                .order_by(saved_screen.c.updated_at.desc())
            )
            .mappings()
            .all()
        )
    return [_screen_row(dict(r)) for r in rows]


def get_screen(user_id: int, screen_id: int, *, engine: Engine | None = None) -> dict[str, Any]:
    with _engine(engine).connect() as conn:
        row = (
            conn.execute(
                select(saved_screen).where(
                    saved_screen.c.id == screen_id, saved_screen.c.user_id == user_id
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise NotFound("No such screen", screen_id=screen_id)
    return _screen_row(dict(row))


def create_screen(
    user_id: int,
    name: str,
    query: str,
    *,
    description: str | None = None,
    columns: list[str] | None = None,
    is_public: bool = False,
    engine: Engine | None = None,
) -> dict[str, Any]:
    # Validate before storing, so a saved screen is always runnable.
    try:
        parse_query(query)
    except QueryError as exc:
        raise InvalidQuery(exc.message, exc.position) from exc

    db = _engine(engine)
    now = utcnow()
    with db.begin() as conn:
        existing = conn.execute(
            select(saved_screen.c.id).where(
                saved_screen.c.user_id == user_id, saved_screen.c.name == name
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise Conflict("You already have a screen with that name", name=name)
        result = conn.execute(
            saved_screen.insert().values(
                user_id=user_id,
                name=name,
                description=description,
                query=query,
                columns=json.dumps(columns) if columns else None,
                is_public=is_public,
                share_token=secrets.token_urlsafe(12) if is_public else None,
                created_at=now,
                updated_at=now,
            )
        )
        screen_id = result.inserted_primary_key[0]
    return get_screen(user_id, screen_id, engine=db)


def update_screen(
    user_id: int,
    screen_id: int,
    name: str,
    query: str,
    *,
    description: str | None = None,
    columns: list[str] | None = None,
    is_public: bool = False,
    engine: Engine | None = None,
) -> dict[str, Any]:
    db = _engine(engine)
    get_screen(user_id, screen_id, engine=db)
    try:
        parse_query(query)
    except QueryError as exc:
        raise InvalidQuery(exc.message, exc.position) from exc

    with db.begin() as conn:
        conn.execute(
            saved_screen.update()
            .where(saved_screen.c.id == screen_id, saved_screen.c.user_id == user_id)
            .values(
                name=name,
                description=description,
                query=query,
                columns=json.dumps(columns) if columns else None,
                is_public=is_public,
                updated_at=utcnow(),
            )
        )
    return get_screen(user_id, screen_id, engine=db)


def delete_screen(user_id: int, screen_id: int, *, engine: Engine | None = None) -> None:
    db = _engine(engine)
    get_screen(user_id, screen_id, engine=db)
    with db.begin() as conn:
        conn.execute(
            saved_screen.delete().where(
                saved_screen.c.id == screen_id, saved_screen.c.user_id == user_id
            )
        )


def list_watchlists(user_id: int, *, engine: Engine | None = None) -> list[dict[str, Any]]:
    db = _engine(engine)
    with db.connect() as conn:
        lists = (
            conn.execute(
                select(watchlist)
                .where(watchlist.c.user_id == user_id)
                .order_by(watchlist.c.created_at)
            )
            .mappings()
            .all()
        )
        items = conn.execute(select(watchlist_item)).mappings().all()

    by_list: dict[int, list[dict[str, Any]]] = {}
    for item in items:
        by_list.setdefault(item["watchlist_id"], []).append(
            {"symbol": item["symbol"], "note": item["note"], "added_at": item["added_at"]}
        )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "items": by_list.get(row["id"], []),
        }
        for row in lists
    ]


def create_watchlist(user_id: int, name: str, *, engine: Engine | None = None) -> dict[str, Any]:
    with _engine(engine).begin() as conn:
        existing = conn.execute(
            select(watchlist.c.id).where(watchlist.c.user_id == user_id, watchlist.c.name == name)
        ).scalar_one_or_none()
        if existing is not None:
            raise Conflict("You already have a list with that name", name=name)
        result = conn.execute(
            watchlist.insert().values(user_id=user_id, name=name, created_at=utcnow())
        )
    return {"id": result.inserted_primary_key[0], "name": name, "items": []}


def _assert_owns(user_id: int, watchlist_id: int, engine: Engine) -> None:
    with engine.connect() as conn:
        owned = conn.execute(
            select(watchlist.c.id).where(
                watchlist.c.id == watchlist_id, watchlist.c.user_id == user_id
            )
        ).scalar_one_or_none()
    if owned is None:
        raise NotFound("No such watchlist", watchlist_id=watchlist_id)


def add_symbol(
    user_id: int,
    watchlist_id: int,
    symbol: str,
    *,
    note: str | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    db = _engine(engine)
    _assert_owns(user_id, watchlist_id, db)
    symbol = symbol.upper()
    with db.begin() as conn:
        conn.execute(
            watchlist_item.delete().where(
                watchlist_item.c.watchlist_id == watchlist_id,
                watchlist_item.c.symbol == symbol,
            )
        )
        conn.execute(
            watchlist_item.insert().values(
                watchlist_id=watchlist_id, symbol=symbol, note=note, added_at=utcnow()
            )
        )
    return {"watchlist_id": watchlist_id, "symbol": symbol, "note": note}


def remove_symbol(
    user_id: int, watchlist_id: int, symbol: str, *, engine: Engine | None = None
) -> None:
    db = _engine(engine)
    _assert_owns(user_id, watchlist_id, db)
    with db.begin() as conn:
        conn.execute(
            watchlist_item.delete().where(
                watchlist_item.c.watchlist_id == watchlist_id,
                watchlist_item.c.symbol == symbol.upper(),
            )
        )


def delete_watchlist(user_id: int, watchlist_id: int, *, engine: Engine | None = None) -> None:
    db = _engine(engine)
    _assert_owns(user_id, watchlist_id, db)
    with db.begin() as conn:
        conn.execute(watchlist.delete().where(watchlist.c.id == watchlist_id))
