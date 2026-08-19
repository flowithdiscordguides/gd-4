"""Normalize non-secret GitHub PAT expiration metadata and calculate current status."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


# GitHub documents this response header as the PAT's expiration timestamp.
TOKEN_EXPIRATION_HEADER = "GitHub-Authentication-Token-Expiration"

# GitHub has returned both a UTC label and numeric offsets, so accept both documented response shapes.
TOKEN_EXPIRATION_FORMATS = ("%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%d %H:%M:%S %z")


# Converts GitHub or persisted timestamps into one UTC ISO value safe for non-secret account metadata.
def clean_token_expiration(value: Any) -> str:
    """Return a canonical UTC expiration timestamp, or an empty string when the value is absent or malformed."""

    cleaned_value = str(value or "").strip()
    if not cleaned_value:
        return ""

    try:
        parsed = datetime.fromisoformat(cleaned_value.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is None:
        for date_format in TOKEN_EXPIRATION_FORMATS:
            try:
                parsed = datetime.strptime(cleaned_value, date_format)
                break
            except ValueError:
                continue
    if parsed is None:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# Reads only GitHub's non-secret expiration header from a response header mapping.
def token_expiration_from_headers(headers: Mapping[str, Any]) -> str:
    """Return the canonical PAT expiration timestamp reported by GitHub response headers."""

    return clean_token_expiration(headers.get(TOKEN_EXPIRATION_HEADER, ""))


# Compares a sanitized timestamp with the current UTC time without opening an operating-system credential item.
def token_expiration_has_passed(value: Any, now: datetime | None = None) -> bool:
    """Return whether a valid expiration timestamp is at or before the supplied or current UTC time."""

    clean_value = clean_token_expiration(value)
    if not clean_value:
        return False
    expiration = datetime.fromisoformat(clean_value.replace("Z", "+00:00"))
    comparison_time = now or datetime.now(timezone.utc)
    if comparison_time.tzinfo is None:
        comparison_time = comparison_time.replace(tzinfo=timezone.utc)
    return expiration <= comparison_time.astimezone(timezone.utc)
