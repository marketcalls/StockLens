"""Security middleware for a self-hosted deployment."""

from __future__ import annotations

import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.auth.security import COOKIE_NAME, AuthError, decode_token
from app.config import Settings

logger = logging.getLogger("stocklens.security")

# 1 MB. Every write in this app is a small JSON body; the largest is a screener
# query capped at 4,000 characters. Anything larger is a mistake or an attack.
MAX_BODY_BYTES = 1_048_576


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Standard hardening headers.

    The content security policy is deliberately strict. StockLens serves its own
    bundle and talks only to its own API, so nothing needs to load from
    elsewhere. `'unsafe-inline'` is allowed for styles because Tailwind and
    Recharts set inline styles; it is NOT allowed for scripts.
    """

    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()"
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")

        # The dev server needs a websocket for hot reload and eval for its
        # client, so the policy is only applied where the bundle is static.
        if not self.settings.is_plain_http:
            response.headers.setdefault(
                "Content-Security-Policy",
                "; ".join(
                    (
                        "default-src 'self'",
                        "script-src 'self'",
                        "style-src 'self' 'unsafe-inline'",
                        "img-src 'self' data:",
                        "font-src 'self'",
                        "connect-src 'self'",
                        "frame-ancestors 'none'",
                        "base-uri 'self'",
                        "form-action 'self'",
                        "object-src 'none'",
                    )
                ),
            )
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        # Never let a proxy or browser cache an authenticated response.
        if request.cookies.get(COOKIE_NAME):
            response.headers.setdefault("Cache-Control", "no-store, private")

        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Refuse oversized request bodies before they are read into memory."""

    async def dispatch(self, request: Request, call_next):
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > MAX_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body is too large"},
                    )
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
        return await call_next(request)


class RateLimitIdentityMiddleware(BaseHTTPMiddleware):
    """Attach the caller's user id so limits follow the account, not the IP.

    Decodes the session cookie only - no database lookup - because this runs on
    every request and the id is all the limiter needs. A forged or expired token
    simply falls back to IP-based limiting.
    """

    async def dispatch(self, request: Request, call_next):
        token = request.cookies.get(COOKIE_NAME)
        if token:
            try:
                payload = decode_token(token)
                request.state.rate_limit_user_id = int(payload["sub"])
            except (AuthError, KeyError, TypeError, ValueError):
                pass
        return await call_next(request)
