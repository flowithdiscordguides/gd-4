"""Git commit activity aggregation for every project known to GitDesk."""

from __future__ import annotations

# Standard-library tools for date windows, stable identifiers, paths, and typed payloads.
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
import hashlib
from pathlib import Path
from typing import Any

# GitPython exposes repository discovery and commit history without introducing a new dependency.
from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo

# GitDesk registries provide the complete set of user-managed project locations.
from gitdesk.errors import AppError
from gitdesk.localprojects import local_projects_state
from gitdesk.managedrepos import clean_repository_map


# Presets use inclusive rolling windows ending on the user's current local day.
PRESET_DAYS = {"week": 7, "month": 30, "year": 365}

# Project colors are assigned in the frontend, so identifiers must remain stable without exposing paths in CSS classes.
PROJECT_ID_LENGTH = 12


# Parses a YYYY-MM-DD value without accepting locale-dependent or ambiguous dates.
def parse_date(value: Any, error_code: str) -> date:
    """Return an ISO calendar date or raise an AppError for malformed input."""

    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError as error:
        raise AppError("Activity dates must use YYYY-MM-DD format.", error_code) from error


# Recovers the earliest stable app-use date from saved metadata or private settings-file creation metadata.
def recover_first_use_date(
    saved_value: Any,
    settings_paths: Iterable[Path],
    today: date | None = None,
) -> date:
    """Return the earliest valid GitDesk-use date, never later than today."""

    current_day = today or date.today()
    if str(saved_value or "").strip():
        try:
            return min(parse_date(saved_value, "ACTIVITY_FIRST_USE_INVALID"), current_day)
        except AppError:
            pass

    candidates = []
    for path in settings_paths:
        try:
            stat_result = path.stat()
        except OSError:
            continue
        created_timestamp = getattr(stat_result, "st_birthtime", None)
        if created_timestamp is None:
            created_timestamp = min(stat_result.st_ctime, stat_result.st_mtime)
        candidates.append(datetime.fromtimestamp(created_timestamp).astimezone().date())
    return min([current_day, *candidates])


# Resolves a preset or custom start date while enforcing the first-use boundary and today's upper bound.
def resolve_range(
    preset_value: Any,
    custom_start_value: Any,
    first_use: date,
    today: date | None = None,
) -> tuple[str, date, date]:
    """Return the normalized preset, inclusive start date, and inclusive end date."""

    current_day = today or date.today()
    preset = str(preset_value or "month").strip().lower()
    if preset == "custom":
        requested_start = parse_date(custom_start_value, "ACTIVITY_START_DATE_INVALID")
        start = max(first_use, min(requested_start, current_day))
        return preset, start, current_day
    if preset not in PRESET_DAYS:
        raise AppError("Choose week, month, year, or custom activity range.", "ACTIVITY_RANGE_INVALID")
    rolling_start = current_day - timedelta(days=PRESET_DAYS[preset] - 1)
    return preset, max(first_use, rolling_start), current_day


# Produces a stable opaque project id from its registry type and canonical root path.
def project_id(kind: str, path: Path) -> str:
    """Return a stable short identifier for a known project root."""

    source = f"{kind}:{path}".encode("utf-8")
    return hashlib.sha256(source).hexdigest()[:PROJECT_ID_LENGTH]


# Resolves a candidate path without failing the activity view when a removable drive is disconnected.
def existing_path(path_value: Any) -> Path | None:
    """Return an existing resolved directory or None for missing and invalid paths."""

    cleaned_path = str(path_value or "").strip()
    if not cleaned_path:
        return None
    try:
        path = Path(cleaned_path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return path if path.is_dir() else None


# Adds a candidate repository path once while preserving discovery order.
def add_candidate(project: dict[str, Any], path_value: Any) -> None:
    """Append one existing candidate directory to a project when it is not already present."""

    candidate = existing_path(path_value)
    if candidate and candidate not in project["candidates"]:
        project["candidates"].append(candidate)


# Returns whether a repository path belongs to a registered Local Mode project root.
def belongs_to_project(repository_path: Path, project_root: Path) -> bool:
    """Return True when repository_path is project_root or one of its descendants."""

    try:
        repository_path.relative_to(project_root)
        return True
    except ValueError:
        return False


# Builds project records from Local Mode roots and every recognized physical version folder.
def local_project_records(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Return activity-source records for registered Local Mode projects."""

    records = []
    for project in local_projects_state(settings).get("projects", []):
        root = existing_path(project.get("path"))
        if not root:
            continue
        record = {
            "id": project_id("local", root),
            "name": str(project.get("name") or root.name),
            "root": root,
            "candidates": [],
        }
        add_candidate(record, root)
        for feature in project.get("features", []):
            for version in feature.get("versions", []):
                add_candidate(record, version.get("path"))
        records.append(record)
    return records


# Merges account-scoped managed repositories into Local Mode projects when paths overlap.
def known_project_records(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Return de-duplicated activity-source records for every project GitDesk knows."""

    projects = local_project_records(settings)
    standalone_paths: set[Path] = set()
    for records in clean_repository_map(settings.get("managed_repositories")).values():
        for repository in records:
            path = existing_path(repository.get("path"))
            if not path:
                continue
            local_project = next(
                (project for project in projects if belongs_to_project(path, project["root"])),
                None,
            )
            if local_project:
                add_candidate(local_project, path)
                continue
            if path in standalone_paths:
                continue
            standalone_paths.add(path)
            projects.append({
                "id": project_id("repository", path),
                "name": str(repository.get("full_name") or repository.get("name") or path.name),
                "root": path,
                "candidates": [path],
            })
    return sorted(projects, key=lambda project: project["name"].lower())


# Opens only repository roots at known candidate locations so parent folders cannot be included accidentally.
def repository_roots(project: dict[str, Any]) -> list[Path]:
    """Return unique Git working-tree roots discovered at a project's known candidate paths."""

    roots = []
    for candidate in project["candidates"]:
        try:
            repository = Repo(candidate, search_parent_directories=False)
            root_value = repository.working_tree_dir
            root = Path(root_value).resolve() if root_value else candidate.resolve()
        except (InvalidGitRepositoryError, NoSuchPathError, OSError):
            continue
        if root not in roots:
            roots.append(root)
    return roots


# Reads factual commit metadata from every reference for the requested inclusive local-date range.
def repository_commits(repository_path: Path, start: date, end: date) -> list[dict[str, Any]]:
    """Return display-safe factual records for commits in one repository and date range."""

    repository = Repo(repository_path, search_parent_directories=False)
    if not repository.head.is_valid():
        return []
    until = end + timedelta(days=1)
    commits = repository.iter_commits(
        "--all",
        since=f"{start.isoformat()} 00:00:00",
        until=f"{until.isoformat()} 00:00:00",
    )
    results = []
    for commit in commits:
        committed_at = commit.committed_datetime.astimezone()
        commit_day = committed_at.date()
        if start <= commit_day <= end:
            results.append({
                "sha": commit.hexsha,
                "short_sha": commit.hexsha[:7],
                "date": commit_day,
                "committed_timestamp": commit.committed_date,
                "committed_at": committed_at.isoformat(),
                "summary": commit.summary,
                "author_name": commit.author.name,
                "author_email": commit.author.email,
                "repository": repository_path.name,
            })
    return results


# Aggregates project histories and suppresses duplicate SHAs copied between Local Mode versions.
def aggregate_activity(
    projects: list[dict[str, Any]],
    start: date,
    end: date,
    commit_reader: Callable[[Path, date, date], list[dict[str, Any]]] = repository_commits,
) -> dict[str, Any]:
    """Return factual commits plus per-day and per-project totals for known projects."""

    day_counts: dict[date, dict[str, int]] = {}
    day_commits: dict[date, list[dict[str, Any]]] = {}
    project_payload = []
    warnings = []
    for project in projects:
        seen_shas = set()
        counts: dict[date, int] = {}
        roots = repository_roots(project)
        for root in roots:
            try:
                commits = commit_reader(root, start, end)
            except (GitCommandError, InvalidGitRepositoryError, NoSuchPathError, OSError, ValueError):
                warnings.append(f"Could not read Git activity for {project['name']}.")
                continue
            for commit in commits:
                commit_sha = str(commit.get("sha") or "").strip()
                commit_day = commit.get("date")
                if not commit_sha or not isinstance(commit_day, date):
                    continue
                if commit_sha in seen_shas or not start <= commit_day <= end:
                    continue
                seen_shas.add(commit_sha)
                counts[commit_day] = counts.get(commit_day, 0) + 1
                day_counts.setdefault(commit_day, {})[project["id"]] = counts[commit_day]
                day_commits.setdefault(commit_day, []).append({
                    "sha": commit_sha,
                    "short_sha": str(commit.get("short_sha") or commit_sha[:7]),
                    "committed_timestamp": int(commit.get("committed_timestamp") or 0),
                    "committed_at": str(commit.get("committed_at") or ""),
                    "summary": str(commit.get("summary") or ""),
                    "author_name": str(commit.get("author_name") or ""),
                    "author_email": str(commit.get("author_email") or ""),
                    "repository": str(commit.get("repository") or root.name),
                    "project_id": project["id"],
                    "project_name": project["name"],
                })
        project_payload.append({
            "id": project["id"],
            "name": project["name"],
            "commits": len(seen_shas),
            "repositories": len(roots),
        })

    days = []
    cursor = start
    while cursor <= end:
        counts = day_counts.get(cursor, {})
        contributions = [
            {"project_id": project["id"], "name": project["name"], "commits": counts[project["id"]]}
            for project in project_payload
            if counts.get(project["id"], 0)
        ]
        commits = sorted(
            day_commits.get(cursor, []),
            key=lambda commit: (commit["committed_timestamp"], commit["sha"]),
        )
        days.append({
            "date": cursor.isoformat(),
            "total": len(commits),
            "projects": contributions,
            "commits": commits,
        })
        cursor += timedelta(days=1)
    return {
        "projects": project_payload,
        "days": days,
        "totals": {
            "commits": sum(project["commits"] for project in project_payload),
            "active_days": sum(1 for day in days if day["total"]),
            "projects": sum(1 for project in project_payload if project["commits"]),
        },
        "warnings": sorted(set(warnings)),
    }


# Builds the complete bridge payload for one requested range.
def activity_snapshot(
    settings: dict[str, Any],
    preset_value: Any,
    custom_start_value: Any,
    first_use: date,
    today: date | None = None,
) -> dict[str, Any]:
    """Return range metadata plus aggregated Git activity for every known project."""

    preset, start, end = resolve_range(preset_value, custom_start_value, first_use, today)
    payload = aggregate_activity(known_project_records(settings), start, end)
    payload["range"] = {
        "preset": preset,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "first_use": first_use.isoformat(),
    }
    return payload
