"""Download GitHub release assets for the GitDesk updater."""

from __future__ import annotations

# Standard-library helpers cover hashing, safe paths, URL validation, and response typing.
import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Third-party libraries provide platform-specific default paths and HTTPS streaming.
from platformdirs import user_downloads_path
import requests

from gitdesk.errors import AppError


# Network requests need bounded waits so one stalled asset download cannot hold a bridge worker indefinitely.
REQUEST_TIMEOUT_SECONDS = 60

# Streaming keeps large DMG or Windows installer downloads out of memory.
DOWNLOAD_CHUNK_BYTES = 1024 * 1024

# Authenticated asset downloads must begin at GitHub's REST asset API before redirects to storage.
ALLOWED_ASSET_API_HOSTS = {"api.github.com"}


# Converts GitHub download failures into user-safe updater errors without exposing request headers.
def download_error_message(response: requests.Response) -> str:
    """Return a safe GitHub download error message for an HTTP response."""

    try:
        payload = response.json()
    except ValueError:
        return f"GitHub update download failed with HTTP {response.status_code}."

    message = payload.get("message") if isinstance(payload, dict) else ""
    if message:
        return f"GitHub update download failed: {message}"
    return f"GitHub update download failed with HTTP {response.status_code}."


# Keeps release asset names from creating unexpected nested paths in the destination folder.
def clean_asset_filename(value: str) -> str:
    """Return a filename safe to create inside the selected destination folder."""

    filename = Path(str(value or "")).name.strip()
    if not filename or filename in {".", ".."}:
        raise AppError("GitHub returned an invalid update asset name.", "UPDATER_ASSET_INVALID")
    return filename


# Ensures repeated downloads do not overwrite a user's existing installer file.
def available_asset_path(asset_name: str, destination_dir: Path) -> Path:
    """Return an unused destination path inside the requested directory."""

    destination_dir.mkdir(parents=True, exist_ok=True)
    filename = clean_asset_filename(asset_name)
    candidate = destination_dir / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    # Finder-style numbering avoids clobbering earlier installers while keeping names recognizable.
    for index in range(1, 1000):
        numbered = destination_dir / f"{stem}-{index}{suffix}"
        if not numbered.exists():
            return numbered
    raise AppError("Unable to choose a unique update download filename.", "UPDATER_DESTINATION_FAILED")


# Ensures repeated downloads do not overwrite a user's existing installer file.
def available_download_path(asset_name: str) -> Path:
    """Return an unused destination path in the user's Downloads folder."""

    return available_asset_path(asset_name, user_downloads_path())


# Validates the GitHub REST asset URL used for authenticated release downloads.
def validate_asset_api_url(value: str) -> str:
    """Return a validated HTTPS GitHub release asset API URL."""

    download_url = str(value or "").strip()
    parsed_url = urlparse(download_url)
    if parsed_url.scheme != "https" or parsed_url.netloc.lower() not in ALLOWED_ASSET_API_HOSTS:
        raise AppError("GitHub returned an unsafe update asset URL.", "UPDATER_DOWNLOAD_URL_INVALID")
    if "/releases/assets/" not in parsed_url.path:
        raise AppError("GitHub returned an unexpected update asset URL.", "UPDATER_DOWNLOAD_URL_INVALID")
    return download_url


# Extracts GitHub's SHA-256 digest when the release asset payload includes one.
def expected_sha256_digest(asset: dict[str, Any]) -> str:
    """Return the expected SHA-256 digest, or an empty string when GitHub omitted it."""

    digest = str(asset.get("digest") or "").strip().lower()
    if not digest.startswith("sha256:"):
        return ""
    return digest.split(":", 1)[1]


# Removes a partial download after a failed transfer without masking the original failure.
def discard_partial_download(part_path: Path) -> None:
    """Best-effort cleanup for an incomplete updater download."""

    try:
        if part_path.exists():
            part_path.unlink()
    except OSError:
        return


# Streams one GitHub release asset from the authenticated REST asset endpoint into a local file.
def download_asset(
    session: requests.Session,
    asset: dict[str, Any],
    destination_dir: Path | None = None,
) -> dict[str, Any]:
    """Download the selected release asset and return the saved file details."""

    target_path = (
        available_asset_path(str(asset.get("name") or ""), destination_dir)
        if destination_dir
        else available_download_path(str(asset.get("name") or ""))
    )
    part_path = target_path.with_name(f".{target_path.name}.part")
    discard_partial_download(part_path)
    download_url = validate_asset_api_url(str(asset.get("url") or ""))
    expected_size = int(asset.get("size") or 0)
    expected_digest = expected_sha256_digest(asset)
    sha256 = hashlib.sha256()
    bytes_written = 0

    try:
        with session.get(
            download_url,
            headers={"Accept": "application/octet-stream"},
            stream=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:
            if response.status_code >= 400:
                raise AppError(download_error_message(response), "UPDATER_DOWNLOAD_FAILED")
            with part_path.open("wb") as download_file:
                for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
                    if not chunk:
                        continue
                    download_file.write(chunk)
                    sha256.update(chunk)
                    bytes_written += len(chunk)

        actual_digest = sha256.hexdigest()
        if expected_size and bytes_written != expected_size:
            message = "The downloaded update size did not match the GitHub release asset."
            raise AppError(message, "UPDATER_DOWNLOAD_SIZE_MISMATCH")
        if expected_digest and actual_digest != expected_digest:
            message = "The downloaded update checksum did not match the GitHub release asset."
            raise AppError(message, "UPDATER_DOWNLOAD_DIGEST_MISMATCH")

        part_path.replace(target_path)
        return {
            "path": str(target_path),
            "filename": target_path.name,
            "size": bytes_written,
            "sha256": actual_digest,
        }
    except requests.RequestException as error:
        discard_partial_download(part_path)
        raise AppError("Unable to download the GitDesk update.", "UPDATER_DOWNLOAD_FAILED") from error
    except OSError as error:
        discard_partial_download(part_path)
        raise AppError("Unable to save the GitDesk update download.", "UPDATER_DESTINATION_FAILED") from error
    except AppError:
        discard_partial_download(part_path)
        raise
