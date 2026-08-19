"""Bridge handlers for selected-version Markdown project notes."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk import localnotes


# Notes handlers remain separate from the near-limit Local Mode project bridge.
def local_note_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return native actions for listing, creating, reading, and saving Markdown notes."""

    return {
        "projectNotesState": lambda payload: handle_notes_state(controller, payload),
        "createProjectNote": lambda payload: handle_create_note(controller, payload),
        "readProjectNote": lambda payload: handle_read_note(controller, payload),
        "saveProjectNote": lambda payload: handle_save_note(controller, payload),
    }


# Loads the current direct-child Markdown note catalog.
def handle_notes_state(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return note metadata for the exact selected Local Mode version."""

    return {"notes": localnotes.notes_state(controller.settings_store.load(), payload)}


# Creates one new Markdown file without replacing an existing project file.
def handle_create_note(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create one selected-version note and return refreshed metadata."""

    settings = controller.settings_store.load()
    note = localnotes.create_note(settings, payload)
    return {"note": note, "notes": localnotes.notes_state(settings, payload)}


# Reads raw Markdown source only; rendered HTML never crosses the native boundary.
def handle_read_note(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return one note's UTF-8 Markdown source and content revision."""

    return {"note": localnotes.read_note(controller.settings_store.load(), payload)}


# Saves raw Markdown after enforcing the expected external-edit revision.
def handle_save_note(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Atomically replace one unchanged note and return its new revision."""

    settings = controller.settings_store.load()
    note = localnotes.save_note(settings, payload)
    return {"note": note, "notes": localnotes.notes_state(settings, payload)}
