"""Validate and build GitHub release mutation payloads for the REST client."""

from __future__ import annotations

from typing import Any

from gitdesk.errors import AppError


# Validates the release label mode before it is sent to GitHub's make_latest field.
def clean_make_latest(value: Any) -> str:
    """Return a GitHub-compatible make_latest value."""

    clean_value = str(value or "true").strip().lower()
    if clean_value not in {"true", "false", "legacy"}:
        raise AppError("Release latest setting is invalid.", "RELEASE_LATEST_INVALID")
    return clean_value


# Builds the shared request payload for creating releases and publishing draft releases.
def release_payload(release_data: dict[str, Any], include_generated_notes: bool) -> dict[str, Any]:
    """Return a GitHub release mutation payload from frontend form data."""

    tag_name = str(release_data.get("tag_name", "")).strip()
    title = str(release_data.get("title", "") or release_data.get("name", "")).strip()
    body = str(release_data.get("body", "")).strip()
    target_commitish = str(release_data.get("target_commitish", "")).strip()
    is_draft = bool(release_data.get("draft", False))
    is_prerelease = bool(release_data.get("prerelease", False))

    if not tag_name:
        raise AppError("Release tag name is required.", "RELEASE_TAG_EMPTY")
    if not title:
        title = tag_name

    if is_draft or is_prerelease:
        make_latest = "false"
    else:
        make_latest = clean_make_latest(release_data.get("make_latest", "true"))

    payload: dict[str, Any] = {
        "tag_name": tag_name,
        "name": title,
        "body": body,
        "draft": is_draft,
        "prerelease": is_prerelease,
        "make_latest": make_latest,
    }

    if target_commitish:
        payload["target_commitish"] = target_commitish
    if include_generated_notes:
        payload["generate_release_notes"] = bool(release_data.get("generate_release_notes", False))
    return payload
