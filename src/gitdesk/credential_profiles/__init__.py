"""Resource-owner PAT profiles, repository reassignment, and bridge authentication routing."""

from __future__ import annotations

from typing import Any

from gitdesk.accounts import account_credential_configured, account_profile_from_user
from gitdesk.accounts import clean_login, find_account, merge_account
from gitdesk.authrecovery import settings_with_token_accounts, token_backed_account
from gitdesk.errors import AppError
from gitdesk.githubapi import GitHubApiClient
from gitdesk.managedrepos import account_context_settings_update, clean_active_repository_map
from gitdesk.managedrepos import clean_repository_map
from gitdesk.patstatus import token_expiration_has_passed
from gitdesk.syncchains import clean_sync_chains


# Reads the current GitHub identity from the selected repository instead of trusting cached registry metadata.
def repository_pair_from_origin(git_service: Any, path: str) -> tuple[str, str]:
    """Return the owner and repository parsed from the selected repository's live GitHub origin."""

    summary = git_service.repository_summary(path)
    owner = str(summary.get("github_owner") or "").strip()
    repo = str(summary.get("github_repo") or "").strip()
    return owner, repo


# Updates Sync Chain stage ownership after repository records move to a newly saved owner profile.
def reassigned_sync_chains(
    settings: dict[str, Any],
    resource_owner: str,
    moved_paths: dict[str, str],
) -> list[dict[str, Any]]:
    """Return chains whose moved repository stages reference the matching resource-owner profile."""

    chains = clean_sync_chains(settings.get("sync_chains"))
    updated_chains = []
    for chain in chains:
        stages = {}
        for stage_name, stage in chain["stages"].items():
            source_profile = moved_paths.get(stage["repository_path"])
            # Only stages that referenced the old owning bucket should move with their exact repository record.
            if source_profile and str(stage.get("account_login") or "").lower() == source_profile.lower():
                stages[stage_name] = {**stage, "account_login": resource_owner}
            else:
                stages[stage_name] = stage
        updated_chains.append({**chain, "stages": stages})
    return clean_sync_chains(updated_chains)


# Moves repositories owned by a saved resource owner out of an older authenticated-user bucket.
def resource_owner_registry_update(settings: dict[str, Any], owner_value: str) -> dict[str, Any]:
    """Return registry updates assigning exact-owner repositories and chain stages to one PAT profile."""

    resource_owner = clean_login(owner_value)
    owner_key = resource_owner.lower()
    repositories = clean_repository_map(settings.get("managed_repositories"))
    active_paths = clean_active_repository_map(settings.get("active_repository_by_account"), repositories)
    destination_profile = next((login for login in repositories if login.lower() == owner_key), resource_owner)
    destination_records = list(repositories.get(destination_profile, []))
    if destination_profile != resource_owner:
        repositories.pop(destination_profile, None)
        destination_active = active_paths.pop(destination_profile, "")
        if destination_active:
            active_paths[resource_owner] = destination_active
    destination_paths = {record["path"] for record in destination_records}
    moved_paths: dict[str, str] = {}

    for profile_login in list(repositories):
        if profile_login.lower() == owner_key:
            continue
        retained_records = []
        for record in repositories[profile_login]:
            # Remote ownership is the factual boundary for moving a record into its exact PAT profile.
            if str(record.get("owner") or "").lower() == owner_key:
                moved_paths[record["path"]] = profile_login
                if record["path"] not in destination_paths:
                    destination_records.append(record)
                    destination_paths.add(record["path"])
            else:
                retained_records.append(record)
        if retained_records:
            repositories[profile_login] = retained_records
        else:
            repositories.pop(profile_login, None)

    if destination_records:
        repositories[resource_owner] = sorted(destination_records, key=lambda item: item["full_name"].lower())

    for profile_login, active_path in list(active_paths.items()):
        # A moved active path cannot remain selected under the profile bucket that no longer owns its record.
        if moved_paths.get(active_path, "").lower() == profile_login.lower():
            active_paths.pop(profile_login, None)
    if resource_owner not in active_paths and moved_paths:
        preferred_path = str(settings.get("repository_path") or "")
        active_paths[resource_owner] = preferred_path if preferred_path in moved_paths else sorted(moved_paths)[0]
    active_paths = clean_active_repository_map(active_paths, repositories)
    return {
        "managed_repositories": repositories,
        "active_repository_by_account": active_paths,
        "sync_chains": reassigned_sync_chains(settings, resource_owner, moved_paths),
    }


# AccountBridgeMixin keeps credential-profile orchestration out of the central native bridge controller.
class AccountBridgeMixin:
    """Provide PAT profile save/select/remove, owner routing, auth state, and secure token retrieval."""

    # Stores a validated PAT under its explicit personal or organization resource owner.
    def handle_save_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Save one resource-owner PAT profile without collapsing tokens from the same authenticated human."""

        token = str(payload.get("token") or "").strip()
        if not token:
            raise AppError("A GitHub token is required.", "TOKEN_EMPTY")
        owner_value = str(payload.get("resource_owner") or "").strip()
        if not owner_value:
            raise AppError("The PAT resource owner is required.", "PAT_RESOURCE_OWNER_REQUIRED")

        client = GitHubApiClient(token)
        account = account_profile_from_user(client.current_user(), client.resource_owner(owner_value))
        account["token_expires_at"] = client.token_expires_at
        self.token_store.save_token(account["login"], token)
        settings = settings_with_token_accounts(self.settings_store, self.token_store)
        registry_updates = resource_owner_registry_update(settings, account["login"])
        accounts = merge_account(settings["github_accounts"], account)
        working_settings = {
            **settings,
            **registry_updates,
            "github_accounts": accounts,
            "active_account": account["login"],
        }
        updates = {
            **registry_updates,
            "github_accounts": accounts,
            "active_account": account["login"],
            **account_context_settings_update(working_settings, account["login"]),
        }
        saved_settings = self.settings_store.save(updates)
        return {"auth": self.auth_state(saved_settings), "user": account, "settings": saved_settings}

    # Removes only the selected resource-owner credential while preserving repository metadata for later sign-in.
    def handle_clear_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Clear one PAT profile without deleting its managed repository or Sync Chain records."""

        account = self.account_from_payload(payload, required=True)
        self.token_store.clear_token(account["login"])
        settings = self.settings_store.load()
        removed_account = {**account, "credential_configured": False, "token_expires_at": ""}
        accounts = merge_account(settings["github_accounts"], removed_account)
        updates = {"github_accounts": accounts, "active_account": account["login"]}
        updates.update(account_context_settings_update(settings, account["login"]))
        saved_settings = self.settings_store.save(updates)
        return {"auth": self.auth_state(), "settings": saved_settings}

    # Switches the active profile used when no repository owner supplies a more exact credential match.
    def handle_select_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Select one signed-in resource-owner PAT profile and restore its active repository context."""

        login = clean_login(str(payload.get("login") or ""))
        account = self.account_from_payload({"account_login": login}, required=True)
        settings = settings_with_token_accounts(self.settings_store, self.token_store)
        updates = {"active_account": account["login"]}
        updates.update(account_context_settings_update(settings, account["login"]))
        saved_settings = self.settings_store.save(updates)
        return {"auth": self.auth_state(), "settings": saved_settings}

    # Prefers an exact resource-owner profile and permits only classic PATs to cross owner boundaries.
    def account_for_owner(
        self,
        owner_value: str,
        payload: dict[str, Any],
        required: bool,
    ) -> dict[str, str] | None:
        """Return the token profile matching owner, with a classic-PAT fallback when one is selected."""

        settings = settings_with_token_accounts(self.settings_store, self.token_store)
        owner = str(owner_value or "").strip()
        if owner:
            exact = find_account(settings["github_accounts"], owner)
            if exact and account_credential_configured(exact):
                if required:
                    self.raise_for_expired_token(exact)
                return exact
        selected = self.account_from_payload(payload, required)
        if selected and required:
            self.raise_for_expired_token(selected)
        if not owner or not selected:
            return selected
        # Classic PATs can legitimately authorize repositories across owners; fine-grained PATs cannot.
        if not self.token_for_account(selected).startswith("github_pat_"):
            return selected
        if required:
            raise AppError(
                f"Save the PAT whose Resource owner is {owner} before accessing {owner} repositories.",
                "PAT_RESOURCE_OWNER_PROFILE_REQUIRED",
                {"resource_owner": owner, "selected_profile": selected["login"]},
            )
        return None

    # Resolves the factual remote owner for a local repository before choosing its Git/API credential.
    def account_for_repository(
        self,
        payload: dict[str, Any],
        required: bool,
    ) -> dict[str, str] | None:
        """Return the exact-owner PAT profile for a managed repository, with active-profile fallback."""

        settings = self.settings_store.load()
        requested_path = str(payload.get("path") or "").strip()
        path = requested_path or str(settings.get("repository_path") or "").strip()
        owner = repository_pair_from_origin(self.git_service, requested_path)[0] if requested_path else ""
        owner = owner or str(payload.get("owner") or "").strip()
        owner = owner or (repository_pair_from_origin(self.git_service, path)[0] if path else "")
        owner = owner or str(settings.get("github_owner") or "").strip()
        return self.account_for_owner(owner, payload, required)

    # Creates an API client with the profile that owns the currently selected repository.
    def github_client(self, payload: dict[str, Any]) -> GitHubApiClient:
        """Return a GitHub API client using the selected repository owner's saved PAT profile."""

        return GitHubApiClient(self.token_for_account(self.account_for_repository(payload, required=True)))

    # Returns a profile key for askpass so Git retrieves the exact resource-owner credential from Keychain.
    def optional_auth_login(self, payload: dict[str, Any]) -> str | None:
        """Return the repository owner's token-backed profile key, or None when no saved credential exists."""

        account = self.account_for_repository(payload, required=False)
        self.raise_for_expired_token(account)
        return account["login"] if account and account_credential_configured(account) else None

    # Returns frontend-safe PAT profile state while never exposing credential values.
    def auth_state(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return saved profile metadata, presence flags, and the active resource-owner key."""

        if settings is None:
            settings = settings_with_token_accounts(self.settings_store, self.token_store)
        accounts = []
        token_logins = []
        for account in settings["github_accounts"]:
            account_payload = dict(account)
            account_payload["token_present"] = account_credential_configured(account)
            account_payload["token_expired"] = (
                account_payload["token_present"]
                and token_expiration_has_passed(account.get("token_expires_at"))
            )
            if account_payload["token_present"]:
                token_logins.append(account["login"])
            accounts.append(account_payload)

        saved_active = str(settings.get("active_account") or "")
        active_login = ""
        if token_logins:
            active_login = saved_active if saved_active in token_logins else token_logins[0]
        if active_login != saved_active:
            self.settings_store.save({"active_account": active_login})
        return {"accounts": accounts, "active_account": active_login}

    # Honors an explicit PAT profile and retains compatibility fallback only when no profile was requested.
    def account_from_payload(self, payload: dict[str, Any], required: bool) -> dict[str, str] | None:
        """Return the exact requested profile or recover an unrequested legacy active profile."""

        settings = settings_with_token_accounts(self.settings_store, self.token_store)
        requested_login = str(payload.get("account_login") or "").strip()
        login = requested_login or str(settings.get("active_account") or "")
        account = None
        if login:
            account = find_account(settings["github_accounts"], login)
            if account and account_credential_configured(account):
                return account

        # An explicit dropdown/request selection must never mutate into another saved profile.
        if requested_login:
            if not account:
                raise AppError("The selected GitHub PAT profile is not signed in.", "ACCOUNT_NOT_FOUND")
            if required:
                raise AppError("No GitHub token is saved for the selected PAT profile.", "TOKEN_MISSING")
            return None

        fallback = token_backed_account(settings, self.token_store, login)
        if fallback:
            if fallback["login"] != settings.get("active_account"):
                self.settings_store.save({"active_account": fallback["login"]})
            return fallback
        if not login:
            if required:
                raise AppError("Select a signed-in GitHub PAT profile first.", "ACCOUNT_REQUIRED")
            return None
        if not account:
            raise AppError("The selected GitHub PAT profile is not signed in.", "ACCOUNT_NOT_FOUND")
        if required:
            raise AppError("No GitHub token is saved for the selected PAT profile.", "TOKEN_MISSING")
        return None

    # Retrieves one PAT from the OS keyring after non-secret metadata selects its resource-owner profile.
    def token_for_account(self, account: dict[str, str] | None) -> str:
        """Return the keyring PAT for one resource-owner profile, or raise when no profile is selected."""

        if not account:
            raise AppError("Select a signed-in GitHub PAT profile first.", "ACCOUNT_REQUIRED")
        self.raise_for_expired_token(account)
        try:
            return self.token_store.get_token(account["login"])
        except AppError as error:
            # A missing external Keychain item corrects metadata without misclassifying backend authorization errors.
            if error.code == "TOKEN_MISSING":
                settings = self.settings_store.load()
                saved_account = find_account(settings["github_accounts"], account["login"])
                if saved_account and account_credential_configured(saved_account):
                    removed_account = {
                        **saved_account,
                        "credential_configured": False,
                        "token_expires_at": "",
                    }
                    self.settings_store.save({
                        "github_accounts": merge_account(settings["github_accounts"], removed_account),
                    })
            raise

    # Rejects a known-expired PAT from non-secret metadata before any Keychain or network access occurs.
    def raise_for_expired_token(self, account: dict[str, str] | None) -> None:
        """Raise GITHUB_TOKEN_EXPIRED when the selected profile's recorded expiration has passed."""

        if not account or not token_expiration_has_passed(account.get("token_expires_at")):
            return
        expires_at = str(account.get("token_expires_at") or "")
        raise AppError(
            f"The GitHub PAT for {account['login']} expired on {expires_at[:10]}. Save a replacement PAT.",
            "GITHUB_TOKEN_EXPIRED",
            {"account_login": account["login"], "expires_at": expires_at},
        )
