"""Bridge handlers for saving, deleting, and exporting theme profiles."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Callable

from gitdesk.dialogs import choose_save_file
from gitdesk.errors import AppError
from gitdesk.theme_profiles import clean_theme_profiles, save_theme_profile, write_exported_profile


def theme_profile_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return the native actions owned by the Theme profile library."""

    return {
        "saveThemeProfile": lambda payload: handle_save_profile(controller, payload),
        "deleteThemeProfile": lambda payload: handle_delete_profile(controller, payload),
        "exportThemeProfile": lambda payload: handle_export_profile(controller, payload),
    }


def saved_profiles(controller: Any) -> list[dict[str, Any]]:
    """Return the current sanitized profile library."""

    return clean_theme_profiles(controller.settings_store.load().get("theme_profiles"))


def requested_profile(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return the saved profile matching the requested identifier."""

    profile_id = str(payload.get("profile_id") or "").strip().lower()
    profile = next((item for item in saved_profiles(controller) if item["id"] == profile_id), None)
    if not profile:
        raise AppError("That theme profile no longer exists.", "THEME_PROFILE_NOT_FOUND")
    return profile


def handle_save_profile(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Save the current visual theme under a reusable profile name."""

    profiles = save_theme_profile(
        saved_profiles(controller),
        payload.get("name"),
        payload.get("theme_colors"),
        payload.get("theme_gradients"),
    )
    return {"settings": controller.settings_store.save({"theme_profiles": profiles})}


def handle_delete_profile(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Delete one explicitly selected saved profile."""

    profile = requested_profile(controller, payload)
    profiles = [item for item in saved_profiles(controller) if item["id"] != profile["id"]]
    return {"settings": controller.settings_store.save({"theme_profiles": profiles})}


def export_filename(name: str) -> str:
    """Return a portable default filename derived from a profile name."""

    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:48] or "gitdesk-theme"
    return f"{slug}.gitdesk-theme.json"


def handle_export_profile(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Prompt for a destination and atomically export the selected profile."""

    profile = requested_profile(controller, payload)
    selected_path = choose_save_file(
        export_filename(profile["name"]),
        "Export GitDesk theme profile",
        (("GitDesk theme profile", "*.gitdesk-theme.json"), ("JSON files", "*.json")),
    )
    if not selected_path:
        return {"path": "", "cancelled": True}
    destination = Path(selected_path).expanduser()
    write_exported_profile(destination, profile)
    return {"path": str(destination), "cancelled": False}
