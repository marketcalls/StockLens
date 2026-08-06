"""Rate limiting.

StockLens is self-hosted, so this is deliberately in-process: a sliding window
counter in memory, no Redis, nothing to run alongside the app. That comes with
two honest limitations, both stated rather than hidden:

- **Counters reset when the app restarts.** Acceptable here. The point is to
  blunt scraping and brute force, not to enforce a billing quota.
- **Counters are per worker.** Running uvicorn with `--workers 4` gives four
  independent counters, so the effective limit is four times what is configured.
  Run a single worker, or put a real limiter in front, if that matters.

Keys are derived from the caller: a signed-in user is limited by account, so
switching IP does not reset the count; anonymous callers are limited by IP.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Rule:
    """`limit` requests per `window` seconds."""

    limit: int
    window: int
    name: str = ""

    @property
    def description(self) -> str:
        unit = "second" if self.window == 1 else f"{self.window} seconds"
        if self.window == 60:
            unit = "minute"
        elif self.window == 3600:
            unit = "hour"
        elif self.window == 86400:
            unit = "day"
        return f"{self.limit} per {unit}"


# Public browsing. Generous: these are cheap reads from SQLite and a real reader
# clicking around a company page fires several at once.
READ = Rule(300, 60, "read")

# The screener is the expensive one and the obvious scraping target.
SCREENER = Rule(40, 60, "screener")

# Sign-in and sign-up. Tight, because this is where credential stuffing lands.
AUTH = Rule(10, 300, "auth")

# Account creation specifically, over a longer window.
SIGNUP = Rule(5, 3600, "signup")

# Export pulls thousands of rows and writes a file.
EXPORT = Rule(20, 3600, "export")

# Writes to a user's own workspace.
WRITE = Rule(120, 60, "write")

# How often to drop aged-out keys. Cheap, so it can be infrequent.
SWEEP_INTERVAL_SECONDS = 300


class SlidingWindowLimiter:
    """Counts request timestamps per key and drops those outside the window."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        # When each key's newest hit ages out. The sweep needs this because a
        # key's window is a property of the rule, not of the stored deque.
        self._expires_at: dict[str, float] = {}
        self._lock = threading.Lock()
        self._last_sweep = 0.0

    def check(self, key: str, rule: Rule, *, now: float | None = None) -> tuple[bool, int, float]:
        """Record a hit. Returns (allowed, remaining, seconds_until_reset)."""
        now = time.monotonic() if now is None else now
        cutoff = now - rule.window

        with self._lock:
            self._maybe_sweep(now)
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= rule.limit:
                retry_after = max(0.0, hits[0] + rule.window - now)
                return False, 0, retry_after

            hits.append(now)
            self._expires_at[key] = now + rule.window
            return True, rule.limit - len(hits), float(rule.window)

    def _maybe_sweep(self, now: float) -> None:
        """Drop keys whose hits have all aged out, so memory does not grow.

        Called under the lock. Pruning inside `check` only touches the key being
        checked, so a scraper coming from thousands of addresses would otherwise
        leave one entry per address forever - each still holding its timestamps,
        because an untouched key is never pruned.
        """
        if now - self._last_sweep < SWEEP_INTERVAL_SECONDS:
            return
        self._last_sweep = now
        stale = [k for k, expiry in self._expires_at.items() if expiry <= now]
        for key in stale:
            self._hits.pop(key, None)
            self._expires_at.pop(key, None)
        for key in [k for k, v in self._hits.items() if not v]:
            self._hits.pop(key, None)
            self._expires_at.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._expires_at.clear()
            self._last_sweep = 0.0

    @property
    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._hits)


limiter = SlidingWindowLimiter()


def client_key(request: Request, rule: Rule) -> str:
    """Identify the caller.

    A signed-in user is keyed by account so that changing IP does not reset the
    count. Anonymous callers fall back to IP.
    """
    user_id = getattr(request.state, "rate_limit_user_id", None)
    if user_id is not None:
        return f"{rule.name}:user:{user_id}"
    return f"{rule.name}:ip:{client_ip(request)}"


def client_ip(request: Request) -> str:
    """The caller's address.

    `X-Forwarded-For` is trusted only when the app is told it sits behind a
    proxy. Trusting it unconditionally would let anyone spoof a fresh identity
    per request by sending the header themselves.
    """
    from app.config import get_settings

    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
    return request.client.host if request.client else "unknown"


def enforce(request: Request, rule: Rule) -> None:
    """Raise 429 when the caller is over the limit."""
    from app.config import get_settings

    if not get_settings().rate_limit_enabled:
        return

    allowed, remaining, retry_after = limiter.check(client_key(request, rule), rule)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. The limit is {rule.description}.",
            headers={
                "Retry-After": str(int(retry_after) + 1),
                "X-RateLimit-Limit": str(rule.limit),
                "X-RateLimit-Remaining": "0",
            },
        )
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_rule = rule


def limit(rule: Rule):
    """Dependency factory: `Depends(limit(SCREENER))`."""

    def dependency(request: Request) -> None:
        enforce(request, rule)

    return dependency
