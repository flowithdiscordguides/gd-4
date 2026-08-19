"""Operation-aware, secret-safe errors for artifact-only GitHub release promotion."""

from __future__ import annotations

from typing import Any, NoReturn

import requests

from gitdesk.errors import AppError
from gitdesk.githubapi import GitHubApiClient
from gitdesk.patstatus import token_expiration_from_headers


# Returns non-secret context that identifies one failing GitHub release boundary.
def release_error_details(
    status: int,
    operation: str,
    pair: tuple[str, str],
    required_permissions: list[str],
) -> dict[str, Any]:
    """Return stable diagnostics without request headers, tokens, or local paths."""

    return {
        "status": status,
        "operation": operation,
        "resource_owner": pair[0],
        "repository": pair[1],
        "required_permissions": required_permissions,
    }


# Calls one JSON release endpoint while preserving its artifact-transfer purpose on a 404.
def request_release_api(
    client: GitHubApiClient,
    method: str,
    path: str,
    pair: tuple[str, str],
    operation: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """Return a GitHub response while translating only operation-specific release 404s."""

    try:
        return client.request(method, path, params=params)
    except AppError as error:
        if error.details.get("status") != 404:
            raise
        specifications = {
            "list_destination_releases": (
                "GitHub could not list releases in the configured destination repository",
                "SYNC_RELEASE_DESTINATION_RELEASES_UNAVAILABLE",
                ["contents:read"],
            ),
            "list_release_assets": (
                "GitHub could not list the release's build artifacts",
                "SYNC_RELEASE_ASSET_LIST_UNAVAILABLE",
                ["contents:read"],
            ),
            "delete_destination_asset": (
                "GitHub could not remove an obsolete asset from the destination release draft",
                "SYNC_RELEASE_DESTINATION_ASSET_UNAVAILABLE",
                ["contents:write"],
            ),
        }
        action, code, permissions = specifications[operation]
        permission_text = ", ".join(permission.replace(":", ": ") for permission in permissions)
        message = (
            f"{action} in {pair[0]}/{pair[1]}. The repository, release, or asset is no longer visible, or the "
            f"saved {pair[0]} PAT lacks {permission_text}."
        )
        details = release_error_details(404, operation, pair, permissions)
        raise AppError(message, code, details) from error


# Deletes one stale draft asset without losing its destination write-operation context.
def delete_destination_release_asset(
    client: GitHubApiClient,
    pair: tuple[str, str],
    asset_id: int,
) -> None:
    """Delete asset_id from the destination draft or raise a contextual write failure."""

    request_release_api(
        client,
        "DELETE",
        f"/repos/{pair[0]}/{pair[1]}/releases/assets/{asset_id}",
        pair,
        "delete_destination_asset",
    )


# Verifies both independently authenticated repositories before resolving or mutating releases.
def validate_release_repositories(
    source_client: GitHubApiClient,
    destination_client: GitHubApiClient,
    source_pair: tuple[str, str],
    destination_pair: tuple[str, str],
) -> dict[str, Any]:
    """Return the destination repository after contextual access checks for both owner PATs."""

    try:
        source_client.repository(*source_pair)
    except AppError as error:
        raise_repository_access_error(error, source_pair, "source", "contents:read")
    try:
        return destination_client.repository(*destination_pair)
    except AppError as error:
        raise_repository_access_error(error, destination_pair, "destination", "contents:write")


# Replaces an ambiguous repository 404 with its owner profile and minimum permission.
def raise_repository_access_error(
    error: AppError,
    pair: tuple[str, str],
    stage_name: str,
    required_permission: str,
) -> NoReturn:
    """Raise an actionable repository error or preserve a non-404 GitHub failure."""

    if error.details.get("status") != 404:
        raise error
    permission_label = required_permission.replace("contents", "Contents").replace(":", ": ")
    message = (
        f"GitHub could not access the configured {stage_name} repository {pair[0]}/{pair[1]}. "
        f"In Settings > GitHub Settings, replace the {pair[0]} PAT and select this repository with "
        f"{permission_label} permission."
    )
    code = "SYNC_RELEASE_SOURCE_REPOSITORY_UNAVAILABLE"
    if stage_name == "destination":
        code = "SYNC_RELEASE_DESTINATION_REPOSITORY_UNAVAILABLE"
    details = release_error_details(404, "repository_access", pair, [required_permission])
    raise AppError(message, code, details) from error


# Replaces GitHub's documented release-mutation 404 with the destination PAT requirements.
def raise_public_release_error(
    error: AppError,
    pair: tuple[str, str],
    operation: str,
) -> NoReturn:
    """Raise an actionable destination release error or preserve a non-404 GitHub failure."""

    if error.details.get("status") != 404:
        raise error
    if operation == "confirm_latest_release":
        message = (
            f"GitHub could not confirm the published release as latest in {pair[0]}/{pair[1]}. The release may "
            f"not be visible yet, or the saved {pair[0]} PAT no longer has Contents: read for this repository. "
            "Retrying this artifact edge is safe."
        )
        details = release_error_details(404, operation, pair, ["contents:read"])
        raise AppError(message, "SYNC_RELEASE_PUBLICATION_UNCONFIRMED", details) from error
    action = {
        "create_release_draft": "create the destination release draft",
        "update_release_draft": "update the destination release draft",
        "publish_release": "publish the verified destination release",
    }.get(operation, "complete the destination release operation")
    permissions = ["contents:write", "workflows:write"]
    message = (
        f"GitHub could not {action} in {pair[0]}/{pair[1]}. The repository or release is not visible to the "
        f"saved {pair[0]} PAT, or that PAT lacks Contents: write and Workflows: write. In Settings > GitHub "
        "Settings, replace the destination owner PAT using the prefilled GitDesk token setup."
    )
    details = release_error_details(404, operation, pair, permissions)
    raise AppError(message, "SYNC_RELEASE_DESTINATION_PERMISSION_REQUIRED", details) from error


# Validates raw release-asset responses while retaining the exact transfer operation.
def raise_for_release_asset_response(
    client: GitHubApiClient,
    response: requests.Response,
    pair: tuple[str, str],
    operation: str,
) -> None:
    """Raise contextual authentication and API failures for binary asset requests."""

    expiration = token_expiration_from_headers(response.headers)
    client.token_expires_at = expiration or client.token_expires_at
    if response.status_code == 401:
        raise AppError(
            "GitHub rejected this PAT as invalid, expired, or revoked. Generate a new PAT and paste its value.",
            "GITHUB_TOKEN_REJECTED",
            {"status": response.status_code},
        )
    if response.status_code < 400:
        return
    if response.status_code != 404:
        details = release_error_details(response.status_code, operation, pair, [])
        raise AppError(client.error_message(response), "GITHUB_API_FAILED", details)
    if operation == "download_source_asset":
        message = (
            f"GitHub could not download a listed build artifact from {pair[0]}/{pair[1]}. The asset was removed "
            f"after it was listed, or the saved {pair[0]} PAT lacks Contents: read for this repository."
        )
        code = "SYNC_RELEASE_SOURCE_ASSET_UNAVAILABLE"
        permissions = ["contents:read"]
    elif operation == "download_destination_asset":
        message = (
            f"GitHub could not verify an uploaded destination artifact in {pair[0]}/{pair[1]}. The asset was removed "
            f"after it was listed, or the saved {pair[0]} PAT lacks Contents: read for this repository."
        )
        code = "SYNC_RELEASE_DESTINATION_ASSET_UNAVAILABLE"
        permissions = ["contents:read"]
    else:
        message = (
            f"GitHub could not upload a build artifact to {pair[0]}/{pair[1]}. The draft release was removed, "
            f"or the saved {pair[0]} PAT lacks Contents: write for this repository."
        )
        code = "SYNC_RELEASE_DESTINATION_ASSET_UNAVAILABLE"
        permissions = ["contents:write"]
    details = release_error_details(404, operation, pair, permissions)
    raise AppError(message, code, details)
