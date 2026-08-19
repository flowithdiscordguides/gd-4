"""Regression coverage for atomic GitDesk settings and repository metadata persistence."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gitdesk import aiskills
from gitdesk.backup_store import BackupStore
from gitdesk.config import SettingsStore
from gitdesk.documentstore import DocumentStore
from gitdesk.errors import AppError
from gitdesk.localactivity_store import activity_store
from gitdesk.media_library_store import MediaLibraryStore
from gitdesk.reposettings_recovery import invalid_json_backup_candidates
from gitdesk.sharedresource_store import SharedResourceStore
from gitdesk.storage import atomic_write_private_json, source_checkout_root
from gitdesk.syncignore_store import SyncIgnoreStore


# SettingsStorageTests isolates every persistence check inside a disposable directory.
class SettingsStorageTests(unittest.TestCase):
    """Verify settings recovery, atomic replacement, and serialized updates."""

    # Builds a real SettingsStore whose settings and registry files both live under the test directory.
    def settings_store(self, root: Path) -> SettingsStore:
        """Return a SettingsStore redirected to root without touching user app data."""

        store = SettingsStore()
        store.config_path = root / "settings.json"
        store.repo_settings_store.config_path = root / "reposettings.json"
        return store

    # Confirms trailing corruption is preserved and salvageable settings continue into repository metadata loading.
    def test_malformed_settings_recovery_preserves_metadata(self) -> None:
        """Recover a complete settings object without discarding valid repository metadata."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = self.settings_store(root)
            store.config_path.write_text('{"active_account": "octocat"} trailing', encoding="utf-8")
            store.repo_settings_store.write({
                "local_projects": [{"path": "/Documents/example", "name": "example", "category": ""}],
            })

            settings = store.load()

            self.assertEqual(settings["active_account"], "octocat")
            self.assertEqual(settings["local_projects"][0]["path"], "/Documents/example")
            self.assertTrue(list(root.glob("settings.json.invalid.recovered*")))
            self.assertIsInstance(json.loads(store.config_path.read_text(encoding="utf-8")), dict)

    # Confirms an earlier preserved settings object restores identities after a prior run created clean defaults.
    def test_existing_invalid_backup_restores_missing_current_values_once(self) -> None:
        """Merge recoverable backup values into empty current settings and then retire the backup."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = self.settings_store(root)
            store.config_path.write_text('{"active_account": ""}\n', encoding="utf-8")
            backup_path = root / "settings.json.invalid"
            backup_path.write_text('{"active_account": "octocat"} trailing', encoding="utf-8")

            settings = store.load()

            self.assertEqual(settings["active_account"], "octocat")
            self.assertEqual(invalid_json_backup_candidates(store.config_path), [])
            self.assertTrue(list(root.glob("settings.json.invalid.recovered*")))

    # Confirms an interrupted replacement never truncates the previously complete destination file.
    def test_atomic_write_failure_preserves_previous_json(self) -> None:
        """Keep the old JSON intact when the final operating-system replacement fails."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.json"
            path.write_text('{"state": "previous"}\n', encoding="utf-8")

            with mock.patch("gitdesk.storage.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    atomic_write_private_json(path, {"state": "next"}, 0o700, 0o600)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"state": "previous"})

    # Confirms separate bridge workers cannot overwrite fields saved by an earlier completed transaction.
    def test_concurrent_settings_updates_merge_from_latest_disk_state(self) -> None:
        """Preserve independent updates submitted concurrently through one SettingsStore."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.settings_store(Path(temporary_directory))
            store.save({})
            updates = [
                {"github_owner": "owner"},
                {"github_repo": "repository"},
            ]

            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(store.save, updates))

            settings = store.load()
            self.assertEqual(settings["github_owner"], "owner")
            self.assertEqual(settings["github_repo"], "repository")

    # Confirms non-secret PAT profile metadata survives persistence without storing a credential value.
    def test_resource_owner_profile_metadata_persists(self) -> None:
        """Keep the organization owner and authenticated human as distinct non-secret settings fields."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.settings_store(Path(temporary_directory))
            saved = store.save({"github_accounts": [{
                "login": "xandland",
                "authenticated_login": "xander-haj",
                "resource_owner_type": "Organization",
                "id": "42",
                "token_expires_at": "2026-08-21T04:00:00Z",
            }]})

            self.assertEqual(saved["github_accounts"][0]["login"], "xandland")
            self.assertEqual(saved["github_accounts"][0]["authenticated_login"], "xander-haj")
            self.assertEqual(saved["github_accounts"][0]["resource_owner_type"], "Organization")
            self.assertTrue(saved["github_accounts"][0]["credential_configured"])
            self.assertEqual(saved["github_accounts"][0]["token_expires_at"], "2026-08-21T04:00:00Z")
            persisted = json.loads(store.config_path.read_text(encoding="utf-8"))["github_accounts"][0]
            self.assertNotIn("token", persisted)
            self.assertIs(persisted["credential_configured"], True)
            self.assertEqual(persisted["token_expires_at"], "2026-08-21T04:00:00Z")

    # Confirms Sync Chains survive owner-only registry persistence and malformed-file recovery.
    def test_sync_chains_persist_and_recover_from_invalid_registry(self) -> None:
        """Recover chain stage metadata without losing managed repository or Local Mode records."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = self.settings_store(root)
            chain = {
                "id": "chain-one",
                "project_path": "/Documents/project",
                "stages": {
                    "private_beta": {
                        "account_login": "octocat",
                        "repository_path": "/Documents/private-beta",
                    },
                },
                "receipts": {},
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
            store.repo_settings_store.write({"sync_chains": [chain]})
            original = store.repo_settings_store.config_path.read_text(encoding="utf-8")
            store.repo_settings_store.config_path.write_text(original + " trailing", encoding="utf-8")

            settings = store.load()

            self.assertEqual(settings["sync_chains"][0]["id"], "chain-one")
            self.assertEqual(
                settings["sync_chains"][0]["stages"]["private_beta"]["repository_path"],
                "/Documents/private-beta",
            )

    # Confirms every app-owned registry and editable resource root uses operating-system per-user storage.
    def test_runtime_storage_defaults_stay_outside_source_checkout(self) -> None:
        """Keep settings, metadata, and editable resources independent from repository-local folders."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_root = root / "platform-config"
            data_root = root / "platform-data"
            with mock.patch("gitdesk.storage.PlatformDirs") as platform_dirs:
                platform_dirs.return_value.user_config_path = config_root
                platform_dirs.return_value.user_data_path = data_root
                settings_store = SettingsStore()
                metadata_paths = {
                    settings_store.config_path,
                    settings_store.repo_settings_store.config_path,
                    DocumentStore().config_path,
                    MediaLibraryStore().config_path,
                    SharedResourceStore().config_path,
                    SyncIgnoreStore().config_path,
                    BackupStore().config_path,
                    activity_store(settings_store.config_path).path,
                }
                writable_resources = aiskills.writable_categories_root()

            self.assertEqual({path.parent for path in metadata_paths}, {config_root.resolve()})
            self.assertEqual(
                writable_resources,
                data_root.resolve() / "Shared-Resources" / "categories",
            )
            checkout_root = source_checkout_root()
            self.assertIsNotNone(checkout_root)
            for path in (*metadata_paths, writable_resources):
                self.assertNotEqual(path, checkout_root)
                self.assertNotIn(checkout_root, path.parents)

    # Confirms even a misconfigured caller cannot atomically write private data into the checkout.
    def test_private_writer_rejects_repository_local_metadata(self) -> None:
        """Raise before creating a retired local-files settings path beneath source control."""

        checkout_root = source_checkout_root()
        self.assertIsNotNone(checkout_root)
        unsafe_path = checkout_root / "local files" / "settings.json"

        with self.assertRaises(AppError) as raised:
            atomic_write_private_json(unsafe_path, {"unsafe": True}, 0o700, 0o600)

        self.assertEqual(raised.exception.code, "APP_STORAGE_PATH_UNSAFE")

    # Confirms source execution reads only the canonical bundled catalog and never the retired directory.
    def test_source_catalog_has_no_retired_directory_dependency(self) -> None:
        """Use the checkout's Shared Resources as read-only seed content."""

        with mock.patch.object(aiskills.sys, "_MEIPASS", "", create=True):
            roots = aiskills.bundled_categories_roots()

        self.assertEqual(roots, [source_checkout_root() / "Shared-Resources" / "categories"])
        self.assertTrue(all("AI-Skills" not in path.parts for path in roots))


if __name__ == "__main__":
    unittest.main()
