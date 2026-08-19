"""Regression coverage for Shared Resources revisions, safe merges, private manifests, and UI contracts."""

from __future__ import annotations

# Standard-library test helpers isolate physical catalogs, projects, and snapshot storage.
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

# GitDesk modules expose the release, install, document-link, and structured-error contracts under test.
from gitdesk.errors import AppError
from gitdesk import sharedresource_documents
from gitdesk import sharedresource_releases
from gitdesk.sharedresource_store import SharedResourceStore, clean_relative_metadata_path
from gitdesk import sharedresources


# SharedResourcesTests isolates every catalog, project version, and metadata file under a temporary directory.
class SharedResourcesTests(unittest.TestCase):
    """Verify resource lifecycle behavior without reading or changing the user's application metadata."""

    # Creates one writable catalog and one Local Mode version used by each focused test.
    def setUp(self) -> None:
        """Prepare isolated resource, version, document, and private metadata paths."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.catalog_root = self.root / "Shared-Resources" / "categories"
        self.catalog_root.mkdir(parents=True)
        self.resource_root = self.catalog_root / "coding"
        self.resource_root.mkdir()
        self.version_root = self.root / "project" / "01 init" / "v1 project"
        self.version_root.mkdir(parents=True)
        self.store = SharedResourceStore(self.root / "metadata" / "shared-resources.json")
        self.catalog_patches = [
            patch("gitdesk.aiskills.category_roots", return_value=[self.catalog_root]),
            patch("gitdesk.aiskills.writable_categories_root", return_value=self.catalog_root),
        ]
        for catalog_patch in self.catalog_patches:
            catalog_patch.start()

    # Stops path patches before TemporaryDirectory removes the isolated filesystem tree.
    def tearDown(self) -> None:
        """Restore catalog helpers and remove all isolated test files."""

        for catalog_patch in reversed(self.catalog_patches):
            catalog_patch.stop()
        self.temporary_directory.cleanup()

    # Writes one UTF-8 resource file while creating any nested resource directories it needs.
    def write_resource(self, relative_path: str, content: str) -> Path:
        """Create or replace one catalog file and return its physical path."""

        path = self.resource_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    # Confirms folder edits stay unpublished until an explicit record action advances the numbered release.
    def test_recorded_release_changes_only_on_explicit_update(self) -> None:
        """Keep v1 stable through a working edit, then record the changed bytes as v2."""

        legacy = sharedresource_releases.list_resources(self.store)["resources"][0]
        self.write_resource("AGENTS.md", "first\n")
        first = sharedresource_releases.record_release("coding", self.store)
        self.write_resource("AGENTS.md", "second\n")
        pending = sharedresource_releases.list_resources(self.store)["resources"][0]
        second = sharedresource_releases.record_release("coding", self.store)

        self.assertEqual(legacy["version_label"], "Legacy")
        self.assertIn("numbered version", legacy["tracking_message"])
        self.assertEqual(first["version"], 1)
        self.assertEqual(pending["version"], 1)
        self.assertEqual(second["version"], 2)
        self.assertNotEqual(first["revision"], second["revision"])

    # Protects unrelated history files through install, outdated detection, update, and explicit resource removal.
    def test_merge_and_removal_touch_only_manifest_paths(self) -> None:
        """Leave project histories untouched while managed resource paths are updated and removed."""

        history_path = self.version_root / ".codex" / "progress-history-project.md"
        history_path.parent.mkdir(parents=True)
        history_path.write_text("project history\n", encoding="utf-8")
        self.write_resource("AGENTS.md", "first\n")
        self.write_resource(".codex/skills/user-laws.md", "law one\n")
        sharedresource_releases.record_release("coding", self.store)

        installed = sharedresources.install_resource("coding", str(self.version_root), self.store)
        self.assertEqual(installed["file_count"], 2)
        self.assertEqual(history_path.read_text(encoding="utf-8"), "project history\n")

        self.write_resource(".codex/skills/user-laws.md", "law two\n")
        unchanged = sharedresources.version_resource_state(str(self.version_root), self.store)
        unchanged_state = next(item for item in unchanged["resources"] if item["name"] == "coding")
        self.assertEqual(unchanged_state["status"], "current")
        sharedresource_releases.record_release("coding", self.store)
        outdated = sharedresources.version_resource_state(str(self.version_root), self.store)
        coding_state = next(item for item in outdated["resources"] if item["name"] == "coding")
        self.assertEqual(coding_state["status"], "outdated")
        self.assertTrue(coding_state["update_available"])

        sharedresources.install_resource("coding", str(self.version_root), self.store)
        installed_law = self.version_root / ".codex" / "skills" / "user-laws.md"
        self.assertEqual(installed_law.read_text(encoding="utf-8"), "law two\n")
        self.assertEqual(history_path.read_text(encoding="utf-8"), "project history\n")

        removed = sharedresources.remove_resource("coding", str(self.version_root), self.store)
        self.assertEqual(removed["removed_file_count"], 2)
        self.assertFalse((self.version_root / "AGENTS.md").exists())
        self.assertFalse(installed_law.exists())
        self.assertEqual(history_path.read_text(encoding="utf-8"), "project history\n")

    # Ensures copied Local Mode versions inherit revision awareness instead of appearing as untracked loose files.
    def test_version_copy_clones_private_installation_manifest(self) -> None:
        """Clone installation metadata alongside a physically copied version folder."""

        self.write_resource("AGENTS.md", "resource\n")
        sharedresource_releases.record_release("coding", self.store)
        sharedresources.install_resource("coding", str(self.version_root), self.store)
        target = self.version_root.with_name("v2 resource management")
        shutil.copytree(self.version_root, target)

        sharedresources.clone_installations(str(self.version_root), str(target), self.store)
        state = sharedresources.version_resource_state(str(target), self.store)
        coding_state = next(item for item in state["resources"] if item["name"] == "coding")
        self.assertTrue(coding_state["tracked"])
        self.assertEqual(coding_state["status"], "current")

    # Protects the migration boundary while allowing a recorded release to merge over matching loose-copy paths.
    def test_preexisting_copy_stays_untracked_until_managed_restore(self) -> None:
        """Merge matching loose files through Apply without claiming or replacing unrelated project content."""

        resource_file = self.write_resource("AGENTS.md", "resource\n")
        sharedresource_releases.record_release("coding", self.store)
        loose_copy = self.version_root / "AGENTS.md"
        shutil.copy2(resource_file, loose_copy)
        unrelated = self.version_root / "project-notes.md"
        unrelated.write_text("keep me\n", encoding="utf-8")

        before = sharedresources.version_resource_state(str(self.version_root), self.store)
        before_state = next(item for item in before["resources"] if item["name"] == "coding")
        self.assertFalse(before_state["installed"])

        sharedresources.apply_resource_selection(str(self.version_root), ["coding"], self.store)
        after = sharedresources.version_resource_state(str(self.version_root), self.store)
        after_state = next(item for item in after["resources"] if item["name"] == "coding")
        self.assertTrue(after_state["tracked"])
        self.assertEqual(after_state["installed_version_label"], "v1")
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep me\n")

    # Converts a tracked legacy manifest by overlaying a numbered snapshot without replacing the project folder.
    def test_legacy_installation_merges_numbered_release_without_replacing_other_files(self) -> None:
        """Replace matching resource paths, preserve other files, and advance legacy metadata to v1."""

        self.write_resource("AGENTS.md", "numbered release\n")
        sharedresource_releases.record_release("coding", self.store)
        managed_path = self.version_root / "AGENTS.md"
        managed_path.write_text("legacy copy\n", encoding="utf-8")
        unrelated = self.version_root / "personal-notes.md"
        unrelated.write_text("untouched\n", encoding="utf-8")
        self.store.set_installation(
            str(self.version_root.resolve()),
            "coding",
            {"version": 0, "revision": "0" * 64, "files": {"AGENTS.md": "0" * 64}},
        )

        before = sharedresources.version_resource_state(str(self.version_root), self.store)
        legacy_state = next(item for item in before["resources"] if item["name"] == "coding")
        self.assertEqual(legacy_state["status"], "legacy")
        self.assertTrue(legacy_state["merge_available"])
        sharedresources.install_resource("coding", str(self.version_root), self.store)
        after = sharedresources.version_resource_state(str(self.version_root), self.store)
        numbered_state = next(item for item in after["resources"] if item["name"] == "coding")

        self.assertEqual(managed_path.read_text(encoding="utf-8"), "numbered release\n")
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "untouched\n")
        self.assertEqual(numbered_state["installed_version_label"], "v1")
        self.assertFalse(numbered_state["installed_legacy"])

    # Removal leaves project edits in place when their bytes no longer match the installed ownership manifest.
    def test_removal_preserves_modified_managed_file(self) -> None:
        """Drop tracking but retain a resource path that the project changed after installation."""

        self.write_resource("AGENTS.md", "resource\n")
        sharedresource_releases.record_release("coding", self.store)
        sharedresources.install_resource("coding", str(self.version_root), self.store)
        installed_file = self.version_root / "AGENTS.md"
        installed_file.write_text("project edit\n", encoding="utf-8")

        result = sharedresources.remove_resource("coding", str(self.version_root), self.store)

        self.assertEqual(result["removed_file_count"], 0)
        self.assertEqual(result["preserved_file_count"], 1)
        self.assertEqual(installed_file.read_text(encoding="utf-8"), "project edit\n")

    # A newer release retires omitted owned bytes while preserving an omitted path changed inside the project.
    def test_update_retires_only_unchanged_paths_removed_from_release(self) -> None:
        """Remove stale owned bytes but preserve project edits when the next release omits both paths."""

        retired = self.write_resource("retired.txt", "owned\n")
        modified = self.write_resource("modified.txt", "owned\n")
        self.write_resource("current.txt", "one\n")
        sharedresource_releases.record_release("coding", self.store)
        sharedresources.install_resource("coding", str(self.version_root), self.store)
        (self.version_root / "modified.txt").write_text("project edit\n", encoding="utf-8")
        retired.unlink()
        modified.unlink()
        self.write_resource("current.txt", "two\n")
        sharedresource_releases.record_release("coding", self.store)

        result = sharedresources.install_resource("coding", str(self.version_root), self.store)

        self.assertEqual(result["retired_file_count"], 1)
        self.assertEqual(result["preserved_retired_file_count"], 1)
        self.assertFalse((self.version_root / "retired.txt").exists())
        self.assertEqual((self.version_root / "modified.txt").read_text(encoding="utf-8"), "project edit\n")
        self.assertEqual((self.version_root / "current.txt").read_text(encoding="utf-8"), "two\n")

    # Confirms Document Builder remembers a destination and produces a new resource revision on later updates.
    def test_document_publish_link_reuses_resource_destination(self) -> None:
        """Publish and update one numbered document file through the same saved resource link."""

        self.write_resource("AGENTS.md", "existing\n")
        document_file = self.root / "documents" / "01 user-laws.md"
        document_file.parent.mkdir()
        document_file.write_text("first document\n", encoding="utf-8")

        published = sharedresource_documents.publish_document_file(
            str(document_file),
            "coding",
            ".codex/skills/user-laws.md",
            self.store,
        )
        document_file.write_text("second document\n", encoding="utf-8")
        updated = sharedresource_documents.update_document_file(str(document_file), self.store)

        target = self.resource_root / ".codex" / "skills" / "user-laws.md"
        self.assertEqual(target.read_text(encoding="utf-8"), "second document\n")
        self.assertEqual(published["version_label"], "Legacy")
        self.assertEqual(updated["version"], 1)
        self.assertEqual(updated["link"]["target_path"], ".codex/skills/user-laws.md")

    # Rejects rooted, traversal, and repository metadata targets across every resource path boundary.
    def test_resource_relative_paths_reject_unsafe_targets(self) -> None:
        """Reject traversal, rooted, drive, and .git paths before they can be normalized as relative."""

        unsafe_paths = (
            "../secret",
            "/absolute/file",
            r"\absolute\file",
            r"\\server\share",
            "C:/secret",
            ".git/config",
        )
        rejecting_validators = (sharedresources.clean_relative_path, sharedresource_releases.clean_working_path)
        # Public and release validators must report the same structured error for every unsafe path spelling.
        for unsafe_path in unsafe_paths:
            for validator in rejecting_validators:
                with self.subTest(path=unsafe_path, validator=validator.__name__):
                    with self.assertRaises(AppError) as raised:
                        validator(unsafe_path)
                    self.assertEqual(raised.exception.code, "SHARED_RESOURCE_PATH_INVALID")
            # Persisted metadata is sanitized rather than raised, but it must reject the identical path set.
            with self.subTest(path=unsafe_path, validator="clean_relative_metadata_path"):
                self.assertEqual(clean_relative_metadata_path(unsafe_path), "")

    # Protects the named controls and matching source/packaged asset order that make both workflows reachable.
    def test_frontend_exposes_version_and_document_resource_workflows(self) -> None:
        """Require Shared Resources controls, dialogs, neutral labels, and dependency ordering in source."""

        project_root = Path(__file__).resolve().parents[1]
        ui_root = project_root / "src" / "gitdesk" / "ui"
        local_source = (ui_root / "local-render.js").read_text(encoding="utf-8")
        local_workspace_source = (ui_root / "local-version-workspace.js").read_text(encoding="utf-8")
        local_detail_source = (ui_root / "local-version-detail.js").read_text(encoding="utf-8")
        local_detail_style = (ui_root / "local-version-detail.css").read_text(encoding="utf-8")
        local_controller_source = (ui_root / "local.js").read_text(encoding="utf-8")
        document_source = (ui_root / "document-builder-ui.js").read_text(encoding="utf-8")
        document_layout_source = (ui_root / "document-builder-layout.css").read_text(encoding="utf-8")
        manager_source = (ui_root / "shared-resources.js").read_text(encoding="utf-8")
        settings_source = (ui_root / "aiskills.js").read_text(encoding="utf-8")
        index_source = (ui_root / "index.html").read_text(encoding="utf-8")
        frontend_source = (project_root / "src" / "gitdesk" / "frontend.py").read_text(encoding="utf-8")

        self.assertIn('id="manage-local-shared-resources"', local_workspace_source)
        self.assertIn('id="local-selected-version-resources"', local_source)
        self.assertLess(
            local_workspace_source.index('id="open-local-vscode"'),
            local_workspace_source.index('id="manage-local-shared-resources"'),
        )
        self.assertNotIn("manage-version-shared-resources", local_detail_source)
        self.assertIn('<button class="local-version-row${active}"', local_detail_source)
        self.assertIn(".local-version-listing", local_detail_style)
        self.assertIn("#manage-local-shared-resources", local_detail_style)
        self.assertIn(
            "sharedResourceManager.bindLocal({ runAction, getVersionPath: activeVersionPath });",
            local_controller_source,
        )
        self.assertNotIn('id="manage-document-shared-resources"', document_source)
        self.assertIn("overflow-x: hidden;\n  overflow-y: auto;", document_layout_source)
        self.assertIn('id="add-document-shared-resource"', document_source)
        self.assertIn('id="update-document-shared-resource"', document_source)
        self.assertIn("Numbered resources merge like Finder", manager_source)
        self.assertIn("localConfig.getVersionPath()", manager_source)
        self.assertIn("Merge ${resource.version_label}", manager_source)
        self.assertIn("Shared Resources", settings_source)
        self.assertIn("recordSharedResourceUpdate", settings_source)
        self.assertNotIn(">AI skills<", settings_source)
        for source in (index_source, frontend_source):
            self.assertLess(source.index("shared-resources.js"), source.index("local.js"))
            self.assertLess(source.index("shared-resources.js"), source.index("document-builder.js"))


if __name__ == "__main__":
    unittest.main()
