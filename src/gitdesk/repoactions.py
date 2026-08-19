"""Repository diff, fetch, and desktop open actions for GitDesk."""

from __future__ import annotations

import difflib
import os
from pathlib import Path
import platform
import subprocess
from urllib.parse import urlparse
import webbrowser
from typing import Any

from git import GitCommandError

from gitdesk.errors import AppError
from gitdesk.gitauth import git_auth_environment, git_remote_argument
from gitdesk.gitops import active_branch_name, auth_login_for_origin, normalize_repository_path, open_repository
from gitdesk.gitops import origin_remote_url, validate_relative_git_path
from gitdesk.giturls import parse_github_remote
from gitdesk.nativeopen import open_in_editor


# Very large diffs make the WebView sluggish, so mirror GitHub's "file too large" behavior.
MAX_INLINE_DIFF_BYTES = 1_000_000
PROTECTED_GITIGNORE_PATHS = {".gitignore", ".git", ".github"}


# Formats a repository-relative path for .gitignore while keeping spaces readable.
def gitignore_pattern_for_path(path_value: str) -> str:
    """Return a .gitignore pattern for a validated repository-relative path."""

    safe_path = validate_relative_git_path(path_value)
    has_trailing_slash = safe_path.endswith("/")
    path_parts = [part for part in safe_path.replace("\\", "/").split("/") if part]
    normalized_path = "/".join(path_parts)
    if normalized_path in PROTECTED_GITIGNORE_PATHS:
        raise AppError(".gitignore, .git, and .github cannot be ignored.", "GITIGNORE_PATH_PROTECTED")
    suffix = "/" if has_trailing_slash else ""
    return f"/{'/'.join(path_parts)}{suffix}"


# Resolves a working-tree file path after Git-relative path validation.
def repository_file_path(repository_root: Path, relative_path: str) -> Path:
    """Return an absolute working-tree file path that stays inside the repository."""

    safe_path = validate_relative_git_path(relative_path)
    candidate = (repository_root / safe_path).resolve()
    try:
        candidate.relative_to(repository_root)
    except ValueError as error:
        raise AppError("A selected file path is outside the repository.", "UNSAFE_REPOSITORY_PATH") from error
    return candidate


# Reads an untracked text file and builds a unified diff from an empty file.
def untracked_file_diff(repository_root: Path, relative_path: str) -> str:
    """Return a unified diff for an untracked working-tree file."""

    file_path = repository_file_path(repository_root, relative_path)
    if not file_path.exists() or not file_path.is_file():
        return ""
    if file_path.stat().st_size > MAX_INLINE_DIFF_BYTES:
        return f"diff --git a/{relative_path} b/{relative_path}\n@@ File too large to display @@\n"
    if b"\0" in file_path.read_bytes()[:8192]:
        return f"diff --git a/{relative_path} b/{relative_path}\nBinary file not shown.\n"

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(
        difflib.unified_diff(
            [],
            lines,
            fromfile="/dev/null",
            tofile=f"b/{relative_path}",
            lineterm="",
        )
    )


# Returns a Git-style diff for a tracked or untracked changed file.
def file_diff(path_value: str, file_path: str) -> dict[str, Any]:
    """Return a display-ready unified diff for one changed repository file."""

    repo = open_repository(path_value)
    root = Path(repo.working_tree_dir or path_value).resolve()
    safe_path = validate_relative_git_path(file_path)

    try:
        staged_diff = repo.git.diff("--cached", "--", safe_path)
        unstaged_diff = repo.git.diff("--", safe_path)
    except GitCommandError as error:
        raise AppError("Git could not read the selected file diff.", "GIT_DIFF_FAILED") from error

    diff_parts = [part for part in (staged_diff, unstaged_diff) if part.strip()]
    if not diff_parts and safe_path in repo.untracked_files:
        diff_parts.append(untracked_file_diff(root, safe_path))

    return {
        "path": safe_path,
        "diff": "\n".join(diff_parts).strip(),
    }


# Fetches origin while using the saved askpass flow only for GitHub HTTPS remotes.
def fetch_repository(path_value: str, auth_login: str | None = None) -> dict[str, Any]:
    """Fetch origin for the active repository and return serialized Git output."""

    repo = open_repository(path_value)
    if not any(remote.name == "origin" for remote in repo.remotes):
        raise AppError("No origin remote is configured for this repository.", "GIT_ORIGIN_MISSING")

    origin_url = origin_remote_url(repo)
    git_login = auth_login_for_origin(repo, auth_login)
    remote_target = git_remote_argument(origin_url, git_login)
    fetch_args = ["--prune", remote_target]
    if remote_target != "origin":
        fetch_args.append("+refs/heads/*:refs/remotes/origin/*")

    try:
        output = repo.git.fetch(*fetch_args, env=git_auth_environment(git_login))
    except GitCommandError as error:
        raise AppError("Git could not fetch from origin.", "GIT_FETCH_FAILED") from error

    return {"messages": [output] if output else []}


# Finds the best upstream ref for the active branch using explicit tracking before origin fallback.
def active_upstream_ref(repo: Any, branch: str) -> str:
    """Return the fetched remote-tracking ref that should be compared with the local branch."""

    for head in repo.heads:
        if head.name != branch:
            continue
        tracking = head.tracking_branch()
        if tracking:
            return tracking.name
    return f"origin/{branch}"


# Compares the active branch with the latest fetched upstream ref without contacting the network.
def sync_status(path_value: str) -> dict[str, Any]:
    """Return local ahead/behind counts for the active branch against its fetched upstream."""

    repo = open_repository(path_value)
    branch = active_branch_name(repo)
    if branch == "DETACHED":
        return {"branch": branch, "upstream": "", "ahead": 0, "behind": 0, "has_upstream": False}

    upstream = active_upstream_ref(repo, branch)
    try:
        repo.git.rev_parse("--verify", upstream)
        ahead = int(repo.git.rev_list("--count", f"{upstream}..{branch}"))
        behind = int(repo.git.rev_list("--count", f"{branch}..{upstream}"))
    except GitCommandError:
        return {"branch": branch, "upstream": upstream, "ahead": 0, "behind": 0, "has_upstream": False}

    return {"branch": branch, "upstream": upstream, "ahead": ahead, "behind": behind, "has_upstream": True}


# Appends one changed file path to .gitignore if it is not already present.
def add_path_to_gitignore(path_value: str, file_path: str) -> dict[str, Any]:
    """Add one repository-relative file path to the repository .gitignore file."""

    repo = open_repository(path_value)
    repository_path = Path(repo.working_tree_dir or path_value).resolve()
    gitignore_path = repository_path / ".gitignore"
    pattern = gitignore_pattern_for_path(file_path)
    existing_text = ""
    existing_lines = []
    if gitignore_path.exists():
        existing_text = gitignore_path.read_text(encoding="utf-8", errors="replace")
        existing_lines = existing_text.splitlines()

    added = pattern not in existing_lines
    if added:
        prefix = "\n" if existing_text and not existing_text.endswith("\n") else ""
        with gitignore_path.open("a", encoding="utf-8") as ignore_file:
            ignore_file.write(f"{prefix}{pattern}\n")

    return {
        "path": pattern,
        "gitignore": str(gitignore_path),
        "added": added,
    }


# Opens a local folder using the platform's normal file manager.
def open_in_file_manager(path_value: str) -> dict[str, str]:
    """Open the repository folder in Finder, Explorer, or the Linux file manager."""

    repo = open_repository(path_value)
    repository_path = str(Path(repo.working_tree_dir or path_value).resolve())
    system_name = platform.system()
    if system_name == "Darwin":
        subprocess.Popen(["open", repository_path])
    elif system_name == "Windows":
        os.startfile(repository_path)
    else:
        subprocess.Popen(["xdg-open", repository_path])
    return {"path": repository_path}


# Opens the active repository folder in the selected validated code editor.
def open_in_vscode(path_value: str, editor_preferences: dict[str, str] | None = None) -> dict[str, str]:
    """Open the repository folder in the user's selected code editor."""

    repository_path = str(normalize_repository_path(path_value))
    return open_in_editor(repository_path, editor_preferences)


# Opens the GitHub repository page inferred from the origin remote.
def open_on_github(path_value: str) -> dict[str, str]:
    """Open the active repository's GitHub page in the default browser."""

    repo = open_repository(path_value)
    remote = parse_github_remote(next((remote.url for remote in repo.remotes if remote.name == "origin"), ""))
    if not remote["owner"] or not remote["repo"]:
        raise AppError("Origin is not a GitHub repository remote.", "GITHUB_REPOSITORY_INVALID")

    url = f"https://github.com/{remote['owner']}/{remote['repo']}"
    webbrowser.open(url, new=2)
    return {"url": url}


# Opens a GitHub URL in the default browser after validating the target host and scheme.
def open_github_url(url_value: str) -> dict[str, str]:
    """Open an HTTPS github.com URL in the default browser."""

    url = str(url_value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise AppError("GitDesk can only open HTTPS GitHub links.", "GITHUB_URL_INVALID")

    webbrowser.open(url, new=2)
    return {"url": url}


# Opens an app-provided website in the default browser without allowing executable or credential-bearing URL forms.
def open_external_url(url_value: str) -> dict[str, str]:
    """Open a validated HTTP(S) URL in the user's default browser."""

    url = str(url_value or "").strip()
    try:
        parsed = urlparse(url)
        parsed.port
    except ValueError as error:
        raise AppError("GitDesk can only open valid HTTP or HTTPS website links.", "EXTERNAL_URL_INVALID") from error
    invalid_target = (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or any(character.isspace() for character in url)
    )
    if invalid_target:
        raise AppError("GitDesk can only open valid HTTP or HTTPS website links.", "EXTERNAL_URL_INVALID")
    if not webbrowser.open(url, new=2):
        raise AppError("The default browser could not open the published site.", "BROWSER_OPEN_FAILED")
    return {"url": url}
