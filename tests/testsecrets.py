"""Regression coverage for GitDesk's operating-system keyring PAT storage."""

from __future__ import annotations

# Standard-library fixtures keep all regression data isolated in memory or temporary directories.
import json
from pathlib import Path
import tempfile
import unittest

# Third-party APIs reproduce the production encryption and keyring error contracts without real credentials.
from cryptography.fernet import Fernet
from keyring.errors import KeyringError, PasswordDeleteError

# GitDesk classes under test provide the migration, structured errors, and credential boundary.
from gitdesk.accounts import account_profile_from_user
from gitdesk.credential_profiles import AccountBridgeMixin, resource_owner_registry_update
from gitdesk.errors import AppError
from gitdesk.legacysecrets import LegacyTokenVault
from gitdesk.secrets import TOKEN_SERVICE_NAME, TokenStore


# MemoryKeyring implements keyring's public password API without reading or writing real OS credentials.
class MemoryKeyring:
    """Keep test credentials in memory under exact service/account pairs."""

    # Starts every test double with an isolated credential mapping.
    def __init__(self) -> None:
        self.credentials: dict[tuple[str, str], str] = {}

    # Returns the stored password or None to match keyring's missing-credential contract.
    def get_password(self, service: str, account: str) -> str | None:
        """Return an in-memory credential for a service and account pair."""

        return self.credentials.get((service, account))

    # Replaces the credential for one exact service/account pair.
    def set_password(self, service: str, account: str, password: str) -> None:
        """Store an in-memory credential for a service and account pair."""

        self.credentials[(service, account)] = password

    # Matches keyring by raising PasswordDeleteError when no credential exists.
    def delete_password(self, service: str, account: str) -> None:
        """Delete an in-memory credential or report that it is already absent."""

        credential_key = (service, account)
        # Match keyring's documented missing-delete behavior so TokenStore's idempotence path is realistic.
        if credential_key not in self.credentials:
            raise PasswordDeleteError("Credential is not present.")
        self.credentials.pop(credential_key)


# FailingKeyring makes one selected backend operation fail with keyring's structured base exception.
class FailingKeyring(MemoryKeyring):
    """Raise a KeyringError for a configured credential operation."""

    # Stores which public keyring method should simulate an unavailable backend.
    def __init__(self, operation: str) -> None:
        super().__init__()
        self.operation = operation

    # Fails reads only when requested and otherwise delegates to the in-memory implementation.
    def get_password(self, service: str, account: str) -> str | None:
        """Return a credential unless this double is configured to fail reads."""

        # Only the selected operation fails so each structured error boundary is tested independently.
        if self.operation == "get":
            raise KeyringError("read failed")
        return super().get_password(service, account)

    # Fails writes only when requested and otherwise delegates to the in-memory implementation.
    def set_password(self, service: str, account: str, password: str) -> None:
        """Store a credential unless this double is configured to fail writes."""

        # Only the selected operation fails so migration cleanup ordering remains observable.
        if self.operation == "set":
            raise KeyringError("write failed")
        super().set_password(service, account, password)

    # Fails deletion only when requested and otherwise delegates to the in-memory implementation.
    def delete_password(self, service: str, account: str) -> None:
        """Delete a credential unless this double is configured to fail deletion."""

        # Only the selected operation fails so deletion errors are distinct from missing credentials.
        if self.operation == "delete":
            raise KeyringError("delete failed")
        super().delete_password(service, account)


# LegacyVaultDouble proves migration ordering without placing a PAT in a filesystem fixture.
class LegacyVaultDouble:
    """Expose configured legacy tokens and record whether cleanup occurred."""

    # Copies test data so migration cannot mutate the caller's fixture.
    def __init__(self, tokens: dict[str, str]) -> None:
        self.tokens = dict(tokens)
        self.removed = False

    # Returns all obsolete-vault PATs for migration into the injected keyring.
    def decrypted_tokens(self) -> dict[str, str]:
        """Return a copy of the configured legacy PAT mapping."""

        return dict(self.tokens)

    # Marks cleanup so tests can require it only after successful keyring writes.
    def remove(self) -> None:
        """Record that obsolete local secret files would be removed."""

        self.removed = True


# TokenStoreFailureDouble injects one structured retrieval result for presence checks.
class TokenStoreFailureDouble(TokenStore):
    """Raise a configured AppError from get_token without contacting a keyring."""

    # Stores the structured failure that presence detection should receive.
    def __init__(self, error: AppError) -> None:
        self.error = error

    # Raises the configured error so has_token can be checked in isolation.
    def get_token(self, login: str) -> str:
        """Raise the test's configured token retrieval error."""

        raise self.error


# MemorySettingsStore provides the load/save contract needed to exercise profile routing without filesystem access.
class MemorySettingsStore:
    """Keep a complete settings dictionary in memory for AccountBridgeMixin regression coverage."""

    # Starts the fake store from one complete caller-owned settings snapshot.
    def __init__(self, settings: dict[str, object]) -> None:
        self.settings = dict(settings)

    # Matches SettingsStore.load while preventing callers from mutating the retained fixture by reference.
    def load(self) -> dict[str, object]:
        """Return a copy of the current in-memory settings."""

        return dict(self.settings)

    # Matches SettingsStore.save by merging only the supplied update fields.
    def save(self, updates: dict[str, object]) -> dict[str, object]:
        """Merge settings updates and return a copy of the result."""

        self.settings.update(updates)
        return dict(self.settings)


# CredentialControllerDouble supplies only the stores required by the resource-owner routing mixin.
class CredentialControllerDouble(AccountBridgeMixin):
    """Exercise production credential selection without constructing the desktop bridge."""

    # Injects the minimal stores used by AccountBridgeMixin's selection paths.
    def __init__(self, settings_store: MemorySettingsStore, token_store: TokenStore) -> None:
        self.settings_store = settings_store
        self.token_store = token_store


# TokenStoreTests protects the PAT/keyring boundary, migration safety, and structured backend errors.
class TokenStoreTests(unittest.TestCase):
    """Verify system-keyring round trips without accessing a real operating-system credential store."""

    # Confirms PATs use the stable GitDesk service and a namespaced GitHub account key.
    def test_token_round_trip_uses_system_keyring_namespace(self) -> None:
        """Save and retrieve one PAT through an injected keyring implementation."""

        keyring_backend = MemoryKeyring()
        store = TokenStore(keyring_module=keyring_backend, legacy_vault=LegacyVaultDouble({}))
        store.save_token("octocat", "test-token")

        self.assertEqual(store.get_token("octocat"), "test-token")
        self.assertEqual(
            keyring_backend.credentials[(TOKEN_SERVICE_NAME, "github-token:octocat")],
            "test-token",
        )

    # Confirms one authenticated human can keep independent personal and organization resource-owner PATs.
    def test_resource_owner_profiles_do_not_overwrite_each_other(self) -> None:
        """Store personal and organization PATs under separate resource-owner keyring accounts."""

        keyring_backend = MemoryKeyring()
        store = TokenStore(keyring_module=keyring_backend, legacy_vault=LegacyVaultDouble({}))
        store.save_token("xander-haj", "personal-token")
        store.save_token("xandland", "organization-token")

        self.assertEqual(store.get_token("xander-haj"), "personal-token")
        self.assertEqual(store.get_token("xandland"), "organization-token")

    # Confirms a resource-owner profile preserves the authenticated human separately from the owner key.
    def test_organization_profile_keeps_authenticated_user_identity(self) -> None:
        """Build an xandland organization profile authenticated by the xander-haj GitHub user."""

        profile = account_profile_from_user(
            {"login": "xander-haj", "id": 42, "name": "Xander", "email": "xander@example.com"},
            {"login": "xandland", "type": "Organization", "html_url": "https://github.com/xandland"},
        )

        self.assertEqual(profile["login"], "xandland")
        self.assertEqual(profile["authenticated_login"], "xander-haj")
        self.assertEqual(profile["resource_owner_type"], "Organization")
        self.assertEqual(profile["email"], "xander@example.com")

    # Confirms another human account cannot be mislabeled as the authenticated user's personal resource owner.
    def test_different_user_cannot_be_saved_as_personal_resource_owner(self) -> None:
        """Reject a User resource owner that differs from the user returned by the PAT."""

        with self.assertRaises(AppError) as raised:
            account_profile_from_user(
                {"login": "xander-haj", "id": 42},
                {"login": "someone-else", "type": "User"},
            )
        self.assertEqual(raised.exception.code, "PAT_RESOURCE_OWNER_MISMATCH")

    # Confirms saving an organization profile repairs existing repository and Sync Chain ownership metadata.
    def test_resource_owner_profile_reassigns_existing_repositories_and_chain_stages(self) -> None:
        """Move xandland records out of xander-haj while preserving the personal repository record."""

        settings = {
            "repository_path": "/repos/xandland",
            "managed_repositories": {
                "xander-haj": [
                    {"path": "/repos/personal", "owner": "xander-haj", "repo": "personal"},
                    {"path": "/repos/xandland", "owner": "xandland", "repo": "organization"},
                ],
            },
            "active_repository_by_account": {"xander-haj": "/repos/xandland"},
            "sync_chains": [{
                "id": "chain-one",
                "project_path": "/projects/example",
                "stages": {
                    "private_beta": {
                        "account_login": "xander-haj",
                        "repository_path": "/repos/xandland",
                    },
                },
                "receipts": {},
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }],
        }

        updates = resource_owner_registry_update(settings, "xandland")

        self.assertEqual([item["path"] for item in updates["managed_repositories"]["xander-haj"]], [
            "/repos/personal",
        ])
        self.assertEqual(updates["managed_repositories"]["xandland"][0]["path"], "/repos/xandland")
        self.assertEqual(updates["active_repository_by_account"]["xandland"], "/repos/xandland")
        stage = updates["sync_chains"][0]["stages"]["private_beta"]
        self.assertEqual(stage["account_login"], "xandland")

    # Confirms a fine-grained personal PAT is never selected for a different organization repository.
    def test_fine_grained_pat_cannot_fall_through_to_wrong_resource_owner(self) -> None:
        """Require an xandland profile instead of routing xandland Git through the xander-haj PAT."""

        keyring_backend = MemoryKeyring()
        token_store = TokenStore(keyring_module=keyring_backend, legacy_vault=LegacyVaultDouble({}))
        token_store.save_token("xander-haj", "github_pat_personal")
        settings_store = MemorySettingsStore({
            "active_account": "xander-haj",
            "github_accounts": [{"login": "xander-haj", "authenticated_login": "xander-haj"}],
        })
        controller = CredentialControllerDouble(settings_store, token_store)

        with self.assertRaises(AppError) as raised:
            controller.account_for_owner("xandland", {}, required=True)

        self.assertEqual(raised.exception.code, "PAT_RESOURCE_OWNER_PROFILE_REQUIRED")
        self.assertEqual(raised.exception.details["resource_owner"], "xandland")

    # Confirms account removal deletes only the selected PAT and remains idempotent.
    def test_clear_token_deletes_selected_keyring_credential(self) -> None:
        """Delete a PAT from keyring and allow a repeated clear without failure."""

        keyring_backend = MemoryKeyring()
        store = TokenStore(keyring_module=keyring_backend, legacy_vault=LegacyVaultDouble({}))
        store.save_token("octocat", "test-token")
        store.clear_token("octocat")
        store.clear_token("octocat")

        self.assertFalse(store.has_token("octocat"))

    # Confirms a successful migration writes every PAT before allowing legacy cleanup.
    def test_legacy_tokens_migrate_before_cleanup(self) -> None:
        """Move all obsolete-vault PATs into keyring and return their logins for metadata recovery."""

        keyring_backend = MemoryKeyring()
        legacy_vault = LegacyVaultDouble({"octocat": "first-token", "hubot": "second-token"})
        store = TokenStore(keyring_module=keyring_backend, legacy_vault=legacy_vault)

        self.assertEqual(store.saved_logins(), ["hubot", "octocat"])
        self.assertTrue(legacy_vault.removed)
        self.assertEqual(store.get_token("hubot"), "second-token")
        self.assertEqual(store.get_token("octocat"), "first-token")

    # Confirms a failed keyring write leaves the obsolete source vault available for a later retry.
    def test_failed_migration_preserves_legacy_vault(self) -> None:
        """Propagate keyring write failure without deleting legacy PAT data."""

        legacy_vault = LegacyVaultDouble({"octocat": "test-token"})
        store = TokenStore(keyring_module=FailingKeyring("set"), legacy_vault=legacy_vault)

        with self.assertRaisesRegex(AppError, "Unable to save"):
            store.saved_logins()
        self.assertFalse(legacy_vault.removed)

    # Confirms normal account saves surface the credential backend rather than claiming GitHub rejected the PAT.
    def test_keyring_write_failure_has_storage_error_code(self) -> None:
        """Report TOKEN_KEYRING_WRITE_FAILED when the operating-system credential write fails."""

        store = TokenStore(keyring_module=FailingKeyring("set"), legacy_vault=LegacyVaultDouble({}))

        with self.assertRaises(AppError) as raised:
            store.save_token("octocat", "test-token")
        self.assertEqual(raised.exception.code, "TOKEN_KEYRING_WRITE_FAILED")

    # Confirms sign-out distinguishes an unavailable credential backend from an already-absent PAT.
    def test_keyring_delete_failure_has_storage_error_code(self) -> None:
        """Report TOKEN_KEYRING_DELETE_FAILED when the operating-system credential delete fails."""

        store = TokenStore(keyring_module=FailingKeyring("delete"), legacy_vault=LegacyVaultDouble({}))

        with self.assertRaises(AppError) as raised:
            store.clear_token("octocat")
        self.assertEqual(raised.exception.code, "TOKEN_KEYRING_DELETE_FAILED")

    # Confirms the actual regression vault format can be decrypted and removed after migration.
    def test_legacy_vault_reader_recovers_encrypted_pat(self) -> None:
        """Read a temporary legacy vault and remove both obsolete secret files."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            key = Fernet.generate_key()
            encrypted_token = Fernet(key).encrypt(b"test-token").decode("ascii")
            (root / "tokens.key").write_bytes(key + b"\n")
            (root / "tokens.vault.json").write_text(
                json.dumps({"version": 1, "tokens": {"github-token:octocat": encrypted_token}}),
                encoding="utf-8",
            )
            vault = LegacyTokenVault(root)

            self.assertEqual(vault.decrypted_tokens(), {"octocat": "test-token"})
            vault.remove()
            self.assertFalse((root / "tokens.vault.json").exists())
            self.assertFalse((root / "tokens.key").exists())

    # Confirms only genuine credential absence becomes a false presence result.
    def test_missing_token_returns_false(self) -> None:
        """Treat TOKEN_MISSING as an absent saved credential."""

        store = TokenStoreFailureDouble(AppError("missing", "TOKEN_MISSING"))
        self.assertFalse(store.has_token("octocat"))

    # Confirms an unavailable OS keyring is surfaced rather than becoming a normal sign-out state.
    def test_keyring_failure_is_not_swallowed(self) -> None:
        """Propagate keyring retrieval errors through token presence checks."""

        store = TokenStore(keyring_module=FailingKeyring("get"), legacy_vault=LegacyVaultDouble({}))
        with self.assertRaisesRegex(AppError, "Unable to read"):
            store.has_token("octocat")


if __name__ == "__main__":
    unittest.main()
