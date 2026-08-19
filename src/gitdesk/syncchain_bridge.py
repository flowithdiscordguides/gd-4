"""Bridge handlers for Project Sync Chain setup and forward folder promotion."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from gitdesk import localactivity, syncchains
from gitdesk.authrecovery import settings_with_token_accounts
from gitdesk.errors import AppError
from gitdesk.githubapi import GitHubApiClient
from gitdesk.localactivity_store import activity_store
from gitdesk.managedrepos import repository_registry_update
from gitdesk.repositorysetup import create_new_repository, resolve_new_repository_target
from gitdesk.syncchain_lifecycle import sync_chain_state
from gitdesk.syncchain_configuration_bridge import (
    handle_choose_sync_stage_folder,
    handle_configure_artifact_sync,
)
from gitdesk.syncchain_handoff import destination_repository_handoff
from gitdesk.syncchain_jobs import start_sync_chain_job, sync_chain_job_status
from gitdesk.syncrelease import promote_latest_release
from gitdesk.synctransaction import SYNC_TRANSACTION_LOCK, begin_mirror_transaction
from gitdesk.syncignore_store import SyncIgnoreStore
from gitdesk.syncnotifications import sync_chain_notifications


# Sync Chain handlers are registered independently so the main bridge remains below its file ceiling.
def sync_chain_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for chain metadata, repository stages, and one-way mirrors."""

    return {
        "syncChainsState": lambda payload: handle_sync_chains_state(controller, payload),
        "syncChainNotifications": lambda payload: handle_sync_chain_notifications(controller, payload),
        "createSyncChain": lambda payload: handle_create_sync_chain(controller, payload),
        "deleteSyncChain": lambda payload: handle_delete_sync_chain(controller, payload),
        "configureSyncStage": lambda payload: handle_configure_sync_stage(controller, payload),
        "configurePublicArtifactSync": lambda payload: handle_configure_public_artifact_sync(controller, payload),
        "configureArtifactSync": lambda payload: handle_configure_artifact_sync(controller, payload, sync_state),
        "removeSyncStage": lambda payload: handle_remove_sync_stage(controller, payload),
        "chooseSyncStageFolder": lambda payload: handle_choose_sync_stage_folder(controller, payload, sync_state),
        "createSyncStageRepository": lambda payload: handle_create_sync_stage_repository(controller, payload),
        "syncChainEdge": lambda payload: handle_sync_chain_edge(controller, payload),
        "startSyncChainEdge": lambda payload: start_sync_chain_job(controller, payload, run_sync_edge),
        "syncChainJobStatus": sync_chain_job_status,
        "syncLocalVersionToPrivateBeta": lambda payload: handle_sync_local_version(controller, payload),
    }


# Returns settings plus fully resolved setup-page records without exposing tokens.
def sync_state(controller: Any, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the frontend-safe settings and Sync Chain state payload."""

    current = settings_with_token_accounts(controller.settings_store, controller.token_store)
    auth = controller.auth_state(current)
    frontend_settings = {
        **current,
        "github_accounts": auth["accounts"],
        "active_account": auth["active_account"],
    }
    return {"settings": frontend_settings, "auth": auth, "sync": sync_chain_state(current)}


# Loads current chain configuration for the setup page.
def handle_sync_chains_state(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return all saved chains, Local Mode projects, managed repositories, and account metadata."""

    return sync_state(controller)


# Runs only Local Mode file detection so responsive notification polling never scans Git commit history.
def handle_sync_chain_notifications(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return pending project notifications after updating factual Local Mode file fingerprints."""

    settings = controller.settings_store.load()
    events, warnings = activity_store(controller.settings_store.config_path).scan(
        localactivity.project_contexts(settings)
    )
    return {
        "sync_chain_notifications": sync_chain_notifications(settings, events),
        "warnings": warnings,
    }


# Creates one empty chain for a Local Mode project already stored in GitDesk metadata.
def handle_create_sync_chain(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a one-per-project Sync Chain and return refreshed setup state."""

    settings = controller.settings_store.load()
    updates = syncchains.create_chain_update(settings, str(payload.get("project_path") or ""))
    return sync_state(controller, controller.settings_store.save(updates))


# Deletes chain metadata without deleting any Local Mode or repository folder.
def handle_delete_sync_chain(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Delete one saved Sync Chain and return refreshed setup state."""

    settings = controller.settings_store.load()
    updates = syncchains.delete_chain_update(settings, str(payload.get("chain_id") or ""))
    return sync_state(controller, controller.settings_store.save(updates))


# Assigns one existing managed repository to an ordered chain stage.
def handle_configure_sync_stage(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Configure a stage from an exact repository record already stored in GitDesk."""

    settings = controller.settings_store.load()
    updates = syncchains.configure_stage_update(
        settings,
        str(payload.get("chain_id") or ""),
        str(payload.get("stage") or ""),
        str(payload.get("account_login") or ""),
        str(payload.get("repository_path") or ""),
    )
    return sync_state(controller, controller.settings_store.save(updates))


# Persists the explicit final-edge release mode while clearing completion from the prior mode.
def handle_configure_public_artifact_sync(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Enable or disable artifact-only Public release promotion for one saved chain."""

    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise AppError("Final sync mode must be enabled or disabled.", "SYNC_PUBLIC_MODE_INVALID")
    settings = controller.settings_store.load()
    updates = syncchains.configure_public_artifact_sync_update(
        settings,
        str(payload.get("chain_id") or ""),
        enabled,
    )
    return sync_state(controller, controller.settings_store.save(updates))


# Removes a stage and every downstream stage while preserving all physical repositories.
def handle_remove_sync_stage(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Remove one configured stage and return refreshed setup state."""

    settings = controller.settings_store.load()
    updates = syncchains.remove_stage_update(
        settings,
        str(payload.get("chain_id") or ""),
        str(payload.get("stage") or ""),
    )
    return sync_state(controller, controller.settings_store.save(updates))


# Validates stage ordering and target separation before creating a remote repository.
def validate_new_stage_target(
    settings: dict[str, Any],
    chain_id: str,
    stage_name: str,
    target_path: Path,
) -> dict[str, Any]:
    """Return the selected chain after validating a proposed new repository folder."""

    index = syncchains.stage_index(stage_name)
    chain = syncchains.require_chain(settings, chain_id)
    if index > 0 and syncchains.STAGE_NAMES[index - 1] not in chain["stages"]:
        previous = syncchains.STAGE_LABELS[syncchains.STAGE_NAMES[index - 1]]
        raise AppError(f"Configure {previous} before adding this stage.", "SYNC_STAGE_PREVIOUS_REQUIRED")
    proposed_stages = {
        **chain["stages"],
        stage_name: {"account_login": "pending", "repository_path": str(target_path)},
    }
    syncchains.validate_distinct_chain_paths(chain["project_path"], proposed_stages)
    return chain


# Creates a new GitHub repository and local checkout, registers it, and assigns it to one stage.
def handle_create_sync_stage_repository(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create and configure a separate repository folder for one Sync Chain stage."""

    settings = controller.settings_store.load()
    chain_id = str(payload.get("chain_id") or "")
    stage_name = str(payload.get("stage") or "")
    target_path = resolve_new_repository_target(
        str(payload.get("parent_path") or ""),
        str(payload.get("folder_name") or ""),
    )
    validate_new_stage_target(settings, chain_id, stage_name, target_path)
    owner = str(payload.get("owner") or "").strip()
    account = controller.account_for_owner(owner, payload, required=True)
    client = GitHubApiClient(controller.token_for_account(account))
    result = create_new_repository(
        controller.git_service,
        str(payload.get("parent_path") or ""),
        str(payload.get("folder_name") or ""),
        account,
        client,
        owner or account["login"],
        str(payload.get("repo") or ""),
        bool(payload.get("private", False)),
        [],
    )
    latest = controller.settings_store.load()
    registry_updates = repository_registry_update(latest, account["login"], result["repository"], "created")
    working_settings = {**latest, **registry_updates}
    chain_updates = syncchains.configure_stage_update(
        working_settings,
        chain_id,
        stage_name,
        account["login"],
        result["repository"]["path"],
    )
    saved = controller.settings_store.save({**registry_updates, **chain_updates})
    return {"created": result, **sync_state(controller, saved)}


# Mirrors one resolved edge and saves its receipt only while rollback remains possible.
def ignored_paths_for_context(context: dict[str, Any]) -> frozenset[str]:
    """Return project rules only for the Local-to-Private-Beta edge."""

    if context["edge_name"] != "local_to_private_beta":
        return frozenset()
    project_path = str(context["chain"]["project_path"])
    return frozenset(SyncIgnoreStore().rules_for_project(project_path))


# Compares only the remote identity fields that determine release API targets, not mutable display metadata.
def repository_remote_identity(context: dict[str, Any], key: str) -> tuple[str, str]:
    """Return the owner/repository pair saved under a resolved edge context key."""

    repository = context.get(key) or {}
    return str(repository.get("owner") or ""), str(repository.get("repo") or "")


# Mirrors one resolved edge and saves its receipt only while rollback remains possible.
def run_sync_edge_locked(
    controller: Any,
    settings: dict[str, Any],
    chain_id: str,
    edge_name: str,
    version_path: str,
    expected_release_tag: str = "",
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run one transactional edge sync and return refreshed state plus copy statistics."""

    context = syncchains.edge_context(settings, chain_id, edge_name, version_path)
    ignored_paths = ignored_paths_for_context(context)
    artifact_release = syncchains.artifact_only_for_edge(context["chain"], edge_name)
    transaction = None
    release_result = None
    if artifact_release:
        release_result = promote_latest_release(controller, context, expected_release_tag, progress)
    else:
        transaction = begin_mirror_transaction(
            context["source_path"],
            context["destination_path"],
            ignored_paths,
        )
    try:
        latest = controller.settings_store.load()
        latest_context = syncchains.edge_context(latest, chain_id, edge_name, version_path)
        stable_paths = (
            latest_context["source_path"] == context["source_path"]
            and latest_context["source_account_login"] == context["source_account_login"]
            and latest_context["destination_path"] == context["destination_path"]
            and latest_context["destination_account_login"] == context["destination_account_login"]
            and latest_context["handoff_destination"] == context["handoff_destination"]
            and syncchains.artifact_only_for_edge(latest_context["chain"], edge_name)
            == syncchains.artifact_only_for_edge(context["chain"], edge_name)
            and repository_remote_identity(latest_context, "source_repository")
            == repository_remote_identity(context, "source_repository")
            and repository_remote_identity(latest_context, "destination_repository")
            == repository_remote_identity(context, "destination_repository")
        )
        if not stable_paths:
            raise AppError("Sync Chain configuration changed during synchronization.", "SYNC_CHAIN_CHANGED")
        # Rule changes alter the installed snapshot and must therefore roll back like a changed chain destination.
        if ignored_paths_for_context(latest_context) != ignored_paths:
            raise AppError("Sync Ignore rules changed during synchronization.", "SYNC_IGNORE_CHANGED")
        receipt = release_result["receipt"] if release_result is not None else transaction.receipt()
        updates = syncchains.receipt_update(latest, chain_id, edge_name, receipt)
        repository_handoff = None
        # Release-only publication never depends on or opens the unchanged local Public checkout.
        if context["handoff_destination"] and not artifact_release:
            selection_updates, repository_handoff = destination_repository_handoff(
                controller,
                {**latest, **updates},
                latest_context,
            )
            updates = {**updates, **selection_updates}
        saved = controller.settings_store.save(updates)
    except Exception:
        if transaction:
            transaction.rollback()
        raise
    warning = transaction.commit() if transaction else ""
    if progress:
        progress({"phase": "complete", "message": "Artifact synchronization complete"})
    return {
        "sync_result": {
            "edge": edge_name,
            "source": context["source_path"],
            "destination": context["destination_path"],
            "receipt": receipt,
            "ignored_path_count": len(ignored_paths),
            "warning": warning,
            "release": release_result["release"] if release_result is not None else None,
        },
        "repository_handoff": repository_handoff,
        **sync_state(controller, saved),
    }


# Holds the global sync lock through filesystem installation, receipt persistence, and final cleanup.
def run_sync_edge(
    controller: Any,
    settings: dict[str, Any],
    chain_id: str,
    edge_name: str,
    version_path: str,
    expected_release_tag: str = "",
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Serialize one complete Sync Chain edge transaction against other bridge workers."""

    if progress:
        progress({"phase": "queued", "message": "Checking artifact sync availability"})
        if not SYNC_TRANSACTION_LOCK.acquire(blocking=False):
            raise AppError(
                "Another Sync Chain operation is still running. Wait for it to finish, then retry this artifact edge.",
                "SYNC_CHAIN_BUSY",
            )
        try:
            return run_sync_edge_locked(
                controller, settings, chain_id, edge_name, version_path, expected_release_tag, progress,
            )
        finally:
            SYNC_TRANSACTION_LOCK.release()
    with SYNC_TRANSACTION_LOCK:
        return run_sync_edge_locked(
            controller,
            settings,
            chain_id,
            edge_name,
            version_path,
            expected_release_tag,
            progress,
        )


# Synchronizes an explicit configured edge from the setup page.
def handle_sync_chain_edge(
    controller: Any,
    payload: dict[str, Any],
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Synchronize one requested forward repository edge."""

    settings = controller.settings_store.load()
    return run_sync_edge(
        controller,
        settings,
        str(payload.get("chain_id") or ""),
        str(payload.get("edge") or ""),
        "",
        str(payload.get("expected_release_tag") or ""),
        progress,
    )


# Resolves the active Local Mode project chain and sends its selected version to Private Beta.
def handle_sync_local_version(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Synchronize a selected saved Local Mode version into its configured Private Beta repository."""

    settings = controller.settings_store.load()
    project_path = str(payload.get("project_path") or settings.get("active_local_project") or "")
    version_path = str(payload.get("version_path") or settings.get("active_local_version") or "")
    chain = next(
        (
            item for item in syncchains.clean_sync_chains(settings.get("sync_chains"))
            if item["project_path"] == project_path
        ),
        None,
    )
    if not chain:
        raise AppError("Set up a Sync Chain for this Local Mode project first.", "SYNC_CHAIN_PROJECT_MISSING")
    return run_sync_edge(
        controller,
        settings,
        chain["id"],
        "local_to_private_beta",
        version_path,
    )
