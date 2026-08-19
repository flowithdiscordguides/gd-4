"""Regression coverage for deterministic Sync Chain snapshots and Git metadata exclusion."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from gitdesk.errors import AppError
from gitdesk.syncmirror import build_verified_snapshot, folder_fingerprint


# SyncMirrorTests checks source snapshot semantics without replacing a repository.
class SyncMirrorTests(unittest.TestCase):
    """Verify content hashing, nested .git exclusion, stable copying, and unsupported entries."""

    # Confirms Git metadata never contributes to a content fingerprint at any directory depth.
    def test_fingerprint_excludes_all_git_entries(self) -> None:
        """Ignore root and nested .git content while hashing the working snapshot."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "source").mkdir()
            source = root / "source"
            (source / "code.txt").write_text("stable", encoding="utf-8")
            (source / ".git").mkdir()
            (source / ".git" / "config").write_text("first", encoding="utf-8")
            (source / "nested" / ".git").mkdir(parents=True)
            (source / "nested" / ".git" / "HEAD").write_text("first", encoding="utf-8")
            before = folder_fingerprint(str(source))
            (source / ".git" / "config").write_text("second", encoding="utf-8")
            (source / "nested" / ".git" / "HEAD").write_text("second", encoding="utf-8")

            after = folder_fingerprint(str(source))

        self.assertEqual(before["digest"], after["digest"])
        self.assertEqual(before["file_count"], 1)

    # Confirms ordinary working files change the deterministic digest.
    def test_fingerprint_detects_working_content_change(self) -> None:
        """Produce a different digest after a source file changes."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory)
            file_path = source / "code.txt"
            file_path.write_text("one", encoding="utf-8")
            before = folder_fingerprint(str(source))
            file_path.write_text("two", encoding="utf-8")
            after = folder_fingerprint(str(source))

        self.assertNotEqual(before["digest"], after["digest"])

    # Confirms the staged tree exactly matches the source while leaving out Git metadata.
    def test_verified_snapshot_matches_source(self) -> None:
        """Copy files and empty directories into staging with the same content digest."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            staging = root / "staging"
            source.mkdir()
            (source / "empty").mkdir()
            (source / "folder").mkdir()
            (source / "folder" / "code.txt").write_text("content", encoding="utf-8")
            (source / ".git").mkdir()

            snapshot = build_verified_snapshot(source, staging)

            self.assertEqual(snapshot["digest"], folder_fingerprint(str(source))["digest"])
            self.assertTrue((staging / "empty").is_dir())
            self.assertFalse((staging / ".git").exists())

    # Confirms an unavailable source is reported before snapshot traversal begins.
    def test_missing_source_is_rejected(self) -> None:
        """Return a structured error for a source folder that does not exist."""

        with self.assertRaises(AppError) as raised:
            folder_fingerprint("/path/that/does/not/exist")

        self.assertEqual(raised.exception.code, "SYNC_SOURCE_INVALID")


if __name__ == "__main__":
    unittest.main()
