"""Native bridge handlers for folder-backed Media Mode album workflows."""

from __future__ import annotations

# Typed callables describe the Media Mode action map used by the central bridge.
from typing import Any, Callable

# GitDesk boundaries coordinate native folder selection, album state, publication, previews, and opening.
from gitdesk.dialogs import choose_directory
from gitdesk.media_album_files import create_media_album, import_media_image
from gitdesk.media_clipboard import copy_media_item, paste_media_clipboard
from gitdesk.media_library import library_state, media_preview, open_album, open_media
from gitdesk.media_library_publish import publish_album
from gitdesk.media_library_store import MediaLibraryStore
from gitdesk.media_move import move_media_item


# Converts bridge query controls into the common bounded Media library state response.
def state_from_payload(payload: dict[str, Any], store: MediaLibraryStore | None = None) -> dict[str, Any]:
    """Return Media Mode state for the requested filters and page."""

    return library_state(
        store,
        payload.get("query"),
        payload.get("kind"),
        payload.get("sort"),
        payload.get("page"),
        payload.get("page_size"),
    )


# Registers every Media Mode action without expanding the central bridge controller.
def media_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return the native actions used by the Media Mode frontend."""

    return {
        "mediaLibraryState": lambda payload: state_from_payload(payload),
        "chooseMediaParent": lambda payload: handle_choose_parent(payload),
        "saveMediaParentFavorite": lambda payload: handle_save_parent_favorite(payload),
        "createMediaAlbum": lambda payload: handle_create_album(payload),
        "chooseMediaAlbum": lambda payload: handle_choose_album(payload),
        "selectMediaAlbum": lambda payload: handle_select_album(payload),
        "renameMediaAlbum": lambda payload: handle_rename_album(payload),
        "removeMediaAlbum": lambda payload: handle_remove_album(payload),
        "mediaPreview": lambda payload: handle_media_preview(payload),
        "openMediaAlbum": lambda payload: open_album(payload.get("album_id")),
        "openMediaItem": lambda payload: open_media(payload.get("album_id"), payload.get("path")),
        "copyMediaItem": lambda payload: handle_copy_media_item(payload),
        "moveMediaItem": lambda payload: handle_move_media_item(payload),
        "importMediaImage": lambda payload: handle_import_image(payload),
        "pasteMediaClipboard": lambda payload: handle_paste_clipboard(payload),
        "publishMediaAlbum": lambda payload: handle_publish_album(payload),
    }


# Opens a native parent picker without creating or registering anything when the dialog is cancelled.
def handle_choose_parent(payload: dict[str, Any]) -> dict[str, Any]:
    """Choose a parent folder for a new Media album."""

    selected = choose_directory(str(payload.get("initial_path") or ""), "Choose Media album parent")
    return {"path": selected or "", "cancelled": not selected}


# Saves one verified Media parent favorite and returns state so every picker can stay synchronized.
def handle_save_parent_favorite(payload: dict[str, Any]) -> dict[str, Any]:
    """Save one Media album parent favorite."""

    store = MediaLibraryStore()
    store.save_parent_favorite(payload.get("path"))
    return state_from_payload(payload, store)


# Creates a new physical album under the selected parent and returns its first empty page.
def handle_create_album(payload: dict[str, Any]) -> dict[str, Any]:
    """Create and select a new Media album."""

    store = MediaLibraryStore()
    create_media_album(payload.get("parent_path"), payload.get("name"), store, payload.get("category"))
    return state_from_payload({**payload, "page": 1}, store)


# Opens a native folder picker and registers the chosen folder without moving its contents.
def handle_choose_album(payload: dict[str, Any]) -> dict[str, Any]:
    """Choose and save one folder-backed Media album."""

    selected = choose_directory(str(payload.get("initial_path") or ""), "Choose Media album folder")
    if not selected:
        return {**state_from_payload(payload), "cancelled": True}
    store = MediaLibraryStore()
    store.add_album(selected, payload.get("name"))
    return state_from_payload(payload, store)


# Persists one active album and returns its first bounded page.
def handle_select_album(payload: dict[str, Any]) -> dict[str, Any]:
    """Select one saved album and return refreshed Media Mode state."""

    store = MediaLibraryStore()
    store.select_album(payload.get("album_id"))
    return state_from_payload({**payload, "page": 1}, store)


# Renames only the Media Mode label while leaving the physical folder unchanged.
def handle_rename_album(payload: dict[str, Any]) -> dict[str, Any]:
    """Rename one saved Media album."""

    store = MediaLibraryStore()
    store.rename_album(payload.get("album_id"), payload.get("name"), payload.get("category"))
    return state_from_payload(payload, store)


# Forgets one album reference without deleting its folder or its published resource.
def handle_remove_album(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove one saved album reference and return refreshed state."""

    store = MediaLibraryStore()
    store.remove_album(payload.get("album_id"))
    return state_from_payload({**payload, "page": 1}, store)


# Returns one on-demand verified raster preview for a visible tile or selected-item inspector.
def handle_media_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded preview for one selected album item."""

    return media_preview(payload.get("album_id"), payload.get("path"))


# Copies one contained original as a native file reference without sending its absolute path to the WebView.
def handle_copy_media_item(payload: dict[str, Any]) -> dict[str, str]:
    """Copy one selected Media original to the desktop clipboard."""

    return copy_media_item(payload.get("album_id"), payload.get("path"))


# Moves one image original into another registered album and refreshes the current source album.
def handle_move_media_item(payload: dict[str, Any]) -> dict[str, Any]:
    """Move one selected photo and return refreshed Media library state."""

    store = MediaLibraryStore()
    result = move_media_item(
        payload.get("album_id"),
        payload.get("destination_album_id"),
        payload.get("path"),
        store,
    )
    data = state_from_payload(payload, store)
    data["moved_item"] = result
    return data


# Imports one validated image without rescanning until the frontend finishes its sequential intake batch.
def handle_import_image(payload: dict[str, Any]) -> dict[str, Any]:
    """Import one image into the addressed Media album."""

    return {
        "imported_image": import_media_image(
            payload.get("album_id"),
            payload.get("name"),
            payload.get("data_url"),
        ),
    }


# Reads the native desktop clipboard, imports its images, and returns one refreshed bounded album page.
def handle_paste_clipboard(payload: dict[str, Any]) -> dict[str, Any]:
    """Paste copied desktop images into the addressed Media album."""

    store = MediaLibraryStore()
    result = paste_media_clipboard(payload.get("album_id"), store)
    data = state_from_payload({**payload, "page": 1}, store)
    data["clipboard_import"] = result
    return data


# Publishes or updates the album's stable Shared Resource and returns its refreshed library state.
def handle_publish_album(payload: dict[str, Any]) -> dict[str, Any]:
    """Publish one Media album as an explicit Shared Resource release."""

    result = publish_album(payload.get("album_id"), payload.get("resource_name"))
    data = state_from_payload(payload)
    data["published_release"] = result
    return data
