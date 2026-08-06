"""Translate domain errors into HTTP.

The service layer raises `ServiceError`; only this module knows about status
codes. Registered once as an exception handler, so no route needs a try block.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.errors import InvalidQuery, ServiceError


def install(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def handle(_request: Request, exc: ServiceError) -> JSONResponse:
        # A query error carries the character position of the fault, which the
        # editor uses to point at it. That nested shape is what the frontend
        # reads, so it stays as it is.
        if isinstance(exc, InvalidQuery):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": {"message": exc.message, "position": exc.position}},
            )

        # Everything else gets the message as a string, with whatever context the
        # service attached alongside it. A person reads `detail`; a program reads
        # `symbol` or `run_id` without having to parse English out of a sentence.
        body: dict[str, object] = {"detail": exc.message}
        body.update({k: v for k, v in exc.context.items() if v is not None})
        return JSONResponse(status_code=exc.status_code, content=body)
