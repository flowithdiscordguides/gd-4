"""Shared structured errors for the GitDesk backend."""

from __future__ import annotations

from typing import Any


# AppError carries a user-safe message and optional diagnostic details across backend boundaries.
class AppError(Exception):
    """Represent an expected application failure that can be returned safely to the UI."""

    # Initializes an application error without exposing stack traces or secret-bearing context.
    def __init__(self, message: str, code: str = "APP_ERROR", details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    # Converts the error into the stable JSON shape consumed by the frontend response handler.
    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


# Converts any unexpected exception into a generic user-safe error payload.
def safe_unexpected_error(error: Exception) -> dict[str, Any]:
    """Return a sanitized error payload for unexpected backend exceptions."""

    error_type = error.__class__.__name__
    error_message = str(error or "").strip()[:500]
    return {
        "code": "UNEXPECTED_ERROR",
        "message": f"An unexpected backend error occurred ({error_type}).",
        "details": {"type": error_type, "message": error_message},
    }
