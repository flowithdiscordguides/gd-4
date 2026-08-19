"""Regression coverage for unconditional Sync Chain working-tree replacement and rollback safety."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from git import Repo

from gitdesk.synctransaction import begin_mirror_transaction, recover_interrupted_transaction, write_journal


# SyncTransactionTests creates real disposable Git repositories without network access.
class SyncTransactionTests(unittest.TestCase):
    """Verify complete replacement, .git preservation, rollback, commit, and fingerprint guards."""

    # Creates separate source and destination folders with an initialized destination repository.
    def folders(self, root: Path) -> tuple[Path, Path]:
        """Return populated source and destination paths for one transaction test."""

        source = root / "source"
        destination = root / "destination"
        source.mkdir()
        destination.mkdir()
        Repo.init(destination)
        (source / "current.txt").write_text("new", encoding="utf-8")
        (destination / "stale.txt").write_text("old", encoding="utf-8")
        return source, destination

    # Confirms commit keeps the new mirror, removes stale files, and retains repository identity.
    def test_commit_installs_complete_mirror_and_preserves_git(self) -> None:
        """Finalize a staged snapshot while retaining the destination's original .git directory."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            source, destination = self.folders(Path(temporary_directory))
            git_path = destination / ".git"
            transaction = begin_mirror_transaction(str(source), str(destination))
            self.assertTrue((transaction.backup / ".git").exists())
            warning = transaction.commit()

            self.assertEqual(warning, "")
            self.assertTrue(git_path.exists())
            self.assertEqual((destination / "current.txt").read_text(encoding="utf-8"), "new")
            self.assertFalse((destination / "stale.txt").exists())

    # Confirms explicit rollback restores the complete prior working tree after installation.
    def test_rollback_restores_previous_destination(self) -> None:
        """Restore stale destination content and remove the newly staged source content."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            source, destination = self.folders(Path(temporary_directory))
            transaction = begin_mirror_transaction(str(source), str(destination))
            transaction.rollback()

            self.assertTrue((destination / ".git").exists())
            self.assertEqual((destination / "stale.txt").read_text(encoding="utf-8"), "old")
            self.assertFalse((destination / "current.txt").exists())

    # Confirms every repeated sync replaces destination edits without a divergence gate or override flag.
    def test_repeated_sync_unconditionally_replaces_destination(self) -> None:
        """Replace every non-Git destination path with the current source snapshot."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            source, destination = self.folders(Path(temporary_directory))
            first = begin_mirror_transaction(str(source), str(destination))
            first.commit()
            (destination / "manual-edit.txt").write_text("replace me", encoding="utf-8")
            (destination / ".github").mkdir()
            (destination / ".github" / "old.yml").write_text("old", encoding="utf-8")
            (destination / ".gitignore").write_text("old-ignore", encoding="utf-8")
            (destination / ".git" / "identity-marker").write_text("destination", encoding="utf-8")
            (source / ".github").mkdir()
            (source / ".github" / "build.yml").write_text("new", encoding="utf-8")
            (source / ".gitignore").write_text("new-ignore", encoding="utf-8")
            (source / ".git").mkdir()
            (source / ".git" / "source-marker").write_text("source", encoding="utf-8")

            second = begin_mirror_transaction(str(source), str(destination))
            second.commit()

            self.assertFalse((destination / "manual-edit.txt").exists())
            self.assertTrue((destination / "current.txt").exists())
            self.assertTrue((destination / ".git").exists())
            self.assertFalse((destination / ".github" / "old.yml").exists())
            self.assertTrue((destination / ".github" / "build.yml").exists())
            self.assertEqual((destination / ".gitignore").read_text(encoding="utf-8"), "new-ignore")
            self.assertEqual((destination / ".git" / "identity-marker").read_text(encoding="utf-8"), "destination")
            self.assertFalse((destination / ".git" / "source-marker").exists())

    # Reproduces the former crash window where .git had moved out of the rollback backup.
    def test_recovery_reclaims_git_metadata_from_legacy_staging(self) -> None:
        """Restore a destination without discarding metadata moved by the former transaction design."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _source, destination = self.folders(root)
            staging = root / ".gitdesk-sync-stage-legacy"
            backup = root / ".gitdesk-sync-backup-legacy"
            journal = root / ".gitdesk-sync-destination.journal.json"
            staging.mkdir()
            destination.rename(backup)
            shutil.move(str(backup / ".git"), str(staging / ".git"))
            write_journal(journal, {
                "destination": str(destination),
                "staging": str(staging),
                "backup": str(backup),
                "phase": "metadata_moved",
            })

            recover_interrupted_transaction(destination, journal)

            self.assertTrue((destination / ".git").exists())
            self.assertTrue((destination / "stale.txt").exists())
            self.assertFalse(staging.exists())
            self.assertFalse(backup.exists())
            self.assertFalse(journal.exists())
            self.assertEqual(Repo(destination).working_tree_dir, str(destination))


if __name__ == "__main__":
    unittest.main()
