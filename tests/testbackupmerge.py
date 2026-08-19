"""Regression contracts for verified Backup version merge-down transactions."""

from __future__ import annotations

# Disposable trees and controlled copy failures prove parent and child ownership boundaries.
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

# Backup services provide real manifests, snapshots, merge transactions, and private state replacement.
from gitdesk.backup_inventory import LOCAL_BACKUP_FOLDER, directory_source
from gitdesk.backup_merge import merge_backup_versions
from gitdesk.backup_selection import apply_backup_selection
from gitdesk.backup_snapshot import BACKUP_LOG_NAME, BACKUP_MANIFEST_NAME, create_backup_snapshot
from gitdesk.backup_store import BackupStore, clean_state
from gitdesk.errors import AppError
from gitdesk.frontend import UI_DIR


# BackupMergeTests uses real dated folders while keeping every fixture outside user data.
class BackupMergeTests(unittest.TestCase):
    """Verify ordered child replay, partial scopes, rollback, metadata, and UI delivery."""

    # Builds one full parent and one partial child containing an overwrite plus an explicit deletion.
    def partial_lineage(self, root: Path) -> tuple[Path, dict, dict, dict]:
        """Return a destination, source, full parent, and partial child fixture."""

        destination = root / "Backups"
        source_root = root / "Project"
        destination.mkdir()
        source_root.mkdir()
        (source_root / "selected.txt").write_text("parent-selected", encoding="utf-8")
        (source_root / "retained.txt").write_text("parent-retained", encoding="utf-8")
        (source_root / "deleted.txt").write_text("remove-me", encoding="utf-8")
        source = directory_source(LOCAL_BACKUP_FOLDER, source_root, "Project")
        parent = create_backup_snapshot(str(destination), [source], "")
        (source_root / "selected.txt").write_text("child-selected", encoding="utf-8")
        (source_root / "retained.txt").write_text("live-but-unselected", encoding="utf-8")
        (source_root / "deleted.txt").unlink()
        selected_sources, _selection = apply_backup_selection([source], [{
            "source_id": source["id"],
            "rules": {"selected.txt": True, "deleted.txt": True},
        }])
        child = create_backup_snapshot(
            str(destination),
            selected_sources,
            parent["version"]["path"],
        )
        return destination, source, parent, child

    # Confirms selected overwrites and deletions reach the parent while excluded and child content remain unchanged.
    def test_partial_child_merges_into_parent_without_mutating_child(self) -> None:
        """Replay only the child's confirmed selection into a verified cumulative parent."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            destination, source, parent, child = self.partial_lineage(Path(temporary_directory))
            versions = [child["version"], parent["version"]]
            child_path = Path(child["version"]["path"])
            child_manifest_before = (child_path / BACKUP_MANIFEST_NAME).read_bytes()

            result = merge_backup_versions(
                str(destination),
                versions,
                parent["version"]["path"],
            )

            parent_target = Path(parent["version"]["path"]) / source["snapshot_path"]
            child_target = child_path / source["snapshot_path"]
            parent_log = json.loads(
                (Path(parent["version"]["path"]) / BACKUP_LOG_NAME).read_text(encoding="utf-8"),
            )
            self.assertEqual((parent_target / "selected.txt").read_text(encoding="utf-8"), "child-selected")
            self.assertEqual((parent_target / "retained.txt").read_text(encoding="utf-8"), "parent-retained")
            self.assertFalse((parent_target / "deleted.txt").exists())
            self.assertFalse((child_target / "retained.txt").exists())
            self.assertEqual((child_path / BACKUP_MANIFEST_NAME).read_bytes(), child_manifest_before)
            self.assertEqual(result["merged_children"], 1)
            self.assertEqual(len(parent_log["merge_down_history"]), 1)

    # Confirms every newer child replays chronologically so the newest content owns the final parent conflict.
    def test_multiple_children_merge_oldest_to_newest(self) -> None:
        """Apply all versions above the selected parent and retain each original child."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = root / "Backups"
            source_root = root / "Project"
            destination.mkdir()
            source_root.mkdir()
            value_path = source_root / "value.txt"
            source = directory_source(LOCAL_BACKUP_FOLDER, source_root, "Project")
            value_path.write_text("parent", encoding="utf-8")
            parent = create_backup_snapshot(str(destination), [source], "")
            value_path.write_text("child-one", encoding="utf-8")
            child_one = create_backup_snapshot(str(destination), [source], parent["version"]["path"])
            value_path.write_text("child-two", encoding="utf-8")
            child_two = create_backup_snapshot(str(destination), [source], child_one["version"]["path"])
            versions = [child_two["version"], child_one["version"], parent["version"]]

            result = merge_backup_versions(str(destination), versions, parent["version"]["path"])

            relative = Path(source["snapshot_path"]) / "value.txt"
            self.assertEqual(Path(parent["version"]["path"]).joinpath(relative).read_text(), "child-two")
            self.assertEqual(Path(child_one["version"]["path"]).joinpath(relative).read_text(), "child-one")
            self.assertEqual(Path(child_two["version"]["path"]).joinpath(relative).read_text(), "child-two")
            self.assertEqual(result["merged_children"], 2)

    # Confirms a copy failure removes staging and leaves both the original parent and child intact.
    def test_failed_merge_rolls_back_without_partial_parent_changes(self) -> None:
        """Retain original versions when staged child replay cannot complete."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            destination, source, parent, child = self.partial_lineage(Path(temporary_directory))
            versions = [child["version"], parent["version"]]
            parent_target = Path(parent["version"]["path"]) / source["snapshot_path"]
            with patch("gitdesk.backup_merge.shutil.copy2", side_effect=OSError("copy failed")):
                with self.assertRaises(AppError) as merge_error:
                    merge_backup_versions(str(destination), versions, parent["version"]["path"])
            remaining_names = [path.name for path in destination.iterdir()]

            self.assertEqual(merge_error.exception.code, "BACKUP_MERGE_COPY_FAILED")
            self.assertEqual((parent_target / "selected.txt").read_text(), "parent-selected")
            self.assertNotIn(".gitdesk-backup-merge-stage-", " ".join(remaining_names))

    # Confirms parent metadata replacement never changes which child remains the latest scan baseline.
    def test_replacing_parent_metadata_preserves_latest_snapshot(self) -> None:
        """Update one parent row without reordering history or promoting it to latest."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = BackupStore(Path(temporary_directory) / "backup-state.json")
            parent = {
                "name": "gitdesk backups parent",
                "path": "/Backups/parent",
                "created_at": "2026-01-01T00:00:00Z",
            }
            child = {
                "name": "gitdesk backups child",
                "path": "/Backups/child",
                "created_at": "2026-01-02T00:00:00Z",
            }
            store.write(clean_state({"versions": [child, parent], "latest_snapshot": child["path"]}))

            state = store.replace_version({**parent, "file_count": 9, "total_bytes": 42})

        self.assertEqual(state["latest_snapshot"], child["path"])
        self.assertEqual([item["path"] for item in state["versions"]], [child["path"], parent["path"]])
        self.assertEqual(state["versions"][1]["file_count"], 9)

    # Confirms the visible version list owns one parent selector and the single merge-down bridge action.
    def test_merge_down_ui_contract_is_delivered(self) -> None:
        """Keep parent choice attached to version rows and route one explicit merge action."""

        mode_source = (UI_DIR / "backup-mode.js").read_text(encoding="utf-8")

        self.assertIn('id="merge-down-backup"', mode_source)
        self.assertIn('name="backup-parent-version"', mode_source)
        self.assertIn('runAction("mergeDownBackupVersions"', mode_source)
        self.assertIn("state.parentVersionPath", mode_source)


if __name__ == "__main__":
    unittest.main()
