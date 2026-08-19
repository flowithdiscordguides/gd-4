"""Non-secret GitHub account metadata helpers for multi-account auth."""

from __future__ import annotations

import re
from typing import Any

from gitdesk.errors import AppError
from gitdesk.patstatus import clean_token_expiration


# GitHub usernames become OS keyring account suffixes, so reject unsafe names before credential lookup.
LOGIN_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")

# GitHub resource owners are either personal accounts or organizations for fine-grained PAT profiles.
RESOURCE_OWNER_TYPES = {"User", "Organization"}


# Validates a GitHub login before it becomes a settings value or OS keyring account key.
def clean_login(login: str) -> str:
    """Return a normalized GitHub login or raise an AppError for unsafe values."""

    cleaned_login = str(login or "").strip()
    if not cleaned_login or not LOGIN_PATTERN.match(cleaned_login):
        raise AppError("A valid GitHub account login is required.", "ACCOUNT_LOGIN_INVALID")
    return cleaned_login


# Builds GitHub's private no-reply email shape when the API does not expose a public email.
def default_commit_email(user_id: Any, login: str) -> str:
    """Return a GitHub no-reply email suitable for commit attribution."""

    numeric_id = str(user_id or "").strip()
    return f"{numeric_id}+{login}@users.noreply.github.com" if numeric_id else f"{login}@users.noreply.github.com"


# Converts the authenticated GitHub user payload into non-secret app account metadata.
def account_from_user(user: dict[str, Any]) -> dict[str, str]:
    """Return non-secret account metadata derived from a validated GitHub token."""

    login = clean_login(str(user.get("login") or ""))
    account_id = str(user.get("id") or "").strip()
    display_name = str(user.get("name") or "").strip() or login
    email = str(user.get("email") or "").strip() or default_commit_email(account_id, login)
    return {
        "login": login,
        "authenticated_login": login,
        "resource_owner_type": "User",
        "name": display_name,
        "email": email,
        "html_url": str(user.get("html_url") or "").strip(),
        "id": account_id,
    }


# Combines the authenticated human with the distinct resource owner selected when the PAT was created.
def account_profile_from_user(
    user: dict[str, Any],
    resource_owner: dict[str, Any],
) -> dict[str, Any]:
    """Return one non-secret PAT profile keyed by its personal or organization resource owner."""

    authenticated = account_from_user(user)
    owner_login = clean_login(str(resource_owner.get("login") or ""))
    owner_type = str(resource_owner.get("type") or "").strip()
    if owner_type not in RESOURCE_OWNER_TYPES:
        raise AppError("GitHub returned an invalid PAT resource owner type.", "PAT_RESOURCE_OWNER_INVALID")
    # A user-owned PAT can only target the authenticated user; another user login cannot be a valid resource owner.
    if owner_type == "User" and owner_login.lower() != authenticated["login"].lower():
        raise AppError(
            "The PAT resource owner must be your GitHub account or an organization you selected on GitHub.",
            "PAT_RESOURCE_OWNER_MISMATCH",
        )
    return {
        **authenticated,
        "login": owner_login,
        "authenticated_login": authenticated["login"],
        "resource_owner_type": owner_type,
        "html_url": str(resource_owner.get("html_url") or "").strip(),
        "credential_configured": True,
    }


# Reads the non-secret credential-state marker without querying the operating-system credential store.
def account_credential_configured(account: dict[str, Any]) -> bool:
    """Return whether account metadata expects a saved PAT, defaulting older profile records to configured."""

    return account.get("credential_configured", True) is not False


# Sanitizes account metadata loaded from disk before it is returned to the frontend.
def clean_account_metadata(value: Any) -> dict[str, Any] | None:
    """Return a cleaned account metadata dictionary, or None when the value is invalid."""

    if not isinstance(value, dict):
        return None

    try:
        login = clean_login(str(value.get("login") or ""))
    except AppError:
        return None

    try:
        authenticated_login = clean_login(str(value.get("authenticated_login") or login))
    except AppError:
        return None
    owner_type = str(value.get("resource_owner_type") or "User").strip()
    if owner_type not in RESOURCE_OWNER_TYPES:
        return None
    account_id = str(value.get("id") or "").strip()
    name = str(value.get("name") or "").strip() or authenticated_login
    email = str(value.get("email") or "").strip() or default_commit_email(account_id, authenticated_login)
    return {
        "login": login,
        "authenticated_login": authenticated_login,
        "resource_owner_type": owner_type,
        "name": name,
        "email": email,
        "html_url": str(value.get("html_url") or f"https://github.com/{login}").strip(),
        "id": account_id,
        "credential_configured": account_credential_configured(value),
        "token_expires_at": clean_token_expiration(value.get("token_expires_at")),
    }


# Replaces an existing account entry with the same login while preserving other accounts.
def merge_account(accounts: list[dict[str, Any]], account: dict[str, Any]) -> list[dict[str, Any]]:
    """Return account metadata with the supplied account inserted once by login."""

    merged = [existing for existing in accounts if existing["login"].lower() != account["login"].lower()]
    merged.append(account)
    return sorted(merged, key=lambda item: item["login"].lower())


# Selects an account by login, or returns None when no matching signed-in account exists.
def find_account(accounts: list[dict[str, Any]], login: str) -> dict[str, Any] | None:
    """Return account metadata for a login without exposing any token value."""

    cleaned_login = clean_login(login)
    return next((account for account in accounts if account["login"].lower() == cleaned_login.lower()), None)
