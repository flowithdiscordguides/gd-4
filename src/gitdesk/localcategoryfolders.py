"""Planning and physical folder moves for category-organized Local Mode projects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gitdesk.categorynames import CATEGORY_CONTAINER_NAME, clean_category_name
from gitdesk.errors import AppError
from gitdesk.localproject_records import clean_local_project_list


# Returns a normalized path without requiring a disconnected or missing project to exist.
def normalized_path(path_value: Any) -> Path:
    """Return a normalized absolute path for migration comparisons."""

    return Path(str(path_value or "").strip()).expanduser().resolve(strict=False)


# Returns whether either path is the other path or one of its descendants.
def paths_overlap(first: Path, second: Path) -> bool:
    """Return whether two folder roots overlap."""

    try:
        first.relative_to(second)
        return True
    except ValueError:
        pass
    try:
        second.relative_to(first)
        return True
    except ValueError:
        return False


# Derives the selected parent that owns category folders for one project record.
def category_parent(record: dict[str, Any], source: Path) -> Path:
    """Return the parent that owns the categories container for this project."""

    if source.parent.parent.name == CATEGORY_CONTAINER_NAME:
        return source.parent.parent.parent
    return source.parent.parent if record.get("category_foldered") is True else source.parent


# Builds the required destination without touching the filesystem.
def category_destination(record: dict[str, Any], source: Path) -> Path | None:
    """Return parent/categories/category/project for a categorized record, or None when uncategorized."""

    category = clean_category_name(record.get("category"))
    if not category:
        return None
    return category_parent(record, source) / CATEGORY_CONTAINER_NAME / category / source.name


# Rejects a future category/project path that would contain or sit inside another saved project root.
def validate_new_project_destination(
    parent_path_value: Any,
    category: str,
    project_name: str,
    settings: dict[str, Any],
) -> None:
    """Raise a structured error when a new category project would overlap a saved project."""

    parent = normalized_path(parent_path_value)
    target = parent / CATEGORY_CONTAINER_NAME / clean_category_name(category) / str(project_name or "").strip()
    for record in clean_local_project_list(settings.get("local_projects")):
        if paths_overlap(target, normalized_path(record["path"])):
            raise AppError(
                "The new category project path overlaps another saved project.",
                "LOCAL_PROJECT_OVERLAPS_SAVED_PROJECT",
                {"target": str(target), "saved_project": record["path"]},
            )


# Explains one unsafe candidate without hiding the project from the migration list.
def candidate_reason(
    record: dict[str, Any],
    source: Path,
    target: Path | None,
    saved_roots: list[Path],
) -> str:
    """Return an empty string for a movable project or a user-facing blocking reason."""

    raw_source = Path(str(record.get("path") or "")).expanduser()
    if not str(record.get("category") or "").strip():
        return "Assign this project a category in Local Mode first."
    if raw_source.is_symlink():
        return "Symbolic-link project folders cannot be moved."
    if not source.exists() or not source.is_dir():
        return "The saved project folder is missing."
    if target is None:
        return "The project category is unavailable."
    raw_category_root = target.parent.parent
    if raw_category_root.is_symlink():
        return "The categories folder is a symbolic link."
    if raw_category_root.exists() and not raw_category_root.is_dir():
        return "The categories path already exists and is not a folder."
    raw_category = target.parent
    if raw_category.is_symlink():
        return "The category folder is a symbolic link."
    if raw_category.exists() and not raw_category.is_dir():
        return "The category path already exists and is not a folder."
    if target.exists():
        return "The destination project folder already exists."
    for other_root in saved_roots:
        if other_root != source and paths_overlap(target, other_root):
            return "The destination overlaps another saved project."
    return ""


# Returns every legacy or category-mismatched project for the User settings checklist.
def category_folder_migration_state(settings: dict[str, Any]) -> dict[str, Any]:
    """Return the saved preference and current whole-project migration candidates."""

    records = clean_local_project_list(settings.get("local_projects"))
    saved_roots = [normalized_path(record["path"]) for record in records]
    projects = []
    for record in records:
        source = normalized_path(record["path"])
        category = str(record.get("category") or "")
        already_organized = (
            record.get("category_foldered") is True
            and source.parent.name == category
            and source.parent.parent.name == CATEGORY_CONTAINER_NAME
        )
        if already_organized:
            continue
        target = category_destination(record, source)
        reason = candidate_reason(record, source, target, saved_roots)
        projects.append({
            "name": str(record.get("name") or source.name),
            "category": category,
            "source": str(source),
            "target": str(target) if target else "",
            "eligible": not reason,
            "reason": reason,
        })
    return {
        "enabled": settings.get("create_categories_as_folders") is True,
        "projects": projects,
    }


# Validates the complete checkbox selection before any project folder is moved.
def project_migration_plans(settings: dict[str, Any], selected_paths: Any) -> list[dict[str, Any]]:
    """Return preflighted move plans for selected saved project roots."""

    if not isinstance(selected_paths, list) or not selected_paths:
        raise AppError("Select at least one project to move.", "CATEGORY_FOLDER_SELECTION_EMPTY")
    selected = [str(normalized_path(path)) for path in selected_paths if str(path or "").strip()]
    if not selected or len(selected) != len(set(selected)):
        raise AppError("Project migration selection is invalid.", "CATEGORY_FOLDER_SELECTION_INVALID")

    candidates = {
        project["source"]: project
        for project in category_folder_migration_state(settings)["projects"]
    }
    plans = []
    target_paths = set()
    for source_value in selected:
        candidate = candidates.get(source_value)
        if not candidate:
            raise AppError(
                "A selected project is no longer available for category migration.",
                "CATEGORY_FOLDER_PROJECT_STALE",
                {"project_path": source_value},
            )
        if not candidate["eligible"]:
            raise AppError(
                candidate["reason"],
                "CATEGORY_FOLDER_PROJECT_BLOCKED",
                {"project_path": source_value},
            )
        target_value = candidate["target"]
        if target_value in target_paths:
            raise AppError(
                "Selected projects resolve to the same destination.",
                "CATEGORY_FOLDER_TARGET_DUPLICATE",
            )
        target_paths.add(target_value)
        plans.append({
            **candidate,
            "source_path": Path(source_value),
            "target_path": Path(target_value),
        })
    return plans


# Moves the complete project root after preflight and records every parent folder it created.
def move_project_root(plan: dict[str, Any]) -> list[Path]:
    """Move one entire project folder and return the parent folders created for rollback."""

    source = plan["source_path"]
    target = plan["target_path"]
    categories_folder = target.parent.parent
    category_folder = target.parent
    created_folders = []
    try:
        for folder in (categories_folder, category_folder):
            if folder.is_symlink():
                raise OSError(f"Cannot create a category path through symbolic link {folder}")
            if folder.exists():
                if not folder.is_dir():
                    raise OSError(f"Category path is not a folder: {folder}")
                continue
            folder.mkdir(parents=False, exist_ok=False)
            created_folders.append(folder)
        source.rename(target)
    except OSError as error:
        for folder in reversed(created_folders):
            try:
                folder.rmdir()
            except OSError:
                pass
        raise AppError(
            "GitDesk could not move the complete project into its category folder.",
            "CATEGORY_FOLDER_MOVE_FAILED",
            {"source": str(source), "target": str(target)},
        ) from error
    return created_folders


# Reverses one completed physical move during compensating rollback.
def rollback_project_root(plan: dict[str, Any], created_folders: list[Path]) -> None:
    """Move a project back and remove only its parent folders that GitDesk created."""

    source = plan["source_path"]
    target = plan["target_path"]
    if target.exists() and not source.exists():
        target.rename(source)
    elif target.exists() or not source.exists():
        raise OSError(f"Cannot safely restore {source}")
    for folder in reversed(created_folders):
        folder.rmdir()


# Marks exactly one moved record as physically organized under its category.
def mark_project_category_foldered(projects: Any, project_path: Path) -> list[dict[str, Any]]:
    """Return project records with the moved target marked as category-foldered."""

    target = str(project_path)
    return [
        {**record, "category_foldered": True} if record["path"] == target else record
        for record in clean_local_project_list(projects)
    ]
