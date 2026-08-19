"""Regression coverage for project-scoped Sync Ignore persistence and exact mirror filtering."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from git import Repo

from gitdesk.frontend import INLINE_SCRIPTS, INLINE_STYLES
from gitdesk.syncignore import sync_ignore_state
from gitdesk.syncignore_store import SyncIgnoreStore, clean_ignore_paths
from gitdesk.synctransaction import begin_mirror_transaction


# SyncIgnoreTests keeps rules and repository replacements inside disposable folders.
class SyncIgnoreTests(unittest.TestCase):
    """Verify rule sanitation, project isolation, selectable trees, and first-edge mirror behavior."""

    # Confirms parent rules replace redundant children and malformed traversal paths never persist.
    def test_rules_are_relative_collapsed_and_project_scoped(self) -> None:
        """Store one minimal rule set without altering another project's rules."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = SyncIgnoreStore(root / "sync-ignore.json")
            first = store.save_project_rules(
                str(root / "Alpha"),
                ["dist/app.js", "dist", "../outside", ".git/config", "notes.txt"],
            )
            store.save_project_rules(str(root / "Beta"), ["private"])
            store.remap_project_path(str(root / "Alpha"), str(root / "Renamed Alpha"))
            loaded = store.load()
            alpha_rules = store.rules_for_project(str(root / "Renamed Alpha"))

        self.assertEqual(clean_ignore_paths(["dist/app.js", "dist"]), ["dist"])
        self.assertEqual(first["projects"][0]["ignored_paths"], ["dist", "notes.txt"])
        self.assertEqual(alpha_rules, ["dist", "notes.txt"])
        self.assertNotIn(str(root / "Alpha"), [item["project_path"] for item in loaded["projects"]])
        self.assertEqual(len(loaded["projects"]), 2)

    # Confirms the modal tree reads only one registered Local project version and reflects saved rules.
    def test_modal_tree_marks_current_version_entries(self) -> None:
        """Return checked files and directories from a selected saved Local version."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "Alpha"
            version = project / "01 init" / "v1 Alpha"
            (version / "dist").mkdir(parents=True)
            (version / "dist" / "bundle.js").write_text("built", encoding="utf-8")
            (version / "README.md").write_text("read me", encoding="utf-8")
            settings = {
                "local_projects": [{"path": str(project), "name": "Alpha", "category": ""}],
            }

            state = sync_ignore_state(settings, str(version), ["dist"])

        nodes = {node["path"]: node for node in state["tree"]["children"]}
        self.assertTrue(nodes["dist"]["checked"])
        self.assertFalse(nodes["README.md"]["checked"])
        self.assertEqual(state["project"]["path"], str(project))
        self.assertNotIn("truncated", state["tree"])

    # Confirms the editor never drops entries after the former 2,000-node display boundary.
    def test_modal_tree_returns_every_version_entry(self) -> None:
        """Return every selectable path in a version containing more than 2,000 direct files."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "Complete Tree"
            version = project / "01 init" / "v1 Complete Tree"
            version.mkdir(parents=True)
            for index in range(2005):
                (version / f"entry-{index:04}.txt").touch()
            settings = {
                "local_projects": [{"path": str(project), "name": "Complete Tree", "category": ""}],
            }

            state = sync_ignore_state(settings, str(version), [])

        self.assertEqual(len(state["tree"]["children"]), 2005)

    # Confirms ignored source paths are absent while the destination repository identity remains intact.
    def test_filtered_transaction_removes_ignored_destination_content(self) -> None:
        """Install only non-ignored files and preserve the destination .git directory."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            destination = root / "destination"
            (source / "dist").mkdir(parents=True)
            destination.mkdir()
            Repo.init(destination)
            (source / "keep.txt").write_text("current", encoding="utf-8")
            (source / "dist" / "bundle.js").write_text("ignored", encoding="utf-8")
            (destination / "dist").mkdir()
            (destination / "dist" / "old.js").write_text("stale", encoding="utf-8")

            transaction = begin_mirror_transaction(
                str(source),
                str(destination),
                frozenset({"dist"}),
            )
            transaction.commit()

            self.assertEqual((destination / "keep.txt").read_text(encoding="utf-8"), "current")
            self.assertFalse((destination / "dist").exists())
            self.assertTrue((destination / ".git").is_dir())

    # Confirms both source and static WebUI delivery include the new modal and metadata viewer assets.
    def test_sync_ignore_assets_are_packaged_in_dependency_order(self) -> None:
        """Deliver Sync Ignore after Local Mode and metadata viewing after Settings mounts."""

        self.assertIn("sync-ignore.css", INLINE_STYLES)
        self.assertLess(INLINE_SCRIPTS.index("local.js"), INLINE_SCRIPTS.index("sync-ignore.js"))
        self.assertLess(INLINE_SCRIPTS.index("sync-chain-render.js"), INLINE_SCRIPTS.index("sync-ignore.js"))
        self.assertLess(
            INLINE_SCRIPTS.index("settings-tabs.js"),
            INLINE_SCRIPTS.index("metadata-settings.js"),
        )

    # Confirms the shared modal shows complete names and starts every folder collapsed from either workspace.
    def test_sync_ignore_modal_is_complete_collapsed_and_available_in_sync_chain(self) -> None:
        """Keep one complete collapsed tree available to Local Mode and the selected Sync Chain project."""

        ui_root = Path(__file__).parents[1] / "src" / "gitdesk" / "ui"
        backend = (ui_root.parent / "syncignore.py").read_text(encoding="utf-8")
        script = (ui_root / "sync-ignore.js").read_text(encoding="utf-8")
        styles = (ui_root / "sync-ignore.css").read_text(encoding="utf-8")
        icons = (ui_root / "toolbar-icons.js").read_text(encoding="utf-8")
        chain_renderer = (ui_root / "sync-chain-render.js").read_text(encoding="utf-8")

        self.assertIn('<button id="save-sync-ignore" class="primary" type="button">Apply</button>', script)
        self.assertLess(script.index('id="save-sync-ignore"'), script.index('id="sync-ignore-tree"'))
        self.assertIn('<details class="sync-ignore-branch">', script)
        self.assertNotIn("MAX_SYNC_IGNORE_TREE_NODES", backend)
        self.assertNotIn("tree.truncated", script)
        complete_name_rule = (
            ".sync-ignore-node-name {\n  min-width: 0;\n  font-weight: 700;\n  overflow-wrap: anywhere;"
        )
        self.assertIn(complete_name_rule, styles)
        self.assertIn('class="sync-ignore-disclosure"', script)
        self.assertIn("parent.indeterminate = !parent.checked && hasSelection;", script)
        self.assertIn('data-sync-ignore-trigger="chain"', chain_renderer)
        self.assertIn('source.querySelector(".sync-chain-local-version")', script)
        self.assertIn("grid-template-rows: auto auto minmax(0, 1fr) auto;", styles)
        self.assertIn("scrollbar-gutter: stable;", styles)
        self.assertIn('M18.5 15.4v2.6M18.5 19.5h.01', icons)


if __name__ == "__main__":
    unittest.main()
