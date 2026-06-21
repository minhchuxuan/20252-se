"""Domain-level exceptions, mapped to HTTP status codes in main.py.

Keeping these framework-agnostic lets services raise meaningful errors without
depending on FastAPI, which keeps the business layer testable in isolation.
"""
from __future__ import annotations


class DomainError(Exception):
    """Base class for expected, user-facing errors."""
    status_code = 400

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class NotFoundError(DomainError):
    status_code = 404


class PermissionDeniedError(DomainError):
    status_code = 403


class ValidationError(DomainError):
    status_code = 422


class ConflictError(DomainError):
    status_code = 409


class SafetyViolationError(DomainError):
    """Raised when a command/rule would breach an NFR-SAF safety rule."""
    status_code = 409


class AuthError(DomainError):
    status_code = 401
