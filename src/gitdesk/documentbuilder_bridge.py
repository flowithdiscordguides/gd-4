"""Bridge handlers for the local-first Document Builder workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from gitdesk import documentbuilder
from gitdesk.dialogs import choose_directory
from gitdesk.documentstore import DocumentStore
from gitdesk.errors import AppError
from gitdesk.nativeopen import open_folder, open_in_editor
from gitdesk.reposettings import clean_category_name


# Registers a dedicated store-backed handler map without expanding BridgeController with feature logic.
def document_builder_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return all native actions used by the Document Builder frontend."""

    store = DocumentStore()
    return {
        "documentBuilderState": lambda payload: handle_state(store, payload),
        "chooseDocumentParent": lambda payload: handle_choose_parent(payload),
        "createDocument": lambda payload: handle_create_document(store, payload),
        "renameDocument": lambda payload: handle_rename_document(store, payload),
        "removeDocument": lambda payload: handle_remove_document(store, payload),
        "setDocumentCategory": lambda payload: handle_set_category(store, payload),
        "selectDocument": lambda payload: handle_select_document(store, payload),
        "createDocumentFolder": lambda payload: handle_create_folder(store, payload),
        "selectDocumentFolder": lambda payload: handle_select_folder(store, payload),
        "createDocumentFile": lambda payload: handle_create_file(store, payload),
        "selectDocumentFile": lambda payload: handle_select_file(store, payload),
        "openDocumentFolder": lambda payload: handle_open_document(store, payload),
        "openDocumentInVSCode": lambda payload: handle_open_document_vscode(controller, store, payload),
        "openDocumentFileInVSCode": lambda payload: handle_open_file_vscode(controller, store, payload),
    }


# Returns a standard response shape after reading current registry and filesystem state.
def state_response(registry: dict[str, Any]) -> dict[str, Any]:
    """Return sanitized registry metadata enriched with live physical hierarchy state."""

    return {"documents": documentbuilder.documents_state(registry)}


# Loads current Document Builder state without mutating metadata.
def handle_state(store: DocumentStore, payload: dict[str, Any]) -> dict[str, Any]:
    """Return all saved documents with current folders, files, and active selections."""

    return state_response(store.load())


# Opens the existing cross-platform folder picker for a document parent directory.
def handle_choose_parent(payload: dict[str, Any]) -> dict[str, str]:
    """Return a selected document parent path or an empty string when cancelled."""

    initial_path = str(payload.get("initial_path") or "")
    return {"path": choose_directory(initial_path, "Choose document parent folder")}


# Finds a payload-selected document only when it is present in the trusted registry.
def registered_document(registry: dict[str, Any], path_value: Any) -> dict[str, str]:
    """Return the requested registered document or raise a user-safe selection error."""

    requested_path = str(path_value or registry.get("active_document") or "").strip()
    record = next(
        (item for item in documentbuilder.clean_document_records(registry.get("documents"))
         if item["path"] == requested_path),
        None,
    )
    if not record:
        raise AppError("Select a registered document first.", "DOCUMENT_NOT_SELECTED")
    return record


# Returns valid live state and locates its currently selected document object.
def active_state(store: DocumentStore, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the registry and live selected document for a hierarchy action."""

    registry = store.load()
    record = registered_document(registry, payload.get("document_path"))
    state = documentbuilder.documents_state({**registry, "active_document": record["path"]})
    document = next((item for item in state["documents"] if item["path"] == record["path"]), None)
    if not document or not document["exists"]:
        raise AppError("The selected document folder is missing.", "DOCUMENT_PATH_INVALID")
    return registry, document


# Creates a physical document root and saves it as the current registry selection.
def handle_create_document(store: DocumentStore, payload: dict[str, Any]) -> dict[str, Any]:
    """Create and register an empty document root."""

    record = documentbuilder.create_document(payload.get("parent_path"), payload.get("name"))
    category = clean_category_name(payload.get("category"))
    record["category"] = category
    registry = store.load()
    documents = documentbuilder.clean_document_records(registry.get("documents")) + [record]
    categories = list(registry.get("categories") or [])
    if category and category not in categories:
        categories.append(category)
    saved = store.save({
        "documents": documents,
        "categories": categories,
        "active_document": record["path"],
        "active_folder": "",
        "active_file": "",
    })
    return {"created": record, **state_response(saved)}


# Rewrites a path only when it is the renamed root or one of its descendants.
def remap_path(path_value: Any, source: Path, target: Path) -> str:
    """Return a saved selection moved under target, or its original value when unrelated."""

    raw_path = str(path_value or "").strip()
    if not raw_path:
        return ""
    try:
        relative_path = Path(raw_path).expanduser().resolve().relative_to(source)
    except (OSError, ValueError):
        return raw_path
    return str((target / relative_path).resolve())


# Renames a registered document root and remaps every active child selection under that root.
def handle_rename_document(store: DocumentStore, payload: dict[str, Any]) -> dict[str, Any]:
    """Rename a document folder and persist its new hierarchy paths."""

    registry = store.load()
    record = registered_document(registry, payload.get("document_path"))
    result = documentbuilder.rename_document(record["path"], payload.get("name"))
    source = Path(result["source"])
    target = Path(result["target"])
    documents = []
    for item in documentbuilder.clean_document_records(registry.get("documents")):
        renamed_item = {**item, "path": str(target), "name": result["name"]}
        documents.append(renamed_item if item["path"] == record["path"] else item)
    saved = store.save({
        "documents": documents,
        "active_document": remap_path(registry.get("active_document"), source, target),
        "active_folder": remap_path(registry.get("active_folder"), source, target),
        "active_file": remap_path(registry.get("active_file"), source, target),
    })
    return {"renamed": result, **state_response(saved)}


# Removes metadata only so user-authored document files are never deleted by the registry control.
def handle_remove_document(store: DocumentStore, payload: dict[str, Any]) -> dict[str, Any]:
    """Unregister one document without deleting its physical folder or files."""

    registry = store.load()
    record = registered_document(registry, payload.get("document_path"))
    documents = [item for item in registry["documents"] if item["path"] != record["path"]]
    updates: dict[str, Any] = {"documents": documents}
    if registry.get("active_document") == record["path"]:
        updates.update({"active_document": "", "active_folder": "", "active_file": ""})
    return state_response(store.save(updates))


# Assigns a safe category and retains it as an available filter even when no other document uses it yet.
def handle_set_category(store: DocumentStore, payload: dict[str, Any]) -> dict[str, Any]:
    """Update one registered document category label."""

    registry = store.load()
    record = registered_document(registry, payload.get("document_path"))
    category = clean_category_name(payload.get("category"))
    documents = [
        {**item, "category": category} if item["path"] == record["path"] else item
        for item in registry["documents"]
    ]
    categories = list(registry.get("categories") or [])
    if category and category not in categories:
        categories.append(category)
    return state_response(store.save({"documents": documents, "categories": categories}))


# Selects a document and chooses its first folder/file only when those physical children exist.
def handle_select_document(store: DocumentStore, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist the selected document and its first available descendants."""

    registry = store.load()
    record = registered_document(registry, payload.get("document_path"))
    state = documentbuilder.documents_state({**registry, "active_document": record["path"]})
    document = next(item for item in state["documents"] if item["path"] == record["path"])
    folder = document["folders"][0] if document["folders"] else None
    file = folder["files"][0] if folder and folder["files"] else None
    saved = store.save({
        "active_document": record["path"],
        "active_folder": folder["path"] if folder else "",
        "active_file": file["path"] if file else "",
    })
    return state_response(saved)


# Creates and selects the next numbered folder under the active registered document.
def handle_create_folder(store: DocumentStore, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a numbered document folder and make it active."""

    registry, document = active_state(store, payload)
    folder = documentbuilder.create_folder(
        document["path"],
        payload.get("parent_folder_path"),
        payload.get("name"),
    )
    saved = store.save({
        "active_document": document["path"],
        "active_folder": folder["path"],
        "active_file": "",
    })
    return {"created": folder, **state_response(saved)}


# Selects a folder only when the live filesystem state proves it belongs to the active document.
def handle_select_folder(store: DocumentStore, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist one active numbered folder and its first available file."""

    registry, document = active_state(store, payload)
    folder_path = str(payload.get("folder_path") or "")
    folders = documentbuilder.flatten_folders(document["folders"])
    folder = next((item for item in folders if item["path"] == folder_path), None)
    if not folder:
        raise AppError("Selected folder does not belong to this document.", "DOCUMENT_FOLDER_PATH_INVALID")
    file = folder["files"][0] if folder["files"] else None
    saved = store.save({
        "active_document": document["path"],
        "active_folder": folder["path"],
        "active_file": file["path"] if file else "",
    })
    return state_response(saved)


# Creates a numbered UTF-8 file from pasted content and selects the saved physical file.
def handle_create_file(store: DocumentStore, payload: dict[str, Any]) -> dict[str, Any]:
    """Save pasted text as the next numbered file in the selected folder."""

    registry, document = active_state(store, payload)
    folder_path = str(payload.get("folder_path") or registry.get("active_folder") or "")
    file = documentbuilder.create_file(
        document["path"],
        folder_path,
        payload.get("name"),
        payload.get("content"),
    )
    saved = store.save({
        "active_document": document["path"],
        "active_folder": folder_path,
        "active_file": file["path"],
    })
    return {"created": file, **state_response(saved)}


# Selects a file only when it appears under the live active folder payload.
def handle_select_file(store: DocumentStore, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist an existing selected document file."""

    registry, document = active_state(store, payload)
    folder_path = str(payload.get("folder_path") or registry.get("active_folder") or "")
    folders = documentbuilder.flatten_folders(document["folders"])
    folder = next((item for item in folders if item["path"] == folder_path), None)
    file_path = str(payload.get("file_path") or "")
    file = next((item for item in (folder or {}).get("files", []) if item["path"] == file_path), None)
    if not file:
        raise AppError("Selected file does not belong to this document folder.", "DOCUMENT_FILE_PATH_INVALID")
    return state_response(store.save({
        "active_document": document["path"],
        "active_folder": folder_path,
        "active_file": file["path"],
    }))


# Opens the registered document root in Finder or the current platform's file manager.
def handle_open_document(store: DocumentStore, payload: dict[str, Any]) -> dict[str, str]:
    """Open the selected registered document root in the file manager."""

    _, document = active_state(store, payload)
    return open_folder(str(documentbuilder.selected_document(document["path"])))


# Opens the registered document root in the saved code editor.
def handle_open_document_vscode(
    controller: Any,
    store: DocumentStore,
    payload: dict[str, Any],
) -> dict[str, str]:
    """Open the selected registered document root in the selected editor."""

    _, document = active_state(store, payload)
    preferences = controller.settings_store.load().get("editor_preferences")
    return open_in_editor(str(documentbuilder.selected_document(document["path"])), preferences)


# Opens one exact managed file after validating its complete live document ownership chain.
def handle_open_file_vscode(
    controller: Any,
    store: DocumentStore,
    payload: dict[str, Any],
) -> dict[str, str]:
    """Open the selected document file directly in the selected editor."""

    registry, document = active_state(store, payload)
    file_path = documentbuilder.selected_file(
        document["path"],
        payload.get("folder_path") or registry.get("active_folder"),
        payload.get("file_path") or registry.get("active_file"),
    )
    preferences = controller.settings_store.load().get("editor_preferences")
    return open_in_editor(str(file_path), preferences)
