"""Lifecycle reconciliation and frontend state projection for Project Sync Chains."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gitdesk import localfeatures
from gitdesk.localpathremap import remap_path_prefix
from gitdesk.localprojects import clean_local_project_list
from gitdesk.managedrepos import clean_repository_map
from gitdesk.syncchains import EDGE_NAMES, STAGE_NAMES, clean_sync_chains, sync_timestamp


# Rewrites every chain path rooted inside a moved Local Mode project folder.
def remap_project_chains(settings: dict[str, Any], old_root: Path, new_root: Path) -> list[dict[str, Any]]:
    """Return chains with project, stage, and receipt paths remapped below old_root."""

    chains = []
    for chain in clean_sync_chains(settings.get("sync_chains")):
        stages = {
            name: {
                **stage,
                "repository_path": remap_path_prefix(stage["repository_path"], old_root, new_root),
            }
            for name, stage in chain["stages"].items()
        }
        receipts = {
            edge: {
                **receipt,
                "source_path": remap_path_prefix(receipt["source_path"], old_root, new_root),
                "destination_path": remap_path_prefix(receipt["destination_path"], old_root, new_root),
            }
            for edge, receipt in chain["receipts"].items()
        }
        chains.append({
            **chain,
            "project_path": remap_path_prefix(chain["project_path"], old_root, new_root),
            "stages": stages,
            "receipts": receipts,
        })
    return clean_sync_chains(chains)


# Removes chains whose required Local Mode project metadata was removed.
def remove_project_chains(settings: dict[str, Any], remaining_project_paths: set[str]) -> list[dict[str, Any]]:
    """Return chains whose project path remains registered in remaining_project_paths."""

    registered_paths = {str(path).strip() for path in remaining_project_paths if str(path).strip()}
    return [
        chain for chain in clean_sync_chains(settings.get("sync_chains"))
        if chain["project_path"] in registered_paths
    ]


# Clears a removed repository stage and every downstream stage that depended on it.
def detach_repository(settings: dict[str, Any], account_login: str, repository_path: str) -> list[dict[str, Any]]:
    """Return chains with a removed managed repository detached without deleting folders."""

    chains = clean_sync_chains(settings.get("sync_chains"))
    next_chains = []
    for chain in chains:
        matching_indexes = [
            STAGE_NAMES.index(name)
            for name, stage in chain["stages"].items()
            if not stage.get("local_only")
            and stage.get("account_login") == account_login
            and stage["repository_path"] == repository_path
        ]
        if not matching_indexes:
            next_chains.append(chain)
            continue
        cutoff = min(matching_indexes)
        stages = {
            name: stage
            for name, stage in chain["stages"].items()
            if STAGE_NAMES.index(name) < cutoff
        }
        receipts = {
            edge: receipt
            for edge, receipt in chain["receipts"].items()
            if EDGE_NAMES.index(edge) < cutoff
        }
        next_chains.append({
            **chain,
            "stages": stages,
            "receipts": receipts,
            "public_artifacts_only": False,
            "updated_at": sync_timestamp(),
        })
    return clean_sync_chains(next_chains)


# Adds the exact physical version folders needed by setup-page Local-to-Private-Beta controls.
def sync_source_projects(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Return saved Local projects with their currently existing version folders."""

    projects = []
    for record in clean_local_project_list(settings.get("local_projects")):
        project_path = Path(record["path"]).expanduser()
        versions = []
        if project_path.is_dir():
            for feature in localfeatures.list_features(record["path"]):
                versions.extend({
                    "name": version["name"],
                    "path": version["path"],
                    "feature_name": feature["name"],
                } for version in feature.get("versions") or [])
        projects.append({**record, "exists": project_path.is_dir(), "versions": versions})
    return projects


# Builds the complete setup-page payload from sanitized project, repository, and chain metadata.
def sync_chain_state(settings: dict[str, Any]) -> dict[str, Any]:
    """Return frontend-safe Sync Chain setup state without filesystem mutation or credentials."""

    repositories = []
    for login, records in clean_repository_map(settings.get("managed_repositories")).items():
        repositories.extend({**record, "account_login": login} for record in records)
    repositories.sort(key=lambda item: (item["account_login"].lower(), item["full_name"].lower()))
    return {
        "chains": clean_sync_chains(settings.get("sync_chains")),
        "projects": sync_source_projects(settings),
        "repositories": repositories,
    }
