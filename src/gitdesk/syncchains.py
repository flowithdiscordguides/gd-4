"""Durable one-way Project Sync Chain metadata and validation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from gitdesk.errors import AppError
from gitdesk.localfeatures import feature_path_for_version
from gitdesk.syncchain_destinations import (
    clean_stage,
    require_local_folder,
    require_managed_repository,
    stage_is_local,
)
from gitdesk.syncchain_destinations import validate_distinct_chain_paths as validate_destination_paths
from gitdesk.syncchain_records import clean_receipt, sync_timestamp
from gitdesk.syncchain_projects import require_saved_project


# Stages are ordered because repository content is only allowed to move forward.
STAGE_NAMES = ("private_beta", "public_beta", "public")

# Each edge owns one receipt that proves what content reached its destination.
EDGE_NAMES = ("local_to_private_beta", "private_beta_to_public_beta", "public_beta_to_public")

# Human-readable labels keep backend errors consistent with the setup page.
STAGE_LABELS = {
    "private_beta": "Private Beta",
    "public_beta": "Public Beta",
    "public": "Public",
}


# Sanitizes a chain while preserving incomplete stage configuration for later repair.
def clean_sync_chain(value: Any) -> dict[str, Any] | None:
    """Return one valid chain record, or None when its identity or project path is missing."""

    if not isinstance(value, dict):
        return None
    chain_id = str(value.get("id") or "").strip()
    project_path = str(value.get("project_path") or "").strip()
    if not chain_id or not project_path:
        return None
    raw_stages = value.get("stages") if isinstance(value.get("stages"), dict) else {}
    raw_receipts = value.get("receipts") if isinstance(value.get("receipts"), dict) else {}
    stages = {name: stage for name in STAGE_NAMES if (stage := clean_stage(raw_stages.get(name)))}
    receipts = {name: receipt for name in EDGE_NAMES if (receipt := clean_receipt(raw_receipts.get(name)))}
    created_at = str(value.get("created_at") or "").strip()[:40]
    updated_at = str(value.get("updated_at") or created_at).strip()[:40]
    artifact_only_edge = str(value.get("artifact_only_edge") or "").strip()
    if not artifact_only_edge and value.get("public_artifacts_only") is True:
        artifact_only_edge = "public_beta_to_public"
    if artifact_only_edge != terminal_artifact_edge(stages):
        artifact_only_edge = ""
    return {
        "id": chain_id[:64],
        "project_path": project_path,
        "stages": stages,
        "receipts": receipts,
        "artifact_only_edge": artifact_only_edge,
        "public_artifacts_only": artifact_only_edge == "public_beta_to_public",
        "created_at": created_at,
        "updated_at": updated_at,
    }


# De-duplicates chains by both stable id and Local Mode project path.
def clean_sync_chains(value: Any) -> list[dict[str, Any]]:
    """Return valid chains with at most one chain per saved project path."""

    if not isinstance(value, list):
        return []
    chains = []
    seen_ids: set[str] = set()
    seen_projects: set[str] = set()
    for raw_chain in value:
        chain = clean_sync_chain(raw_chain)
        if not chain or chain["id"] in seen_ids or chain["project_path"] in seen_projects:
            continue
        chains.append(chain)
        seen_ids.add(chain["id"])
        seen_projects.add(chain["project_path"])
    return sorted(chains, key=lambda item: (item["project_path"].lower(), item["id"]))


# Finds one chain by stable id and fails instead of allowing a frontend-forged record.
def require_chain(settings: dict[str, Any], chain_id: str) -> dict[str, Any]:
    """Return a saved chain matching chain_id or raise a structured not-found error."""

    cleaned_id = str(chain_id or "").strip()
    chain = next((item for item in clean_sync_chains(settings.get("sync_chains")) if item["id"] == cleaned_id), None)
    if not chain:
        raise AppError("The selected sync chain no longer exists.", "SYNC_CHAIN_NOT_FOUND")
    return chain


# Validates every configured folder remains separate before saving or running a chain.
def validate_distinct_chain_paths(project_path: str, stages: dict[str, dict[str, Any]]) -> None:
    """Raise when the Local Mode project or any configured stage folders overlap on disk."""

    validate_destination_paths(project_path, stages, STAGE_LABELS)


def terminal_artifact_edge(stages: dict[str, dict[str, Any]]) -> str:
    """Return the artifact-capable edge into the final configured repository stage, or empty."""

    configured = [name for name in STAGE_NAMES if name in stages]
    if len(configured) < 2 or tuple(configured) != STAGE_NAMES[:len(configured)]:
        return ""
    destination_index = STAGE_NAMES.index(configured[-1])
    source = stages.get(STAGE_NAMES[destination_index - 1])
    destination = stages.get(STAGE_NAMES[destination_index])
    if stage_is_local(source) or stage_is_local(destination):
        return ""
    return EDGE_NAMES[destination_index]


def artifact_only_for_edge(chain: dict[str, Any], edge_name: str) -> bool:
    """Return whether one edge owns the saved source-free release delivery mode."""

    configured_edge = str(chain.get("artifact_only_edge") or "")
    if not configured_edge and chain.get("public_artifacts_only") is True:
        configured_edge = "public_beta_to_public"
    return configured_edge == edge_name


# Creates one empty ordered chain for a saved Local Mode project.
def create_chain_update(settings: dict[str, Any], project_path: str) -> dict[str, Any]:
    """Return a sync_chains update containing a new one-per-project chain."""

    project = require_saved_project(settings, project_path)
    chains = clean_sync_chains(settings.get("sync_chains"))
    if any(chain["project_path"] == project["path"] for chain in chains):
        raise AppError("That Local Mode project already has a sync chain.", "SYNC_CHAIN_PROJECT_EXISTS")
    timestamp = sync_timestamp()
    chains.append({
        "id": uuid4().hex,
        "project_path": project["path"],
        "stages": {},
        "receipts": {},
        "artifact_only_edge": "",
        "created_at": timestamp,
        "updated_at": timestamp,
    })
    return {"sync_chains": clean_sync_chains(chains)}


# Returns the first stage index whose configuration becomes invalid after a changed stage.
def stage_index(stage_name: str) -> int:
    """Return the ordered index for a recognized stage name."""

    if stage_name not in STAGE_NAMES:
        raise AppError("The requested sync stage is invalid.", "SYNC_STAGE_INVALID")
    return STAGE_NAMES.index(stage_name)


# Configures one stage while clearing receipts that depended on its prior destination.
def configure_stage_update(
    settings: dict[str, Any],
    chain_id: str,
    stage_name: str,
    account_login: str,
    repository_path: str,
) -> dict[str, Any]:
    """Return a sync_chains update with one validated managed repository stage assigned."""

    index = stage_index(stage_name)
    chain = require_chain(settings, chain_id)
    repository = require_managed_repository(settings, account_login, repository_path)
    stages = dict(chain["stages"])
    if index > 0 and STAGE_NAMES[index - 1] not in stages:
        previous = STAGE_LABELS[STAGE_NAMES[index - 1]]
        raise AppError(f"Configure {previous} before adding this stage.", "SYNC_STAGE_PREVIOUS_REQUIRED")
    stages[stage_name] = {
        "local_only": False,
        "account_login": str(account_login).strip(),
        "repository_path": repository["path"],
    }
    validate_distinct_chain_paths(chain["project_path"], stages)
    receipts = {
        edge: receipt
        for edge, receipt in chain["receipts"].items()
        if EDGE_NAMES.index(edge) < index
    }
    updated_chain = {**chain, "stages": stages, "receipts": receipts, "updated_at": sync_timestamp()}
    chains = [
        updated_chain if item["id"] == chain["id"] else item
        for item in clean_sync_chains(settings.get("sync_chains"))
    ]
    return {"sync_chains": clean_sync_chains(chains)}


# Configures one stage from an explicit native folder selection without requiring Git metadata.
def configure_local_stage_update(
    settings: dict[str, Any],
    chain_id: str,
    stage_name: str,
    folder_path: str,
) -> dict[str, Any]:
    """Return a sync_chains update with one validated ordinary local folder stage assigned."""

    index = stage_index(stage_name)
    chain = require_chain(settings, chain_id)
    if index > 0 and STAGE_NAMES[index - 1] not in chain["stages"]:
        previous = STAGE_LABELS[STAGE_NAMES[index - 1]]
        raise AppError(f"Configure {previous} before adding this stage.", "SYNC_STAGE_PREVIOUS_REQUIRED")
    stages = dict(chain["stages"])
    stages[stage_name] = {
        "local_only": True,
        "repository_path": require_local_folder(folder_path),
    }
    validate_distinct_chain_paths(chain["project_path"], stages)
    receipts = {edge: value for edge, value in chain["receipts"].items() if EDGE_NAMES.index(edge) < index}
    updated_chain = {**chain, "stages": stages, "receipts": receipts, "updated_at": sync_timestamp()}
    chains = [
        updated_chain if item["id"] == chain["id"] else item
        for item in clean_sync_chains(settings.get("sync_chains"))
    ]
    return {"sync_chains": clean_sync_chains(chains)}


# Changes the final edge mode while invalidating only completion recorded under the prior mode.
def configure_public_artifact_sync_update(
    settings: dict[str, Any],
    chain_id: str,
    enabled: bool,
) -> dict[str, Any]:
    """Return a sync_chains update with artifact-only final publication enabled or disabled."""

    return configure_artifact_sync_update(settings, chain_id, "public_beta_to_public", enabled)


def configure_artifact_sync_update(
    settings: dict[str, Any],
    chain_id: str,
    edge_name: str,
    enabled: bool,
) -> dict[str, Any]:
    """Return a sync_chains update with release assets enabled on the terminal repository edge."""

    chain = require_chain(settings, chain_id)
    eligible_edge = terminal_artifact_edge(chain["stages"])
    if edge_name != eligible_edge:
        message = "Built artifacts only requires the final two configured stages to be GitHub repositories."
        raise AppError(message, "SYNC_ARTIFACT_EDGE_REQUIRED")
    requested = bool(enabled)
    current_edge = str(chain.get("artifact_only_edge") or "")
    requested_edge = edge_name if requested else ""
    if requested_edge == current_edge:
        return {"sync_chains": clean_sync_chains(settings.get("sync_chains"))}
    receipts = dict(chain["receipts"])
    receipts.pop(edge_name, None)
    updated_chain = {
        **chain,
        "receipts": receipts,
        "artifact_only_edge": requested_edge,
        "public_artifacts_only": requested_edge == "public_beta_to_public",
        "updated_at": sync_timestamp(),
    }
    chains = [
        updated_chain if item["id"] == chain["id"] else item
        for item in clean_sync_chains(settings.get("sync_chains"))
    ]
    return {"sync_chains": clean_sync_chains(chains)}


# Removes a stage and every downstream stage because forward chains cannot contain gaps.
def remove_stage_update(settings: dict[str, Any], chain_id: str, stage_name: str) -> dict[str, Any]:
    """Return a sync_chains update with a stage and all later stages removed."""

    index = stage_index(stage_name)
    chain = require_chain(settings, chain_id)
    stages = {name: stage for name, stage in chain["stages"].items() if STAGE_NAMES.index(name) < index}
    receipts = {edge: receipt for edge, receipt in chain["receipts"].items() if EDGE_NAMES.index(edge) < index}
    updated_chain = {
        **chain,
        "stages": stages,
        "receipts": receipts,
        "artifact_only_edge": "",
        "public_artifacts_only": False,
        "updated_at": sync_timestamp(),
    }
    chains = [
        updated_chain if item["id"] == chain["id"] else item
        for item in clean_sync_chains(settings.get("sync_chains"))
    ]
    return {"sync_chains": clean_sync_chains(chains)}


# Deletes only chain metadata; repository and Local Mode folders remain untouched.
def delete_chain_update(settings: dict[str, Any], chain_id: str) -> dict[str, Any]:
    """Return a sync_chains update without the selected chain."""

    chain = require_chain(settings, chain_id)
    chains = [item for item in clean_sync_chains(settings.get("sync_chains")) if item["id"] != chain["id"]]
    return {"sync_chains": chains}


# Updates one edge receipt only after the filesystem mirror has completed successfully.
def receipt_update(
    settings: dict[str, Any],
    chain_id: str,
    edge_name: str,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Return a sync_chains update containing a sanitized successful sync receipt."""

    if edge_name not in EDGE_NAMES:
        raise AppError("The requested sync edge is invalid.", "SYNC_EDGE_INVALID")
    chain = require_chain(settings, chain_id)
    cleaned_receipt = clean_receipt(receipt)
    if not cleaned_receipt:
        raise AppError("The synchronization receipt is invalid.", "SYNC_RECEIPT_INVALID")
    edge_index = EDGE_NAMES.index(edge_name)
    # A newly installed upstream snapshot makes every later edge receipt stale for the current ordered chain.
    receipts = {
        saved_edge: saved_receipt
        for saved_edge, saved_receipt in chain["receipts"].items()
        if EDGE_NAMES.index(saved_edge) < edge_index
    }
    receipts[edge_name] = cleaned_receipt
    updated_chain = {**chain, "receipts": receipts, "updated_at": sync_timestamp()}
    chains = [
        updated_chain if item["id"] == chain["id"] else item
        for item in clean_sync_chains(settings.get("sync_chains"))
    ]
    return {"sync_chains": clean_sync_chains(chains)}


# Resolves one requested edge into its exact source and destination stage names.
def edge_context(settings: dict[str, Any], chain_id: str, edge_name: str, version_path: str = "") -> dict[str, Any]:
    """Return validated source/destination paths and handoff metadata for one forward edge."""

    if edge_name not in EDGE_NAMES:
        raise AppError("The requested sync edge is invalid.", "SYNC_EDGE_INVALID")
    edge_index = EDGE_NAMES.index(edge_name)
    chain = require_chain(settings, chain_id)
    destination_name = STAGE_NAMES[edge_index]
    destination_stage = chain["stages"].get(destination_name)
    if not destination_stage:
        raise AppError(f"Configure {STAGE_LABELS[destination_name]} before synchronizing.", "SYNC_STAGE_REQUIRED")
    destination_repository = None
    destination_account_login = ""
    if stage_is_local(destination_stage):
        destination_path = require_local_folder(destination_stage["repository_path"])
    else:
        destination_repository = require_managed_repository(
            settings,
            destination_stage["account_login"],
            destination_stage["repository_path"],
        )
        destination_account_login = destination_stage["account_login"]
        destination_path = destination_stage["repository_path"]
    source_repository = None
    source_account_login = ""
    if edge_index == 0:
        project = require_saved_project(settings, chain["project_path"])
        source_path = str(version_path or "").strip()
        feature_path_for_version(Path(project["path"]).expanduser().resolve(), source_path)
    else:
        source_name = STAGE_NAMES[edge_index - 1]
        source_stage = chain["stages"].get(source_name)
        if not source_stage:
            raise AppError(f"Configure {STAGE_LABELS[source_name]} first.", "SYNC_STAGE_REQUIRED")
        if stage_is_local(source_stage):
            source_path = require_local_folder(source_stage["repository_path"])
        else:
            source_repository = require_managed_repository(
                settings,
                source_stage["account_login"],
                source_stage["repository_path"],
            )
            source_account_login = source_stage["account_login"]
            source_path = source_stage["repository_path"]
    validate_distinct_chain_paths(chain["project_path"], chain["stages"])
    return {
        "chain": chain,
        "edge_name": edge_name,
        "source_path": source_path,
        "source_account_login": source_account_login,
        "source_repository": source_repository,
        "destination_path": destination_path,
        "destination_account_login": destination_account_login,
        "destination_repository": destination_repository,
        "destination_label": STAGE_LABELS[destination_name],
        "handoff_destination": bool(destination_repository) and (
            edge_index > 0 or "public_beta" not in chain["stages"]
        ),
    }
