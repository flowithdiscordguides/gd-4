"""Artifact-only promotion of a source stage's latest release into its destination repository."""

from __future__ import annotations

from tempfile import SpooledTemporaryFile
from typing import Any

from gitdesk.errors import AppError
from gitdesk.githubapi import GitHubApiClient
from gitdesk.githubreleaseerrors import delete_destination_release_asset, validate_release_repositories
from gitdesk.githubreleaseassets import (
    ASSET_MEMORY_LIMIT,
    ReleaseAssetTransport,
    clean_asset_digest,
    clean_source_assets,
    destination_asset_matches,
    positive_id,
    release_assets,
    validate_uploaded_asset,
)
from gitdesk.githubserializers import clean_repository_pair, clean_tag_name, serialize_release
from gitdesk.syncreleasepublication import (
    destination_release_data,
    prepare_destination_draft,
    publish_destination_release,
    release_digest,
)
from gitdesk.syncreleaseresolution import destination_release_for_tag, latest_source_release
from gitdesk.syncprogress import ProgressCallback, report_progress
from gitdesk.syncchains import EDGE_NAMES, sync_timestamp

# Reconciles a destination draft to the exact source asset set while preserving no extra artifacts.
def synchronize_draft_assets(
    source_client: GitHubApiClient,
    destination_client: GitHubApiClient,
    source_pair: tuple[str, str],
    destination_pair: tuple[str, str],
    source_release: dict[str, Any],
    destination_release: dict[str, Any],
    progress: ProgressCallback | None = None,
) -> tuple[dict[str, str], int]:
    """Replace one draft's assets with the exact verified source release assets and return their digests."""

    source_assets = clean_source_assets(release_assets(source_client, *source_pair, source_release["id"]))
    destination_id = positive_id(destination_release.get("id"), "SYNC_RELEASE_ID_INVALID")
    destination_assets = release_assets(destination_client, *destination_pair, destination_id)
    destination_by_name = {str(item.get("name") or ""): item for item in destination_assets}
    source_names = {item["name"] for item in source_assets}
    source_transport = ReleaseAssetTransport(source_client)
    destination_transport = ReleaseAssetTransport(destination_client)
    expected_digests: dict[str, str] = {}
    asset_count = len(source_assets)

    for name, asset in destination_by_name.items():
        if name not in source_names:
            delete_destination_release_asset(
                destination_client,
                destination_pair,
                positive_id(asset.get("id"), "SYNC_RELEASE_ASSET_ID_INVALID"),
            )

    for asset_index, source_asset in enumerate(source_assets, start=1):
        server_digest = clean_asset_digest(source_asset.get("digest"))
        current = destination_by_name.get(source_asset["name"])
        # A matching authenticated GitHub digest makes an idempotent draft check metadata-only.
        if server_digest and current and destination_asset_matches(
            destination_transport,
            *destination_pair,
            current,
            source_asset["size"],
            server_digest,
        ):
            expected_digests[source_asset["name"]] = server_digest
            report_progress(
                progress,
                phase="verifying",
                message=f"Verified {source_asset['name']}",
                asset_index=asset_index,
                asset_count=asset_count,
            )
            continue
        if server_digest:
            if current:
                delete_destination_release_asset(
                    destination_client,
                    destination_pair,
                    positive_id(current.get("id"), "SYNC_RELEASE_ASSET_ID_INVALID"),
                )
            uploaded, digest = source_transport.copy_to(
                destination_transport,
                source_pair,
                destination_pair,
                destination_id,
                source_asset,
                lambda transferred, total: report_progress(
                    progress,
                    phase="transferring",
                    message=f"Transferring {source_asset['name']} from the source release",
                    asset_index=asset_index,
                    asset_count=asset_count,
                    bytes_transferred=transferred,
                    bytes_total=total,
                ),
                lambda transferred, total: report_progress(
                    progress,
                    phase="transferring",
                    message=f"Uploading {source_asset['name']} to the destination release",
                    asset_index=asset_index,
                    asset_count=asset_count,
                    bytes_transferred=transferred,
                    bytes_total=total,
                ),
            )
            if server_digest != digest:
                raise AppError("A source release asset failed digest verification.", "SYNC_RELEASE_ASSET_MISMATCH")
            expected_digests[source_asset["name"]] = digest
            validate_uploaded_asset(
                destination_transport,
                destination_pair,
                uploaded,
                source_asset,
                digest,
                lambda transferred, total: report_progress(
                    progress,
                    phase="verifying",
                    message=f"Verifying {source_asset['name']} in the destination release",
                    asset_index=asset_index,
                    asset_count=asset_count,
                    bytes_transferred=transferred,
                    bytes_total=total,
                ),
            )
            continue
        with SpooledTemporaryFile(max_size=ASSET_MEMORY_LIMIT, mode="w+b") as temporary_file:
            digest = source_transport.download(
                *source_pair,
                source_asset,
                temporary_file,
                lambda transferred, total: report_progress(
                    progress,
                    phase="downloading",
                    message=f"Downloading {source_asset['name']} for verification",
                    asset_index=asset_index,
                    asset_count=asset_count,
                    bytes_transferred=transferred,
                    bytes_total=total,
                ),
            )
            expected_digests[source_asset["name"]] = digest
            if current and destination_asset_matches(
                destination_transport,
                *destination_pair,
                current,
                source_asset["size"],
                digest,
            ):
                continue
            if current:
                delete_destination_release_asset(
                    destination_client,
                    destination_pair,
                    positive_id(current.get("id"), "SYNC_RELEASE_ASSET_ID_INVALID"),
                )
            uploaded = destination_transport.upload(
                *destination_pair,
                destination_id,
                source_asset,
                temporary_file,
                lambda transferred, total: report_progress(
                    progress,
                    phase="uploading",
                    message=f"Uploading {source_asset['name']} to the destination release",
                    asset_index=asset_index,
                    asset_count=asset_count,
                    bytes_transferred=transferred,
                    bytes_total=total,
                ),
            )
            validate_uploaded_asset(
                destination_transport,
                destination_pair,
                uploaded,
                source_asset,
                digest,
                lambda transferred, total: report_progress(
                    progress,
                    phase="verifying",
                    message=f"Verifying {source_asset['name']} in the destination release",
                    asset_index=asset_index,
                    asset_count=asset_count,
                    bytes_transferred=transferred,
                    bytes_total=total,
                ),
            )

    verified_assets = release_assets(destination_client, *destination_pair, destination_id)
    if {str(item.get("name") or "") for item in verified_assets} != source_names:
        raise AppError("The destination release asset set failed verification.", "SYNC_RELEASE_ASSET_SET_MISMATCH")
    for asset in verified_assets:
        name = str(asset.get("name") or "")
        source_asset = next(item for item in source_assets if item["name"] == name)
        if not destination_asset_matches(
            destination_transport,
            *destination_pair,
            asset,
            source_asset["size"],
            expected_digests[name],
            lambda transferred, total: report_progress(
                progress,
                phase="verifying",
                message=f"Verifying {name} in the final destination asset set",
                bytes_transferred=transferred,
                bytes_total=total,
            ),
        ):
            raise AppError("The destination release asset set failed verification.", "SYNC_RELEASE_ASSET_SET_MISMATCH")
    return expected_digests, sum(item["size"] for item in source_assets)


# Confirms an already-published destination release is exact without deleting or replacing public assets.
def verify_published_assets(
    source_client: GitHubApiClient,
    destination_client: GitHubApiClient,
    source_pair: tuple[str, str],
    destination_pair: tuple[str, str],
    source_release: dict[str, Any],
    destination_release: dict[str, Any],
    progress: ProgressCallback | None = None,
) -> tuple[dict[str, str], int]:
    """Return exact asset digests or reject a conflicting published release without mutating it."""

    source_assets = clean_source_assets(release_assets(source_client, *source_pair, source_release["id"]))
    destination_assets = release_assets(
        destination_client,
        *destination_pair,
        positive_id(destination_release.get("id"), "SYNC_RELEASE_ID_INVALID"),
    )
    destination_by_name = {str(item.get("name") or ""): item for item in destination_assets}
    if set(destination_by_name) != {item["name"] for item in source_assets}:
        raise AppError(
            "The destination repository already has a different published release for this tag.",
            "SYNC_RELEASE_PUBLISHED_CONFLICT",
        )
    source_transport = ReleaseAssetTransport(source_client)
    destination_transport = ReleaseAssetTransport(destination_client)
    expected_digests: dict[str, str] = {}
    for asset_index, source_asset in enumerate(source_assets, start=1):
        digest = clean_asset_digest(source_asset.get("digest"))
        # Older asset records without a digest still require authenticated byte hashing.
        if not digest:
            with SpooledTemporaryFile(max_size=ASSET_MEMORY_LIMIT, mode="w+b") as temporary_file:
                digest = source_transport.download(
                    *source_pair,
                    source_asset,
                    temporary_file,
                    lambda transferred, total: report_progress(
                        progress,
                        phase="downloading",
                        message=f"Downloading {source_asset['name']} for verification",
                        asset_index=asset_index,
                        asset_count=len(source_assets),
                        bytes_transferred=transferred,
                        bytes_total=total,
                    ),
                )
        if not destination_asset_matches(
            destination_transport,
            *destination_pair,
            destination_by_name[source_asset["name"]],
            source_asset["size"],
            digest,
            lambda transferred, total: report_progress(
                progress,
                phase="verifying",
                message=f"Verifying {source_asset['name']} in the destination release",
                asset_index=asset_index,
                asset_count=len(source_assets),
                bytes_transferred=transferred,
                bytes_total=total,
            ),
        ):
            raise AppError(
                "The destination repository already has a different published release for this tag.",
                "SYNC_RELEASE_PUBLISHED_CONFLICT",
            )
        expected_digests[source_asset["name"]] = digest
        report_progress(
            progress,
            phase="verifying",
            message=f"Verified {source_asset['name']}",
            asset_index=asset_index,
            asset_count=len(source_assets),
        )
    return expected_digests, sum(item["size"] for item in source_assets)


# Executes an enabled repository edge with independent credentials and no filesystem mirror.
def promote_latest_release(
    controller: Any,
    context: dict[str, Any],
    expected_tag: str = "",
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Copy only latest release assets into the destination and return its release plus receipt."""

    if context.get("edge_name") not in EDGE_NAMES[1:]:
        raise AppError(
            "Artifact-only synchronization requires a repository-to-repository edge.",
            "SYNC_RELEASE_EDGE_INVALID",
        )
    report_progress(progress, phase="checking", message="Checking source and destination repositories")
    source_repository = context.get("source_repository") or {}
    destination_repository = context.get("destination_repository") or {}
    source_pair = clean_repository_pair(source_repository.get("owner"), source_repository.get("repo"))
    destination_pair = clean_repository_pair(destination_repository.get("owner"), destination_repository.get("repo"))
    source_account = controller.account_for_owner(
        source_pair[0],
        {"account_login": context.get("source_account_login")},
        required=True,
    )
    destination_account = controller.account_for_owner(
        destination_pair[0],
        {"account_login": context.get("destination_account_login")},
        required=True,
    )
    source_client = GitHubApiClient(controller.token_for_account(source_account))
    destination_client = GitHubApiClient(controller.token_for_account(destination_account))
    validate_release_repositories(
        source_client,
        destination_client,
        source_pair,
        destination_pair,
    )

    source_release = latest_source_release(source_client, *source_pair)
    report_progress(
        progress,
        phase="checking",
        message=f"Checking release {source_release['tag_name']} and its attached artifacts",
    )
    if expected_tag and source_release["tag_name"] != clean_tag_name(expected_tag):
        raise AppError(
            "The expected source release is not GitHub's latest full release.",
            "SYNC_RELEASE_EXPECTED_TAG_MISMATCH",
        )
    existing = destination_release_for_tag(destination_client, *destination_pair, source_release["tag_name"])
    if existing and not bool(existing.get("draft")):
        asset_digests, total_bytes = verify_published_assets(
            source_client,
            destination_client,
            source_pair,
            destination_pair,
            source_release,
            existing,
            progress,
        )
        release_id = positive_id(existing.get("id"), "SYNC_RELEASE_ID_INVALID")
    else:
        draft = prepare_destination_draft(destination_client, destination_pair, source_release, existing)
        asset_digests, total_bytes = synchronize_draft_assets(
            source_client,
            destination_client,
            source_pair,
            destination_pair,
            source_release,
            draft,
            progress,
        )
        release_id = positive_id(draft.get("id"), "SYNC_RELEASE_ID_INVALID")
    report_progress(progress, phase="publishing", message="Publishing the verified destination release")
    published = publish_destination_release(
        destination_client,
        destination_pair,
        source_release,
        release_id,
    )
    digest = release_digest(source_release["tag_name"], asset_digests)
    receipt = {
        "source_path": context["source_path"],
        "destination_path": context["destination_path"],
        "source_digest": digest,
        "destination_digest": digest,
        "synced_at": sync_timestamp(),
        "file_count": len(asset_digests),
        "directory_count": 0,
        "total_bytes": total_bytes,
        "sync_mode": "release_artifacts",
        "release_tag": source_release["tag_name"],
    }
    report_progress(progress, phase="finalizing", message="Destination release published; saving the receipt")
    return {"release": serialize_release(published), "receipt": receipt}
