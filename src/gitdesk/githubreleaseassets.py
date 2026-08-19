"""Authenticated binary transport and validation for GitHub release assets."""

from __future__ import annotations

from hashlib import sha256
from tempfile import SpooledTemporaryFile
from typing import Any, BinaryIO, Callable, Iterator

import requests

from gitdesk.errors import AppError
from gitdesk.githubapi import GitHubApiClient
from gitdesk.githubreleaseerrors import raise_for_release_asset_response, request_release_api
from gitdesk.githubserializers import clean_repository_pair


# Large active transfers remain unbounded, but 30 seconds without another byte is a stalled request.
ASSET_TRANSFER_TIMEOUT = (15, 30)

# Eight MiB remains in memory before Python moves a large artifact into a secure temporary file.
ASSET_MEMORY_LIMIT = 8 * 1024 * 1024

# One MiB chunks keep hashing and authenticated downloads bounded for desktop-sized artifacts.
ASSET_CHUNK_SIZE = 1024 * 1024

TransferProgress = Callable[[int, int], None]


# Presents a requests byte iterator as a bounded reader while hashing the bytes consumed by an upload.
class DigestingStreamReader:
    """Read one source response incrementally and expose its verified digest after upload."""

    def __init__(
        self,
        chunks: Iterator[bytes],
        expected_size: int,
        on_progress: TransferProgress | None,
    ) -> None:
        self.chunks = chunks
        self.expected_size = expected_size
        self.on_progress = on_progress
        self.buffer = bytearray()
        self.digest = sha256()
        self.byte_count = 0
        self.finished = False

    def __len__(self) -> int:
        return self.expected_size

    def read(self, size: int = ASSET_CHUNK_SIZE) -> bytes:
        """Return at most size bytes without loading the complete artifact into memory."""

        requested = ASSET_CHUNK_SIZE if size is None or size < 0 else size
        while len(self.buffer) < requested and not self.finished:
            try:
                chunk = next(self.chunks)
            except StopIteration:
                self.finished = True
                break
            if chunk:
                self.buffer.extend(chunk)
        data = bytes(self.buffer[:requested])
        del self.buffer[:requested]
        if data:
            self.digest.update(data)
            self.byte_count += len(data)
            if self.on_progress:
                self.on_progress(self.byte_count, self.expected_size)
        return data

    def verified_digest(self) -> str:
        """Return the streamed digest only when the upload consumed the expected byte count."""

        if self.byte_count != self.expected_size:
            raise AppError("A downloaded release asset failed size verification.", "SYNC_RELEASE_ASSET_SIZE_MISMATCH")
        return f"sha256:{self.digest.hexdigest()}"


# Adds upload progress without changing the caller-owned source stream or its length contract.
class ProgressReader:
    """Forward reads to a source while reporting cumulative uploaded bytes."""

    def __init__(self, source: BinaryIO, expected_size: int, on_progress: TransferProgress) -> None:
        self.source = source
        self.expected_size = expected_size
        self.on_progress = on_progress
        self.byte_count = 0

    def __len__(self) -> int:
        return self.expected_size

    def read(self, size: int = -1) -> bytes:
        """Read from the wrapped source and report only bytes actually consumed by requests."""

        data = self.source.read(size)
        if data:
            self.byte_count += len(data)
            self.on_progress(self.byte_count, self.expected_size)
        return data


# Converts API identifiers into positive integers before they become release or asset path segments.
def positive_id(value: Any, error_code: str) -> int:
    """Return a positive GitHub object id or raise error_code for malformed API data."""

    try:
        identifier = int(value)
    except (TypeError, ValueError) as error:
        raise AppError("GitHub returned an invalid release identifier.", error_code) from error
    if identifier <= 0:
        raise AppError("GitHub returned an invalid release identifier.", error_code)
    return identifier


# Converts GitHub's asset size into a safe non-negative byte count before transfer validation.
def clean_asset_size(value: Any) -> int:
    """Return a non-negative asset byte count or raise for malformed GitHub data."""

    try:
        size = int(value or 0)
    except (TypeError, ValueError) as error:
        raise AppError("GitHub returned an invalid release asset size.", "SYNC_RELEASE_ASSET_INVALID") from error
    if size < 0:
        raise AppError("GitHub returned an invalid release asset size.", "SYNC_RELEASE_ASSET_INVALID")
    return size


# Normalizes GitHub's optional server-calculated SHA-256 value for exact asset comparisons.
def clean_asset_digest(value: Any) -> str:
    """Return a normalized sha256:<hex> digest, or empty when GitHub omitted it."""

    digest = str(value or "").strip().lower()
    prefix, separator, hexadecimal = digest.partition(":")
    if prefix != "sha256" or separator != ":" or len(hexadecimal) != 64:
        return ""
    if any(character not in "0123456789abcdef" for character in hexadecimal):
        return ""
    return digest


# ReleaseAssetTransport performs authenticated raw-byte transfers outside the JSON-only API method.
class ReleaseAssetTransport:
    """Download and upload release assets through an owner-routed API client session."""

    # Retains the authenticated session selected for the factual repository owner.
    def __init__(self, client: GitHubApiClient) -> None:
        """Store the GitHub client whose bearer token authorizes every binary request."""

        self.client = client

    # Downloads one asset into a caller-owned file while hashing and size-checking the bytes.
    def download(
        self,
        owner: str,
        repo: str,
        asset: dict[str, Any],
        target: BinaryIO,
        on_progress: TransferProgress | None = None,
        operation: str = "download_source_asset",
    ) -> str:
        """Write asset bytes to target and return their verified SHA-256 digest."""

        clean_owner, clean_repo = clean_repository_pair(owner, repo)
        asset_id = positive_id(asset.get("id"), "SYNC_RELEASE_ASSET_ID_INVALID")
        expected_size = clean_asset_size(asset.get("size"))
        url = f"https://api.github.com/repos/{clean_owner}/{clean_repo}/releases/assets/{asset_id}"
        target.seek(0)
        target.truncate(0)
        digest = sha256()
        byte_count = 0
        try:
            with self.client.session.get(
                url,
                headers={"Accept": "application/octet-stream"},
                stream=True,
                timeout=ASSET_TRANSFER_TIMEOUT,
            ) as response:
                raise_for_release_asset_response(
                    self.client,
                    response,
                    (clean_owner, clean_repo),
                    operation,
                )
                for chunk in response.iter_content(chunk_size=ASSET_CHUNK_SIZE):
                    if chunk:
                        target.write(chunk)
                        digest.update(chunk)
                        byte_count += len(chunk)
                        if on_progress:
                            on_progress(byte_count, expected_size)
        except requests.RequestException as error:
            raise AppError("Unable to transfer a GitHub release asset.", "GITHUB_NETWORK_FAILED") from error
        if byte_count != expected_size:
            raise AppError("A downloaded release asset failed size verification.", "SYNC_RELEASE_ASSET_SIZE_MISMATCH")
        target.seek(0)
        return f"sha256:{digest.hexdigest()}"

    # Uploads raw bytes to GitHub's release-specific uploads endpoint.
    def upload(
        self,
        owner: str,
        repo: str,
        release_id: int,
        source_asset: dict[str, Any],
        source: BinaryIO,
        on_progress: TransferProgress | None = None,
        rewind: bool = True,
    ) -> dict[str, Any]:
        """Upload source while preserving its normalized name, label, and media type."""

        clean_owner, clean_repo = clean_repository_pair(owner, repo)
        clean_release_id = positive_id(release_id, "SYNC_RELEASE_ID_INVALID")
        asset_name = str(source_asset.get("name") or "").strip()
        asset_label = str(source_asset.get("label") or "").strip()
        content_type = str(source_asset.get("content_type") or "application/octet-stream").strip()
        content_type = content_type or "application/octet-stream"
        expected_size = clean_asset_size(source_asset.get("size"))
        if "\n" in content_type or "\r" in content_type:
            raise AppError("GitHub returned an invalid release asset media type.", "SYNC_RELEASE_ASSET_INVALID")
        url = f"https://uploads.github.com/repos/{clean_owner}/{clean_repo}/releases/{clean_release_id}/assets"
        if rewind:
            source.seek(0)
        upload_source = ProgressReader(source, expected_size, on_progress) if on_progress else source
        try:
            response = self.client.session.post(
                url,
                params={"name": asset_name, "label": asset_label},
                headers={"Content-Type": content_type, "Content-Length": str(expected_size)},
                data=upload_source,
                timeout=ASSET_TRANSFER_TIMEOUT,
            )
        except requests.RequestException as error:
            raise AppError("Unable to upload a GitHub release asset.", "GITHUB_NETWORK_FAILED") from error
        try:
            raise_for_release_asset_response(
                self.client,
                response,
                (clean_owner, clean_repo),
                "upload_destination_asset",
            )
            payload = response.json()
        except ValueError as error:
            raise AppError("GitHub returned an invalid release asset response.", "GITHUB_RESPONSE_INVALID") from error
        finally:
            response.close()
        if not isinstance(payload, dict):
            raise AppError("GitHub returned an invalid release asset response.", "GITHUB_RESPONSE_INVALID")
        return payload

    # Streams a digest-backed source GET directly into a destination POST so the two transfers overlap.
    def copy_to(
        self,
        destination: "ReleaseAssetTransport",
        source_pair: tuple[str, str],
        destination_pair: tuple[str, str],
        destination_release_id: int,
        source_asset: dict[str, Any],
        on_download_progress: TransferProgress | None = None,
        on_upload_progress: TransferProgress | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Upload one authenticated source asset to a destination draft while hashing the same byte stream."""

        source_owner, source_repo = clean_repository_pair(*source_pair)
        asset_id = positive_id(source_asset.get("id"), "SYNC_RELEASE_ASSET_ID_INVALID")
        expected_size = clean_asset_size(source_asset.get("size"))
        url = f"https://api.github.com/repos/{source_owner}/{source_repo}/releases/assets/{asset_id}"
        try:
            with self.client.session.get(
                url,
                headers={"Accept": "application/octet-stream"},
                stream=True,
                timeout=ASSET_TRANSFER_TIMEOUT,
            ) as response:
                raise_for_release_asset_response(
                    self.client,
                    response,
                    (source_owner, source_repo),
                    "download_source_asset",
                )
                reader = DigestingStreamReader(
                    iter(response.iter_content(chunk_size=ASSET_CHUNK_SIZE)),
                    expected_size,
                    on_download_progress,
                )
                uploaded = destination.upload(
                    *destination_pair,
                    destination_release_id,
                    source_asset,
                    reader,
                    on_upload_progress,
                    rewind=False,
                )
                return uploaded, reader.verified_digest()
        except requests.RequestException as error:
            raise AppError("Unable to transfer a GitHub release asset.", "GITHUB_NETWORK_FAILED") from error


# Reads every release asset page so the exact set is never inferred from a partial response.
def release_assets(client: GitHubApiClient, owner: str, repo: str, release_id: int) -> list[dict[str, Any]]:
    """Return all raw assets for one release in stable filename order."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    clean_release_id = positive_id(release_id, "SYNC_RELEASE_ID_INVALID")
    assets: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = request_release_api(
            client,
            "GET",
            f"/repos/{clean_owner}/{clean_repo}/releases/{clean_release_id}/assets",
            (clean_owner, clean_repo),
            "list_release_assets",
            params={"per_page": 100, "page": page},
        )
        if not isinstance(payload, list):
            raise AppError("GitHub returned an invalid release asset list.", "GITHUB_RESPONSE_INVALID")
        if any(not isinstance(item, dict) for item in payload):
            raise AppError("GitHub returned an invalid release asset list.", "GITHUB_RESPONSE_INVALID")
        assets.extend(payload)
        if len(payload) < 100:
            return sorted(assets, key=lambda item: str(item.get("name") or "").lower())
        page += 1


# Validates that every source entry is a complete, uniquely named, non-empty build artifact.
def clean_source_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return validated source release assets or raise before Public is changed."""

    if not assets:
        raise AppError("The latest Public Beta release has no built artifacts.", "SYNC_RELEASE_ASSETS_MISSING")
    cleaned = []
    seen_names: set[str] = set()
    for asset in assets:
        name = str(asset.get("name") or "").strip()
        size = clean_asset_size(asset.get("size"))
        if not name or str(asset.get("state") or "") != "uploaded" or size <= 0:
            raise AppError("The latest Public Beta release has an incomplete asset.", "SYNC_RELEASE_ASSET_INVALID")
        if name in seen_names:
            raise AppError("The latest Public Beta release has duplicate asset names.", "SYNC_RELEASE_ASSET_DUPLICATE")
        positive_id(asset.get("id"), "SYNC_RELEASE_ASSET_ID_INVALID")
        cleaned.append({**asset, "name": name, "size": size})
        seen_names.add(name)
    return sorted(cleaned, key=lambda item: item["name"].lower())


# Downloads a destination asset only when GitHub omitted a usable server digest.
def destination_asset_matches(
    transport: ReleaseAssetTransport,
    owner: str,
    repo: str,
    asset: dict[str, Any],
    expected_size: int,
    expected_digest: str,
    on_progress: TransferProgress | None = None,
) -> bool:
    """Return whether a destination asset exactly matches verified source bytes."""

    if clean_asset_size(asset.get("size")) != expected_size:
        return False
    saved_digest = clean_asset_digest(asset.get("digest"))
    if saved_digest:
        return saved_digest == expected_digest
    with SpooledTemporaryFile(max_size=ASSET_MEMORY_LIMIT, mode="w+b") as temporary_file:
        return transport.download(
            owner,
            repo,
            asset,
            temporary_file,
            on_progress,
            operation="download_destination_asset",
        ) == expected_digest


# Applies the shared post-upload contract to streamed and two-pass transfers.
def validate_uploaded_asset(
    transport: ReleaseAssetTransport,
    destination_pair: tuple[str, str],
    uploaded: dict[str, Any],
    source_asset: dict[str, Any],
    digest: str,
    on_progress: TransferProgress | None = None,
) -> None:
    """Reject incomplete, renamed, or byte-mismatched destination assets."""

    if str(uploaded.get("state") or "") != "uploaded":
        raise AppError("GitHub did not finish a promoted release asset.", "SYNC_RELEASE_ASSET_INVALID")
    if str(uploaded.get("name") or "") != source_asset["name"]:
        raise AppError("GitHub renamed a promoted release asset.", "SYNC_RELEASE_ASSET_NAME_CHANGED")
    if not destination_asset_matches(
        transport,
        *destination_pair,
        uploaded,
        source_asset["size"],
        digest,
        on_progress,
    ):
        raise AppError("An uploaded Public release asset failed verification.", "SYNC_RELEASE_ASSET_MISMATCH")
