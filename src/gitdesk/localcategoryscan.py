"""Read-only category-folder discovery and private metadata reconciliation for Local Mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gitdesk import localactivity
from gitdesk import localprojects
from gitdesk import sharedresources
from gitdesk import syncchain_lifecycle
from gitdesk.categorynames import CATEGORY_CONTAINER_NAME, clean_category_name
from gitdesk.errors import AppError
from gitdesk.localpathremap import metadata_uses_path_prefix
from gitdesk.localproject_records import clean_local_project_list
from gitdesk.syncignore_store import SyncIgnoreStore


# These are the complete settings fields whose paths can change during reconciliation.
RECONCILED_SETTING_KEYS = (
    "workspace_mode",
    "repository_path",
    "managed_repositories",
    "active_repository_by_account",
    "local_projects",
    "active_local_project",
    "active_local_feature",
    "active_local_version",
    "local_permission_grants",
    "local_version_statuses",
    "project_timeline",
    "sync_chains",
)


# Validates the user-selected scan root without following a categories-folder symbolic link.
def categories_folder(path_value: Any) -> Path:
    """Return an existing literal categories directory selected for read-only discovery."""

    raw_path = Path(str(path_value or "").strip()).expanduser()
    if not str(path_value or "").strip():
        raise AppError("Choose the categories folder to scan.", "CATEGORY_SCAN_PATH_EMPTY")
    if raw_path.is_symlink():
        raise AppError("The categories folder cannot be a symbolic link.", "CATEGORY_SCAN_PATH_INVALID")
    try:
        resolved_path = raw_path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise AppError("The selected categories folder is unavailable.", "CATEGORY_SCAN_PATH_INVALID") from error
    if not resolved_path.is_dir() or resolved_path.name != CATEGORY_CONTAINER_NAME:
        raise AppError(
            f"Choose the literal {CATEGORY_CONTAINER_NAME} folder.",
            "CATEGORY_SCAN_PATH_INVALID",
        )
    return resolved_path


# Lists only real direct-child directories so the scan never crosses a symbolic-link boundary.
def direct_child_folders(parent: Path, kind: str) -> list[Path]:
    """Return sorted non-symlink directories directly inside parent."""

    folders = []
    try:
        entries = sorted(parent.iterdir(), key=lambda entry: entry.name.casefold())
        for entry in entries:
            if entry.is_symlink():
                if entry.is_dir():
                    raise AppError(
                        f"A symbolic-link {kind} folder cannot be scanned.",
                        "CATEGORY_SCAN_SYMLINK_INVALID",
                        {"path": str(entry)},
                    )
                continue
            if entry.is_dir():
                folders.append(entry)
    except AppError:
        raise
    except OSError as error:
        raise AppError(
            f"GitDesk could not read the selected {kind} folders.",
            "CATEGORY_SCAN_READ_FAILED",
            {"path": str(parent)},
        ) from error
    return folders


# Discovers direct category labels and their direct project folders without opening project files.
def discover_category_projects(path_value: Any) -> dict[str, Any]:
    """Return categories and project roots found below one literal categories folder."""

    root = categories_folder(path_value)
    categories = []
    projects = []
    for category_path in direct_child_folders(root, "category"):
        try:
            category = clean_category_name(category_path.name)
        except AppError as error:
            raise AppError(
                f"Category folder name is invalid: {category_path.name}",
                "CATEGORY_SCAN_CATEGORY_INVALID",
                {"path": str(category_path)},
            ) from error
        categories.append(category)
        for project_path in direct_child_folders(category_path, "project"):
            projects.append({
                "name": project_path.name,
                "category": category,
                "path": str(project_path.resolve()),
            })
    return {
        "categories_folder": str(root),
        "categories": categories,
        "projects": projects,
    }


# Returns names that can identify an older record without treating an arbitrary flat parent as a category.
def record_names(record: dict[str, Any]) -> set[str]:
    """Return the saved and path-derived project names for identity matching."""

    return {
        str(record.get("name") or "").strip(),
        Path(str(record.get("path") or "")).name,
    } - {""}


# Returns category evidence carried by metadata or a formerly category-foldered physical path.
def record_categories(record: dict[str, Any]) -> set[str]:
    """Return category labels that can safely identify a moved project record."""

    categories = {str(record.get("category") or "").strip()} - {""}
    record_path = Path(str(record.get("path") or ""))
    if record.get("category_foldered") is True:
        categories.add(record_path.parent.name)
    return categories


# Finds one destination for a saved record while retaining the evidence used for duplicate consolidation.
def detected_match(
    record: dict[str, Any],
    detected_projects: list[dict[str, str]],
) -> dict[str, str] | None:
    """Return one exact, category/name, or unique-name destination for a saved record."""

    source = str(Path(record["path"]).expanduser().resolve(strict=False))
    exact = [detected for detected in detected_projects if detected["path"] == source]
    if exact:
        detected = exact[0]
        evidence = "exact"
    else:
        named = [
            detected for detected in detected_projects
            if detected["name"] in record_names(record)
        ]
        categorized = [
            detected for detected in named
            if detected["category"] in record_categories(record)
        ]
        candidates = categorized or named
        if len(candidates) > 1:
            raise AppError(
                f"More than one detected folder matches the saved project {record['name']}.",
                "CATEGORY_SCAN_PROJECT_AMBIGUOUS",
            )
        if not candidates:
            return None
        detected = candidates[0]
        evidence = "category_name" if categorized else "name"
    return {
        "source": source,
        "target": detected["path"],
        "category": detected["category"],
        "evidence": evidence,
    }


# Matches only saved projects and permits stale duplicates to merge into one exact canonical detected record.
def existing_project_matches(
    settings: dict[str, Any],
    discovery: dict[str, Any],
) -> list[dict[str, str]]:
    """Return confirmed saved-record matches, including stale duplicates of one exact detected owner."""

    matches = [
        match
        for record in clean_local_project_list(settings.get("local_projects"))
        if (match := detected_match(record, discovery["projects"]))
    ]
    matches_by_target: dict[str, list[dict[str, str]]] = {}
    for match in matches:
        matches_by_target.setdefault(match["target"], []).append(match)
    for target_matches in matches_by_target.values():
        if len(target_matches) < 2:
            continue
        exact_count = sum(match["evidence"] == "exact" for match in target_matches)
        if exact_count != 1:
            raise AppError(
                "More than one saved project could own the same detected folder.",
                "CATEGORY_SCAN_PROJECT_AMBIGUOUS",
            )
    return matches


# Carries one confirmed project-root mapping through every settings-owned absolute path.
def remap_settings_project(
    settings: dict[str, Any],
    source: Path,
    target: Path,
) -> dict[str, Any]:
    """Return complete working settings after remapping one confirmed project root."""

    updates = localprojects.remap_settings_paths(settings, source, target)
    updates["workspace_mode"] = settings.get("workspace_mode", "repo")
    updates["sync_chains"] = syncchain_lifecycle.remap_project_chains(settings, source, target)
    return {**settings, **updates}


# Applies detected category labels only to saved records already matched by the scan.
def apply_matched_categories(
    projects: Any,
    matches: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Return saved records with matched folder categories and category-folder status."""

    categories_by_target = {
        match["target"]: match["category"]
        for match in matches
    }
    records = []
    for record in clean_local_project_list(projects):
        category = categories_by_target.get(record["path"])
        if category is not None:
            record = {
                **record,
                "category": category,
                "category_foldered": True,
            }
        records.append(record)
    return records


# Creates one complete existing-project metadata plan before any private registry is written.
def category_scan_plan(settings: dict[str, Any], path_value: Any) -> dict[str, Any]:
    """Return confirmed existing-project matches and path-only metadata updates."""

    discovery = discover_category_projects(path_value)
    matches = existing_project_matches(settings, discovery)
    mappings_by_source = {
        match["source"]: {"source": match["source"], "target": match["target"]}
        for match in matches
        if match["source"] != match["target"]
    }
    # The migration layout makes each matched project's former Parent/Project root deterministic.
    reconciled_values = {
        key: settings.get(key)
        for key in RECONCILED_SETTING_KEYS
    }
    for match in matches:
        legacy_root = Path(discovery["categories_folder"]).parent / Path(match["target"]).name
        if (
            legacy_root != Path(match["target"])
            and metadata_uses_path_prefix(reconciled_values, legacy_root)
        ):
            mappings_by_source[str(legacy_root)] = {
                "source": str(legacy_root),
                "target": match["target"],
            }
    mappings = list(mappings_by_source.values())
    working_settings = dict(settings)
    for mapping in mappings:
        working_settings = remap_settings_project(
            working_settings,
            Path(mapping["source"]),
            Path(mapping["target"]),
        )

    working_settings["local_projects"] = apply_matched_categories(
        working_settings.get("local_projects"),
        matches,
    )
    return {
        "discovery": discovery,
        "matches": matches,
        "mappings": mappings,
        "updates": {
            key: working_settings.get(key)
            for key in RECONCILED_SETTING_KEYS
        },
    }


# Reverses completed private-registry path writes if a later reconciliation step fails.
def rollback_private_metadata(
    completed: list[dict[str, Any]],
    activity_store: Any,
    sync_ignore_store: SyncIgnoreStore,
    original_sync_ignore: dict[str, Any],
) -> list[str]:
    """Reverse completed metadata remaps and return rollback error descriptions."""

    rollback_errors = []
    for completed_mapping in reversed(completed):
        source = completed_mapping["source"]
        target = completed_mapping["target"]
        if completed_mapping["activity_remapped"]:
            try:
                activity_store.remap_paths(target, source)
            except Exception as error:
                rollback_errors.append(f"Local Activity {target}: {error}")
        if completed_mapping["resources_remapped"]:
            try:
                sharedresources.remap_installations(target, source)
            except Exception as error:
                rollback_errors.append(f"Shared Resources {target}: {error}")
    try:
        sync_ignore_store.write(original_sync_ignore)
    except Exception as error:
        rollback_errors.append(f"Sync Ignore registry: {error}")
    return rollback_errors


# Applies a preflighted scan as one private-metadata transaction while leaving the project tree read-only.
def reconcile_category_scan(controller: Any, path_value: Any) -> dict[str, Any]:
    """Persist one category scan and return refreshed settings, Local state, and scan counts."""

    original_settings = controller.settings_store.load()
    plan = category_scan_plan(original_settings, path_value)
    activity_store = localactivity.activity_store(controller.settings_store.config_path)
    sync_ignore_path = Path(controller.settings_store.config_path).with_name("sync-ignore.json")
    sync_ignore_store = SyncIgnoreStore(sync_ignore_path)
    original_sync_ignore = sync_ignore_store.load()
    completed = []
    save_started = False
    try:
        for mapping in plan["mappings"]:
            source = Path(mapping["source"])
            target = Path(mapping["target"])
            completed_mapping = {
                "source": source,
                "target": target,
                "resources_remapped": False,
                "activity_remapped": False,
            }
            completed.append(completed_mapping)
            sharedresources.remap_installations(source, target)
            completed_mapping["resources_remapped"] = True
            activity_store.remap_paths(source, target)
            completed_mapping["activity_remapped"] = True
            sync_ignore_store.remap_project_path(source, target)
        save_started = True
        saved_settings = controller.settings_store.save(plan["updates"])
        local_state = localprojects.local_projects_state(saved_settings)
    except Exception as error:
        rollback_errors = rollback_private_metadata(
            completed,
            activity_store,
            sync_ignore_store,
            original_sync_ignore,
        )
        if save_started:
            try:
                controller.settings_store.save(original_settings)
            except Exception as restore_error:
                rollback_errors.append(f"settings: {restore_error}")
        if rollback_errors:
            raise AppError(
                "Category scan failed and GitDesk could not completely restore private metadata.",
                "CATEGORY_SCAN_ROLLBACK_FAILED",
                {"rollback_errors": rollback_errors},
            ) from error
        if isinstance(error, AppError):
            raise error
        raise AppError(
            "GitDesk could not reconcile category-folder metadata.",
            "CATEGORY_SCAN_RECONCILIATION_FAILED",
        ) from error

    discovery = plan["discovery"]
    matched_targets = {match["target"] for match in plan["matches"]}
    return {
        "cancelled": False,
        "scan": {
            "categories_folder": discovery["categories_folder"],
            "category_count": len(discovery["categories"]),
            "detected_project_count": len(discovery["projects"]),
            "matched_project_count": len(matched_targets),
            "matched_record_count": len(plan["matches"]),
            "consolidated_record_count": len(plan["matches"]) - len(matched_targets),
            "ignored_project_count": len(discovery["projects"]) - len(matched_targets),
            "remapped_count": len(plan["mappings"]),
        },
        "settings": saved_settings,
        "local": local_state,
    }
