"""Regression coverage for read-only category discovery and metadata-path reconciliation."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gitdesk.errors import AppError
from gitdesk import localcategoryscan
from gitdesk.localcategory_bridge import handle_scan_local_categories


# LocalCategoryScanTests keeps every discovery fixture inside a disposable folder hierarchy.
class LocalCategoryScanTests(unittest.TestCase):
    """Verify existing-project ownership, complete remapping, rollback, and frontend wiring."""

    # Captures directory names and file bytes so a discovery pass can prove that the project tree stayed unchanged.
    def tree_snapshot(self, root: Path) -> list[tuple[str, bytes | None]]:
        """Return sorted relative paths with bytes for files and None for directories."""

        snapshot = []
        for path in sorted(root.rglob("*"), key=lambda item: str(item.relative_to(root)).casefold()):
            relative_path = str(path.relative_to(root))
            snapshot.append((relative_path, path.read_bytes() if path.is_file() else None))
        return snapshot

    # Creates the canonical categories/category/project shape used by focused scan cases.
    def category_project(self, parent: Path, category: str, project: str) -> Path:
        """Return a created Parent/categories/Category/Project folder."""

        project_path = parent / "categories" / category / project
        project_path.mkdir(parents=True)
        return project_path

    # Confirms discovery reads only direct category and project folders and never changes their contents.
    def test_discovery_lists_direct_projects_without_mutating_tree(self) -> None:
        """Read category labels and project roots while preserving every directory and file byte."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory).resolve()
            alpha = self.category_project(parent, "Game", "Alpha")
            (alpha / "01 init" / "v1 Alpha").mkdir(parents=True)
            (alpha / "README.md").write_text("preserve me", encoding="utf-8")
            (parent / "categories" / "Empty").mkdir()
            (parent / "categories" / "not-a-category.txt").write_text("ignored", encoding="utf-8")
            before = self.tree_snapshot(parent)

            discovery = localcategoryscan.discover_category_projects(parent / "categories")
            after = self.tree_snapshot(parent)

        self.assertEqual(discovery["categories"], ["Empty", "Game"])
        self.assertEqual(
            discovery["projects"],
            [{"name": "Alpha", "category": "Game", "path": str(alpha.resolve())}],
        )
        self.assertEqual(after, before)

    # Confirms the picker cannot accidentally turn an arbitrary parent into an authoritative project scan.
    def test_discovery_requires_literal_categories_folder(self) -> None:
        """Reject a selected parent whose final path segment is not categories."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(AppError) as raised:
                localcategoryscan.discover_category_projects(temporary_directory)

        self.assertEqual(raised.exception.code, "CATEGORY_SCAN_PATH_INVALID")

    # Confirms a stale saved project root is remapped while unmatched saved and detected projects stay untouched.
    def test_plan_remaps_only_existing_matched_projects(self) -> None:
        """Repair one saved project without importing discoveries or deleting unmatched metadata."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory).resolve()
            target = self.category_project(parent, "Game", "Alpha")
            self.category_project(parent, "Game", "Not Saved")
            version = target / "01 init" / "v1 Alpha"
            repository = version / "repo"
            icon = target / "art" / "icon.svg"
            repository.mkdir(parents=True)
            icon.parent.mkdir()
            icon.write_text("<svg/>", encoding="utf-8")
            old_root = parent / "Game" / "Alpha"
            old_version = old_root / "01 init" / "v1 Alpha"
            old_repository = old_version / "repo"
            stale = parent / "Old" / "Missing"
            settings = {
                "workspace_mode": "repo",
                "local_projects": [
                    {
                        "path": str(old_root),
                        "name": "Alpha",
                        "category": "Game",
                        "icon_path": str(old_root / "art" / "icon.svg"),
                        "category_foldered": True,
                    },
                    {"path": str(stale), "name": "Missing", "category": "Old"},
                ],
                "local_project_categories": ["Old"],
                "active_local_project": str(old_root),
                "active_local_feature": str(old_version.parent),
                "active_local_version": str(old_version),
                "local_permission_grants": {
                    str(old_root): {
                        "project_path": str(old_root),
                        "granted_path": str(old_root),
                    },
                    str(stale): {
                        "project_path": str(stale),
                        "granted_path": str(stale),
                    },
                },
                "local_version_statuses": {str(old_version): "current"},
                "project_timeline": [{
                    "title": "Created",
                    "project_path": str(old_root),
                    "feature_path": str(old_version.parent),
                    "version_path": str(old_version),
                }],
                "repository_path": str(old_repository),
                "managed_repositories": {
                    "octocat": [{"path": str(old_repository), "full_name": "octocat/alpha"}],
                },
                "active_repository_by_account": {"octocat": str(old_repository)},
                "sync_chains": [
                    {"id": "alpha", "project_path": str(old_root), "stages": {}, "receipts": {}},
                    {"id": "stale", "project_path": str(stale), "stages": {}, "receipts": {}},
                ],
            }

            plan = localcategoryscan.category_scan_plan(settings, parent / "categories")
            updates = plan["updates"]

        self.assertEqual(plan["mappings"], [{"source": str(old_root), "target": str(target)}])
        self.assertEqual(
            [record["path"] for record in updates["local_projects"]],
            [str(target), str(stale)],
        )
        self.assertEqual(updates["local_projects"][0]["category"], "Game")
        self.assertIs(updates["local_projects"][0]["category_foldered"], True)
        self.assertEqual(updates["local_projects"][0]["icon_path"], str(icon))
        self.assertNotIn(
            str(parent / "categories" / "Game" / "Not Saved"),
            [record["path"] for record in updates["local_projects"]],
        )
        self.assertNotIn("local_project_categories", updates)
        self.assertEqual(updates["active_local_project"], str(target))
        self.assertEqual(updates["active_local_version"], str(version))
        self.assertEqual(updates["workspace_mode"], "repo")
        self.assertEqual(set(updates["local_permission_grants"]), {str(target), str(stale)})
        self.assertEqual(set(updates["local_version_statuses"]), {str(version)})
        self.assertEqual(updates["repository_path"], str(repository))
        self.assertEqual(
            {chain["project_path"] for chain in updates["sync_chains"]},
            {str(target), str(stale)},
        )

    # Confirms an exact correct record does not block its stale duplicate from updating every active JSON path.
    def test_plan_consolidates_stale_duplicate_into_exact_detected_record(self) -> None:
        """Remap the stale duplicate to the exact canonical record and collapse the duplicate path."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory).resolve()
            target = self.category_project(parent, "games", "spider-man game")
            source = parent / "spider-man game"
            old_feature = source / "01 init"
            old_version = old_feature / "v5 add comets"
            settings = {
                "workspace_mode": "local",
                "local_projects": [
                    {
                        "path": str(target),
                        "name": "spider-man game",
                        "category": "games",
                        "category_foldered": True,
                    },
                    {
                        "path": str(source),
                        "name": "spider-man game",
                        "category": "",
                        "category_foldered": False,
                    },
                ],
                "active_local_project": str(source),
                "active_local_feature": str(old_feature),
                "active_local_version": str(old_version),
                "sync_chains": [{
                    "id": "spider-chain",
                    "project_path": str(target),
                    "stages": {},
                    "receipts": {
                        "local_to_private_beta": {
                            "source_path": str(old_version),
                            "destination_path": str(parent / "private"),
                            "destination_digest": "digest",
                        },
                    },
                }],
            }

            plan = localcategoryscan.category_scan_plan(settings, parent / "categories")
            updates = plan["updates"]
            exact_settings = {
                **settings,
                "local_projects": [settings["local_projects"][0]],
                "active_local_project": str(target),
                "active_local_feature": str(target / "01 init"),
                "active_local_version": str(target / "01 init" / "v5 add comets"),
            }
            exact_plan = localcategoryscan.category_scan_plan(exact_settings, parent / "categories")

        self.assertEqual(plan["mappings"], [{"source": str(source), "target": str(target)}])
        self.assertEqual(len(updates["local_projects"]), 1)
        self.assertEqual(updates["local_projects"][0]["path"], str(target))
        self.assertEqual(updates["active_local_project"], str(target))
        self.assertEqual(updates["active_local_feature"], str(target / "01 init"))
        self.assertEqual(updates["active_local_version"], str(target / "01 init" / "v5 add comets"))
        receipt = updates["sync_chains"][0]["receipts"]["local_to_private_beta"]
        self.assertEqual(receipt["source_path"], str(target / "01 init" / "v5 add comets"))
        self.assertEqual(exact_plan["mappings"], [{"source": str(source), "target": str(target)}])
        exact_receipt = exact_plan["updates"]["sync_chains"][0]["receipts"]["local_to_private_beta"]
        self.assertEqual(exact_receipt["source_path"], str(target / "01 init" / "v5 add comets"))

    # Confirms duplicate names without unique path or category evidence stop before metadata can be misassigned.
    def test_plan_rejects_ambiguous_project_identity(self) -> None:
        """Reject two stale same-name records when neither uniquely matches the scanned category."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory).resolve()
            self.category_project(parent, "Game", "Alpha")
            settings = {
                "local_projects": [
                    {"path": str(parent / "One" / "Alpha"), "name": "Alpha", "category": "One"},
                    {"path": str(parent / "Two" / "Alpha"), "name": "Alpha", "category": "Two"},
                ],
            }
            with self.assertRaises(AppError) as raised:
                localcategoryscan.category_scan_plan(settings, parent / "categories")

        self.assertEqual(raised.exception.code, "CATEGORY_SCAN_PROJECT_AMBIGUOUS")

    # Confirms one stale same-name record cannot be assigned arbitrarily between two detected category folders.
    def test_plan_rejects_name_fallback_when_detected_projects_share_name(self) -> None:
        """Reject name-only matching when more than one detected project has the same folder name."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory).resolve()
            self.category_project(parent, "Game", "Alpha")
            self.category_project(parent, "Tools", "Alpha")
            settings = {
                "local_projects": [{
                    "path": str(parent / "Legacy" / "Alpha"),
                    "name": "Alpha",
                    "category": "Legacy",
                }],
            }
            with self.assertRaises(AppError) as raised:
                localcategoryscan.category_scan_plan(settings, parent / "categories")

        self.assertEqual(raised.exception.code, "CATEGORY_SCAN_PROJECT_AMBIGUOUS")

    # Confirms private metadata stores receive the same proven mapping before repaired settings are saved.
    def test_reconcile_remaps_private_metadata_and_returns_local_state(self) -> None:
        """Remap Shared Resources and Local Activity, then save and return refreshed Local state."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory).resolve()
            target = self.category_project(parent, "Game", "Alpha")
            source = parent / "Game" / "Alpha"
            settings = {
                "workspace_mode": "local",
                "local_projects": [{
                    "path": str(source),
                    "name": "Alpha",
                    "category": "Game",
                    "category_foldered": True,
                }],
                "sync_chains": [],
            }
            controller = mock.Mock()
            controller.settings_store.config_path = parent / "settings.json"
            controller.settings_store.load.return_value = settings
            controller.settings_store.save.side_effect = lambda updates: {**settings, **updates}
            activity_store = mock.Mock()

            with mock.patch(
                "gitdesk.localcategoryscan.sharedresources.remap_installations",
            ) as remap_resources, mock.patch(
                "gitdesk.localcategoryscan.localactivity.activity_store",
                return_value=activity_store,
            ), mock.patch(
                "gitdesk.localcategoryscan.localprojects.local_projects_state",
                return_value={"projects": ["detected"]},
            ):
                response = localcategoryscan.reconcile_category_scan(controller, parent / "categories")

        remap_resources.assert_called_once_with(source, target)
        activity_store.remap_paths.assert_called_once_with(source, target)
        self.assertEqual(response["scan"]["detected_project_count"], 1)
        self.assertEqual(response["scan"]["matched_project_count"], 1)
        self.assertEqual(response["scan"]["ignored_project_count"], 0)
        self.assertEqual(response["scan"]["remapped_count"], 1)
        self.assertEqual(response["local"], {"projects": ["detected"]})

    # Confirms a later metadata failure reverses an earlier registry remap and never saves the scan plan.
    def test_reconcile_rolls_back_private_metadata_when_activity_remap_fails(self) -> None:
        """Restore Shared Resource paths when Local Activity metadata cannot be updated."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory).resolve()
            target = self.category_project(parent, "Game", "Alpha")
            source = parent / "Game" / "Alpha"
            settings = {
                "local_projects": [{
                    "path": str(source),
                    "name": "Alpha",
                    "category": "Game",
                    "category_foldered": True,
                }],
                "sync_chains": [],
            }
            controller = mock.Mock()
            controller.settings_store.config_path = parent / "settings.json"
            controller.settings_store.load.return_value = settings
            activity_store = mock.Mock()
            activity_store.remap_paths.side_effect = OSError("activity metadata unavailable")

            with mock.patch(
                "gitdesk.localcategoryscan.sharedresources.remap_installations",
            ) as remap_resources, mock.patch(
                "gitdesk.localcategoryscan.localactivity.activity_store",
                return_value=activity_store,
            ):
                with self.assertRaises(AppError) as raised:
                    localcategoryscan.reconcile_category_scan(controller, parent / "categories")

        self.assertEqual(raised.exception.code, "CATEGORY_SCAN_RECONCILIATION_FAILED")
        self.assertEqual(
            remap_resources.call_args_list,
            [mock.call(source, target), mock.call(target, source)],
        )
        controller.settings_store.save.assert_not_called()

    # Confirms cancelling the native folder dialog is a no-op rather than an empty authoritative scan.
    def test_bridge_cancellation_does_not_save_metadata(self) -> None:
        """Return cancellation without loading or saving settings."""

        controller = mock.Mock()
        with mock.patch("gitdesk.localcategory_bridge.choose_directory", return_value=""):
            response = handle_scan_local_categories(controller, {"initial_path": "/projects"})

        self.assertEqual(response, {"cancelled": True})
        controller.settings_store.load.assert_not_called()
        controller.settings_store.save.assert_not_called()

    # Protects the existing-project scan control, native action, repaired-state application, and package manifest.
    def test_scan_control_and_package_metadata_are_wired(self) -> None:
        """Require scan wiring in Local Projects and keep it out of the New Project favorite control."""

        root = Path(__file__).resolve().parents[1]
        local_render = (root / "src" / "gitdesk" / "ui" / "local-render.js").read_text(encoding="utf-8")
        scan_controller = (root / "src" / "gitdesk" / "ui" / "local-category-scan.js").read_text(encoding="utf-8")
        favorites = (root / "src" / "gitdesk" / "ui" / "local-parent-favorites.js").read_text(encoding="utf-8")
        bridge_source = (root / "src" / "gitdesk" / "localcategory_bridge.py").read_text(encoding="utf-8")
        frontend_source = (root / "src" / "gitdesk" / "frontend.py").read_text(encoding="utf-8")
        index_source = (root / "src" / "gitdesk" / "ui" / "index.html").read_text(encoding="utf-8")
        sources = (root / "src" / "gitdesk.egg-info" / "SOURCES.txt").read_text(encoding="utf-8")

        self.assertIn('id="scan-local-categories"', local_render)
        self.assertIn('callNative("scanLocalCategories"', scan_controller)
        self.assertIn("applyLocalResponse(data)", scan_controller)
        self.assertNotIn("scanLocalCategories", favorites)
        self.assertNotIn('id="scan-local-categories"', favorites)
        self.assertIn('"scanLocalCategories"', bridge_source)
        self.assertIn('"local-category-scan.js"', frontend_source)
        self.assertIn('<script src="./local-category-scan.js"></script>', index_source)
        self.assertIn("src/gitdesk/localcategoryscan.py", sources)
        self.assertIn("src/gitdesk/ui/local-category-scan.js", sources)
        self.assertIn("tests/testlocalcategoryscan.py", sources)


if __name__ == "__main__":
    unittest.main()
