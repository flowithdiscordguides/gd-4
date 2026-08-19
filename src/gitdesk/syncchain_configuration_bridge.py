"""Native configuration handlers for local-folder and terminal artifact Sync Chain modes."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk import syncchains
from gitdesk.dialogs import choose_directory
from gitdesk.errors import AppError


StateBuilder = Callable[[Any, dict[str, Any] | None], dict[str, Any]]


def handle_choose_sync_stage_folder(
    controller: Any,
    payload: dict[str, Any],
    state_builder: StateBuilder,
) -> dict[str, Any]:
    """Choose, validate, and save one ordinary local folder as a chain stage."""

    settings = controller.settings_store.load()
    chain_id = str(payload.get("chain_id") or "")
    stage_name = str(payload.get("stage") or "")
    chain = syncchains.require_chain(settings, chain_id)
    current = chain["stages"].get(stage_name) or {}
    initial_path = str(current.get("repository_path") or chain["project_path"])
    selected = choose_directory(initial_path, f"Choose {syncchains.STAGE_LABELS.get(stage_name, 'stage')} folder")
    if not selected:
        return state_builder(controller, settings)
    updates = syncchains.configure_local_stage_update(settings, chain_id, stage_name, selected)
    return state_builder(controller, controller.settings_store.save(updates))


def handle_configure_artifact_sync(
    controller: Any,
    payload: dict[str, Any],
    state_builder: StateBuilder,
) -> dict[str, Any]:
    """Enable or disable release-assets-only delivery on the exact terminal repository edge."""

    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise AppError("Artifact delivery mode must be enabled or disabled.", "SYNC_ARTIFACT_MODE_INVALID")
    settings = controller.settings_store.load()
    updates = syncchains.configure_artifact_sync_update(
        settings,
        str(payload.get("chain_id") or ""),
        str(payload.get("edge") or ""),
        enabled,
    )
    return state_builder(controller, controller.settings_store.save(updates))
