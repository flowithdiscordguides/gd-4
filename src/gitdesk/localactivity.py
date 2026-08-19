"""Factual Local Mode activity normalization and Project Activity payload enrichment."""

from __future__ import annotations

# Standard-library helpers provide dates, stable ids, paths, and typed payloads.
from datetime import date, datetime
import hashlib
from pathlib import Path
from typing import Any

# GitDesk project models and private file tracking supply every local activity source.
from gitdesk import activity_tracker
from gitdesk import localprojects
from gitdesk.localactivity_store import activity_store, birth_timestamp_ns, timestamp_from_ns
from gitdesk.localactivity_streaks import streak_summary
from gitdesk.syncnotifications import sync_chain_notifications

# Timeline types stay factual and project-scoped; unrelated maintenance events are excluded.
TIMELINE_KIND_LABELS = {
    "project_created": "Project created",
    "project_imported": "Project imported",
    "project_renamed": "Project renamed",
    "feature_created": "Feature created",
    "version_created": "Version created",
    "version_files_copied": "Version files copied",
    "safety_snapshot": "Safety snapshot",
    "files_restored": "Files restored",
    "version_promoted": "Version promoted",
    "pages_published": "Pages published",
    "release_created": "Release created",
}

# Compact codes let artifacts identify their meaning without requiring an external legend.
ACTIVITY_CODES = {
    "commit": "COMMIT",
    "file_added": "NEW FILE",
    "file_modified": "EDIT",
    "project_created": "PROJECT",
    "project_imported": "IMPORT",
    "project_renamed": "RENAME",
    "feature_created": "FEATURE",
    "version_created": "VERSION",
    "version_files_copied": "COPY",
    "safety_snapshot": "SNAPSHOT",
    "files_restored": "RESTORE",
    "version_promoted": "PROMOTE",
    "pages_published": "PAGES",
    "release_created": "RELEASE",
}


# Produces a stable activity id from the factual source type, entity, and timestamp.
def activity_id(kind: str, entity: str, occurred_at: str) -> str:
    """Return a short stable id used to de-duplicate normalized activity items."""

    source = f"{kind}:{entity}:{occurred_at}".encode("utf-8")
    return hashlib.sha256(source).hexdigest()[:32]


# Returns whether candidate belongs to root without relying on unsafe string-prefix matching.
def belongs_to(candidate: str, root: str) -> bool:
    """Return True when candidate resolves to root or one of its descendants."""

    try:
        Path(candidate).expanduser().resolve().relative_to(Path(root).expanduser().resolve())
        return True
    except (OSError, ValueError):
        return False


# Flattens Local Mode project, feature, and version hierarchy for activity ownership and scanning.
def project_contexts(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Return existing Local Mode projects with every physical version and stable project id."""

    contexts = []
    for project in localprojects.local_projects_state(settings).get("projects", []):
        if not project.get("exists"):
            continue
        context = {
            "project_id": activity_tracker.project_id("local", Path(project["path"]).resolve()),
            "project_path": project["path"],
            "project_name": project["name"],
            "features": [],
            "versions": [],
        }
        for feature in project.get("features", []):
            feature_record = {"path": feature["path"], "name": feature["name"]}
            context["features"].append(feature_record)
            for version in feature.get("versions", []):
                context["versions"].append({
                    "path": version["path"],
                    "name": version["name"],
                    "feature_path": feature["path"],
                    "feature_name": feature["name"],
                })
        contexts.append(context)
    return contexts


# Resolves a timeline or file event to its current project after path remaps and imports.
def event_context(event: dict[str, Any], contexts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the project context owning any path stored on event."""

    candidate_paths = [
        str(event.get("project_path") or ""),
        str(event.get("feature_path") or ""),
        str(event.get("version_path") or ""),
    ]
    for context in contexts:
        if any(path and belongs_to(path, context["project_path"]) for path in candidate_paths):
            return context
    return None


# Finds display names for event feature and version paths inside their current project context.
def hierarchy_names(event: dict[str, Any], context: dict[str, Any]) -> tuple[str, str]:
    """Return feature and version names resolved from event paths."""

    feature_path = str(event.get("feature_path") or "")
    version_path = str(event.get("version_path") or "")
    feature_name = str(event.get("feature_name") or "")
    version_name = str(event.get("version_name") or "")
    if not feature_name and feature_path:
        feature = next((item for item in context["features"] if item["path"] == feature_path), None)
        feature_name = feature["name"] if feature else Path(feature_path).name
    if not version_name and version_path:
        version = next((item for item in context["versions"] if item["path"] == version_path), None)
        version_name = version["name"] if version else Path(version_path).name
        if not feature_name and version:
            feature_name = version["feature_name"]
    return feature_name, version_name


# Normalizes one stored Project Hub timeline event for the atlas.
def timeline_activity(event: dict[str, Any], contexts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return a project-scoped activity item or None for unrelated timeline maintenance."""

    kind = str(event.get("type") or "")
    occurred_at = str(event.get("timestamp") or "")
    context = event_context(event, contexts)
    if kind not in TIMELINE_KIND_LABELS or not occurred_at or not context:
        return None
    feature_name, version_name = hierarchy_names(event, context)
    detail = str(event.get("detail") or "")
    facts = [{"label": "Project", "value": context["project_name"]}]
    if feature_name:
        facts.append({"label": "Feature", "value": feature_name})
    if version_name:
        facts.append({"label": "Version", "value": version_name})
    if detail:
        facts.append({"label": "Details", "value": detail})
    if kind in {"project_created", "project_imported", "project_renamed"}:
        entity = str(event.get("project_path") or context["project_path"])
    elif kind == "feature_created":
        entity = str(event.get("feature_path") or context["project_path"])
    else:
        entity = str(event.get("version_path") or event.get("feature_path") or context["project_path"])
    return {
        "id": activity_id(kind, f"{entity}:{event.get('title', '')}", occurred_at),
        "kind": kind,
        "kind_label": TIMELINE_KIND_LABELS[kind],
        "occurred_at": occurred_at,
        "project_id": context["project_id"],
        "project_name": context["project_name"],
        "title": str(event.get("title") or TIMELINE_KIND_LABELS[kind]),
        "subtitle": " / ".join(value for value in (feature_name, version_name) if value) or detail,
        "short_code": ACTIVITY_CODES[kind],
        "facts": facts,
        "entity_path": entity,
        "durable": True,
    }


# Normalizes one detected file event with exact project, version, path, and modification facts.
def file_activity(event: dict[str, Any], contexts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return an atlas item for one added or modified local file."""

    context = event_context(event, contexts)
    if not context:
        return None
    kind = str(event.get("kind") or "")
    feature_name, version_name = hierarchy_names(event, context)
    file_path = str(event.get("file_path") or "")
    return {
        "id": str(event.get("id") or activity_id(kind, file_path, event["occurred_at"])),
        "kind": kind,
        "kind_label": "File added" if kind == "file_added" else "File edited",
        "occurred_at": event["occurred_at"],
        "project_id": context["project_id"],
        "project_name": context["project_name"],
        "title": str(event.get("title") or "Local file activity"),
        "subtitle": " / ".join(value for value in (feature_name, version_name, file_path) if value),
        "short_code": ACTIVITY_CODES.get(kind, "FILE"),
        "facts": [
            {"label": "Project", "value": context["project_name"]},
            {"label": "Feature", "value": feature_name},
            {"label": "Version", "value": version_name},
            {"label": "File", "value": file_path},
        ],
    }


# Converts one factual Git record into the same artifact contract used by Local Mode events.
def commit_activity(commit: dict[str, Any], day_value: str) -> dict[str, Any]:
    """Return a normalized commit activity item without losing Git metadata."""

    occurred_at = str(commit.get("committed_at") or "")
    project_id = str(commit.get("project_id") or "")
    sha = str(commit.get("sha") or "")
    author = str(commit.get("author_name") or "") or "Unknown author"
    return {
        "id": activity_id("commit", f"{project_id}:{sha}", occurred_at),
        "kind": "commit",
        "kind_label": "Git commit",
        "occurred_at": occurred_at,
        "project_id": project_id,
        "project_name": str(commit.get("project_name") or ""),
        "title": str(commit.get("summary") or "Commit without a subject"),
        "subtitle": f"{commit.get('repository', '')} / {author}",
        "short_code": str(commit.get("short_sha") or sha[:7]),
        "facts": [
            {"label": "Project", "value": str(commit.get("project_name") or "")},
            {"label": "Repository", "value": str(commit.get("repository") or "")},
            {"label": "Author", "value": author},
            {"label": "Email", "value": str(commit.get("author_email") or "")},
            {"label": "Commit", "value": sha},
            {"label": "Calendar date", "value": day_value},
        ],
    }


# Builds a lifecycle item from an actual directory creation timestamp where the OS provides one.
def directory_activity(
    kind: str,
    path: str,
    context: dict[str, Any],
    feature_name: str = "",
    version_name: str = "",
) -> dict[str, Any] | None:
    """Return a factual folder-creation item or None without creation-time support."""

    try:
        created_ns = birth_timestamp_ns(Path(path).stat())
    except OSError:
        return None
    if not created_ns:
        return None
    occurred_at = timestamp_from_ns(created_ns)
    label = TIMELINE_KIND_LABELS[kind]
    entity_name = version_name or feature_name or context["project_name"]
    facts = [{"label": "Project", "value": context["project_name"]}]
    if feature_name:
        facts.append({"label": "Feature", "value": feature_name})
    if version_name:
        facts.append({"label": "Version", "value": version_name})
    return {
        "id": activity_id(kind, path, occurred_at),
        "kind": kind,
        "kind_label": label,
        "occurred_at": occurred_at,
        "project_id": context["project_id"],
        "project_name": context["project_name"],
        "title": f"{label}: {entity_name}",
        "subtitle": " / ".join(value for value in (feature_name, version_name) if value),
        "short_code": ACTIVITY_CODES[kind],
        "facts": facts,
        "entity_path": path,
    }


# Derives historical lifecycle facts only from operating-system folder creation metadata.
def directory_lifecycle_activity(contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return factual project, feature, and version folder creation items."""

    activities = []
    for context in contexts:
        project_item = directory_activity("project_created", context["project_path"], context)
        if project_item:
            activities.append(project_item)
        for feature in context["features"]:
            feature_item = directory_activity(
                "feature_created", feature["path"], context, feature["name"]
            )
            if feature_item:
                activities.append(feature_item)
        for version in context["versions"]:
            version_item = directory_activity(
                "version_created",
                version["path"],
                context,
                version["feature_name"],
                version["name"],
            )
            if version_item:
                activities.append(version_item)
    return activities


# Parses a stored UTC timestamp into the user's local calendar day for range and streak calculations.
def activity_day(occurred_at: str) -> date | None:
    """Return the local calendar day represented by occurred_at or None when malformed."""

    try:
        parsed = datetime.fromisoformat(str(occurred_at or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone().date()


# Removes directory-derived lifecycle duplicates when a durable timeline action records the same entity.
def deduplicate_activity(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unique items while preferring durable timeline events over derived folder metadata."""

    timeline_entities = {
        (item["kind"], item["entity_path"])
        for item in items if item.get("durable") and item.get("entity_path")
    }
    unique = {}
    for item in items:
        entity_path = str(item.get("entity_path") or "")
        if entity_path and not item.get("durable") and (item["kind"], entity_path) in timeline_entities:
            continue
        unique[item["id"]] = item
    return list(unique.values())


# Merges commits, timeline history, folder facts, and detected file edits into one activity payload.
def enrich_activity(
    settings: dict[str, Any],
    payload: dict[str, Any],
    settings_path: Path,
    today: date,
) -> dict[str, Any]:
    """Return Project Activity enriched with Local Mode artifacts and factual streak totals."""

    contexts = project_contexts(settings)
    file_events, scan_warnings = activity_store(settings_path).scan(contexts)
    items = []
    for day_record in payload.get("days", []):
        for commit in day_record.get("commits", []):
            items.append(commit_activity(commit, day_record["date"]))
    for event in settings.get("project_timeline") or []:
        normalized = timeline_activity(event, contexts)
        if normalized:
            items.append(normalized)
    for event in file_events:
        normalized = file_activity(event, contexts)
        if normalized:
            items.append(normalized)
    items.extend(directory_lifecycle_activity(contexts))

    start = date.fromisoformat(payload["range"]["start"])
    end = date.fromisoformat(payload["range"]["end"])
    ranged_items = []
    for item in deduplicate_activity(items):
        item_date = activity_day(item["occurred_at"])
        if item_date and start <= item_date <= end:
            public_item = {key: value for key, value in item.items() if key not in {"entity_path", "durable"}}
            ranged_items.append({**public_item, "date": item_date.isoformat()})
    ranged_items.sort(key=lambda item: (item["occurred_at"], item["id"]))

    activities_by_day: dict[str, list[dict[str, Any]]] = {}
    for item in ranged_items:
        activities_by_day.setdefault(item["date"], []).append(item)
    for day_record in payload.get("days", []):
        day_record["activities"] = activities_by_day.get(day_record["date"], [])

    active_dates = {date.fromisoformat(day_value) for day_value in activities_by_day}
    streaks = streak_summary(active_dates, today)
    payload["totals"].update({
        "activities": len(ranged_items),
        "active_days": len(active_dates),
        "projects": len({item["project_id"] for item in ranged_items}),
        "local_events": sum(1 for item in ranged_items if item["kind"] != "commit"),
        "files_changed": sum(1 for item in ranged_items if item["kind"].startswith("file_")),
        "current_streak": streaks["current"],
        "current_streak_open": bool(streaks["current"] and start in active_dates),
        "longest_streak": streaks["longest"],
        "streak_range_start": start.isoformat(),
        "last_active": streaks["last_active"],
    })
    payload["sync_chain_notifications"] = sync_chain_notifications(settings, file_events)
    payload["warnings"] = sorted(set([*(payload.get("warnings") or []), *scan_warnings]))
    return payload
