"""GitHub PAT storage backed by the operating system credential service."""

from __future__ import annotations

# Standard-library typing keeps the injected keyring surface backend-agnostic.
from typing import Any

# Third-party keyring APIs provide platform credential access and structured backend failures.
import keyring
from keyring.errors import KeyringError, PasswordDeleteError

# GitDesk modules validate account keys, migrate regressed storage, and serialize concurrent credential operations.
from gitdesk.accounts import clean_login
from gitdesk.errors import AppError
from gitdesk.legacysecrets import LegacyTokenVault
from gitdesk.storage import APP_STORAGE_LOCK


# This stable service name keeps GitDesk PATs in one recognizable OS credential-store namespace across releases.
TOKEN_SERVICE_NAME = "GitDesk"

# Namespaced account keys prevent GitHub PAT entries from colliding with other future GitDesk credentials.
TOKEN_ACCOUNT_PREFIX = "github-token"


# Builds the credential-store account name for one validated GitHub resource-owner profile.
def token_account_name(login: str) -> str:
    """Return the stable keyring account name used for one GitHub resource-owner profile."""

    return f"{TOKEN_ACCOUNT_PREFIX}:{clean_login(login)}"


# TokenStore is the only application boundary allowed to read, write, migrate, or remove GitHub PAT values.
class TokenStore:
    """Store GitHub PATs in the platform keyring while keeping secrets out of metadata JSON."""

    # Dependency injection keeps tests isolated from real OS credentials while production defaults to keyring.
    def __init__(
        self,
        keyring_module: Any = keyring,
        legacy_vault: LegacyTokenVault | None = None,
    ) -> None:
        self.keyring_module = keyring_module
        self.legacy_vault = legacy_vault or LegacyTokenVault()
        self._migration_complete = False
        self._migrated_logins: list[str] = []
        # Keep authorized PATs only in volatile process memory so repeated checks do not reopen Keychain prompts.
        self._session_tokens: dict[str, str] = {}

    # Exposes the non-secret service identifier for diagnostics without initializing or reading a credential backend.
    @property
    def service_name(self) -> str:
        """Return the stable operating-system credential service used by GitDesk."""

        return TOKEN_SERVICE_NAME

    # Builds the keyring account name that isolates the PAT for one personal or organization resource owner.
    def credential_account(self, login: str) -> str:
        """Return the credential-store account name for one cleaned GitHub resource-owner profile."""

        return token_account_name(login)

    # Converts backend read failures into a structured message without exposing credential values.
    def keyring_token(self, login: str) -> str:
        """Return one PAT from the system keyring, or an empty string when the credential is absent."""

        try:
            token = self.keyring_module.get_password(self.service_name, self.credential_account(login))
        except KeyringError as error:
            raise AppError(
                "Unable to read the GitHub PAT from the operating system credential store.",
                "TOKEN_KEYRING_READ_FAILED",
            ) from error
        return str(token or "").strip()

    # Writes one PAT through keyring so macOS, Windows, or Linux owns the credential at rest.
    def save_keyring_token(self, login: str, token: str) -> None:
        """Persist one non-empty PAT under its GitHub resource-owner profile in the system keyring."""

        cleaned_login = clean_login(login)
        cleaned_token = str(token or "").strip()
        # Reject empty credentials before a backend call so Keychain never receives an unusable item.
        if not cleaned_token:
            raise AppError("A GitHub token is required.", "TOKEN_EMPTY")
        # A failed replacement must not leave an older in-memory PAT masking the authoritative Keychain result.
        self._session_tokens.pop(cleaned_login, None)
        try:
            self.keyring_module.set_password(
                self.service_name,
                self.credential_account(cleaned_login),
                cleaned_token,
            )
        except KeyringError as error:
            raise AppError(
                "Unable to save the GitHub PAT in the operating system credential store.",
                "TOKEN_KEYRING_WRITE_FAILED",
            ) from error
        self._session_tokens[cleaned_login] = cleaned_token

    # Removes one PAT and treats a credential that is already absent as a completed sign-out.
    def clear_keyring_token(self, login: str) -> None:
        """Delete one GitHub PAT from the system keyring without failing when it is already absent."""

        cleaned_login = clean_login(login)
        try:
            self.keyring_module.delete_password(self.service_name, self.credential_account(cleaned_login))
        except PasswordDeleteError:
            self._session_tokens.pop(cleaned_login, None)
            return
        except KeyringError as error:
            raise AppError(
                "Unable to remove the GitHub PAT from the operating system credential store.",
                "TOKEN_KEYRING_DELETE_FAILED",
            ) from error
        self._session_tokens.pop(cleaned_login, None)

    # Moves every vault-regression PAT before deleting either legacy file, preserving retriable source data on failure.
    def ensure_legacy_migration(self) -> None:
        """Migrate obsolete local-vault PATs into keyring exactly once for this TokenStore instance."""

        # Multiple token reads during bootstrap must not repeat migration or credential prompts.
        if self._migration_complete:
            return
        legacy_tokens = self.legacy_vault.decrypted_tokens()
        # Every decrypted PAT must reach keyring before the obsolete local files are eligible for removal.
        for login, token in legacy_tokens.items():
            self.save_keyring_token(login, token)
        self.legacy_vault.remove()
        self._migrated_logins = sorted(legacy_tokens, key=str.lower)
        self._migration_complete = True

    # Reports only identities migrated in this process because standard OS keyrings do not enumerate service accounts.
    def saved_logins(self) -> list[str]:
        """Return logins discovered during one-time legacy migration for metadata recovery."""

        with APP_STORAGE_LOCK:
            self.ensure_legacy_migration()
            return list(self._migrated_logins)

    # Retrieves one PAT for backend API and Git operations without returning it to the WebUI.
    def get_token(self, login: str) -> str:
        """Return the PAT for one resource-owner profile or raise TOKEN_MISSING when absent."""

        with APP_STORAGE_LOCK:
            cleaned_login = clean_login(login)
            self.ensure_legacy_migration()
            cached_token = self._session_tokens.get(cleaned_login, "")
            if cached_token:
                return cached_token
            token = self.keyring_token(cleaned_login)
            # Only a non-empty keyring result is a usable authentication credential.
            if token:
                self._session_tokens[cleaned_login] = token
                return token
            raise AppError("No GitHub token is saved for the selected account.", "TOKEN_MISSING")

    # Persists a validated PAT only in the OS credential store after completing any pending vault migration.
    def save_token(self, login: str, token: str) -> None:
        """Save one GitHub PAT without writing it to settings, repository metadata, or browser state."""

        with APP_STORAGE_LOCK:
            cleaned_login = clean_login(login)
            cleaned_token = str(token or "").strip()
            # Preserve the backend validation boundary for callers other than the account form.
            if not cleaned_token:
                raise AppError("A GitHub token is required.", "TOKEN_EMPTY")
            self.ensure_legacy_migration()
            self.save_keyring_token(cleaned_login, cleaned_token)

    # Removes a PAT from the same OS credential namespace used by every API and Git authentication path.
    def clear_token(self, login: str) -> None:
        """Delete the PAT for one resource-owner profile from the operating system keyring."""

        with APP_STORAGE_LOCK:
            cleaned_login = clean_login(login)
            self.ensure_legacy_migration()
            self.clear_keyring_token(cleaned_login)

    # Distinguishes a missing credential from keyring failures so broken storage is never reported as signed out.
    def has_token(self, login: str) -> bool:
        """Return whether one resource-owner profile has a saved PAT while propagating backend failures."""

        try:
            return bool(self.get_token(login))
        except AppError as error:
            # Credential absence is normal sign-out state; backend and migration errors require user-visible repair.
            if error.code == "TOKEN_MISSING":
                return False
            raise
