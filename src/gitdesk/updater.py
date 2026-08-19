"""GitDesk self-update discovery and installer download support."""

from __future__ import annotations

# Standard library helpers cover platform detection and response typing.
import platform
import sys
from pathlib import Path
from typing import Any

# Third-party libraries provide HTTPS requests for GitHub release metadata.
import requests

# GitDesk modules provide app version metadata, structured UI errors, downloads, and GitHub API headers.
from gitdesk import APP_VERSION
from gitdesk.errors import AppError
from gitdesk.githubapi import GITHUB_API_VERSION
from gitdesk.updater_download import download_asset
from gitdesk.updater_install import macos_install_context, prepare_update_stage, stage_macos_update


# The updater is intentionally pinned to GitDesk's release repository rather than user project settings.
UPDATE_OWNER = "xandlab"

# The public updater repository hosts the signed-off desktop binaries users should download.
UPDATE_REPO = "gd-public"

# The public releases page is the human-facing source of every update GitDesk offers.
UPDATE_RELEASES_URL = f"https://github.com/{UPDATE_OWNER}/{UPDATE_REPO}/releases"

# GitHub exposes only the latest published, non-draft, non-prerelease release through this endpoint.
LATEST_RELEASE_URL = f"https://api.github.com/repos/{UPDATE_OWNER}/{UPDATE_REPO}/releases/latest"

# Network requests need bounded waits so one stalled update check cannot hold a bridge worker indefinitely.
REQUEST_TIMEOUT_SECONDS = 60

# Windows currently ships as x64 from the workflow, so avoid offering unsupported architectures.
WINDOWS_X64_MACHINES = {"amd64", "x86_64"}

# Apple Silicon machine names identify the ARM64 DMG produced by the native macOS runner.
MAC_ARM_MACHINES = {"arm64", "aarch64"}

# Intel machine names identify the x86_64 DMG produced by GitHub's Intel macOS runner.
MAC_INTEL_MACHINES = {"amd64", "x86_64"}

# Builds an anonymous session because GitDesk updates now come exclusively from a public repository.
def release_session() -> requests.Session:
    """Return an unauthenticated HTTP session for public release metadata and asset downloads."""

    session = requests.Session()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": f"GitDesk/{APP_VERSION}",
    }
    session.headers.update(headers)
    return session


# Converts GitHub HTTP failures into user-safe updater errors.
def github_error_message(response: requests.Response) -> str:
    """Return a safe GitHub API error message without exposing request headers."""

    try:
        payload = response.json()
    except ValueError:
        return f"GitHub update check failed with HTTP {response.status_code}."

    message = payload.get("message") if isinstance(payload, dict) else ""
    if message:
        return f"GitHub update check failed: {message}"
    return f"GitHub update check failed with HTTP {response.status_code}."


# Fetches the latest release object from the fixed GitDesk update repository.
def fetch_latest_release(session: requests.Session) -> dict[str, Any]:
    """Return the latest published GitDesk release payload from GitHub."""

    try:
        response = session.get(LATEST_RELEASE_URL, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as error:
        raise AppError("Unable to reach the GitDesk update service.", "UPDATER_NETWORK_FAILED") from error

    if response.status_code == 404:
        message = "No published GitDesk update release is visible yet."
        raise AppError(message, "UPDATER_RELEASE_NOT_FOUND", {"url": LATEST_RELEASE_URL})
    if response.status_code >= 400:
        raise AppError(github_error_message(response), "UPDATER_RELEASE_CHECK_FAILED")

    try:
        payload = response.json()
    except ValueError as error:
        raise AppError("GitHub returned an invalid update response.", "UPDATER_RESPONSE_INVALID") from error
    if not isinstance(payload, dict):
        raise AppError("GitHub returned an unexpected update response.", "UPDATER_RESPONSE_INVALID")
    return payload


# Identifies the only operating systems and architectures this updater can safely serve.
def platform_update_target() -> dict[str, str]:
    """Return the update asset target for the current operating system."""

    system_name = sys.platform
    machine_name = platform.machine().lower()
    if system_name == "darwin":
        if machine_name in MAC_ARM_MACHINES:
            return {
                "platform": "macos",
                "architecture": "arm64",
                "label": "macOS Apple Silicon",
                "expected_asset": "GitDesk-macOS-arm64.dmg",
            }
        if machine_name in MAC_INTEL_MACHINES:
            return {
                "platform": "macos",
                "architecture": "x86_64",
                "label": "macOS Intel",
                "expected_asset": "GitDesk-macOS-x86_64.dmg",
            }
        message = "GitDesk macOS updates require an Apple Silicon or 64-bit Intel Mac."
        raise AppError(message, "UPDATER_PLATFORM_UNSUPPORTED", {"machine": machine_name})

    if system_name == "win32":
        if machine_name not in WINDOWS_X64_MACHINES:
            message = "GitDesk Windows updates are currently available only for Windows x64."
            raise AppError(message, "UPDATER_PLATFORM_UNSUPPORTED", {"machine": machine_name})
        return {
            "platform": "windows",
            "architecture": "x64",
            "label": "Windows x64",
            "expected_asset": "GitDesk-Windows-x64.exe",
        }

    message = "GitDesk updater downloads are currently supported only on macOS and Windows."
    raise AppError(message, "UPDATER_PLATFORM_UNSUPPORTED", {"platform": system_name})


# Extracts comparable numeric version parts from app versions and release tags.
def version_parts(value: str) -> tuple:
    """Return numeric version parts from a simple version label."""

    clean_value = str(value or "").strip().lower()
    if clean_value.startswith("v"):
        clean_value = clean_value[1:]
    clean_value = clean_value.split("+", 1)[0].split("-", 1)[0]
    parts = []
    for raw_part in clean_value.split("."):
        if not raw_part.isdigit():
            return ()
        parts.append(int(raw_part))
    return tuple(parts)


# Compares release tags with the local app version without adding another dependency.
def compare_versions(left_value: str, right_value: str) -> int:
    """Return 1, 0, or -1 when the left version is newer, equal, or older."""

    left_parts = version_parts(left_value)
    right_parts = version_parts(right_value)
    if not left_parts or not right_parts:
        message = "GitDesk could not compare the release version with the installed version."
        raise AppError(message, "UPDATER_VERSION_INVALID", {"latest": left_value, "current": right_value})

    part_count = max(len(left_parts), len(right_parts))
    padded_left = left_parts + ((0,) * (part_count - len(left_parts)))
    padded_right = right_parts + ((0,) * (part_count - len(right_parts)))
    if padded_left > padded_right:
        return 1
    if padded_left < padded_right:
        return -1
    return 0


# Returns the release fields the frontend needs without preserving unnecessary GitHub payload detail.
def release_summary(release: dict[str, Any]) -> dict[str, Any]:
    """Return a compact release summary for the updater UI."""

    return {
        "tag_name": str(release.get("tag_name") or ""),
        "name": str(release.get("name") or ""),
        "html_url": str(release.get("html_url") or ""),
        "published_at": str(release.get("published_at") or ""),
    }


# Normalizes one GitHub asset into the fields required for download and display.
def asset_summary(asset: dict[str, Any]) -> dict[str, Any]:
    """Return the safe subset of a GitHub release asset payload."""

    return {
        "url": str(asset.get("url") or ""),
        "name": str(asset.get("name") or ""),
        "size": int(asset.get("size") or 0),
        "digest": str(asset.get("digest") or ""),
        "browser_download_url": str(asset.get("browser_download_url") or ""),
    }


# Scores macOS assets against the exact architecture-specific release filename.
def macos_asset_score(asset_name: str, target: dict[str, str]) -> int:
    """Return a positive score only for a GitDesk macOS DMG matching the detected architecture."""

    lowered = asset_name.lower()
    expected_name = target.get("expected_asset", "").lower()
    if not expected_name or lowered != expected_name:
        return 0
    return 30


# Scores Windows assets while preferring a standalone executable over the current zip archive.
def windows_asset_score(asset_name: str) -> int:
    """Return a positive score for a Windows x64 release asset."""

    lowered = asset_name.lower()
    platform_match = "windows" in lowered or "win" in lowered
    architecture_match = "x64" in lowered or "amd64" in lowered
    if not platform_match or not architecture_match:
        return 0
    if lowered.endswith(".exe"):
        return 30 if lowered == "gitdesk-windows-x64.exe" else 20
    if lowered.endswith(".zip"):
        return 10
    return 0


# Chooses the release asset matching the current operating system.
def select_asset(release: dict[str, Any], target: dict[str, str]) -> dict[str, Any]:
    """Return the best release asset for the detected platform target."""

    assets = release.get("assets") or []
    if not isinstance(assets, list):
        raise AppError("GitHub returned an invalid release asset list.", "UPDATER_RESPONSE_INVALID")

    scored_assets = []
    for raw_asset in assets:
        if not isinstance(raw_asset, dict) or raw_asset.get("state") != "uploaded":
            continue
        asset_name = str(raw_asset.get("name") or "")
        if target["platform"] == "macos":
            score = macos_asset_score(asset_name, target)
        else:
            score = windows_asset_score(asset_name)
        if score > 0:
            scored_assets.append((score, raw_asset))

    if not scored_assets:
        message = f"No {target['label']} update asset was attached to the latest GitDesk release."
        raise AppError(message, "UPDATER_ASSET_MISSING", {"expected_asset": target["expected_asset"]})
    scored_assets.sort(key=lambda item: item[0], reverse=True)
    return asset_summary(scored_assets[0][1])


# Builds the shared public update state used by check, download, and install workflows.
def latest_update_state() -> tuple[requests.Session, dict[str, Any]]:
    """Return the public release state and its anonymous asset-download session."""

    target = platform_update_target()
    session = release_session()
    release = fetch_latest_release(session)
    latest_version = str(release.get("tag_name") or "").strip()
    current_version = APP_VERSION

    if compare_versions(latest_version, current_version) <= 0:
        return session, {
            "status": "current",
            "update_available": False,
            "current_version": current_version,
            "latest_version": latest_version,
            "install_supported": target["platform"] == "macos",
            "release_source": UPDATE_RELEASES_URL,
            "target": target,
            "release": release_summary(release),
        }

    asset = select_asset(release, target)
    return session, {
        "status": "available",
        "update_available": True,
        "current_version": current_version,
        "latest_version": latest_version,
        "install_supported": target["platform"] == "macos",
        "release_source": UPDATE_RELEASES_URL,
        "target": target,
        "release": release_summary(release),
        "asset": asset,
    }


# Performs release discovery without downloading or staging an installer.
def check_latest_update() -> dict[str, Any]:
    """Return whether the public release repository has a compatible newer GitDesk release."""

    _session, state = latest_update_state()
    return state


# Performs the check-and-download workflow retained for manual installer downloads.
def download_latest_update() -> dict[str, Any]:
    """Check GitHub for a newer GitDesk release and download the matching installer asset."""

    session, state = latest_update_state()
    if state["status"] == "current":
        return state

    download = download_asset(session, state["asset"])
    return {
        **state,
        "status": "downloaded",
        "download": download,
    }


# Rejects a stale install click if the public latest release changed after the user's check.
def validate_checked_version(state: dict[str, Any], expected_version: str) -> None:
    """Require an available release whose tag exactly matches the version confirmed by the check action."""

    checked_version = str(expected_version or "").strip()
    if not checked_version:
        message = "Check for updates before installing a GitDesk update."
        raise AppError(message, "UPDATER_CHECK_REQUIRED")

    latest_version = str(state.get("latest_version") or "").strip()
    if state.get("status") != "available" or latest_version != checked_version:
        message = "The latest public release changed after the update check. Check again before installing."
        details = {"checked_version": checked_version, "latest_version": latest_version}
        raise AppError(message, "UPDATER_RELEASE_CHANGED", details)


# Performs the full macOS self-update workflow after a separate successful Settings check.
def install_latest_update(expected_version: str) -> dict[str, Any]:
    """Download and stage the exact public release version confirmed by the preceding check action."""

    session, state = latest_update_state()
    validate_checked_version(state, expected_version)

    target = state["target"]
    if target["platform"] != "macos":
        message = "Automatic install and restart updates are currently available only for macOS DMG builds."
        raise AppError(message, "UPDATER_INSTALL_UNSUPPORTED", {"platform": target["platform"]})

    macos_install_context()
    stage_dir = prepare_update_stage(str(state["latest_version"]))
    download = download_asset(session, state["asset"], stage_dir)
    install = stage_macos_update(Path(download["path"]), stage_dir)
    return {
        **state,
        "status": "restarting",
        "download": download,
        "install": install,
    }
