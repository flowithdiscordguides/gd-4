"""Bridge handlers for Backup Mode destination, scans, versions, and native opening."""

from __future__ import annotations

# Path and handler typing support fixed destination/version validation.
from pathlib import Path
from typing import Any, Callable

# Backup services keep inventory, manifests, persistence, and snapshot transactions separate.
from gitdesk.backup_inventory import backup_sources, inventory_summary
from gitdesk.backup_jobs import BACKUP_JOB_MANAGER, CancellationGate
from gitdesk.backup_manifest import backup_timestamp, manifest_diff, scan_sources
from gitdesk.backup_merge import merge_backup_versions
from gitdesk.backup_progress import ProgressCallback
from gitdesk.backup_snapshot import (
    create_backup_snapshot,
    load_snapshot_manifest,
    previous_snapshot_path,
    validate_backup_destination,
)
from gitdesk.backup_selection import (
    apply_backup_selection,
    backup_selection_children,
    backup_selection_tree,
    changed_backup_selection,
    clean_backup_selection,
    clean_selection_rules,
    default_backup_selection,
)
from gitdesk.backup_store import BackupStore
from gitdesk.dialogs import choose_directory
from gitdesk.errors import AppError
from gitdesk.nativeopen import open_folder, reveal_path


# Registers Backup Mode actions independently from the central bridge.
def backup_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for Backup Mode state and filesystem operations."""

    return {
        "backupState": lambda payload: handle_backup_state(controller, payload),
        "chooseBackupDestination": lambda payload: handle_choose_backup_destination(controller, payload),
        "saveBackupDestination": lambda payload: handle_save_backup_destination(controller, payload),
        "saveBackupParentFavorite": lambda payload: handle_save_backup_parent_favorite(controller, payload),
        "backupSelectionTree": lambda payload: handle_backup_selection_tree(controller, payload),
        "backupSelectionChildren": lambda payload: handle_backup_selection_children(controller, payload),
        "scanBackupChanges": lambda payload: handle_scan_backup_changes(controller, payload),
        "mergeDownBackupVersions": lambda payload: handle_merge_down_backup_versions(controller, payload),
        "syncBackup": lambda payload: handle_sync_backup(controller, payload),
        "startBackupJob": lambda payload: handle_start_backup_job(controller, payload),
        "backupJobStatus": lambda payload: handle_backup_job_status(controller, payload),
        "cancelBackupJob": lambda payload: handle_cancel_backup_job(controller, payload),
        "openBackupSkippedItem": lambda payload: handle_open_backup_skipped_item(controller, payload),
        "openBackupDestination": lambda payload: handle_open_backup_destination(controller, payload),
        "openBackupVersion": lambda payload: handle_open_backup_version(controller, payload),
    }


# Restores a pre-selection Backup version's complete-root scope from its completed manifest.
def effective_selection(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return saved selection or a backward-compatible scope from the latest manifest."""

    saved = clean_backup_selection(state.get("selection"))
    if saved:
        return saved
    manifest = latest_manifest(state)
    sources = manifest.get("sources", []) if isinstance(manifest, dict) else []
    migrated = []
    for source in sources:
        if not isinstance(source, dict) or not source.get("id"):
            continue
        raw_rules = source.get("selection_rules") if "selection_rules" in source else {"": True}
        rules = clean_selection_rules(raw_rules)
        if any(rules.values()):
            migrated.append({"source_id": str(source["id"]), "rules": rules})
    return clean_backup_selection(migrated)


# Combines private Backup Mode state with non-scanning registered source counts.
def backup_state_payload(controller: Any, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return frontend-safe Backup Mode state and inventory counts."""

    current_state = dict(state or BackupStore().load())
    current_state["selection"] = effective_selection(current_state)
    sources = backup_sources(controller.settings_store.load())
    return {
        "backup": current_state,
        "inventory": inventory_summary(sources),
    }


# Returns current state without hashing registered content.
def handle_backup_state(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return Backup Mode state and inventory counts."""

    return backup_state_payload(controller)


# Opens the native folder picker without changing the saved destination.
def handle_choose_backup_destination(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return a chosen backup parent path for modal review, or a cancellation result."""

    current = BackupStore().load()
    initial_path = str(payload.get("initial_path") or current.get("destination") or "")
    selected_path = choose_directory(initial_path, "Choose GitDesk backup destination")
    if not selected_path:
        return {"cancelled": True, "path": ""}
    return {"cancelled": False, "path": selected_path}


# Validates the reviewed modal value before replacing the active backup destination.
def handle_save_backup_destination(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Save one explicitly applied backup destination and return refreshed state."""

    selected_path = str(payload.get("path") or "").strip()
    if not selected_path:
        raise AppError("Choose a backup destination before applying.", "BACKUP_DESTINATION_REQUIRED")
    validate_backup_destination(selected_path, backup_sources(controller.settings_store.load()))
    state = BackupStore().save_destination(selected_path)
    return backup_state_payload(controller, state)


# Saves one validated Backup-specific parent favorite without selecting it as the destination.
def handle_save_backup_parent_favorite(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Save a backup parent favorite and return refreshed state."""

    state = BackupStore().save_parent_favorite(payload.get("path"))
    return backup_state_payload(controller, state)


# Returns grouped source roots and workflow-specific first-backup or detected-change defaults.
def handle_backup_selection_tree(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return the lazy Backup source tree and preselected include/exclude rules."""

    state = BackupStore().load()
    sources = backup_sources(controller.settings_store.load())
    is_sync = bool(state.get("latest_snapshot"))
    changed_source_ids = state.get("scan", {}).get("changed_source_ids", [])
    # A sync begins with detected roots only; a first backup still offers the complete available inventory.
    selection = changed_backup_selection(sources, changed_source_ids) if is_sync else default_backup_selection(sources)
    _selected_sources, selection = apply_backup_selection(sources, selection)
    return {
        "tree": backup_selection_tree(sources),
        "selection": selection,
        "changed_source_ids": changed_source_ids if is_sync else [],
        "is_sync": is_sync,
    }


# Returns one safe direct-child page for an expanded Backup source folder.
def handle_backup_selection_children(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return lazy direct children for one current registered source."""

    sources = backup_sources(controller.settings_store.load())
    return backup_selection_children(
        sources,
        payload.get("source_id"),
        payload.get("path"),
        payload.get("offset"),
    )


# Loads the latest completed manifest only when it remains under the selected destination.
def latest_manifest(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return the latest valid destination manifest or None."""

    destination_value = str(state.get("destination") or "")
    if not destination_value:
        return None
    destination = Path(destination_value).expanduser()
    if destination.is_symlink() or not destination.is_dir():
        return None
    snapshot = previous_snapshot_path(destination.resolve(), state.get("latest_snapshot"))
    return load_snapshot_manifest(snapshot)


# Hashes all registered sources and persists a bounded added/modified/deleted summary.
def handle_scan_backup_changes(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Scan registered sources and return pending changes against the latest snapshot."""

    store = BackupStore()
    state = store.load()
    if not state["destination"]:
        raise AppError("Choose a backup destination before scanning.", "BACKUP_DESTINATION_REQUIRED")
    inventory = backup_sources(controller.settings_store.load())
    sources, _selection = apply_backup_selection(inventory, effective_selection(state))
    if not state.get("latest_snapshot") or not sources:
        raise AppError("Create the first confirmed backup before scanning for changes.", "BACKUP_SELECTION_REQUIRED")
    try:
        validate_backup_destination(state["destination"], inventory)
    except AppError as error:
        scan = {
            "scanned_at": backup_timestamp(),
            "errors": [{
                "label": "Backup destination",
                "path": state["destination"],
                "category": "Destination",
                "message": error.message,
                "code": error.code,
            }],
        }
        return backup_state_payload(controller, store.save_scan(scan))
    manifest = scan_sources(sources)
    changes = manifest_diff(latest_manifest(state), manifest)
    scan = {
        **changes,
        "scanned_at": manifest["scanned_at"],
        "errors": manifest["errors"],
    }
    saved = store.save_scan(scan)
    return backup_state_payload(controller, saved)


# Replays every newer completed version into one explicitly selected parent without changing child folders.
def handle_merge_down_backup_versions(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Merge newer versions into a chosen parent and return refreshed Backup state."""

    store = BackupStore()
    state = store.load()
    result = merge_backup_versions(
        state.get("destination"),
        state.get("versions", []),
        payload.get("parent_path"),
    )
    saved = state if result["no_changes"] else store.replace_version(result["version"])
    return {
        "merged_children": result["merged_children"],
        "merge_no_changes": result["no_changes"],
        "cleanup_warning": result["cleanup_warning"],
        **backup_state_payload(controller, saved),
    }


# Enforces the required reviewed-selection agreement before synchronous or background creation.
def require_backup_confirmation(payload: dict[str, Any]) -> None:
    """Reject any Backup creation request without explicit confirmation."""

    if payload.get("confirmed") is not True:
        raise AppError("Confirm the reviewed backup selection before continuing.", "BACKUP_CONFIRMATION_REQUIRED")


# Performs one complete Backup transaction for synchronous callers or a cancellable background job.
def perform_sync_backup(
    controller: Any,
    payload: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancellation: CancellationGate | None = None,
) -> dict[str, Any]:
    """Create one merge-forward backup snapshot and return updated state."""

    require_backup_confirmation(payload)
    store = BackupStore()
    state = store.load()
    if not state["destination"]:
        raise AppError("Choose a backup destination before syncing.", "BACKUP_DESTINATION_REQUIRED")
    inventory = backup_sources(controller.settings_store.load())
    sources, selection = apply_backup_selection(inventory, payload.get("selection"))
    if not sources:
        raise AppError("Select at least one file or folder to back up.", "BACKUP_SELECTION_REQUIRED")
    validate_backup_destination(state["destination"], inventory)
    result = create_backup_snapshot(
        state["destination"],
        sources,
        state.get("latest_snapshot"),
        progress_callback,
        cancellation.requested if cancellation else None,
        cancellation.seal if cancellation else None,
    )
    if result["no_changes"]:
        scan = {
            **result["changes"],
            "scanned_at": result["manifest"]["scanned_at"],
            "errors": result["manifest"]["errors"],
        }
        saved = store.save_selection_scan(selection, scan)
        return {"no_changes": True, **backup_state_payload(controller, saved)}
    pending_scan = {
        **result["pending_changes"],
        "scanned_at": result["manifest"]["scanned_at"],
        "errors": [],
    }
    saved = store.add_version(result["version"], selection, pending_scan)
    return {
        "no_changes": False,
        "created_version": result["version"],
        "skipped_items": result["skipped_items"],
        "_skipped_source_paths": result["_skipped_source_paths"],
        **backup_state_payload(controller, saved),
    }


# Creates the next verified version synchronously for direct service and regression callers.
def handle_sync_backup(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create one synchronous Backup snapshot and return updated state."""

    result = perform_sync_backup(controller, payload)
    result.pop("_skipped_source_paths", None)
    return result


# Starts one responsive Backup transaction after enforcing confirmation on the initiating request.
def handle_start_backup_job(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Start one cancellable Backup job and return its initial polling state."""

    require_backup_confirmation(payload)
    request = dict(payload)

    # The worker receives manager-owned progress and cancellation capabilities only.
    def worker(progress_callback: ProgressCallback, cancellation: CancellationGate) -> dict[str, Any]:
        return perform_sync_backup(controller, request, progress_callback, cancellation)

    return BACKUP_JOB_MANAGER.start(worker)


# Returns factual progress for one opaque process-owned Backup job.
def handle_backup_job_status(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return one active or terminal Backup job payload."""

    return BACKUP_JOB_MANAGER.status(payload.get("job_id"))


# Requests cleanup-safe cancellation before the job crosses its atomic install boundary.
def handle_cancel_backup_job(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Cancel one Backup job when its staging transaction is still reversible."""

    return BACKUP_JOB_MANAGER.cancel(payload.get("job_id"))


# Reveals one private skipped source path owned by the exact completed background job.
def handle_open_backup_skipped_item(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Reveal one skipped source without accepting a frontend-supplied filesystem path."""

    path = BACKUP_JOB_MANAGER.skipped_path(payload.get("job_id"), payload.get("item_id"))
    return reveal_path(path)


# Opens the exact currently saved destination rather than a frontend-supplied arbitrary path.
def handle_open_backup_destination(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Open the saved backup destination in the operating-system file manager."""

    destination = BackupStore().load()["destination"]
    if not destination:
        raise AppError("Choose a backup destination first.", "BACKUP_DESTINATION_REQUIRED")
    return open_folder(destination)


# Opens only a version path already present in private Backup Mode history.
def handle_open_backup_version(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Open one saved completed backup version."""

    requested_path = str(payload.get("path") or "").strip()
    state = BackupStore().load()
    version = next((item for item in state["versions"] if item["path"] == requested_path), None)
    if not version:
        raise AppError("That backup version is not in GitDesk history.", "BACKUP_VERSION_NOT_FOUND")
    destination_value = str(state.get("destination") or "")
    destination = Path(destination_value).expanduser()
    if destination.is_symlink() or not destination.is_dir():
        raise AppError("The backup destination is unavailable.", "BACKUP_DESTINATION_UNAVAILABLE")
    safe_version = previous_snapshot_path(destination.resolve(), version["path"])
    if safe_version is None or str(safe_version) != version["path"]:
        raise AppError("That backup version is outside the selected destination.", "BACKUP_VERSION_INVALID")
    return open_folder(str(safe_version))
