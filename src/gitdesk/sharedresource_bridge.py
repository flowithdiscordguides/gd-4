"""Bridge handlers for Shared Resources catalog, Local Mode management, and document publishing."""

from __future__ import annotations

# Typed callables define the native action table exposed to the frontend bridge.
from typing import Any, Callable

# GitDesk modules validate selected folders and coordinate catalog, Local, and Document Builder workflows.
from gitdesk import aiskills
from gitdesk import documentbuilder
from gitdesk import localversions
from gitdesk import sharedresource_documents
from gitdesk import sharedresources


# Registers neutral action names while the legacy AI Skills bridge remains available for older frontend callers.
def shared_resource_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return every native action used by Shared Resources workflows."""

    return {
        "listSharedResources": lambda payload: handle_list_resources(controller, payload),
        "createSharedResource": lambda payload: handle_create_resource(controller, payload),
        "recordSharedResourceUpdate": lambda payload: handle_record_resource(controller, payload),
        "openSharedResource": lambda payload: handle_open_resource(controller, payload),
        "addSharedResourceToRepo": lambda payload: handle_add_resource_to_repo(controller, payload),
        "saveSharedResourceSelection": lambda payload: handle_save_selection(controller, payload),
        "localSharedResourceState": lambda payload: handle_local_resource_state(controller, payload),
        "applyLocalSharedResources": lambda payload: handle_apply_local_resources(controller, payload),
        "updateLocalSharedResource": lambda payload: handle_update_local_resource(controller, payload),
        "documentSharedResourceState": lambda payload: handle_document_resource_state(controller, payload),
        "addDocumentToSharedResource": lambda payload: handle_add_document_resource(controller, payload),
        "updateDocumentSharedResource": lambda payload: handle_update_document_resource(controller, payload),
    }


# Combines current content revisions with the existing selected-starter preference.
def handle_list_resources(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return all Shared Resources and the saved default selection."""

    data = sharedresources.list_resources()
    data["selected"] = controller.settings_store.load().get("active_ai_skill_categories", [])
    return data


# Creates one writable resource and returns the refreshed catalog used by every checklist surface.
def handle_create_resource(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a Shared Resource folder and return current catalog state."""

    result = aiskills.create_category(str(payload.get("name") or ""))
    sharedresources.record_resource_update(result["name"])
    return handle_list_resources(controller, payload)


# Advances a user-edited working folder only when the user explicitly confirms its next release in Settings.
def handle_record_resource(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Record one Shared Resource update and return the refreshed catalog."""

    result = sharedresources.record_resource_update(str(payload.get("name") or ""))
    data = handle_list_resources(controller, payload)
    data["recorded_release"] = result
    return data


# Materializes and opens one resource's editable folder through the existing cross-platform boundary.
def handle_open_resource(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Open one Shared Resource folder in the platform file manager."""

    return aiskills.open_category(str(payload.get("name") or ""))


# Adds one resource to the active repository without changing the repository's unrelated files.
def handle_add_resource_to_repo(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Overlay one Shared Resource into the active repository root."""

    path = controller.repository_path_from_payload(payload)
    result = sharedresources.install_resource(str(payload.get("name") or ""), str(path))
    result["status"] = controller.git_service.status(path)
    return result


# Retains the existing private setting key so saved user selections survive the terminology migration.
def handle_save_selection(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist selected default Shared Resources and return refreshed catalog state."""

    resources = payload.get("resources") or []
    settings = controller.settings_store.save({"active_ai_skill_categories": resources})
    data = sharedresources.list_resources()
    data["selected"] = settings["active_ai_skill_categories"]
    return data


# Resolves the requested or active Local Mode version through the authoritative version-folder validator.
def selected_version_path(controller: Any, payload: dict[str, Any]) -> str:
    """Return a validated Local Mode version path for resource management."""

    settings = controller.settings_store.load()
    raw_path = str(payload.get("version_path") or settings.get("active_local_version") or "")
    return str(localversions.normalize_version_directory(raw_path))


# Returns resource checkboxes and revision status for the selected physical version.
def handle_local_resource_state(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return Shared Resources installation state for one Local Mode version."""

    return sharedresources.version_resource_state(selected_version_path(controller, payload))


# Applies explicit checked and unchecked states without auto-updating outdated selected resources.
def handle_apply_local_resources(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Add and remove Shared Resources selected in the Local Mode management modal."""

    return sharedresources.apply_resource_selection(
        selected_version_path(controller, payload),
        payload.get("resources") or [],
    )


# Updates one row immediately so the user can review other checkbox changes independently.
def handle_update_local_resource(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Merge the current revision of one Shared Resource into the selected version."""

    version_path = selected_version_path(controller, payload)
    sharedresources.install_resource(str(payload.get("name") or ""), version_path)
    return sharedresources.version_resource_state(version_path)


# Validates the complete live Document Builder hierarchy before a file can be published outside it.
def selected_document_file(payload: dict[str, Any]) -> str:
    """Return a selected regular document file after validating document and folder ownership."""

    file_path = documentbuilder.selected_file(
        payload.get("document_path"),
        payload.get("folder_path"),
        payload.get("file_path"),
    )
    return str(file_path)


# Supplies resource choices and a prior publish link for the selected document file.
def handle_document_resource_state(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return Shared Resources publishing state for one selected Document Builder file."""

    return sharedresource_documents.document_resource_state(selected_document_file(payload))


# Publishes a selected file to the user-chosen resource and relative destination path.
def handle_add_document_resource(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Add one selected Document Builder file to Shared Resources."""

    return sharedresource_documents.publish_document_file(
        selected_document_file(payload),
        str(payload.get("resource") or ""),
        str(payload.get("target_path") or ""),
    )


# Reuses the private saved link so a document edit updates exactly the previously selected resource file.
def handle_update_document_resource(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Update a selected Document Builder file's linked Shared Resource destination."""

    return sharedresource_documents.update_document_file(selected_document_file(payload))
