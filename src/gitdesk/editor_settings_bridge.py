"""Bridge handlers for preferred external editor settings and discovery."""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any, Callable

from gitdesk.dialogs import choose_file
from gitdesk.editor_preferences import clean_editor_preferences
from gitdesk.nativeopen import editor_status


def editor_settings_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return focused User settings actions for external editor selection."""

    return {
        "editorSettingsState": lambda payload: handle_editor_state(controller, payload),
        "chooseVSCodiumExecutable": lambda payload: handle_choose_vscodium(controller, payload),
        "saveEditorPreferences": lambda payload: handle_save_editor_preferences(controller, payload),
    }


def current_preferences(controller: Any) -> dict[str, str]:
    """Return sanitized persisted editor preferences."""

    return clean_editor_preferences(controller.settings_store.load().get("editor_preferences"))


def handle_editor_state(controller: Any, payload: dict[str, Any]) -> dict[str, object]:
    """Return current selection plus platform-specific installation discovery."""

    return editor_status(current_preferences(controller))


def handle_choose_vscodium(controller: Any, payload: dict[str, Any]) -> dict[str, object]:
    """Choose a VSCodium executable on non-macOS platforms and return refreshed discovery."""

    preferences = current_preferences(controller)
    if platform.system() != "Darwin":
        initial_path = str(payload.get("initial_path") or preferences["vscodium_path"])
        patterns = ("*.exe",) if platform.system() == "Windows" else ("*",)
        selected_path = choose_file(
            initial_path,
            "Choose VSCodium executable",
            patterns,
            "VSCodium executable",
        )
        if selected_path:
            preferences["vscodium_path"] = str(Path(selected_path).expanduser().resolve())
    return editor_status(preferences)


def handle_save_editor_preferences(controller: Any, payload: dict[str, Any]) -> dict[str, object]:
    """Persist the chosen editor and return its refreshed availability state."""

    preferences = clean_editor_preferences(payload.get("editor_preferences"))
    saved = controller.settings_store.save({"editor_preferences": preferences})
    return {"settings": saved, "editor_state": editor_status(saved["editor_preferences"])}
