"""Domain errors.

The service layer raises these. app/api translates them to status codes, so a
caller that is not HTTP - an agent, a script, a test - gets a meaningful Python
exception rather than a 404 it has to parse.
"""

from __future__ import annotations


class ServiceError(Exception):
    """Base class. Carries a message fit to show a person."""

    status_code = 400

    def __init__(self, message: str, **context: object) -> None:
        super().__init__(message)
        self.message = message
        self.context = context


class NotFound(ServiceError):
    status_code = 404


class InvalidQuery(ServiceError):
    """A screener query could not be parsed. `position` locates the fault."""

    status_code = 400

    def __init__(self, message: str, position: int | None = None) -> None:
        super().__init__(message, position=position)
        self.position = position


class Forbidden(ServiceError):
    status_code = 403


class Conflict(ServiceError):
    status_code = 409
