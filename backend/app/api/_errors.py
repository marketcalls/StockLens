"""Record unhandled exceptions instead of losing them to stdout.

FastAPI turns an unhandled exception into a 500 and prints a traceback. In a
container nobody is reading that. This logs it - which the database handler
picks up, traceback and all - and returns a response that says an operator can
find the detail, without leaking the detail to the caller.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.logstore import context

logger = logging.getLogger("stocklens.unhandled")


def install(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def handle(request: Request, exc: Exception) -> JSONResponse:
        actor = getattr(request.state, "user_id", None)
        logger.error(
            "Unhandled %s on %s %s: %s",
            type(exc).__name__,
            request.method,
            request.url.path,
            exc,
            exc_info=exc,
            extra=context(path=request.url.path, method=request.method, status=500, actor_id=actor),
        )
        # The traceback goes to the log, not to the caller: it names internal
        # paths and can carry values from the failing call.
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Something went wrong. An administrator can see the details"
                " under Diagnostics."
            },
        )
