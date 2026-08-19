"""Native bridge handlers for Repo Mode Actions jingle settings and audio data."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk.action_jingle_store import ACTION_JINGLE_MIME_TYPES, ActionJingleStore
from gitdesk.action_jingle_store import clean_jingle_kind
from gitdesk.dialogs import choose_file


ACTION_JINGLE_PATTERNS = tuple(f"*{suffix}" for suffix in ACTION_JINGLE_MIME_TYPES)


def action_jingle_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for replacing and reading Actions jingles."""

    return {
        "replaceActionJingle": handle_replace_action_jingle,
        "actionJingleAudio": handle_action_jingle_audio,
    }


def action_jingle_settings() -> dict[str, Any]:
    """Return basename-only success and failure jingle state for bootstrap."""

    return ActionJingleStore().public_settings()


def handle_replace_action_jingle(payload: dict[str, Any]) -> dict[str, Any]:
    """Open the native audio picker and persist one validated external file path."""

    kind = clean_jingle_kind(payload.get("kind"))
    store = ActionJingleStore()
    registry = store.load()
    selected_path = choose_file(
        registry[f"{kind}_path"],
        f"Choose a {kind} Actions jingle",
        ACTION_JINGLE_PATTERNS,
        "Audio files",
    )
    if not selected_path:
        return {"cancelled": True, "action_jingles": store.public_settings(registry)}
    saved = store.replace(kind, selected_path)
    return {"cancelled": False, "action_jingles": store.public_settings(saved)}


def handle_action_jingle_audio(payload: dict[str, Any]) -> dict[str, Any]:
    """Return one validated custom jingle as a private-path-free data URL."""

    return ActionJingleStore().audio_payload(payload.get("kind"))
