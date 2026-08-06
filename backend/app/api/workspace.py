"""Saved screens, watchlists and export. Everything here needs an account.

Thin wrappers over app/services/workspace, which holds ownership rules and is
callable without HTTP.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.deps import current_role, export_limit_for, require_user, row_cap_for
from app.auth.models import Role
from app.security.ratelimit import EXPORT, WRITE, limit
from app.services import screener as screener_service
from app.services import workspace as workspace_service

router = APIRouter(prefix="/api", tags=["workspace"], dependencies=[Depends(limit(WRITE))])


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


# --- saved screens ------------------------------------------------------------


@router.get("/screens")
def list_screens(user: dict = Depends(require_user)) -> dict[str, Any]:
    return {"screens": workspace_service.list_screens(user["id"])}


@router.post("/screens", status_code=201)
def create_screen(payload: ScreenPayload, user: dict = Depends(require_user)) -> dict[str, Any]:
    return workspace_service.create_screen(
        user["id"],
        payload.name,
        payload.query,
        description=payload.description,
        columns=payload.columns,
        is_public=payload.is_public,
    )


@router.get("/screens/{screen_id}")
def get_screen(screen_id: int, user: dict = Depends(require_user)) -> dict[str, Any]:
    return workspace_service.get_screen(user["id"], screen_id)


@router.patch("/screens/{screen_id}")
def update_screen(
    screen_id: int, payload: ScreenPayload, user: dict = Depends(require_user)
) -> dict[str, Any]:
    return workspace_service.update_screen(
        user["id"],
        screen_id,
        payload.name,
        payload.query,
        description=payload.description,
        columns=payload.columns,
        is_public=payload.is_public,
    )


@router.delete("/screens/{screen_id}", status_code=204)
def delete_screen(screen_id: int, user: dict = Depends(require_user)) -> None:
    workspace_service.delete_screen(user["id"], screen_id)


@router.post("/screens/{screen_id}/run")
def run_saved_screen(
    screen_id: int, page: int = 1, user: dict = Depends(require_user)
) -> dict[str, Any]:
    screen = workspace_service.get_screen(user["id"], screen_id)
    payload = screener_service.run(
        screen["query"],
        display_columns=screen["columns"],
        page=page,
        row_cap=row_cap_for(Role(user["role"])),
    )
    payload["screen"] = {"id": screen["id"], "name": screen["name"]}
    return payload


# --- watchlists ---------------------------------------------------------------


@router.get("/watchlists")
def list_watchlists(user: dict = Depends(require_user)) -> dict[str, Any]:
    return {"watchlists": workspace_service.list_watchlists(user["id"])}


@router.post("/watchlists", status_code=201)
def create_watchlist(
    payload: WatchlistPayload, user: dict = Depends(require_user)
) -> dict[str, Any]:
    return workspace_service.create_watchlist(user["id"], payload.name)


@router.post("/watchlists/{watchlist_id}/items", status_code=201)
def add_watchlist_item(
    watchlist_id: int, payload: WatchlistItemPayload, user: dict = Depends(require_user)
) -> dict[str, Any]:
    return workspace_service.add_symbol(user["id"], watchlist_id, payload.symbol, note=payload.note)


@router.delete("/watchlists/{watchlist_id}/items/{symbol}", status_code=204)
def remove_watchlist_item(
    watchlist_id: int, symbol: str, user: dict = Depends(require_user)
) -> None:
    workspace_service.remove_symbol(user["id"], watchlist_id, symbol)


@router.delete("/watchlists/{watchlist_id}", status_code=204)
def delete_watchlist(watchlist_id: int, user: dict = Depends(require_user)) -> None:
    workspace_service.delete_watchlist(user["id"], watchlist_id)


# --- export -------------------------------------------------------------------


@router.get("/export/screen", dependencies=[Depends(limit(EXPORT))])
def export_screen(
    query: str = Query(min_length=1, max_length=4000),
    user: dict = Depends(require_user),
) -> StreamingResponse:
    """CSV of a screen's results. Signed-in only, with a per-role row ceiling."""
    role = Role(user["role"])
    ceiling = export_limit_for(role)
    if ceiling <= 0:
        raise HTTPException(status_code=403, detail="Exporting needs an account")

    result = screener_service.run(query, page_size=100, row_cap=None)
    rows = list(result["rows"])
    page = 2
    while len(rows) < min(result["total"], ceiling):
        more = screener_service.run(query, page=page, page_size=100, row_cap=None)
        if not more["rows"]:
            break
        rows.extend(more["rows"])
        page += 1
    rows = rows[:ceiling]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Symbol", *[c["label"] for c in result["columns"]]])
    for row in rows:
        writer.writerow([row.get("symbol"), *[row.get(c["key"]) for c in result["columns"]]])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="stocklens-screen.csv"',
            # Say what was left out in a header rather than silently returning
            # fewer rows than the caller expects.
            "X-StockLens-Total": str(result["total"]),
            "X-StockLens-Exported": str(len(rows)),
            "X-StockLens-Truncated": "true" if result["total"] > ceiling else "false",
        },
    )


@router.get("/limits/screener")
def screener_limits(role: Role = Depends(current_role)) -> dict[str, Any]:
    return {"role": role.label, "row_cap": row_cap_for(role)}
