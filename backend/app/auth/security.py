"""Password hashing and session tokens."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.auth.models import Role
from app.config import get_settings

_hasher = PasswordHasher()

ALGORITHM = "HS256"
COOKIE_NAME = "stocklens_session"

MIN_PASSWORD_LENGTH = 10

# HMAC-SHA256 wants at least 32 bytes of key (RFC 7518 section 3.2). The
# development default is deliberately shorter than that so it cannot be mistaken
# for a real secret.
MIN_JWT_SECRET_BYTES = 32
DEV_JWT_SECRET = "dev_only_change_me"


def jwt_secret_problem() -> str | None:
    """Why the configured signing secret is unsafe, or None.

    A weak secret means sessions can be forged, so this is checked at startup
    rather than left to be discovered.
    """
    settings = get_settings()
    secret = settings.jwt_secret.get_secret_value()
    if secret == DEV_JWT_SECRET:
        return "JWT_SECRET is still the development default"
    if len(secret.encode()) < MIN_JWT_SECRET_BYTES:
        return (
            f"JWT_SECRET is {len(secret.encode())} bytes; "
            f"at least {MIN_JWT_SECRET_BYTES} are needed to sign sessions safely"
        )
    return None


class AuthError(Exception):
    """Authentication failed. The message is deliberately vague to the caller."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return False


def password_problem(password: str) -> str | None:
    """Return a reason the password is unacceptable, or None.

    Length only. Composition rules push people towards predictable
    substitutions without adding real strength.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password) > 1024:
        return "Password is too long"
    return None


def normalise_email(email: str) -> str:
    return email.strip().lower()


# A login address here is an identifier, not somewhere we will ever send mail.
# StockLens is self-hosted, so admin@stocklens.local, admin@localhost and
# intranet-only domains are all legitimate - and a strict deliverability check
# would reject exactly the addresses an operator is most likely to pick.
#
# This is deliberately the ONLY rule in the codebase. The CLI used to accept
# addresses the login endpoint then refused, which let an operator create the
# owner account and find themselves permanently locked out of it.
_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.?[^@\s]*$")

MAX_EMAIL_LENGTH = 254  # RFC 5321


def email_problem(email: str) -> str | None:
    """Why this address cannot be used as a login, or None if it can."""
    cleaned = normalise_email(email)
    if not cleaned:
        return "Enter an email address"
    if len(cleaned) > MAX_EMAIL_LENGTH:
        return f"That address is longer than {MAX_EMAIL_LENGTH} characters"
    if not _EMAIL_SHAPE.match(cleaned):
        return "Enter a valid email address"
    return None


def issue_token(user_id: int, role: Role, *, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    minutes = expires_minutes if expires_minutes is not None else settings.jwt_expiry_minutes
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": int(role),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid or expired session") from exc
