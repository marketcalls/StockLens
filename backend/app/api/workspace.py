"""Saved screens, watchlists and export. Everything here needs an account."""

from __future__ import annotations

import csv
import io
import json
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.deps import current_role, export_limit_for, require_user, row_cap_for
from app.auth.models import Role, saved_screen, watchlist, watchlist_item
from app.auth.service import utcnow
from app.db.engine import get_engine
from app.screener.execute import run_screen
from app.screener.parser import QueryError, parse

router = APIRouter(prefix="/api", tags=["workspace"])


class ScreenPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    query: str = Field(min_length=1, max_length=4000)
    description: str | None = Field(default=None, max_length=1000)
    columns: list[str] | None = None
    is_public: bool = False


class WatchlistPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WatchlistItemPayload(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=2000)


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


# --- saved screens ------------------------------------------------------------


@router.get("/screens")
def list_screens(user: dict = Depends(require_user)) -> dict[str, Any]:
    with get_engine().connect() as conn:
        rows = (
            conn.execute(
                select(saved_screen)
                .where(saved_screen.c.user_id == user["id"])
                .order_by(saved_screen.c.updated_at.desc())
            )
            .mappings()
            .all()
        )
    return {"screens": [_screen_row(dict(r)) for r in rows]}


@router.post("/screens", status_code=201)
def create_screen(payload: ScreenPayload, user: dict = Depends(require_user)) -> dict[str, Any]:
    # Validate before storing, so a saved screen is always runnable.
    try:
        parse(payload.query)
    except QueryError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    now = utcnow()
    engine = get_engine()
    with engine.begin() as conn:
        existing = conn.execute(
            select(saved_screen.c.id).where(
                saved_screen.c.user_id == user["id"], saved_screen.c.name == payload.name
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="You already have a screen with that name")
        result = conn.execute(
            saved_screen.insert().values(
                user_id=user["id"],
                name=payload.name,
                description=payload.description,
                query=payload.query,
                columns=json.dumps(payload.columns) if payload.columns else None,
                is_public=payload.is_public,
                share_token=secrets.token_urlsafe(12) if payload.is_public else None,
                created_at=now,
                updated_at=now,
            )
        )
        screen_id = result.inserted_primary_key[0]

    return _get_owned_screen(screen_id, user["id"])


def _get_owned_screen(screen_id: int, user_id: int) -> dict[str, Any]:
    with get_engine().connect() as conn:
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
        # 404 rather than 403 so the response cannot confirm that someone
        # else's screen exists.
        raise HTTPException(status_code=404, detail="No such screen")
    return _screen_row(dict(row))


@router.get("/screens/{screen_id}")
def get_screen(screen_id: int, user: dict = Depends(require_user)) -> dict[str, Any]:
    return _get_owned_screen(screen_id, user["id"])


@router.patch("/screens/{screen_id}")
def update_screen(
    screen_id: int, payload: ScreenPayload, user: dict = Depends(require_user)
) -> dict[str, Any]:
    _get_owned_screen(screen_id, user["id"])
    try:
        parse(payload.query)
    except QueryError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    with get_engine().begin() as conn:
        conn.execute(
            saved_screen.update()
            .where(saved_screen.c.id == screen_id, saved_screen.c.user_id == user["id"])
            .values(
                name=payload.name,
                description=payload.description,
                query=payload.query,
                columns=json.dumps(payload.columns) if payload.columns else None,
                is_public=payload.is_public,
                updated_at=utcnow(),
            )
        )
    return _get_owned_screen(screen_id, user["id"])


@router.delete("/screens/{screen_id}", status_code=204)
def delete_screen(screen_id: int, user: dict = Depends(require_user)) -> None:
    _get_owned_screen(screen_id, user["id"])
    with get_engine().begin() as conn:
        conn.execute(
            saved_screen.delete().where(
                saved_screen.c.id == screen_id, saved_screen.c.user_id == user["id"]
            )
        )


@router.post("/screens/{screen_id}/run")
def run_saved_screen(
    screen_id: int, page: int = 1, user: dict = Depends(require_user)
) -> dict[str, Any]:
    screen = _get_owned_screen(screen_id, user["id"])
    result = run_screen(
        get_engine(),
        screen["query"],
        display_columns=screen["columns"],
        page=page,
        row_cap=row_cap_for(Role(user["role"])),
    )
    payload = result.as_dict()
    payload.pop("sql", None)
    payload["screen"] = {"id": screen["id"], "name": screen["name"]}
    return payload


# --- watchlists ---------------------------------------------------------------


@router.get("/watchlists")
def list_watchlists(user: dict = Depends(require_user)) -> dict[str, Any]:
    engine = get_engine()
    with engine.connect() as conn:
        lists = (
            conn.execute(
                select(watchlist)
                .where(watchlist.c.user_id == user["id"])
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

    return {
        "watchlists": [
            {
                "id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"],
                "items": by_list.get(row["id"], []),
            }
            for row in lists
        ]
    }


@router.post("/watchlists", status_code=201)
def create_watchlist(
    payload: WatchlistPayload, user: dict = Depends(require_user)
) -> dict[str, Any]:
    with get_engine().begin() as conn:
        existing = conn.execute(
            select(watchlist.c.id).where(
                watchlist.c.user_id == user["id"], watchlist.c.name == payload.name
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="You already have a list with that name")
        result = conn.execute(
            watchlist.insert().values(user_id=user["id"], name=payload.name, created_at=utcnow())
        )
    return {"id": result.inserted_primary_key[0], "name": payload.name, "items": []}


def _assert_owns_watchlist(watchlist_id: int, user_id: int) -> None:
    with get_engine().connect() as conn:
        owned = conn.execute(
            select(watchlist.c.id).where(
                watchlist.c.id == watchlist_id, watchlist.c.user_id == user_id
            )
        ).scalar_one_or_none()
    if owned is None:
        raise HTTPException(status_code=404, detail="No such watchlist")


@router.post("/watchlists/{watchlist_id}/items", status_code=201)
def add_watchlist_item(
    watchlist_id: int, payload: WatchlistItemPayload, user: dict = Depends(require_user)
) -> dict[str, Any]:
    _assert_owns_watchlist(watchlist_id, user["id"])
    symbol = payload.symbol.upper()
    with get_engine().begin() as conn:
        conn.execute(
            watchlist_item.delete().where(
                watchlist_item.c.watchlist_id == watchlist_id,
                watchlist_item.c.symbol == symbol,
            )
        )
        conn.execute(
            watchlist_item.insert().values(
                watchlist_id=watchlist_id, symbol=symbol, note=payload.note, added_at=utcnow()
            )
        )
    return {"watchlist_id": watchlist_id, "symbol": symbol, "note": payload.note}


@router.delete("/watchlists/{watchlist_id}/items/{symbol}", status_code=204)
def remove_watchlist_item(
    watchlist_id: int, symbol: str, user: dict = Depends(require_user)
) -> None:
    _assert_owns_watchlist(watchlist_id, user["id"])
    with get_engine().begin() as conn:
        conn.execute(
            watchlist_item.delete().where(
                watchlist_item.c.watchlist_id == watchlist_id,
                watchlist_item.c.symbol == symbol.upper(),
            )
        )


@router.delete("/watchlists/{watchlist_id}", status_code=204)
def delete_watchlist(watchlist_id: int, user: dict = Depends(require_user)) -> None:
    _assert_owns_watchlist(watchlist_id, user["id"])
    with get_engine().begin() as conn:
        conn.execute(watchlist.delete().where(watchlist.c.id == watchlist_id))


# --- export -------------------------------------------------------------------


@router.get("/export/screen")
def export_screen(
    query: str = Query(min_length=1, max_length=4000),
    user: dict = Depends(require_user),
) -> StreamingResponse:
    """CSV of a screen's results. Signed-in only, with a per-role row ceiling."""
    role = Role(user["role"])
    limit = export_limit_for(role)
    if limit <= 0:
        raise HTTPException(status_code=403, detail="Exporting needs an account")

    try:
        result = run_screen(get_engine(), query, page_size=100, row_cap=None)
    except QueryError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    # run_screen paginates; gather up to the ceiling.
    rows = list(result.rows)
    page = 2
    while len(rows) < min(result.total, limit):
        more = run_screen(get_engine(), query, page=page, page_size=100, row_cap=None)
        if not more.rows:
            break
        rows.extend(more.rows)
        page += 1
    rows = rows[:limit]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    headers = ["Symbol", *[c["label"] for c in result.columns]]
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row.get("symbol"), *[row.get(c["key"]) for c in result.columns]])

    buffer.seek(0)
    truncated = result.total > limit
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="stocklens-screen.csv"',
            # Say so in a header rather than silently returning fewer rows.
            "X-StockLens-Total": str(result.total),
            "X-StockLens-Exported": str(len(rows)),
            "X-StockLens-Truncated": "true" if truncated else "false",
        },
    )


@router.get("/limits/screener")
def screener_limits(role: Role = Depends(current_role)) -> dict[str, Any]:
    return {"role": role.label, "row_cap": row_cap_for(role)}
