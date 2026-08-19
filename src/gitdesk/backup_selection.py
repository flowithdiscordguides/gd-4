"""Safe Backup Mode source-selection rules and lazy inventory browsing."""

from __future__ import annotations

# Paths stay source-relative while direct-child pagination keeps huge repositories usable.
from pathlib import Path, PurePosixPath
from typing import Any

# Structured errors keep stale, unsafe, or unavailable tree requests visible to the user.
from gitdesk.errors import AppError


# Rule limits reject hostile metadata without silently broadening a backup selection.
MAX_SELECTION_RULES = 2000

# Direct-child pages avoid freezing the WebView on unusually wide folders.
SELECTION_CHILD_PAGE_SIZE = 500


# Converts one selection path to a portable source-relative value.
def clean_selection_path(value: Any) -> str:
    """Return a safe source-relative POSIX path, including an empty source-root path."""

    normalized = str(value or "").replace("\\", "/").strip().strip("/")
    if not normalized:
        return ""
    parts = PurePosixPath(normalized).parts
    drive_path = len(normalized) >= 2 and normalized[1] == ":"
    control_path = any(ord(character) < 32 for character in normalized)
    if normalized.startswith("/") or drive_path or control_path or "." in parts or ".." in parts:
        raise AppError("Backup selections must stay inside their registered source.", "BACKUP_SELECTION_PATH_INVALID")
    return "/".join(parts)


# Returns the nearest explicit rule affecting one path, defaulting to excluded.
def selection_state(rules: dict[str, bool], path_value: Any) -> bool:
    """Return whether a source-relative path is included by its most specific rule."""

    path = clean_selection_path(path_value)
    state = bool(rules.get("", False))
    if not path:
        return state
    parts = path.split("/")
    for index in range(1, len(parts) + 1):
        candidate = "/".join(parts[:index])
        if candidate in rules:
            state = rules[candidate]
    return state


# Detects explicit included descendants needed beneath an excluded folder.
def has_included_descendant(rules: dict[str, bool], path_value: Any) -> bool:
    """Return whether any deeper rule explicitly includes content below path."""

    path = clean_selection_path(path_value)
    prefix = f"{path}/" if path else ""
    return any(rule_path.startswith(prefix) and rule_path != path and included
               for rule_path, included in rules.items())


# Removes redundant rules without changing the effective include/exclude result.
def clean_selection_rules(value: Any) -> dict[str, bool]:
    """Return bounded normalized rules ordered from source root to deepest child."""

    if not isinstance(value, dict) or len(value) > MAX_SELECTION_RULES:
        return {}
    candidates: dict[str, bool] = {}
    for raw_path, included in value.items():
        if not isinstance(included, bool):
            continue
        try:
            path = clean_selection_path(raw_path)
        except AppError:
            continue
        candidates[path] = included
    cleaned: dict[str, bool] = {}
    for path in sorted(candidates, key=lambda item: (item.count("/"), item.casefold())):
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        parent_state = selection_state(cleaned, parent) if path else False
        if candidates[path] != parent_state:
            cleaned[path] = candidates[path]
    return cleaned


# Sanitizes persisted or frontend selection records without accepting duplicate source ownership.
def clean_backup_selection(value: Any) -> list[dict[str, Any]]:
    """Return de-duplicated source selection records containing at least one include rule."""

    if not isinstance(value, list):
        return []
    selection = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id") or "").strip()[:128]
        rules = clean_selection_rules(item.get("rules"))
        if not source_id or source_id in seen or not any(rules.values()):
            continue
        selection.append({"source_id": source_id, "rules": rules})
        seen.add(source_id)
    return selection


# Applies only current registered source ids and makes their rules available to manifest scanning.
def apply_backup_selection(
    sources: list[dict[str, Any]],
    value: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return selected source records and their canonical current-inventory selection."""

    requested = {item["source_id"]: item for item in clean_backup_selection(value)}
    selected_sources = []
    canonical_selection = []
    for source in sources:
        item = requested.get(source["id"])
        if not item:
            continue
        rules = item["rules"]
        # A metadata source is one file, so only its source-root rule can select it.
        if source["kind"] == "file":
            if not selection_state(rules, ""):
                continue
            rules = {"": True}
        selected_sources.append({**source, "selection_rules": rules})
        canonical_selection.append({"source_id": source["id"], "rules": rules})
    return selected_sources, canonical_selection


# Reports source availability without following a registered root symlink.
def source_available(source: dict[str, Any]) -> bool:
    """Return whether one registered source currently has its required filesystem type."""

    raw_path = str(source.get("path") or "").strip()
    path = Path(raw_path).expanduser()
    if not raw_path or path.is_symlink():
        return False
    return path.is_dir() if source.get("kind") == "directory" else path.is_file()


# Preselects every currently available source for the first backup while leaving all choices editable.
def default_backup_selection(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return source-root include rules for every currently available registered source."""

    return [
        {"source_id": source["id"], "rules": {"": True}}
        for source in sources
        if source_available(source)
    ]


# Preselects only available source roots confirmed by the latest complete change scan.
def changed_backup_selection(
    sources: list[dict[str, Any]],
    changed_source_ids: Any,
) -> list[dict[str, Any]]:
    """Return source-root include rules for available detected-change owners."""

    raw_source_ids = changed_source_ids if isinstance(changed_source_ids, list) else []
    requested = {str(source_id or "").strip() for source_id in raw_source_ids}
    return [
        {"source_id": source["id"], "rules": {"": True}}
        for source in sources
        if source["id"] in requested and source_available(source)
    ]


# Groups source roots into the four human-readable Backup Mode sections.
def backup_selection_tree(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return lazy expandable source roots grouped in stable inventory order."""

    group_order = [
        ("local mode backups", "Local Mode"),
        ("repo mode backups", "Repo Mode"),
        ("media mode backup", "Media Mode"),
        ("user settings and other setting backups", "User settings"),
    ]
    groups = []
    for category, label in group_order:
        nodes = []
        for source in sources:
            if source["category"] != category:
                continue
            available = source_available(source)
            nodes.append({
                "source_id": source["id"],
                "name": source["label"],
                "path": "",
                "kind": source["kind"],
                "available": available,
                "expandable": available and source["kind"] == "directory",
            })
        groups.append({"category": category, "label": label, "children": nodes})
    return groups


# Resolves one lazy tree folder while rejecting symlink traversal and stale source ids.
def selection_folder(
    sources: list[dict[str, Any]],
    source_id_value: Any,
    relative_path_value: Any,
) -> tuple[dict[str, Any], Path, Path, str]:
    """Return the source, root, requested folder, and normalized relative path."""

    source_id = str(source_id_value or "").strip()
    source = next((item for item in sources if item["id"] == source_id), None)
    if not source or source["kind"] != "directory":
        raise AppError("That backup source is no longer available.", "BACKUP_SELECTION_SOURCE_INVALID")
    relative_path = clean_selection_path(relative_path_value)
    root = Path(source["path"]).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise AppError("That backup source folder is unavailable.", "BACKUP_SOURCE_UNAVAILABLE")
    root = root.resolve()
    folder = root
    for part in PurePosixPath(relative_path).parts if relative_path else ():
        folder = folder / part
        if folder.is_symlink():
            raise AppError("Linked folders cannot be expanded in Backup selection.", "BACKUP_SELECTION_LINKED_FOLDER")
    if not folder.is_dir():
        raise AppError("That backup selection folder is unavailable.", "BACKUP_SELECTION_FOLDER_INVALID")
    return source, root, folder, relative_path


# Formats file sizes consistently with the compact New Version tree.
def size_label(byte_count: int) -> str:
    """Return a compact binary byte-size label."""

    value = float(max(0, byte_count))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"


# Lists one alphabetical direct-child page so every folder remains incrementally reachable.
def backup_selection_children(
    sources: list[dict[str, Any]],
    source_id_value: Any,
    relative_path_value: Any,
    offset_value: Any,
) -> dict[str, Any]:
    """Return one safe page of direct children for a lazy Backup selection folder."""

    source, root, folder, relative_path = selection_folder(
        sources,
        source_id_value,
        relative_path_value,
    )
    try:
        offset = max(0, int(offset_value or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        entries = sorted(
            folder.iterdir(),
            key=lambda item: (item.is_symlink() or not item.is_dir(), item.name.casefold()),
        )
    except OSError as error:
        raise AppError("That backup selection folder could not be read.", "BACKUP_SOURCE_READ_FAILED") from error
    page = entries[offset:offset + SELECTION_CHILD_PAGE_SIZE]
    children = []
    for path in page:
        child_relative = path.relative_to(root).as_posix()
        is_directory = not path.is_symlink() and path.is_dir()
        try:
            byte_count = path.lstat().st_size
        except OSError:
            byte_count = 0
        children.append({
            "source_id": source["id"],
            "name": path.name,
            "path": child_relative,
            "kind": "directory" if is_directory else "file",
            "available": True,
            "expandable": is_directory,
            "size_label": "" if is_directory else size_label(byte_count),
        })
    next_offset = offset + len(page) if offset + len(page) < len(entries) else None
    return {
        "source_id": source["id"],
        "path": relative_path,
        "children": children,
        "next_offset": next_offset,
    }
