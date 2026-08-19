"""Restore non-secret GitHub account metadata from saved token records."""

from __future__ import annotations

from typing import Any

from gitdesk.accounts import account_credential_configured, clean_account_metadata, clean_login, merge_account
from gitdesk.config import SettingsStore
from gitdesk.errors import AppError
from gitdesk.secrets import TokenStore


# Builds configured candidates from LocalApp metadata plus identities discovered during one-time vault migration.
def saved_token_logins(
    settings: dict[str, Any],
    token_store: TokenStore,
    migrated_logins: list[str] | None = None,
) -> list[str]:
    """Return logins expected to have PATs without reading any operating-system credential item."""

    candidates = []
    candidate_keys = set()
    migrated_logins = token_store.saved_logins() if migrated_logins is None else migrated_logins
    account_by_login = {
        account["login"].lower(): account
        for account in settings.get("github_accounts", [])
    }
    ordered_logins = [settings.get("active_account"), *migrated_logins]
    ordered_logins.extend(
        account["login"]
        for account in settings.get("github_accounts", [])
        if account_credential_configured(account)
    )
    for raw_login in ordered_logins:
        try:
            login = clean_login(str(raw_login or ""))
        except AppError:
            continue
        account = account_by_login.get(login.lower())
        is_migrated = any(login.lower() == migrated.lower() for migrated in migrated_logins)
        login_key = login.lower()
        if login_key not in candidate_keys and (is_migrated or (account and account_credential_configured(account))):
            candidates.append(login)
            candidate_keys.add(login_key)
    return candidates


# Finds the preferred saved-token account while preserving deterministic login order.
def token_backed_account(
    settings: dict[str, Any],
    token_store: TokenStore,
    preferred_login: str = "",
) -> dict[str, Any] | None:
    """Return account metadata for a login marked as having a saved PAT."""

    account_by_login = {account["login"].lower(): account for account in settings.get("github_accounts", [])}
    saved_logins = saved_token_logins(settings, token_store)
    candidates = []
    preferred_key = preferred_login.lower()
    saved_keys = {login.lower() for login in saved_logins}
    if preferred_key in account_by_login and preferred_key in saved_keys:
        candidates.append(preferred_login)
    candidate_keys = {candidate.lower() for candidate in candidates}
    candidates.extend(
        login
        for login in saved_logins
        if login.lower() in account_by_login and login.lower() not in candidate_keys
    )

    return account_by_login.get(candidates[0].lower()) if candidates else None


# Rebuilds metadata for identities recovered while obsolete local-vault PATs migrate into the OS keyring.
def settings_with_token_accounts(settings_store: SettingsStore, token_store: TokenStore) -> dict[str, Any]:
    """Return settings with any newly migrated GitHub account identities restored."""

    settings = settings_store.load()
    accounts = list(settings["github_accounts"])
    active_login = str(settings.get("active_account") or "")
    migrated_logins = token_store.saved_logins()
    migrated_keys = {login.lower() for login in migrated_logins}
    saved_logins = saved_token_logins(settings, token_store, migrated_logins)
    account_logins = {account["login"].lower() for account in accounts}
    changed = False

    for login in saved_logins:
        login_key = login.lower()
        existing = next((account for account in accounts if account["login"].lower() == login_key), None)
        if existing:
            if login_key in migrated_keys and not account_credential_configured(existing):
                accounts = merge_account(accounts, {**existing, "credential_configured": True})
                changed = True
            continue
        account = clean_account_metadata({"login": login})
        if not account:
            continue
        accounts = merge_account(accounts, account)
        account_logins.add(login_key)
        changed = True

    saved_login_keys = {login.lower() for login in saved_logins}
    token_login = next((login for login in saved_logins if login.lower() in account_logins), "")
    if token_login and active_login.lower() not in saved_login_keys:
        active_login = token_login
        changed = True
    elif active_login and active_login.lower() not in saved_login_keys:
        active_login = ""
        changed = True
    elif not accounts and active_login:
        active_login = ""
        changed = True

    if changed:
        return settings_store.save({"github_accounts": accounts, "active_account": active_login})
    return settings
