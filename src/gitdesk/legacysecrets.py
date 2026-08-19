"""One-time migration support for PATs written by the local-vault regression."""

from __future__ import annotations

# Standard-library readers load only the two known app-config files from the regression.
import json
from pathlib import Path

# Fernet is retained solely to decrypt PATs before their one-time move into the OS keyring.
from cryptography.fernet import Fernet, InvalidToken

# GitDesk modules validate recovered account names, structure failures, and resolve LocalApp metadata.
from gitdesk.accounts import clean_login
from gitdesk.errors import AppError
from gitdesk.storage import app_config_path


# The regressed release used these exact app-config filenames for encrypted PAT records and their key.
LEGACY_TOKEN_VAULT_FILENAME = "tokens.vault.json"
LEGACY_TOKEN_KEY_FILENAME = "tokens.key"
LEGACY_TOKEN_VAULT_VERSION = 1
LEGACY_TOKEN_ACCOUNT_PREFIX = "github-token:"


# LegacyTokenVault reads the obsolete encrypted files solely so PATs can move into the system credential store.
class LegacyTokenVault:
    """Read and remove the encrypted token files created by the vault-only regression."""

    # Accepts an explicit config directory for isolated regression tests and otherwise uses GitDesk app metadata.
    def __init__(self, config_path: Path | None = None) -> None:
        root = config_path or app_config_path()
        self.vault_path = root / LEGACY_TOKEN_VAULT_FILENAME
        self.key_path = root / LEGACY_TOKEN_KEY_FILENAME

    # Loads the legacy JSON structure without creating files or returning malformed records.
    def encrypted_records(self) -> dict[str, str]:
        """Return encrypted legacy records keyed by their namespaced GitHub account names."""

        # A missing vault means there is no regressed PAT storage to migrate.
        if not self.vault_path.exists():
            return {}
        try:
            payload = json.loads(self.vault_path.read_text(encoding="utf-8"))
        except OSError as error:
            raise AppError("Unable to read the previous GitHub token vault.", "TOKEN_MIGRATION_READ_FAILED") from error
        except json.JSONDecodeError as error:
            raise AppError("The previous GitHub token vault is invalid.", "TOKEN_MIGRATION_INVALID") from error

        # Only the exact format written by the regressed TokenStore is safe to interpret.
        if not isinstance(payload, dict) or payload.get("version") != LEGACY_TOKEN_VAULT_VERSION:
            raise AppError("The previous GitHub token vault has an unsupported format.", "TOKEN_MIGRATION_INVALID")
        records = payload.get("tokens")
        # Missing token records indicate corruption, so cleanup must not remove the source files.
        if not isinstance(records, dict):
            raise AppError("The previous GitHub token vault is missing token records.", "TOKEN_MIGRATION_INVALID")
        return {
            account: token
            for account, token in records.items()
            if isinstance(account, str) and isinstance(token, str)
        }

    # Reads and validates the legacy encryption key only when an encrypted vault actually exists.
    def cipher(self) -> Fernet:
        """Return the cipher required to decrypt the previous local token vault."""

        # Ciphertext without its original key cannot be migrated and must remain untouched for diagnosis.
        if not self.key_path.is_file():
            raise AppError("The previous GitHub token vault key is missing.", "TOKEN_MIGRATION_KEY_MISSING")
        try:
            return Fernet(self.key_path.read_bytes().strip())
        except (OSError, ValueError) as error:
            raise AppError(
                "The previous GitHub token vault key is unreadable.",
                "TOKEN_MIGRATION_KEY_FAILED",
            ) from error

    # Decrypts every valid namespaced record before deletion so migration is all-or-preserved.
    def decrypted_tokens(self) -> dict[str, str]:
        """Return legacy PATs keyed by cleaned GitHub login without modifying either legacy file."""

        records = self.encrypted_records()
        # Avoid reading or requiring an encryption key when no encrypted records exist.
        if not records:
            return {}
        cipher = self.cipher()
        tokens: dict[str, str] = {}
        for account_name, encrypted_token in records.items():
            # Ignore unrelated records because only GitDesk GitHub-token entries belong in this credential service.
            if not account_name.startswith(LEGACY_TOKEN_ACCOUNT_PREFIX):
                continue
            login = clean_login(account_name[len(LEGACY_TOKEN_ACCOUNT_PREFIX):])
            try:
                token = cipher.decrypt(encrypted_token.encode("ascii")).decode("utf-8").strip()
            except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError, ValueError) as error:
                raise AppError(
                    "A PAT in the previous GitHub token vault could not be decrypted.",
                    "TOKEN_MIGRATION_DECRYPT_FAILED",
                ) from error
            # An empty decrypted value is not a usable PAT and must stop cleanup of the original vault.
            if not token:
                raise AppError("A PAT in the previous GitHub token vault is empty.", "TOKEN_MIGRATION_INVALID")
            tokens[login] = token
        return tokens

    # Deletes ciphertext before its key only after TokenStore has written every migrated PAT to the OS keyring.
    def remove(self) -> None:
        """Remove obsolete local secret files after a successful keyring migration."""

        try:
            self.vault_path.unlink(missing_ok=True)
            self.key_path.unlink(missing_ok=True)
        except OSError as error:
            raise AppError(
                "PATs reached the system credential store, but obsolete local token files could not be removed.",
                "TOKEN_MIGRATION_CLEANUP_FAILED",
            ) from error
