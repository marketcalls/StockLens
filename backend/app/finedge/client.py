"""Async FinEdge API client.

Auth is a `token` query parameter. The token must never appear in a log line,
an exception message, or a response, so every URL that leaves this module is
passed through `redact`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_TOKEN_PATTERN = re.compile(r"(token=)[^&\s]+")

# 400 means a missing or invalid parameter; retrying cannot help.
# 401 means a bad key; retrying cannot help either.
NON_RETRYABLE_STATUS = frozenset({400, 401, 403, 404})


def redact(text: str) -> str:
    """Replace any token value in a string with a placeholder."""
    return _TOKEN_PATTERN.sub(r"\1REDACTED", text)


class FinEdgeError(Exception):
    """Base class for FinEdge failures."""


class FinEdgeAuthError(FinEdgeError):
    """The API key was missing, invalid, or rejected."""


class FinEdgeParameterError(FinEdgeError):
    """The request was well-formed but the parameters were rejected (HTTP 400)."""


class FinEdgeUnavailableError(FinEdgeError):
    """The API failed repeatedly and the retry budget was exhausted."""


@dataclass(frozen=True)
class FinEdgeResponse:
    """A successful FinEdge response plus the metadata ingestion needs."""

    endpoint: str
    params: dict[str, Any]
    payload: Any
    raw_bytes: bytes
    status_code: int
    elapsed_seconds: float

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.raw_bytes).hexdigest()

    @property
    def size_bytes(self) -> int:
        return len(self.raw_bytes)


class RateLimiter:
    """Simple async token-bucket-free pacer.

    FinEdge publishes no rate limit and returns no rate-limit headers
    (see docs/prd/09-open-questions.md Q1), so we pace conservatively by
    enforcing a minimum interval between request starts.
    """

    def __init__(self, max_rps: float) -> None:
        self._min_interval = 1.0 / max_rps if max_rps > 0 else 0.0
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_allowed = now + self._min_interval


class FinEdgeClient:
    """Async client with retry, backoff and token redaction."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.finedge_timeout_seconds),
            follow_redirects=True,
        )
        self._limiter = RateLimiter(self.settings.finedge_max_rps)
        self.calls_made = 0
        self.bytes_fetched = 0

    async def __aenter__(self) -> FinEdgeClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get(self, endpoint: str, **params: Any) -> FinEdgeResponse:
        """Fetch one endpoint, retrying transient failures.

        `endpoint` is a path such as '/api/v1/quote'. Params with a None value
        are dropped so callers can pass optional arguments unconditionally.
        """
        if not self.settings.has_finedge_key:
            raise FinEdgeAuthError("FINEDGE_API_KEY is not configured")

        clean_params = {k: v for k, v in params.items() if v is not None}
        request_params = dict(clean_params)
        request_params["token"] = self.settings.finedge_api_key.get_secret_value()
        url = f"{self.settings.finedge_base_url}{endpoint}"

        last_error: Exception | None = None
        for attempt in range(self.settings.finedge_max_retries + 1):
            await self._limiter.acquire()
            started = time.monotonic()
            try:
                response = await self._client.get(url, params=request_params)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "finedge request failed endpoint=%s attempt=%d error=%s",
                    endpoint,
                    attempt + 1,
                    redact(str(exc)),
                )
                await self._backoff(attempt)
                continue

            elapsed = time.monotonic() - started
            self.calls_made += 1
            self.bytes_fetched += len(response.content)

            if response.status_code == 200:
                return FinEdgeResponse(
                    endpoint=endpoint,
                    params=clean_params,
                    payload=self._decode(response),
                    raw_bytes=response.content,
                    status_code=response.status_code,
                    elapsed_seconds=elapsed,
                )

            body = response.text[:200]
            if response.status_code in NON_RETRYABLE_STATUS:
                message = f"{endpoint} returned {response.status_code}: {redact(body)}"
                if response.status_code in (401, 403):
                    raise FinEdgeAuthError(message)
                raise FinEdgeParameterError(message)

            # 429 and 5xx are worth retrying. 503 was observed transiently on
            # /api/v1/commodity-list and /api/v1/name-changes.
            last_error = FinEdgeUnavailableError(
                f"{endpoint} returned {response.status_code}: {redact(body)}"
            )
            logger.warning(
                "finedge transient failure endpoint=%s status=%d attempt=%d",
                endpoint,
                response.status_code,
                attempt + 1,
            )
            await self._backoff(attempt, retry_after=response.headers.get("retry-after"))

        raise FinEdgeUnavailableError(
            f"{endpoint} failed after {self.settings.finedge_max_retries + 1} attempts: "
            f"{redact(str(last_error))}"
        )

    async def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        if retry_after:
            try:
                await asyncio.sleep(min(float(retry_after), 60.0))
                return
            except ValueError:
                pass
        delay = min(2.0**attempt, 30.0) + random.uniform(0, 0.5)
        await asyncio.sleep(delay)

    @staticmethod
    def _decode(response: httpx.Response) -> Any:
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError):
            return {"_raw_text": response.text}

    async def healthcheck(self) -> bool:
        """Unauthenticated liveness probe."""
        try:
            response = await self._client.get(f"{self.settings.finedge_base_url}/healthcheck")
        except httpx.HTTPError:
            return False
        return response.status_code == 200
