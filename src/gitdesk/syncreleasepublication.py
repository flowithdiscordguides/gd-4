"""Destination release metadata preparation, publication, and receipt digest helpers."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from gitdesk.errors import AppError
from gitdesk.githubapi import GitHubApiClient
from gitdesk.githubrelease import release_payload
from gitdesk.githubreleaseassets import positive_id
from gitdesk.githubreleaseerrors import raise_public_release_error


# Produces the destination release mutation while omitting the source repository's commit target.
def destination_release_data(source_release: dict[str, Any], draft: bool) -> dict[str, Any]:
    """Return release fields that preserve tag, title, and notes without copying a source commit reference."""

    return {
        "tag_name": source_release["tag_name"],
        "title": str(source_release.get("name") or source_release["tag_name"]),
        "body": str(source_release.get("body") or ""),
        "draft": draft,
        "prerelease": False,
        "make_latest": "false" if draft else "true",
        "generate_release_notes": False,
    }


# Creates a safe draft boundary or refreshes an earlier incomplete draft for the same tag.
def prepare_destination_draft(
    client: GitHubApiClient,
    pair: tuple[str, str],
    source_release: dict[str, Any],
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a destination draft whose metadata matches the source release."""

    payload = release_payload(destination_release_data(source_release, True), True)
    operation = "update_release_draft" if existing else "create_release_draft"
    try:
        if existing:
            release_id = positive_id(existing.get("id"), "SYNC_RELEASE_ID_INVALID")
            updated = client.request(
                "PATCH",
                f"/repos/{pair[0]}/{pair[1]}/releases/{release_id}",
                json_body=payload,
            )
            if isinstance(updated, dict):
                return updated
        else:
            created = client.request("POST", f"/repos/{pair[0]}/{pair[1]}/releases", json_body=payload)
            if isinstance(created, dict):
                return created
    except AppError as error:
        raise_public_release_error(error, pair, operation)
    raise AppError("GitHub returned an invalid destination release.", "GITHUB_RESPONSE_INVALID")


# Publishes a verified release and confirms GitHub now identifies its matching tag as latest.
def publish_destination_release(
    client: GitHubApiClient,
    pair: tuple[str, str],
    source_release: dict[str, Any],
    release_id: int,
) -> dict[str, Any]:
    """Publish release_id as the latest full release and return the confirmed latest payload."""

    payload = release_payload(destination_release_data(source_release, False), False)
    try:
        published = client.request(
            "PATCH",
            f"/repos/{pair[0]}/{pair[1]}/releases/{positive_id(release_id, 'SYNC_RELEASE_ID_INVALID')}",
            json_body=payload,
        )
    except AppError as error:
        raise_public_release_error(error, pair, "publish_release")
    try:
        latest = client.request("GET", f"/repos/{pair[0]}/{pair[1]}/releases/latest")
    except AppError as error:
        raise_public_release_error(error, pair, "confirm_latest_release")
    if not isinstance(published, dict) or not isinstance(latest, dict):
        raise AppError("GitHub returned an invalid destination release.", "GITHUB_RESPONSE_INVALID")
    latest_id = positive_id(latest.get("id"), "SYNC_RELEASE_ID_INVALID")
    if latest_id != release_id or str(latest.get("tag_name") or "") != source_release["tag_name"]:
        raise AppError("GitHub did not mark the promoted release as latest.", "SYNC_RELEASE_NOT_LATEST")
    return latest


# Derives one stable receipt digest from the exact tag, filenames, and verified asset hashes.
def release_digest(tag_name: str, asset_digests: dict[str, str]) -> str:
    """Return a deterministic digest for an exact promoted release asset set."""

    digest = sha256()
    digest.update(tag_name.encode("utf-8"))
    digest.update(b"\0")
    for name in sorted(asset_digests):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(asset_digests[name].encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()
