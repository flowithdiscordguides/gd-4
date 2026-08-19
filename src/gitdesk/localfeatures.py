"""Local feature-folder operations for GitDesk Local Mode."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
from typing import Any

from gitdesk.errors import AppError
from gitdesk.localversions import clean_version_label, list_versions, version_number
from gitdesk import sharedresources


# Every new local project starts with an ordered init feature so later features sort naturally.
INIT_FEATURE_NAME = "01 init"
LEGACY_INIT_FEATURE_NAME = "init"

# Ordered feature folders use a two-digit prefix while keeping the user-entered label readable.
FEATURE_PREFIX_PATTERN = re.compile(r"^(?P<number>[0-9]{2,})\s+(?P<label>.+)$")

# Feature names become folder names, so path separators and hidden/system-style names are rejected.
LOCAL_FEATURE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$")


# Validates the feature folder name entered by the user.
def clean_feature_name(value: str) -> str:
    """Return a safe user-entered feature label."""

    name = str(value or "").strip()
    prefix_match = FEATURE_PREFIX_PATTERN.match(name)
    if prefix_match:
        name = prefix_match.group("label").strip()
    if not name or name in {".", ".."}:
        raise AppError("Feature name is required.", "LOCAL_FEATURE_NAME_EMPTY")
    if "/" in name or "\\" in name or name.startswith(".") or not LOCAL_FEATURE_PATTERN.match(name):
        raise AppError("Feature name contains invalid characters.", "LOCAL_FEATURE_NAME_INVALID")
    if version_number(name):
        raise AppError("Feature name cannot use the vN version-folder format.", "LOCAL_FEATURE_NAME_INVALID")
    return name


# Reads the numeric prefix from ordered feature folders and maps legacy init folders to slot 1.
def feature_number(folder_name: str) -> int:
    """Return the ordered feature number encoded in a folder name, or zero for unnumbered features."""

    if folder_name == LEGACY_INIT_FEATURE_NAME:
        return 1
    match = FEATURE_PREFIX_PATTERN.match(folder_name)
    return int(match.group("number")) if match else 0


# Builds a stable sort key that keeps numbered features ahead of older unnumbered folders.
def feature_sort_key(feature: dict[str, Any]) -> tuple[int, int, str]:
    """Return the ordering tuple used by Local Mode feature lists."""

    number = int(feature.get("number") or 0)
    return (0 if number else 1, number, str(feature.get("name") or "").lower())


# Names a first version after the project so editor windows are distinguishable.
def first_version_name(project_path: Path) -> str:
    """Return the v1 folder name for a newly created feature."""

    label = clean_version_label(project_path.name)
    return f"v1 {label}" if label else "v1"


# Creates the payload shape used by frontend version selectors.
def version_payload(version_path: Path) -> dict[str, Any]:
    """Return frontend metadata for one physical local version folder."""

    return {
        "name": version_path.name,
        "number": version_number(version_path.name),
        "path": str(version_path.resolve()),
    }


# Resolves a project path before feature folders are scanned or created inside it.
def normalize_project_directory(path_value: str) -> Path:
    """Return a resolved existing local project directory."""

    cleaned_path = str(path_value or "").strip()
    if not cleaned_path:
        raise AppError("Local project path is required.", "LOCAL_PROJECT_PATH_EMPTY")

    project_path = Path(cleaned_path).expanduser().resolve()
    if not project_path.exists() or not project_path.is_dir():
        raise AppError("Local project path must point to an existing directory.", "LOCAL_PROJECT_PATH_INVALID")
    return project_path


# Installs selected Shared Resources into a local version folder with revision ownership metadata.
def copy_shared_resources(resource_names: list[str], destination: Path) -> int:
    """Install Shared Resources into a local version folder and return the merged file count."""

    copied_files = 0
    for resource_name in resource_names:
        result = sharedresources.install_resource(str(resource_name or ""), str(destination))
        copied_files += int(result.get("file_count") or 0)
    return copied_files


# Builds frontend metadata for one feature folder and the versions directly inside it.
def feature_payload(feature_path: Path, name: str, legacy: bool) -> dict[str, Any]:
    """Return one feature record with its direct vN version folders."""

    versions = list_versions(
        str(feature_path),
        "LOCAL_FEATURE_PATH_EMPTY",
        "LOCAL_FEATURE_PATH_INVALID",
    )
    return {
        "name": name,
        "number": feature_number(name),
        "path": str(feature_path.resolve()),
        "exists": feature_path.is_dir(),
        "legacy": legacy,
        "versions": versions,
    }


# Lists feature folders under one project, including old direct project/vN folders as init.
def list_features(project_path_value: str) -> list[dict[str, Any]]:
    """Return sorted feature folders for a local project."""

    project_path = normalize_project_directory(project_path_value)
    features = []
    direct_versions = list_versions(
        str(project_path),
        "LOCAL_PROJECT_PATH_EMPTY",
        "LOCAL_PROJECT_PATH_INVALID",
    )
    if direct_versions:
        features.append(feature_payload(project_path, INIT_FEATURE_NAME, True))

    for child in sorted(project_path.iterdir(), key=lambda item: item.name.lower()):
        if child.is_dir() and not version_number(child.name):
            display_name = INIT_FEATURE_NAME if child.name == LEGACY_INIT_FEATURE_NAME else child.name
            features.append(feature_payload(child, display_name, child.name == LEGACY_INIT_FEATURE_NAME))
    return sorted(features, key=feature_sort_key)


# Resolves and validates a feature path relative to its project.
def normalize_feature_directory(project_path: Path, feature_path_value: str) -> Path:
    """Return a feature folder path that belongs to the given project."""

    cleaned_path = str(feature_path_value or "").strip()
    if not cleaned_path:
        raise AppError("Local feature path is required.", "LOCAL_FEATURE_PATH_EMPTY")

    feature_path = Path(cleaned_path).expanduser().resolve()
    if not feature_path.exists() or not feature_path.is_dir():
        raise AppError("Local feature path must point to an existing directory.", "LOCAL_FEATURE_PATH_INVALID")

    direct_versions = list_versions(
        str(project_path),
        "LOCAL_PROJECT_PATH_EMPTY",
        "LOCAL_PROJECT_PATH_INVALID",
    )
    valid_legacy_feature = feature_path == project_path and bool(direct_versions)
    valid_feature_child = feature_path.parent == project_path and not version_number(feature_path.name)
    if not valid_legacy_feature and not valid_feature_child:
        raise AppError("Local feature must be inside the selected project.", "LOCAL_FEATURE_PATH_INVALID")
    return feature_path


# Infers the owning feature folder from a selected vN version path.
def feature_path_for_version(project_path: Path, version_path_value: str) -> Path:
    """Return the feature folder that owns a version path."""

    cleaned_path = str(version_path_value or "").strip()
    if not cleaned_path:
        raise AppError("Version folder path is required.", "LOCAL_VERSION_EMPTY")

    version_path = Path(cleaned_path).expanduser().resolve()
    if not version_path.exists() or not version_path.is_dir() or not version_number(version_path.name):
        raise AppError("Version folder path must point to an existing vN folder.", "LOCAL_VERSION_INVALID")
    if version_path.parent == project_path:
        return project_path
    if version_path.parent.parent == project_path and not version_number(version_path.parent.name):
        return version_path.parent
    raise AppError("Local version must belong to the selected project.", "LOCAL_VERSION_INVALID")


# Verifies that a selected version belongs to the active feature.
def validate_version_for_feature(project_path: Path, feature_path: Path, version_path_value: str) -> Path:
    """Return a version path after confirming it belongs to the feature."""

    version_path = Path(str(version_path_value or "")).expanduser().resolve()
    owner_path = feature_path_for_version(project_path, str(version_path))
    if owner_path != feature_path:
        raise AppError("Local version must belong to the selected feature.", "LOCAL_VERSION_INVALID")
    return version_path


# Finds the next ordered feature number without reusing gaps from deleted feature folders.
def next_feature_number(project_path: Path) -> int:
    """Return the next feature sequence number for a project."""

    features_seen = 0
    numbers = []
    direct_versions = list_versions(
        str(project_path),
        "LOCAL_PROJECT_PATH_EMPTY",
        "LOCAL_PROJECT_PATH_INVALID",
    )
    if direct_versions:
        features_seen += 1
        numbers.append(1)

    for child in project_path.iterdir():
        if child.is_dir() and not version_number(child.name):
            features_seen += 1
            number = feature_number(child.name)
            if number:
                numbers.append(number)
    return max(numbers + [features_seen]) + 1


# Combines the next sequence number with the cleaned user label to form the physical folder name.
def next_feature_path(project_path: Path, label_value: str) -> tuple[Path, str]:
    """Return the destination feature path and display name for a new feature."""

    feature_label = clean_feature_name(label_value)
    feature_name = f"{next_feature_number(project_path):02d} {feature_label}"
    feature_path = (project_path / feature_name).resolve()
    if feature_path.parent != project_path:
        raise AppError("Local feature must stay inside the selected project.", "LOCAL_FEATURE_PATH_INVALID")
    return feature_path, feature_name


# Picks the newest version from a feature record because version lists are already sorted numerically.
def latest_feature_version(feature: dict[str, Any]) -> Path | None:
    """Return the latest version path for a feature record, or None when it has no versions."""

    versions = feature.get("versions") or []
    return Path(versions[-1]["path"]).expanduser().resolve() if versions else None


# Reuses Local Mode's ordered feature/version contract for every project-level current-work consumer.
def latest_project_version(features: list[dict[str, Any]]) -> Path | None:
    """Return the latest version in the latest ordered feature containing physical versions."""

    for feature in reversed(features):
        version_path = latest_feature_version(feature)
        if version_path:
            return version_path
    return None


# Resolves the version that should seed a brand-new feature folder.
def source_version_for_new_feature(project_path: Path, source_path_value: str) -> Path | None:
    """Return the selected source version, falling back to the latest version in the project."""

    if str(source_path_value or "").strip():
        try:
            source_path = Path(str(source_path_value)).expanduser().resolve()
            feature_path_for_version(project_path, str(source_path))
            return source_path
        except AppError:
            pass

    return latest_project_version(list_features(str(project_path)))


# Validates that the target feature and first-version paths are available before copying content.
def ensure_new_feature_paths(feature_path: Path, version_path: Path) -> None:
    """Raise an AppError when the new feature or v1 destination would collide with existing content."""

    if feature_path.exists() and not feature_path.is_dir():
        raise AppError("Local feature path already exists and is not a folder.", "LOCAL_FEATURE_EXISTS")
    if feature_path.exists() and any(feature_path.iterdir()):
        raise AppError("Local feature folder already exists and is not empty.", "LOCAL_FEATURE_EXISTS")
    if version_path.exists() and not version_path.is_dir():
        raise AppError("The feature v1 path already exists and is not a folder.", "LOCAL_VERSION_EXISTS")
    if version_path.exists() and any(version_path.iterdir()):
        raise AppError("The feature v1 folder already exists and is not empty.", "LOCAL_VERSION_EXISTS")


# Copies the selected source version so a new feature starts from the previous feature's current work.
def clone_source_version(source_path: Path, version_path: Path) -> None:
    """Copy one version folder into a new feature's first version folder."""

    shutil.copytree(source_path, version_path, symlinks=True)
    sharedresources.clone_installations(str(source_path), str(version_path))


# Creates the ordered init feature for a new project and installs optional Shared Resources into v1.
def create_initial_feature(project_path_value: str, resources: list[str]) -> dict[str, Any]:
    """Create 01 init with a project-named v1 folder for a new local project."""

    project_path = normalize_project_directory(project_path_value)
    resources = sharedresources.validate_resource_selection(resources)
    feature_path = (project_path / INIT_FEATURE_NAME).resolve()
    version_path = feature_path / first_version_name(project_path)
    ensure_new_feature_paths(feature_path, version_path)
    version_path.mkdir(parents=True, exist_ok=True)
    copied_files = copy_shared_resources(resources, version_path)
    return {
        "feature": feature_payload(feature_path, INIT_FEATURE_NAME, False),
        "version": version_payload(version_path),
        "copied_shared_resource_files": copied_files,
        "copied_ai_files": copied_files,
        "source_version": "",
    }


# Creates an ordered feature folder whose first version is copied from the active/latest prior version.
def create_local_feature(
    project_path_value: str,
    name_value: str,
    resources: list[str],
    source_version_path_value: str = "",
) -> dict[str, Any]:
    """Create the next feature folder and its project-named v1 version."""

    project_path = normalize_project_directory(project_path_value)
    resources = sharedresources.validate_resource_selection(resources)
    feature_path, feature_name = next_feature_path(project_path, name_value)
    version_path = feature_path / first_version_name(project_path)
    ensure_new_feature_paths(feature_path, version_path)
    source_path = source_version_for_new_feature(project_path, source_version_path_value)

    if source_path:
        clone_source_version(source_path, version_path)
        copied_files = 0
    else:
        version_path.mkdir(parents=True, exist_ok=True)
        copied_files = copy_shared_resources(resources, version_path)

    return {
        "feature": feature_payload(feature_path, feature_name, False),
        "version": version_payload(version_path),
        "copied_shared_resource_files": copied_files,
        "copied_ai_files": copied_files,
        "source_version": str(source_path or ""),
    }
