"""Regression coverage for reusing authorized Keychain PATs during one GitDesk process."""

from __future__ import annotations

# Standard-library unittest keeps the credential regression isolated from the real macOS Keychain.
import unittest

# Third-party keyring errors reproduce the missing-credential deletion contract.
from keyring.errors import PasswordDeleteError

# GitDesk boundaries under test reproduce bootstrap account recovery and PAT presence checks.
from gitdesk.credential_profiles import AccountBridgeMixin
from gitdesk.errors import AppError
from gitdesk.secrets import TOKEN_SERVICE_NAME, TokenStore


# CountingMemoryKeyring records every credential read without accessing an operating-system keyring.
class CountingMemoryKeyring:
    """Keep PATs in memory and expose the exact number of backend reads."""

    # Starts with isolated credentials and no recorded Keychain-style reads.
    def __init__(self) -> None:
        self.credentials: dict[tuple[str, str], str] = {}
        self.get_calls: list[tuple[str, str]] = []

    # Records and returns one credential using keyring's public read contract.
    def get_password(self, service: str, account: str) -> str | None:
        """Return an in-memory credential while recording the requested item."""

        self.get_calls.append((service, account))
        return self.credentials.get((service, account))

    # Stores one credential using keyring's public write contract.
    def set_password(self, service: str, account: str, password: str) -> None:
        """Save an in-memory credential for one exact service and account."""

        self.credentials[(service, account)] = password

    # Deletes one credential or reports that it is already absent.
    def delete_password(self, service: str, account: str) -> None:
        """Remove an in-memory credential using keyring's missing-item behavior."""

        credential_key = (service, account)
        if credential_key not in self.credentials:
            raise PasswordDeleteError("Credential is not present.")
        self.credentials.pop(credential_key)


# EmptyLegacyVault prevents regression tests from reading obsolete on-disk secret files.
class EmptyLegacyVault:
    """Represent a completed legacy migration with no PATs to move."""

    # Returns no legacy PATs so only current Keychain behavior is exercised.
    def decrypted_tokens(self) -> dict[str, str]:
        """Return an empty legacy credential mapping."""

        return {}

    # Matches migration cleanup without changing the filesystem.
    def remove(self) -> None:
        """Complete the no-op legacy cleanup step."""


# MemorySettingsStore provides the metadata contract needed by bootstrap account recovery.
class MemorySettingsStore:
    """Keep non-secret account metadata in memory for auth-state regression coverage."""

    # Copies the caller's settings so later updates remain isolated within the test.
    def __init__(self, settings: dict[str, object]) -> None:
        self.settings = dict(settings)

    # Returns a copy matching the production settings-store read boundary.
    def load(self) -> dict[str, object]:
        """Return current non-secret settings without exposing the retained mapping."""

        return dict(self.settings)

    # Merges the selected metadata update like the production settings store.
    def save(self, updates: dict[str, object]) -> dict[str, object]:
        """Persist non-secret settings updates in memory and return the result."""

        self.settings.update(updates)
        return dict(self.settings)


# CredentialControllerDouble supplies the stores used by production auth-state recovery.
class CredentialControllerDouble(AccountBridgeMixin):
    """Exercise auth-state PAT checks without constructing the desktop bridge."""

    # Injects only the settings and token stores required by AccountBridgeMixin.
    def __init__(self, settings_store: MemorySettingsStore, token_store: TokenStore) -> None:
        self.settings_store = settings_store
        self.token_store = token_store


# KeychainSessionTests protects lazy selected-PAT access and the volatile cache from prompt-loop regressions.
class KeychainSessionTests(unittest.TestCase):
    """Verify startup does not probe Keychain and selected PAT reads occur once per process session."""

    # Prevents bootstrap metadata rendering from opening a Keychain authorization prompt before a PAT is needed.
    def test_auth_state_defers_keychain_read_until_selected_pat_use(self) -> None:
        """Render configured profile state without reading Keychain, then cache the first selected PAT read."""

        keyring_backend = CountingMemoryKeyring()
        keyring_backend.set_password(TOKEN_SERVICE_NAME, "github-token:octocat", "test-token")
        token_store = TokenStore(keyring_module=keyring_backend, legacy_vault=EmptyLegacyVault())
        settings_store = MemorySettingsStore({
            "active_account": "octocat",
            "github_accounts": [{"login": "octocat", "authenticated_login": "octocat"}],
        })
        controller = CredentialControllerDouble(settings_store, token_store)

        auth = controller.auth_state()

        self.assertTrue(auth["accounts"][0]["token_present"])
        self.assertEqual(keyring_backend.get_calls, [])

        account = controller.account_from_payload({"account_login": "octocat"}, required=True)
        self.assertEqual(controller.token_for_account(account), "test-token")
        self.assertEqual(controller.token_for_account(account), "test-token")
        self.assertEqual(keyring_backend.get_calls, [(TOKEN_SERVICE_NAME, "github-token:octocat")])

    # Reproduces the user's three-PAT update case and requires bootstrap to leave every Keychain item unopened.
    def test_auth_state_does_not_probe_multiple_configured_pat_profiles(self) -> None:
        """Return three configured profiles without issuing a credential backend read for any profile."""

        keyring_backend = CountingMemoryKeyring()
        accounts = []
        for login in ("xander-haj", "xandland", "matrixguides"):
            keyring_backend.set_password(TOKEN_SERVICE_NAME, f"github-token:{login}", f"token-{login}")
            accounts.append({"login": login, "authenticated_login": "xander-haj"})
        token_store = TokenStore(keyring_module=keyring_backend, legacy_vault=EmptyLegacyVault())
        settings_store = MemorySettingsStore({
            "active_account": "xander-haj",
            "github_accounts": accounts,
        })
        controller = CredentialControllerDouble(settings_store, token_store)

        auth = controller.auth_state()

        self.assertEqual([account["login"] for account in auth["accounts"]], [
            "xander-haj",
            "xandland",
            "matrixguides",
        ])
        self.assertTrue(all(account["token_present"] for account in auth["accounts"]))
        self.assertEqual(keyring_backend.get_calls, [])

    # Makes a known-expired profile visible while preventing it from opening or returning a Keychain item.
    def test_expired_pat_status_rejects_before_keychain_read(self) -> None:
        """Expose expiration metadata and raise GITHUB_TOKEN_EXPIRED without reading the saved PAT."""

        keyring_backend = CountingMemoryKeyring()
        keyring_backend.set_password(TOKEN_SERVICE_NAME, "github-token:octocat", "expired-test-token")
        token_store = TokenStore(keyring_module=keyring_backend, legacy_vault=EmptyLegacyVault())
        settings_store = MemorySettingsStore({
            "active_account": "octocat",
            "github_accounts": [{
                "login": "octocat",
                "authenticated_login": "octocat",
                "token_expires_at": "2020-01-01T00:00:00Z",
            }],
        })
        controller = CredentialControllerDouble(settings_store, token_store)

        auth = controller.auth_state()
        account = controller.account_from_payload({"account_login": "octocat"}, required=True)
        with self.assertRaises(AppError) as context:
            controller.token_for_account(account)

        self.assertTrue(auth["accounts"][0]["token_present"])
        self.assertTrue(auth["accounts"][0]["token_expired"])
        self.assertEqual(context.exception.code, "GITHUB_TOKEN_EXPIRED")
        self.assertEqual(keyring_backend.get_calls, [])

    # Keeps a successful removal authoritative without reading the deleted Keychain item again for refreshed UI state.
    def test_account_removal_marks_profile_unconfigured_without_keychain_read(self) -> None:
        """Delete one PAT and return removed profile state without a follow-up credential probe."""

        keyring_backend = CountingMemoryKeyring()
        keyring_backend.set_password(TOKEN_SERVICE_NAME, "github-token:octocat", "test-token")
        token_store = TokenStore(keyring_module=keyring_backend, legacy_vault=EmptyLegacyVault())
        settings_store = MemorySettingsStore({
            "active_account": "octocat",
            "github_accounts": [{"login": "octocat", "authenticated_login": "octocat"}],
        })
        controller = CredentialControllerDouble(settings_store, token_store)

        result = controller.handle_clear_account({"account_login": "octocat"})

        self.assertFalse(result["auth"]["accounts"][0]["token_present"])
        self.assertFalse(settings_store.settings["github_accounts"][0]["credential_configured"])
        self.assertEqual(keyring_backend.get_calls, [])

    # Prevents an externally deleted credential from being requested again after its first factual missing result.
    def test_missing_selected_pat_corrects_metadata_after_one_keychain_read(self) -> None:
        """Mark one configured profile signed out when its selected Keychain item is actually absent."""

        keyring_backend = CountingMemoryKeyring()
        token_store = TokenStore(keyring_module=keyring_backend, legacy_vault=EmptyLegacyVault())
        settings_store = MemorySettingsStore({
            "active_account": "octocat",
            "github_accounts": [{"login": "octocat", "authenticated_login": "octocat"}],
        })
        controller = CredentialControllerDouble(settings_store, token_store)

        account = controller.account_from_payload({"account_login": "octocat"}, required=True)
        with self.assertRaises(AppError) as context:
            controller.token_for_account(account)

        self.assertEqual(context.exception.code, "TOKEN_MISSING")
        self.assertFalse(settings_store.settings["github_accounts"][0]["credential_configured"])
        self.assertEqual(keyring_backend.get_calls, [(TOKEN_SERVICE_NAME, "github-token:octocat")])
        with self.assertRaises(AppError) as second_context:
            controller.account_from_payload({"account_login": "octocat"}, required=True)
        self.assertEqual(second_context.exception.code, "TOKEN_MISSING")
        self.assertEqual(keyring_backend.get_calls, [(TOKEN_SERVICE_NAME, "github-token:octocat")])

    # Confirms cache updates never replace Keychain as the authoritative persistent store.
    def test_session_cache_tracks_keychain_save_and_clear(self) -> None:
        """Update and remove volatile PAT state only after matching keyring operations."""

        keyring_backend = CountingMemoryKeyring()
        store = TokenStore(keyring_module=keyring_backend, legacy_vault=EmptyLegacyVault())

        store.save_token("octocat", "test-token")
        self.assertEqual(store.get_token("octocat"), "test-token")
        self.assertEqual(keyring_backend.get_calls, [])

        store.clear_token("octocat")
        self.assertFalse(store.has_token("octocat"))
        self.assertEqual(keyring_backend.get_calls, [(TOKEN_SERVICE_NAME, "github-token:octocat")])


# Allows direct unittest discovery while keeping production imports side-effect free.
if __name__ == "__main__":
    unittest.main()
