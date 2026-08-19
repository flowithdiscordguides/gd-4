"""Sanitation and export helpers for reusable GitDesk theme profiles."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from uuid import uuid4

from gitdesk.errors import AppError
from gitdesk.settings_preferences import clean_theme_colors
from gitdesk.theme_gradients import clean_theme_gradients


MAX_THEME_PROFILES = 30
MAX_THEME_PROFILE_NAME = 60
PROFILE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def clean_profile_name(value: Any) -> str:
    """Return a bounded single-line profile name."""

    return " ".join(str(value or "").split())[:MAX_THEME_PROFILE_NAME]


def profile_gradients(value: Any) -> dict[str, Any]:
    """Return profile-owned gradients without the global favorites library."""

    cleaned = clean_theme_gradients(value)
    return {"dark": cleaned["dark"], "light": cleaned["light"]}


def clean_theme_profile(value: Any) -> dict[str, Any] | None:
    """Return one complete reusable theme profile or None for malformed metadata."""

    if not isinstance(value, dict):
        return None
    profile_id = str(value.get("id") or "").strip().lower()
    name = clean_profile_name(value.get("name"))
    if not name or not PROFILE_ID_PATTERN.fullmatch(profile_id):
        return None
    return {
        "id": profile_id,
        "name": name,
        "theme_colors": clean_theme_colors(value.get("theme_colors")),
        "theme_gradients": profile_gradients(value.get("theme_gradients")),
        "updated_at": str(value.get("updated_at") or "").strip()[:40],
    }


def clean_theme_profiles(value: Any) -> list[dict[str, Any]]:
    """Return a bounded list with unique profile identifiers and names."""

    profiles = []
    identifiers = set()
    names = set()
    for raw_profile in (value if isinstance(value, list) else []):
        profile = clean_theme_profile(raw_profile)
        name_key = profile["name"].casefold() if profile else ""
        if profile and profile["id"] not in identifiers and name_key not in names:
            profiles.append(profile)
            identifiers.add(profile["id"])
            names.add(name_key)
        if len(profiles) == MAX_THEME_PROFILES:
            break
    return profiles


def save_theme_profile(profiles: Any, name: Any, colors: Any, gradients: Any) -> list[dict[str, Any]]:
    """Create or replace a named profile and return the sanitized collection."""

    clean_name = clean_profile_name(name)
    if not clean_name:
        raise AppError("Enter a name for this theme profile.", "THEME_PROFILE_NAME_REQUIRED")
    saved_profiles = clean_theme_profiles(profiles)
    existing = next((item for item in saved_profiles if item["name"].casefold() == clean_name.casefold()), None)
    profile = {
        "id": existing["id"] if existing else uuid4().hex,
        "name": clean_name,
        "theme_colors": clean_theme_colors(colors),
        "theme_gradients": profile_gradients(gradients),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    remaining = [item for item in saved_profiles if item["id"] != profile["id"]]
    return clean_theme_profiles([profile, *remaining])


def exported_profile_payload(profile: Any) -> dict[str, Any]:
    """Return the versioned JSON shape written for one saved profile."""

    cleaned = clean_theme_profile(profile)
    if not cleaned:
        raise AppError("That theme profile no longer exists.", "THEME_PROFILE_NOT_FOUND")
    return {"format": "gitdesk-theme-profile", "version": 1, "profile": cleaned}


def write_exported_profile(path: Path, profile: Any) -> None:
    """Atomically write a private profile file without changing its parent directory."""

    encoded = json.dumps(exported_profile_payload(profile), indent=2, sort_keys=True).encode("utf-8") + b"\n"
    temporary_path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary_path = Path(raw_path)
        with os.fdopen(descriptor, "wb") as output_file:
            output_file.write(encoded)
            output_file.flush()
            os.fsync(output_file.fileno())
        temporary_path.chmod(0o600)
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as error:
        raise AppError("The theme profile could not be exported.", "THEME_PROFILE_EXPORT_FAILED") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
