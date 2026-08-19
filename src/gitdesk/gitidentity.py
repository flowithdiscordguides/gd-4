"""Git author identity helpers for account-aware commits."""

from __future__ import annotations

import os
from typing import Any

from git import Actor, Repo


# Converts non-secret account metadata into the GitPython author object used for commits.
def actor_from_account(account: dict[str, Any] | None) -> Actor | None:
    """Return a Git Actor for an account, or None when no complete identity is available."""

    if not account:
        return None

    name = str(account.get("name") or account.get("login") or "").strip()
    email = str(account.get("email") or "").strip()
    if not name or not email:
        return None
    return Actor(name, email)


# Supplies Git's native commit process with the same selected-profile identity used by GitPython commits.
def git_commit_environment(account: dict[str, Any] | None) -> dict[str, str]:
    """Return a process environment containing explicit author and committer identity when available."""

    environment = dict(os.environ)
    actor = actor_from_account(account)
    if actor is None:
        return environment
    environment.update({
        "GIT_AUTHOR_NAME": actor.name,
        "GIT_AUTHOR_EMAIL": actor.email,
        "GIT_COMMITTER_NAME": actor.name,
        "GIT_COMMITTER_EMAIL": actor.email,
    })
    return environment


# Writes the selected account identity into the repository-local Git config for consistency.
def configure_repository_identity(repo: Repo, account: dict[str, Any] | None) -> None:
    """Set repository-local user.name and user.email when a signed-in account is selected."""

    actor = actor_from_account(account)
    if actor is None:
        return

    with repo.config_writer() as config:
        config.set_value("user", "name", actor.name)
        config.set_value("user", "email", actor.email)
