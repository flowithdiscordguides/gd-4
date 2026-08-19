"""Regression coverage for category-based project creation and whole-project migration."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gitdesk.config import SettingsStore
from gitdesk.errors import AppError
from gitdesk import localcategoryfolders
from gitdesk.localcategory_bridge import handle_apply_category_folder_migration
from gitdesk.localpathremap import remap_permission_grants
from gitdesk.localproject_records import clean_local_project_record
from gitdesk import localprojects
from gitdesk import projecthub


# LocalCategoryFolderTests keeps every physical move inside a disposable filesystem boundary.
class LocalCategoryFolderTests(unittest.TestCase):
    """Verify layout markers, future creation, migration safety, remapping, and rollback."""

    # Builds the minimum durable record used by service and bridge migration tests.
    def project_record(self, project_path: Path, category: str = "Game") -> dict[str, object]:
        """Return a flat legacy project record for project_path."""

        return {
            "path": str(project_path),
            "name": project_path.name,
            "category": category,
            "icon_path": "",
            "category_foldered": False,
        }

    # Confirms older records remain migration candidates while the new marker survives sanitization.
    def test_project_record_layout_marker_defaults_false_and_preserves_true(self) -> None:
        """Distinguish legacy flat projects from projects already organized by GitDesk."""

        legacy = clean_local_project_record({"path": "/parent/project", "category": "Game"})
        organized = clean_local_project_record({
            "path": "/parent/categories/Game/project",
            "category": "Game",
            "category_foldered": True,
        })

        self.assertIs(legacy["category_foldered"], False)
        self.assertIs(organized["category_foldered"], True)

    # Confirms enabled creation inserts the categories container and label folder above the normal project structure.
    def test_future_project_creation_uses_parent_categories_category_project(self) -> None:
        """Create Parent/categories/Category/Project with its init feature and v1 below the project root."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory).resolve()
            result = localprojects.create_local_project(parent, "My Project", [], "Game", True)
            project_path = parent / "categories" / "Game" / "My Project"

            self.assertEqual(result["project"]["path"], str(project_path.resolve()))
            self.assertIs(result["project"]["category_foldered"], True)
            self.assertTrue((parent / "categories").is_dir())
            self.assertEqual(result["feature"]["path"], str((project_path / "01 init").resolve()))
            self.assertTrue(Path(result["version"]["path"]).is_dir())

    # Confirms projects created with the former layout remain eligible for the corrected container layout.
    def test_previous_category_layout_migrates_into_categories_container(self) -> None:
        """Target Parent/categories/Category/Project from the former Parent/Category/Project path."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory).resolve()
            source = parent / "Game" / "project"
            source.mkdir(parents=True)
            record = {**self.project_record(source), "category_foldered": True}

            migration = localcategoryfolders.category_folder_migration_state({"local_projects": [record]})

        self.assertEqual(migration["projects"][0]["source"], str(source))
        self.assertEqual(migration["projects"][0]["target"], str(parent / "categories" / "Game" / "project"))
        self.assertTrue(migration["projects"][0]["eligible"])

    # Confirms an enabled category layout cannot silently fall back to a flat project path.
    def test_future_project_creation_requires_category_when_setting_is_enabled(self) -> None:
        """Raise a structured error instead of violating Parent/categories/Category/Project."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(AppError) as raised:
                localprojects.create_local_project(temporary_directory, "My Project", [], "", True)

        self.assertEqual(raised.exception.code, "LOCAL_PROJECT_CATEGORY_REQUIRED")

    # Confirms every legacy record stays visible even when it cannot yet be selected.
    def test_migration_state_lists_uncategorized_and_missing_projects_with_reasons(self) -> None:
        """Expose blocked legacy projects instead of dropping them from the User settings list."""

        settings = {
            "create_categories_as_folders": True,
            "local_projects": [
                self.project_record(Path("/missing/categorized")),
                self.project_record(Path("/missing/uncategorized"), ""),
            ],
        }

        migration = localcategoryfolders.category_folder_migration_state(settings)
        projects = {project["name"]: project for project in migration["projects"]}

        self.assertFalse(projects["categorized"]["eligible"])
        self.assertIn("missing", projects["categorized"]["reason"].lower())
        self.assertFalse(projects["uncategorized"]["eligible"])
        self.assertIn("assign", projects["uncategorized"]["reason"].lower())

    # Confirms a category destination cannot nest one project inside another saved project root.
    def test_preflight_rejects_destination_overlapping_another_project(self) -> None:
        """Block Parent/categories/Category/Project when Category is itself a saved project folder."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory).resolve()
            source = parent / "source"
            category_project = parent / "categories" / "Game"
            source.mkdir()
            category_project.mkdir(parents=True)
            settings = {
                "create_categories_as_folders": True,
                "local_projects": [
                    self.project_record(source),
                    self.project_record(category_project, "Other"),
                ],
            }

            state = localcategoryfolders.category_folder_migration_state(settings)
            source_candidate = next(project for project in state["projects"] if project["source"] == str(source))

            self.assertFalse(source_candidate["eligible"])
            self.assertIn("overlaps another saved project", source_candidate["reason"])

    # Confirms future category creation cannot use an existing saved project as its category directory.
    def test_future_project_destination_rejects_saved_project_overlap(self) -> None:
        """Block a new project before it can be nested inside another saved project root."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory).resolve()
            category_project = parent / "categories" / "Game"
            category_project.mkdir(parents=True)
            settings = {"local_projects": [self.project_record(category_project, "Other")]}

            with self.assertRaises(AppError) as raised:
                localcategoryfolders.validate_new_project_destination(
                    parent,
                    "Game",
                    "Nested Project",
                    settings,
                )

        self.assertEqual(raised.exception.code, "LOCAL_PROJECT_OVERLAPS_SAVED_PROJECT")

    # Confirms path-keyed permission receipts follow the project root alongside other canonical settings.
    def test_permission_grants_remap_keys_and_nested_values(self) -> None:
        """Move both grant identity fields from the old project root to the category destination."""

        fixture_root = Path.cwd().resolve() / "path-remap-fixture"
        old_root = fixture_root / "project"
        new_root = fixture_root / "categories" / "Game" / "project"
        settings = {
            "local_permission_grants": {
                str(old_root): {
                    "project_path": str(old_root),
                    "granted_path": str(old_root / "01 init"),
                    "app_version": "1.0",
                },
            },
        }

        grants = remap_permission_grants(settings, old_root, new_root)

        self.assertIn(str(new_root), grants)
        self.assertEqual(grants[str(new_root)]["project_path"], str(new_root))
        self.assertEqual(grants[str(new_root)]["granted_path"], str(new_root / "01 init"))

    # Confirms Apply moves arbitrary root content and remaps every settings and private-registry dependency.
    def test_apply_moves_entire_project_and_remaps_all_dependent_paths(self) -> None:
        """Move the project root, not only its feature/version folders, and preserve dependent metadata."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory).resolve()
            source = parent / "project"
            version = source / "01 init" / "v1 project"
            icon = source / "art" / "icon.svg"
            repository = version / "repo"
            repository.mkdir(parents=True)
            icon.parent.mkdir()
            icon.write_text("<svg/>", encoding="utf-8")
            (source / "README.md").write_text("entire project", encoding="utf-8")
            settings = {
                "create_categories_as_folders": True,
                "workspace_mode": "repo",
                "local_projects": [{
                    **self.project_record(source),
                    "icon_path": str(icon),
                }],
                "active_local_project": str(source),
                "active_local_feature": str(version.parent),
                "active_local_version": str(version),
                "local_permission_grants": {
                    str(source): {
                        "project_path": str(source),
                        "granted_path": str(source),
                    },
                },
                "local_version_statuses": {str(version): "current"},
                "project_timeline": [{
                    "title": "Created",
                    "project_path": str(source),
                    "feature_path": str(version.parent),
                    "version_path": str(version),
                }],
                "repository_path": str(repository),
                "managed_repositories": {
                    "octocat": [{"path": str(repository), "full_name": "octocat/project"}],
                },
                "active_repository_by_account": {"octocat": str(repository)},
                "sync_chains": [{
                    "id": "chain-one",
                    "project_path": str(source),
                    "stages": {},
                    "receipts": {},
                }],
            }
            controller = mock.Mock()
            controller.settings_store.config_path = parent / "settings.json"
            controller.settings_store.load.return_value = settings
            controller.settings_store.save.side_effect = lambda updates: dict(updates)
            activity_store = mock.Mock()

            with mock.patch(
                "gitdesk.localcategory_bridge.sharedresources.remap_installations",
            ) as remap_resources, mock.patch(
                "gitdesk.localcategory_bridge.localactivity.activity_store",
                return_value=activity_store,
            ), mock.patch(
                "gitdesk.localcategory_bridge.localprojects.local_projects_state",
                return_value={"projects": ["refreshed"]},
            ):
                response = handle_apply_category_folder_migration(
                    controller,
                    {"project_paths": [str(source)]},
                )

            target = parent / "categories" / "Game" / "project"
            saved = response["settings"]
            saved_project = saved["local_projects"][0]

            self.assertFalse(source.exists())
            self.assertEqual((target / "README.md").read_text(encoding="utf-8"), "entire project")
            self.assertTrue((target / "01 init" / "v1 project" / "repo").is_dir())
            self.assertEqual(saved_project["path"], str(target))
            self.assertEqual(saved_project["icon_path"], str(target / "art" / "icon.svg"))
            self.assertIs(saved_project["category_foldered"], True)
            self.assertEqual(saved["active_local_project"], str(target))
            self.assertEqual(saved["workspace_mode"], "repo")
            self.assertIn(str(target), saved["local_permission_grants"])
            self.assertIn(str(target / "01 init" / "v1 project"), saved["local_version_statuses"])
            self.assertEqual(saved["sync_chains"][0]["project_path"], str(target))
            self.assertEqual(saved["repository_path"], str(target / "01 init" / "v1 project" / "repo"))
            remap_resources.assert_called_once_with(source, target)
            activity_store.remap_paths.assert_called_once_with(source, target)

    # Confirms a post-move registry failure restores the original whole project and Shared Resource paths.
    def test_apply_rolls_back_physical_move_when_registry_remap_fails(self) -> None:
        """Restore the source root and remove GitDesk's empty category folder after a failed Apply."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory).resolve()
            source = parent / "project"
            source.mkdir()
            (source / "root-file.txt").write_text("preserve", encoding="utf-8")
            settings = {
                "create_categories_as_folders": True,
                "local_projects": [self.project_record(source)],
                "sync_chains": [],
            }
            controller = mock.Mock()
            controller.settings_store.config_path = parent / "settings.json"
            controller.settings_store.load.return_value = settings
            activity_store = mock.Mock()
            activity_store.remap_paths.side_effect = OSError("activity registry unavailable")

            with mock.patch(
                "gitdesk.localcategory_bridge.sharedresources.remap_installations",
            ) as remap_resources, mock.patch(
                "gitdesk.localcategory_bridge.localactivity.activity_store",
                return_value=activity_store,
            ):
                with self.assertRaises(AppError) as raised:
                    handle_apply_category_folder_migration(
                        controller,
                        {"project_paths": [str(source)]},
                    )

            target = parent / "categories" / "Game" / "project"
            self.assertEqual(raised.exception.code, "CATEGORY_FOLDER_MIGRATION_FAILED")
            self.assertTrue((source / "root-file.txt").is_file())
            self.assertFalse(target.exists())
            self.assertFalse((parent / "categories" / "Game").exists())
            self.assertFalse((parent / "categories").exists())
            self.assertEqual(
                remap_resources.call_args_list,
                [mock.call(source, target), mock.call(target, source)],
            )
            controller.settings_store.save.assert_not_called()

    # Confirms the preference, record marker, and Project Hub backup contract all survive persistence.
    def test_setting_and_layout_marker_persist_and_export(self) -> None:
        """Keep category-folder intent across restart and Project Hub backup/import."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            store = SettingsStore()
            store.config_path = root / "settings.json"
            store.repo_settings_store.config_path = root / "reposettings.json"
            saved = store.save({
                "create_categories_as_folders": True,
                "local_projects": [{
                    "path": str(root / "categories" / "Game" / "project"),
                    "name": "project",
                    "category": "Game",
                    "category_foldered": True,
                }],
            })
            loaded = store.load()
            exported = projecthub.export_project_hub_settings(saved)
            imported = projecthub.import_project_hub_settings(exported["json"])

            settings_json = json.loads(store.config_path.read_text(encoding="utf-8"))

        self.assertIs(settings_json["create_categories_as_folders"], True)
        self.assertIs(loaded["local_projects"][0]["category_foldered"], True)
        self.assertIs(imported["create_categories_as_folders"], True)


# CategoryFolderFrontendSourceTests protects the static and inlined User settings delivery paths.
class CategoryFolderFrontendSourceTests(unittest.TestCase):
    """Verify visible migration controls and packaged asset order without launching the desktop runtime."""

    # Confirms the setting, modal checkbox list, Apply action, and whole-project copy are present in source.
    def test_user_settings_source_exposes_explicit_project_migration(self) -> None:
        """Require a true switch and modal with readable square project checkboxes."""

        root = Path(__file__).resolve().parents[1]
        script = (root / "src" / "gitdesk" / "ui" / "category-folders.js").read_text(encoding="utf-8")
        style = (root / "src" / "gitdesk" / "ui" / "category-folders.css").read_text(encoding="utf-8")

        self.assertIn("Create categories as folders", script)
        self.assertIn("Parent / categories / Category / Project", script)
        self.assertIn('role="switch"', script)
        self.assertIn('role="dialog" aria-modal="true"', script)
        self.assertIn('className = "category-folder-project-check"', script)
        self.assertNotIn('document.createElement("code")', script)
        self.assertIn("Apply selected", script)
        self.assertIn("complete project folder", script)
        self.assertIn('"applyCategoryFolderMigration"', script)
        self.assertIn("border-radius: 4px;", style)
        self.assertIn(".category-folder-project-check:checked", style)

    # Confirms CSS and JavaScript are loaded by both static index and inlined frontend assembly.
    def test_category_folder_assets_are_packaged_in_dependency_order(self) -> None:
        """Load settings tabs before the category card in every frontend delivery path."""

        root = Path(__file__).resolve().parents[1]
        index = (root / "src" / "gitdesk" / "ui" / "index.html").read_text(encoding="utf-8")
        frontend = (root / "src" / "gitdesk" / "frontend.py").read_text(encoding="utf-8")

        self.assertIn('href="./category-folders.css"', index)
        self.assertLess(index.index('src="./settings-tabs.js"'), index.index('src="./category-folders.js"'))
        self.assertIn('"category-folders.css"', frontend)
        self.assertLess(frontend.index('"settings-tabs.js"'), frontend.index('"category-folders.js"'))


if __name__ == "__main__":
    unittest.main()
