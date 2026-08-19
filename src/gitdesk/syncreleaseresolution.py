"""Source and destination release lookup for artifact-only terminal-stage promotion."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from gitdesk.errors import AppError
from gitdesk.githubapi import GitHubApiClient
from gitdesk.githubreleaseassets import positive_id
from gitdesk.githubreleaseerrors import release_error_details, request_release_api
from gitdesk.githubserializers import clean_repository_pair, clean_tag_name


# Fetches the preceding repository's authoritative latest published full release.
def latest_source_release(client: GitHubApiClient, owner: str, repo: str) -> dict[str, Any]:
    """Return the latest non-draft, non-prerelease source release with a validated tag and id."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    try:
        release = client.request("GET", f"/repos/{clean_owner}/{clean_repo}/releases/latest")
    except AppError as error:
        if error.details.get("status") == 404:
            raise AppError(
                f"The source stage has no visible full release in {clean_owner}/{clean_repo}. Confirm that the "
                "release exists and its owner PAT has Contents: read.",
                "SYNC_RELEASE_SOURCE_MISSING",
                release_error_details(
                    404,
                    "get_latest_source_release",
                    (clean_owner, clean_repo),
                    ["contents:read"],
                ),
            ) from error
        raise
    if not isinstance(release, dict):
        raise AppError("GitHub returned an invalid latest release.", "GITHUB_RESPONSE_INVALID")
    release["id"] = positive_id(release.get("id"), "SYNC_RELEASE_ID_INVALID")
    release["tag_name"] = clean_tag_name(str(release.get("tag_name") or ""))
    return release


# Finds an existing release by exact tag, including drafts that the by-tag endpoint does not return.
def destination_release_for_tag(
    client: GitHubApiClient,
    owner: str,
    repo: str,
    tag_name: str,
) -> dict[str, Any] | None:
    """Return the destination release for tag_name, or None when the tag has no release."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    clean_tag = clean_tag_name(tag_name)
    try:
        release = client.request(
            "GET",
            f"/repos/{clean_owner}/{clean_repo}/releases/tags/{quote(clean_tag, safe='')}",
        )
        if isinstance(release, dict):
            return release
    except AppError as error:
        if error.details.get("status") != 404:
            raise
    page = 1
    while True:
        payload = request_release_api(
            client,
            "GET",
            f"/repos/{clean_owner}/{clean_repo}/releases",
            (clean_owner, clean_repo),
            "list_destination_releases",
            params={"per_page": 100, "page": page},
        )
        if not isinstance(payload, list):
            raise AppError("GitHub returned an invalid releases list.", "GITHUB_RESPONSE_INVALID")
        matching = next(
            (
                item for item in payload
                if isinstance(item, dict) and str(item.get("tag_name") or "") == clean_tag
            ),
            None,
        )
        if isinstance(matching, dict):
            return matching
        if len(payload) < 100:
            return None
        page += 1
