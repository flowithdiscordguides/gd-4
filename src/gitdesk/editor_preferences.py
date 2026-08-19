"""Sanitation for the user's preferred external code editor."""

from __future__ import annotations

from typing import Any


EDITOR_IDS = ("vscode", "vscodium")
EDITOR_NAMES = {"vscode": "VS Code", "vscodium": "VSCodium"}
DEFAULT_EDITOR_PREFERENCES = {"editor": "vscode", "vscodium_path": ""}


def default_editor_preferences() -> dict[str, str]:
    """Return a fresh editor preference map."""

    return dict(DEFAULT_EDITOR_PREFERENCES)


def clean_editor_preferences(value: Any) -> dict[str, str]:
    """Return a safe editor identifier and inert executable path string."""

    source = value if isinstance(value, dict) else {}
    editor = str(source.get("editor") or "vscode").strip().lower()
    return {
        "editor": editor if editor in EDITOR_IDS else "vscode",
        "vscodium_path": str(source.get("vscodium_path") or "").strip()[:4096],
    }


def editor_name(value: Any) -> str:
    """Return the display name for a sanitized preference or identifier."""

    editor = value.get("editor") if isinstance(value, dict) else value
    return EDITOR_NAMES.get(str(editor or "").lower(), EDITOR_NAMES["vscode"])
