"""Regression coverage for default-continuing Backup item failures and private reveal paths."""

from __future__ import annotations

import errno
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gitdesk.backup_inventory import LOCAL_BACKUP_FOLDER, directory_source
from gitdesk.backup_jobs import BackupJob
from gitdesk.backup_snapshot import BACKUP_LOG_NAME, BACKUP_MANIFEST_NAME, create_backup_snapshot
from gitdesk.errors import AppError
from gitdesk.frontend import INLINE_SCRIPTS, UI_DIR
from gitdesk.nativeopen import reveal_path


# BackupSkipTests exercises item-local continuation without launching the desktop application.
class BackupSkipTests(unittest.TestCase):
    """Verify exact installed subsets, durable ledgers, retry state, and safe native reveal ownership."""

    # Creates one two-file source whose blocked item can fail independently from copied content.
    def source_fixture(self, root: Path) -> tuple[dict[str, str], Path]:
        """Return one registered directory source and its physical root."""

        source_root = root / "Project"
        source_root.mkdir()
        source_root.joinpath("copied.txt").write_text("copied", encoding="utf-8")
        source_root.joinpath("blocked.txt").write_text("blocked", encoding="utf-8")
        return directory_source(LOCAL_BACKUP_FOLDER, source_root, "Project"), source_root

    # Raises one realistic exclusive-create collision only for the selected destination item.
    def collision_open(self, original_open):
        """Return a Path.open replacement that reports File exists for blocked.txt writes."""

        def open_path(path: Path, *args, **kwargs):
            mode = str(args[0] if args else kwargs.get("mode") or "r")
            if path.name == "blocked.txt" and mode == "xb":
                with original_open(path, "wb") as destination_metadata:
                    destination_metadata.write(b"destination-generated metadata")
                raise FileExistsError(errno.EEXIST, "File exists", str(path))
            return original_open(path, *args, **kwargs)

        return open_path

    # Confirms one File exists error creates a verified subset and a complete location ledger.
    def test_item_collision_continues_and_records_exact_installed_subset(self) -> None:
        """Install copied content, omit the failed item, and retain its original location only in the log."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = root / "Backups"
            destination.mkdir()
            source, source_root = self.source_fixture(root)
            original_open = Path.open
            with patch.object(Path, "open", new=self.collision_open(original_open)):
                result = create_backup_snapshot(str(destination), [source], "")
            snapshot = Path(result["version"]["path"])
            target = snapshot / source["snapshot_path"]
            log = json.loads((snapshot / BACKUP_LOG_NAME).read_text(encoding="utf-8"))
            manifest = json.loads((snapshot / BACKUP_MANIFEST_NAME).read_text(encoding="utf-8"))
            copied_exists = (target / "copied.txt").is_file()
            blocked_exists = (target / "blocked.txt").exists()
            blocked_source_path = str(source_root / "blocked.txt")

        self.assertTrue(copied_exists)
        self.assertTrue(blocked_exists)
        self.assertEqual(result["version"]["skipped_count"], 1)
        self.assertNotIn("source_path", result["skipped_items"][0])
        self.assertEqual(log["skipped_items"][0]["source_path"], blocked_source_path)
        self.assertNotIn(f'{source["snapshot_path"]}/blocked.txt', manifest["entries"])
        self.assertTrue(result["pending_changes"]["has_changes"])

    # Confirms an omitted item stays different from the latest manifest and is copied by the next sync.
    def test_skipped_item_is_retried_by_the_next_snapshot(self) -> None:
        """Retry a prior skipped item instead of treating it as already backed up."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = root / "Backups"
            destination.mkdir()
            source, _source_root = self.source_fixture(root)
            original_open = Path.open
            with patch.object(Path, "open", new=self.collision_open(original_open)):
                first = create_backup_snapshot(str(destination), [source], "")
            second = create_backup_snapshot(str(destination), [source], first["version"]["path"])
            copied = Path(second["version"]["path"]) / source["snapshot_path"] / "blocked.txt"
            copied_exists = copied.is_file()

        self.assertTrue(copied_exists)
        self.assertEqual(second["skipped_items"], [])
        self.assertFalse(second["pending_changes"]["has_changes"])

    # Confirms a full or failed destination remains fatal instead of converting every later item into noise.
    def test_destination_wide_write_failure_still_rolls_back_transaction(self) -> None:
        """Stop and remove staging when the destination reports no space."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = root / "Backups"
            destination.mkdir()
            source, _source_root = self.source_fixture(root)
            original_open = Path.open

            # Reports a transaction-wide capacity failure only for the blocked destination file.
            def no_space(path: Path, *args, **kwargs):
                mode = str(args[0] if args else kwargs.get("mode") or "r")
                if path.name == "blocked.txt" and mode == "xb":
                    raise OSError(errno.ENOSPC, "No space left on device", str(path))
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "open", new=no_space):
                with self.assertRaises(AppError) as failure:
                    create_backup_snapshot(str(destination), [source], "")
            remaining = list(destination.iterdir())

        self.assertEqual(failure.exception.code, "BACKUP_DESTINATION_WRITE_FAILED")
        self.assertEqual(remaining, [])

    # Confirms a background job strips private source locations from every public polling payload.
    def test_job_retains_private_skipped_paths_by_opaque_id(self) -> None:
        """Keep reveal locations process-owned while public results expose only item ids."""

        job = BackupJob(lambda progress, gate: {
            "skipped_items": [{"id": "opaque", "name": "blocked.txt"}],
            "_skipped_source_paths": {"opaque": "/source/blocked.txt"},
        })
        job.run()

        self.assertNotIn("_skipped_source_paths", job.payload()["result"])
        self.assertEqual(job.skipped_path("opaque"), "/source/blocked.txt")

    # Confirms macOS reveal uses Finder selection rather than opening or displaying a raw path in the UI.
    def test_reveal_path_uses_finder_reveal_and_frontend_loads_before_transfer(self) -> None:
        """Use open -R and deliver the skipped ledger before its parent transfer module."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            item = Path(temporary_directory) / "blocked.txt"
            item.write_text("blocked", encoding="utf-8")
            with patch("gitdesk.nativeopen.platform.system", return_value="Darwin"):
                with patch("gitdesk.nativeopen.subprocess.Popen") as launcher:
                    reveal_path(str(item))

        launcher.assert_called_once_with(["open", "-R", str(item.resolve())])
        self.assertLess(
            INLINE_SCRIPTS.index("backup-skipped-items.js"),
            INLINE_SCRIPTS.index("backup-transfer-modal.js"),
        )
        skipped_source = (UI_DIR / "backup-skipped-items.js").read_text(encoding="utf-8")
        self.assertIn('callNative("openBackupSkippedItem", { job_id: state.jobId, item_id: itemId })', skipped_source)
        self.assertNotIn("source_path", skipped_source)


if __name__ == "__main__":
    unittest.main()
