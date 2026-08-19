"""Regression coverage for permanent Local Mode version deletion and its inline list action."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gitdesk.errors import AppError
from gitdesk.localactivity_store import LocalActivityStore
from gitdesk.localversion_bridge import handle_delete_local_version
from gitdesk.sharedresource_store import SharedResourceStore


# FakeSettingsStore preserves SettingsStore's merge contract while exposing every attempted transaction update.
class FakeSettingsStore:
    """Keep isolated in-memory settings for destructive bridge tests."""

    def __init__(self, settings: dict, config_path: Path) -> None:
        self.settings = deepcopy(settings)
        self.config_path = config_path
        self.save_calls = []

    def load(self) -> dict:
        """Return a detached settings snapshot."""

        return deepcopy(self.settings)

    def save(self, updates: dict) -> dict:
        """Merge one update payload and return the resulting complete settings."""

        self.save_calls.append(deepcopy(updates))
        self.settings.update(deepcopy(updates))
        return deepcopy(self.settings)


# LocalVersionDeletionTests isolates every permanent folder operation below a disposable project root.
class LocalVersionDeletionTests(unittest.TestCase):
    """Verify ownership, selection, metadata cleanup, rollback, and frontend reachability."""

    # Creates a project with two feature-scoped versions and complete active-selection metadata.
    def deletion_fixture(self, root: Path) -> tuple[Path, Path, Path, Path, dict]:
        """Return project hierarchy paths and settings for one active latest version."""

        project_path = root / "project"
        feature_path = project_path / "01 init"
        first_version = feature_path / "v1 project"
        second_version = feature_path / "v2 work"
        first_version.mkdir(parents=True)
        second_version.mkdir()
        (second_version / "work.txt").write_text("keep transaction evidence\n", encoding="utf-8")
        settings = {
            "workspace_mode": "local",
            "local_projects": [{
                "path": str(project_path.resolve()),
                "name": "project",
                "category": "Game",
            }],
            "active_local_project": str(project_path.resolve()),
            "active_local_feature": str(feature_path.resolve()),
            "active_local_version": str(second_version.resolve()),
            "local_version_statuses": {
                str(first_version.resolve()): "working",
                str(second_version.resolve()): "complete",
            },
        }
        return project_path, feature_path, first_version, second_version, settings

    # Confirms active deletion selects the latest survivor and removes only exact live version metadata.
    def test_delete_active_version_selects_survivor_and_cleans_metadata(self) -> None:
        """Permanently remove one version while retaining its feature and older version."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            project, feature, first_version, second_version, settings = self.deletion_fixture(root)
            settings_store = FakeSettingsStore(settings, root / "settings.json")
            controller = mock.Mock(settings_store=settings_store)
            resource_store = mock.Mock()
            resource_records = {"coding": {"resource": "coding", "files": {}}}
            resource_store.remove_version_installations.return_value = resource_records
            activity_store = mock.Mock()
            activity_snapshot = {"app.py": {"modified_ns": 1, "size": 2, "birth_ns": 0}}
            activity_store.remove_version_snapshot.return_value = activity_snapshot

            with (
                mock.patch("gitdesk.localversion_bridge.SharedResourceStore", return_value=resource_store),
                mock.patch("gitdesk.localversion_bridge.localactivity.activity_store", return_value=activity_store),
                mock.patch(
                    "gitdesk.localversion_bridge.localprojects.local_projects_state",
                    side_effect=lambda saved: {"active_version": saved["active_local_version"]},
                ),
            ):
                response = handle_delete_local_version(controller, {
                    "project_path": str(project),
                    "feature_path": str(feature),
                    "version_path": str(second_version),
                })

            self.assertFalse(second_version.exists())
            self.assertTrue(first_version.is_dir())
            self.assertEqual(response["deleted"]["path"], str(second_version.resolve()))
            self.assertEqual(response["settings"]["active_local_version"], str(first_version.resolve()))
            self.assertEqual(
                response["settings"]["local_version_statuses"],
                {str(first_version.resolve()): "working"},
            )
            resource_store.remove_version_installations.assert_called_once_with(str(second_version.resolve()))
            activity_store.remove_version_snapshot.assert_called_once_with(str(second_version.resolve()))
            resource_store.restore_version_installations.assert_not_called()
            activity_store.restore_version_snapshot.assert_not_called()
            self.assertEqual(list(feature.glob(".gitdesk-delete-*")), [])

    # Confirms a row cannot delete a version owned by any feature other than the payload's selected feature.
    def test_delete_rejects_version_from_another_feature(self) -> None:
        """Reject cross-feature deletion before constructing metadata stores or renaming folders."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            project, feature, _, _, settings = self.deletion_fixture(root)
            other_feature = project / "02 other"
            other_version = other_feature / "v1 other"
            other_version.mkdir(parents=True)
            controller = mock.Mock(settings_store=FakeSettingsStore(settings, root / "settings.json"))

            with (
                mock.patch("gitdesk.localversion_bridge.SharedResourceStore") as store_type,
                self.assertRaises(AppError) as raised,
            ):
                handle_delete_local_version(controller, {
                    "project_path": str(project),
                    "feature_path": str(feature),
                    "version_path": str(other_version),
                })

            self.assertEqual(raised.exception.code, "LOCAL_VERSION_INVALID")
            self.assertTrue(other_version.is_dir())
            store_type.assert_not_called()

    # Confirms the native endpoint cannot delete a well-formed vN folder from an unregistered project.
    def test_delete_rejects_version_from_unsaved_project(self) -> None:
        """Require the canonical project root to exist in GitDesk's saved Local Projects registry."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            project, feature, _, second_version, settings = self.deletion_fixture(root)
            settings["local_projects"] = []
            controller = mock.Mock(settings_store=FakeSettingsStore(settings, root / "settings.json"))

            with (
                mock.patch("gitdesk.localversion_bridge.SharedResourceStore") as store_type,
                self.assertRaises(AppError) as raised,
            ):
                handle_delete_local_version(controller, {
                    "project_path": str(project),
                    "feature_path": str(feature),
                    "version_path": str(second_version),
                })

            self.assertEqual(raised.exception.code, "LOCAL_PROJECT_NOT_FOUND")
            self.assertTrue(second_version.is_dir())
            store_type.assert_not_called()

    # Confirms deleting a feature's only version keeps the feature selected without inventing a replacement.
    def test_delete_only_version_clears_active_version(self) -> None:
        """Leave an empty feature selected after its sole physical version is permanently removed."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            project, feature, first_version, second_version, settings = self.deletion_fixture(root)
            first_version.rmdir()
            settings["local_version_statuses"] = {str(second_version.resolve()): "working"}
            settings_store = FakeSettingsStore(settings, root / "settings.json")
            controller = mock.Mock(settings_store=settings_store)
            resource_store = mock.Mock()
            resource_store.remove_version_installations.return_value = {}
            activity_store = mock.Mock()
            activity_store.remove_version_snapshot.return_value = None

            with (
                mock.patch("gitdesk.localversion_bridge.SharedResourceStore", return_value=resource_store),
                mock.patch("gitdesk.localversion_bridge.localactivity.activity_store", return_value=activity_store),
                mock.patch(
                    "gitdesk.localversion_bridge.localprojects.local_projects_state",
                    side_effect=lambda saved: {"active_version": saved["active_local_version"]},
                ),
            ):
                response = handle_delete_local_version(controller, {
                    "project_path": str(project),
                    "feature_path": str(feature),
                    "version_path": str(second_version),
                })

            self.assertFalse(second_version.exists())
            self.assertEqual(response["settings"]["active_local_feature"], str(feature.resolve()))
            self.assertEqual(response["settings"]["active_local_version"], "")
            self.assertEqual(response["settings"]["local_version_statuses"], {})

    # Confirms a failed final removal restores the folder, settings, resource records, and activity snapshot.
    def test_delete_failure_rolls_back_folder_and_private_metadata(self) -> None:
        """Restore every reversible surface when permanent filesystem removal cannot finish."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            project, feature, _, second_version, settings = self.deletion_fixture(root)
            settings_store = FakeSettingsStore(settings, root / "settings.json")
            controller = mock.Mock(settings_store=settings_store)
            resource_store = mock.Mock()
            records = {"coding": {"resource": "coding", "files": {}}}
            resource_store.remove_version_installations.return_value = records
            activity_store = mock.Mock()
            snapshot = {"app.py": {"modified_ns": 1, "size": 2, "birth_ns": 0}}
            activity_store.remove_version_snapshot.return_value = snapshot

            with (
                mock.patch("gitdesk.localversion_bridge.SharedResourceStore", return_value=resource_store),
                mock.patch("gitdesk.localversion_bridge.localactivity.activity_store", return_value=activity_store),
                mock.patch("gitdesk.localversion_bridge.shutil.rmtree", side_effect=OSError("locked")),
                self.assertRaises(AppError) as raised,
            ):
                handle_delete_local_version(controller, {
                    "project_path": str(project),
                    "feature_path": str(feature),
                    "version_path": str(second_version),
                })

            self.assertEqual(raised.exception.code, "LOCAL_VERSION_DELETE_FAILED")
            self.assertTrue(second_version.is_dir())
            self.assertEqual(settings_store.settings["active_local_version"], settings["active_local_version"])
            resource_store.restore_version_installations.assert_called_once_with(
                str(second_version.resolve()),
                records,
            )
            activity_store.restore_version_snapshot.assert_called_once_with(
                str(second_version.resolve()),
                snapshot,
            )
            self.assertEqual(list(feature.glob(".gitdesk-delete-*")), [])

    # Confirms exact version-group cleanup never removes another version's Shared Resources records.
    def test_shared_resource_version_cleanup_is_exact_and_reversible(self) -> None:
        """Remove and restore one complete installation group by its physical version key."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            store = SharedResourceStore(root / "shared-resources.json")
            version_path = str(root / "v1")
            other_path = str(root / "v2")
            record = {
                "version": 1,
                "revision": "a" * 64,
                "files": {"AGENTS.md": "b" * 64},
            }
            store.set_installation(version_path, "coding", record)
            store.set_installation(other_path, "coding", record)

            removed = store.remove_version_installations(version_path)

            self.assertEqual(removed["coding"]["resource"], "coding")
            self.assertNotIn(version_path, store.load()["installations"])
            self.assertIn(other_path, store.load()["installations"])

            store.restore_version_installations(version_path, removed)

            self.assertEqual(store.load()["installations"][version_path], removed)

    # Confirms version deletion removes only its scan baseline and leaves factual history available.
    def test_local_activity_version_cleanup_preserves_history_and_is_reversible(self) -> None:
        """Remove and restore one exact snapshot without deleting historical activity events."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            store = LocalActivityStore(root / "local-activity.json")
            version_path = str(root / "v1")
            other_path = str(root / "v2")
            snapshot = {"app.py": {"modified_ns": 1, "size": 2, "birth_ns": 0}}
            event = {
                "id": "event-1",
                "kind": "file_added",
                "occurred_at": "2026-07-26T12:00:00Z",
                "version_path": version_path,
                "file_path": "app.py",
            }
            store.save({"version": 1, "events": [event], "files": {
                version_path: snapshot,
                other_path: {},
            }})

            removed = store.remove_version_snapshot(version_path)
            current = store.load()

            self.assertEqual(removed, snapshot)
            self.assertNotIn(version_path, current["files"])
            self.assertIn(other_path, current["files"])
            self.assertEqual(current["events"][0]["version_path"], version_path)

            store.restore_version_snapshot(version_path, removed)

            self.assertEqual(store.load()["files"][version_path], snapshot)

    # Protects the inline row action, app-owned confirmation, event isolation, and packaged dependency order.
    def test_frontend_exposes_confirmed_trash_action_beside_every_version(self) -> None:
        """Require one accessible inline trash button for each mapped version listing."""

        project_root = Path(__file__).resolve().parents[1]
        ui_root = project_root / "src" / "gitdesk" / "ui"
        detail_source = (ui_root / "local-version-detail.js").read_text(encoding="utf-8")
        delete_source = (ui_root / "local-version-delete.js").read_text(encoding="utf-8")
        detail_style = (ui_root / "local-version-detail.css").read_text(encoding="utf-8")
        local_style = (ui_root / "local.css").read_text(encoding="utf-8")
        local_source = (ui_root / "local.js").read_text(encoding="utf-8")
        index_source = (ui_root / "index.html").read_text(encoding="utf-8")
        frontend_source = (project_root / "src" / "gitdesk" / "frontend.py").read_text(encoding="utf-8")
        manifest_source = (project_root / "src" / "gitdesk.egg-info" / "SOURCES.txt").read_text(encoding="utf-8")

        self.assertIn("versions.map((version) =>", detail_source)
        self.assertIn('class="local-version-delete icon-button"', detail_source)
        self.assertIn('data-delete-version-path="${escapeHtml(version.path)}"', detail_source)
        self.assertIn('aria-label="Delete ${escapeHtml(version.name)}"', detail_source)
        self.assertNotIn("window.confirm(", detail_source)
        self.assertNotIn("window.confirm(", delete_source)
        self.assertIn("event.stopPropagation();", detail_source)
        self.assertIn("onDeleteVersion(button.dataset.deleteVersionPath", detail_source)
        self.assertIn('id="local-version-delete-modal"', delete_source)
        self.assertIn('role="dialog" aria-modal="true"', delete_source)
        self.assertIn("This cannot be undone.", delete_source)
        self.assertIn("openDeleteDialog(versionPath, versionName, trigger)", delete_source)
        self.assertIn('byId("confirm-local-version-delete").addEventListener', delete_source)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 32px;", detail_style)
        self.assertIn("width: 32px;", detail_style)
        self.assertIn("min-width: 32px;", detail_style)
        self.assertIn(".local-version-delete-modal[hidden]", detail_style)
        self.assertIn("#confirm-local-version-delete", detail_style)
        self.assertIn(".local-version-listing:not(.active)", local_style)
        self.assertIn('runAction("deleteLocalVersion"', delete_source)
        self.assertIn("localVersionDelete.bind(", local_source)
        bridge_source = (project_root / "src" / "gitdesk" / "localversion_bridge.py").read_text(encoding="utf-8")
        self.assertIn("with APP_STORAGE_LOCK:", bridge_source)
        for source in (index_source, frontend_source):
            self.assertLess(source.index("local-version-detail.js"), source.index("local-version-delete.js"))
            self.assertLess(source.index("local-version-delete.js"), source.index("local.js"))
        self.assertIn("src/gitdesk/localversion_bridge.py", manifest_source)
        self.assertIn("src/gitdesk/ui/local-version-delete.js", manifest_source)
        self.assertIn("tests/testlocalversiondelete.py", manifest_source)


if __name__ == "__main__":
    unittest.main()
