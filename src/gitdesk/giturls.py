"""GitHub remote URL parsing and validation helpers for GitDesk."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from gitdesk.errors import AppError


# GitHub remote URLs are parsed only to prefill API owner/repo fields; Git itself remains the source of truth.
HTTPS_REMOTE_PATTERN = re.compile(r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")
SSH_REMOTE_PATTERN = re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$")
SSH_URL_REMOTE_PATTERN = re.compile(r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")

# Local clone folder names must stay within the destination parent directory.
LOCAL_FOLDER_PATTERN = re.compile(r"^[A-Za-z0-9._ -]+$")

# GitHub account and repository segments are validated before any Git process receives the URL.
OWNER_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPO_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


# Removes userinfo from HTTP(S) remotes before any URL is returned to JavaScript or parsed for metadata.
def redact_url_credentials(url: str) -> str:
    """Return a remote URL with any embedded HTTP(S) username/password removed."""

    cleaned_url = str(url or "").strip()
    parsed_url = urlsplit(cleaned_url)
    if parsed_url.scheme not in {"http", "https"} or "@" not in parsed_url.netloc:
        return cleaned_url

    safe_netloc = parsed_url.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parsed_url.scheme, safe_netloc, parsed_url.path, parsed_url.query, parsed_url.fragment))


# Parses GitHub remote URL formats used by HTTPS and SSH remotes.
def parse_github_remote(url: str) -> dict[str, str]:
    """Return owner and repo names from a GitHub remote URL, or empty strings when unsupported."""

    cleaned_url = redact_url_credentials(url)
    for pattern in (HTTPS_REMOTE_PATTERN, SSH_REMOTE_PATTERN, SSH_URL_REMOTE_PATTERN):
        match = pattern.match(cleaned_url)
        if match:
            return {"owner": match.group("owner"), "repo": match.group("repo")}
    return {"owner": "", "repo": ""}


# Validates clone URLs so the app only invokes Git for GitHub HTTPS or SSH remotes.
def normalize_github_clone_url(url: str) -> str:
    """Return a validated GitHub clone URL for HTTPS or SSH cloning."""

    cleaned_url = str(url or "").strip()
    if not cleaned_url:
        raise AppError("GitHub clone URL is required.", "CLONE_URL_EMPTY")

    safe_url = redact_url_credentials(cleaned_url)
    parsed_remote = parse_github_remote(safe_url)
    if not parsed_remote["owner"] or not parsed_remote["repo"]:
        raise AppError("Clone URL must be a GitHub HTTPS or SSH repository URL.", "CLONE_URL_INVALID")
    if not OWNER_SEGMENT_PATTERN.match(parsed_remote["owner"]):
        raise AppError("GitHub owner in clone URL contains invalid characters.", "CLONE_URL_INVALID")
    if not REPO_SEGMENT_PATTERN.match(parsed_remote["repo"]):
        raise AppError("GitHub repository in clone URL contains invalid characters.", "CLONE_URL_INVALID")
    return safe_url


# Derives a default local folder name from the repository segment of a GitHub remote URL.
def default_clone_folder_name(url: str) -> str:
    """Return the default local folder name for a validated GitHub clone URL."""

    parsed_remote = parse_github_remote(url)
    repository_name = parsed_remote.get("repo", "").removesuffix(".git")
    return normalize_clone_folder_name(repository_name)


# Validates a user-supplied local clone folder name without accepting path traversal.
def normalize_clone_folder_name(folder_name: str) -> str:
    """Return a safe local folder name for a clone target directory."""

    cleaned_name = str(folder_name or "").strip()
    if not cleaned_name or cleaned_name in {".", ".."}:
        raise AppError("Local clone folder name is required.", "CLONE_FOLDER_EMPTY")
    if "/" in cleaned_name or "\\" in cleaned_name:
        raise AppError("Local clone folder name cannot contain path separators.", "CLONE_FOLDER_INVALID")
    if cleaned_name.startswith(".") or not LOCAL_FOLDER_PATTERN.match(cleaned_name):
        raise AppError("Local clone folder name contains invalid characters.", "CLONE_FOLDER_INVALID")
    return cleaned_name
