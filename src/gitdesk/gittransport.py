"""Cross-platform bounded Git transport commands for the synchronous desktop bridge."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from git import Git, GitCommandError, Repo

from gitdesk.errors import AppError
from gitdesk.giterrors import git_error_details, git_failure_message


GIT_PUSH_TIMEOUT_SECONDS = 105


def push_git_command(repo: Repo, remote: str, refspec: str, environment: dict[str, str]) -> str:
    """Run one push with a backend deadline that settles before the WebView request timeout."""

    working_tree = Path(str(repo.working_tree_dir or "")).resolve()
    command = [Git.GIT_PYTHON_GIT_EXECUTABLE, "push", "--progress", remote, refspec]
    try:
        result = subprocess.run(
            command,
            cwd=str(working_tree),
            env=environment,
            capture_output=True,
            text=True,
            timeout=GIT_PUSH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AppError(
            "Git push stopped after 105 seconds without completing. The local commit is safe. Refresh before retrying "
            "because the remote may have received the update before the connection stopped.",
            "GIT_PUSH_TIMEOUT",
            {"timeout_seconds": GIT_PUSH_TIMEOUT_SECONDS, "remote_state": "unknown"},
        ) from error
    if result.returncode:
        error = GitCommandError(command, result.returncode, stderr=result.stderr, stdout=result.stdout)
        message = git_failure_message("Git could not push the active branch.", error)
        raise AppError(message, "GIT_PUSH_FAILED", git_error_details(error)) from error
    return (result.stderr or result.stdout or "").strip()
