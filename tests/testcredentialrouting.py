"""Regression coverage for repository-origin PAT profile routing."""

from __future__ import annotations

import unittest

from gitdesk.credential_profiles import AccountBridgeMixin


# MemorySettingsStore preserves one complete non-secret settings snapshot for routing tests.
class MemorySettingsStore:
    """Provide the SettingsStore load/save contract without filesystem access."""

    def __init__(self, settings: dict[str, object]) -> None:
        """Retain a caller-owned settings snapshot."""

        self.settings = dict(settings)

    def load(self) -> dict[str, object]:
        """Return an isolated settings snapshot."""

        return dict(self.settings)

    def save(self, updates: dict[str, object]) -> dict[str, object]:
        """Merge non-secret settings updates."""

        self.settings.update(updates)
        return dict(self.settings)


# TokenStoreDouble exposes only token presence needed by profile selection.
class TokenStoreDouble:
    """Represent saved owner-keyed PATs without storing real credentials."""

    def __init__(self, logins: set[str]) -> None:
        """Record the resource-owner profiles that have PATs."""

        self.logins = set(logins)

    def saved_logins(self) -> list[str]:
        """Return no migration-only identities."""

        return []

    def has_token(self, login: str) -> bool:
        """Return whether one owner profile has a saved PAT."""

        return login in self.logins

    def get_token(self, login: str) -> str:
        """Return a deterministic marker for the requested existing Keychain entry."""

        return f"token-{login}" if self.has_token(login) else ""


# GitServiceDouble returns the current origin identity for the selected local repository.
class GitServiceDouble:
    """Expose a live repository summary independently from stale settings metadata."""

    def __init__(self, owner: str) -> None:
        """Set the GitHub owner parsed from the current origin."""

        self.owner = owner
        self.paths: list[str] = []

    def repository_summary(self, path: str) -> dict[str, str]:
        """Return the current origin owner and record the inspected path."""

        self.paths.append(path)
        return {"path": path, "github_owner": self.owner, "github_repo": "gd-beta"}


# CredentialControllerDouble supplies AccountBridgeMixin's three production dependencies.
class CredentialControllerDouble(AccountBridgeMixin):
    """Exercise live-origin credential selection without constructing the desktop bridge."""

    def __init__(
        self,
        settings: dict[str, object],
        origin_owner: str,
        token_logins: set[str] | None = None,
    ) -> None:
        """Create isolated settings, token, and Git service doubles."""

        self.settings_store = MemorySettingsStore(settings)
        saved_logins = {"xander-haj", "xandland"} if token_logins is None else token_logins
        self.token_store = TokenStoreDouble(saved_logins)
        self.git_service = GitServiceDouble(origin_owner)


# CredentialRoutingTests protects the selected-repository-to-PAT boundary used by Git operations.
class CredentialRoutingTests(unittest.TestCase):
    """Verify current origin ownership wins over cached managed-repository metadata."""

    def test_live_xander_haj_origin_overrides_stale_xandland_record(self) -> None:
        """Route xander-haj/gd-beta through the xander-haj profile selected in the dropdown."""

        path = "/repos/gd-beta"
        controller = CredentialControllerDouble({
            "active_account": "xander-haj",
            "github_accounts": [
                {"login": "xander-haj", "authenticated_login": "xander-haj"},
                {"login": "xandland", "authenticated_login": "xander-haj"},
            ],
            "managed_repositories": {
                "xandland": [{"path": path, "owner": "xandland", "repo": "gd-beta"}],
                "xander-haj": [{"path": path, "owner": "xandland", "repo": "gd-beta"}],
            },
            "github_owner": "xandland",
        }, "xander-haj")

        login = controller.optional_auth_login({"path": path, "account_login": "xander-haj"})

        self.assertEqual(login, "xander-haj")
        self.assertEqual(controller.git_service.paths, [path])

    def test_github_client_uses_selected_repository_payload_keychain_profile(self) -> None:
        """Build the API client from the same xander-haj path requested by Commit History."""

        path = "/repos/gd-beta"
        controller = CredentialControllerDouble({
            "active_account": "xandland",
            "github_accounts": [
                {
                    "login": "xander-haj",
                    "authenticated_login": "xander-haj",
                },
                {"login": "xandland", "authenticated_login": "xander-haj"},
            ],
            "repository_path": "/repos/other",
            "github_owner": "xandland",
        }, "xander-haj")

        client = controller.github_client({"path": path, "account_login": "xander-haj"})

        self.assertEqual(client.session.headers["Authorization"], "Bearer token-xander-haj")
        self.assertEqual(controller.git_service.paths, [path])

    def test_explicit_account_never_falls_through_to_another_saved_pat(self) -> None:
        """Keep an explicit xander-haj request from silently becoming the xandland profile."""

        controller = CredentialControllerDouble({
            "active_account": "xandland",
            "github_accounts": [
                {
                    "login": "xander-haj",
                    "authenticated_login": "xander-haj",
                    "credential_configured": False,
                },
                {"login": "xandland", "authenticated_login": "xander-haj"},
            ],
        }, "xander-haj", {"xandland"})

        account = controller.account_from_payload({"account_login": "xander-haj"}, required=False)

        self.assertIsNone(account)
        self.assertEqual(controller.settings_store.settings["active_account"], "xandland")


if __name__ == "__main__":
    unittest.main()
