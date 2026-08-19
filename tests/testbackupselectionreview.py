"""Focused regression contracts for detected-change Backup selection review."""

from __future__ import annotations

# Standard-library fixtures isolate available and unavailable source roots.
from pathlib import Path
import tempfile
import unittest

# Backup services expose the pure scan, selection, persistence, and asset contracts under review.
from gitdesk.backup_inventory import LOCAL_BACKUP_FOLDER, directory_source
from gitdesk.backup_manifest import manifest_diff
from gitdesk.backup_selection import changed_backup_selection
from gitdesk.backup_store import BACKUP_STATE_SCHEMA_VERSION, clean_scan, clean_state
from gitdesk.frontend import INLINE_SCRIPTS, UI_DIR


# BackupSelectionReviewTests verifies changed owners remain complete and become the only sync defaults.
class BackupSelectionReviewTests(unittest.TestCase):
    """Verify detected-first defaults, safe persistence, and frontend delivery order."""

    # Builds a minimal manifest entry whose identity can be changed independently from its owner.
    def entry(self, source_id: str, digest: str = "digest") -> dict[str, object]:
        """Return one deterministic file entry for manifest-diff fixtures."""

        return {
            "source_id": source_id,
            "kind": "file",
            "size": 1,
            "digest": digest,
            "link_target": "",
        }

    # Confirms added, modified, and deleted paths all identify their owning source roots.
    def test_manifest_diff_reports_every_changed_source_owner(self) -> None:
        """Return complete changed source identifiers across all change kinds."""

        previous = {
            "entries": {
                "local/deleted.txt": self.entry("local-source"),
                "repo/modified.txt": self.entry("repo-source", "old"),
            },
        }
        current = {
            "entries": {
                "repo/modified.txt": self.entry("repo-source", "new"),
                "media/added.txt": self.entry("media-source"),
            },
        }

        changes = manifest_diff(previous, current)

        self.assertEqual(
            changes["changed_source_ids"],
            ["local-source", "media-source", "repo-source"],
        )

    # Confirms the 500-row display cap never truncates changed folder ownership.
    def test_changed_source_owners_remain_complete_when_path_details_truncate(self) -> None:
        """Retain every changed source identifier beyond the visible path sample."""

        entries = {
            f"local/{index:04d}.txt": self.entry("local-source")
            for index in range(501)
        }
        entries["zzzz-media/changed.txt"] = self.entry("media-source")

        changes = manifest_diff(None, {"entries": entries})

        self.assertTrue(changes["truncated"])
        self.assertEqual(len(changes["changes"]), 500)
        self.assertEqual(changes["changed_source_ids"], ["local-source", "media-source"])

    # Confirms stored changed-source identifiers are private, bounded, unique, and schema-versioned.
    def test_scan_state_sanitizes_changed_source_identifiers(self) -> None:
        """Clean malformed identifiers without losing valid detected owners."""

        scan = clean_scan({
            "changed_source_ids": ["local-source", "local-source", "", None, "repo-source"],
        })
        state = clean_state({"scan": scan})

        self.assertEqual(scan["changed_source_ids"], ["local-source", "repo-source"])
        self.assertEqual(state["schema_version"], BACKUP_STATE_SCHEMA_VERSION)
        self.assertEqual(BACKUP_STATE_SCHEMA_VERSION, 5)

    # Confirms only available detected roots start checked while every other root stays optional.
    def test_changed_backup_selection_checks_only_available_detected_roots(self) -> None:
        """Return root rules for available changed sources and nothing else."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            changed_path = root / "Changed"
            unchanged_path = root / "Unchanged"
            changed_path.mkdir()
            unchanged_path.mkdir()
            sources = [
                directory_source(LOCAL_BACKUP_FOLDER, changed_path, "Changed"),
                directory_source(LOCAL_BACKUP_FOLDER, unchanged_path, "Unchanged"),
                directory_source(LOCAL_BACKUP_FOLDER, root / "Missing", "Missing"),
            ]
            changed_ids = [sources[0]["id"], sources[2]["id"]]

            selection = changed_backup_selection(sources, changed_ids)

        self.assertEqual(selection, [{"source_id": sources[0]["id"], "rules": {"": True}}])

    # Confirms model, controller, static shell, and inline assembly share one dependency order and UI contract.
    def test_detected_change_selection_assets_and_contract_are_delivered(self) -> None:
        """Load the pure model before the modal and preserve detected-first controls."""

        self.assertLess(
            INLINE_SCRIPTS.index("backup-transfer-modal.js"),
            INLINE_SCRIPTS.index("backup-selection-model.js"),
        )
        self.assertLess(
            INLINE_SCRIPTS.index("backup-selection-model.js"),
            INLINE_SCRIPTS.index("backup-selection-modal.js"),
        )
        model_source = (UI_DIR / "backup-selection-model.js").read_text(encoding="utf-8")
        modal_source = (UI_DIR / "backup-selection-modal.js").read_text(encoding="utf-8")
        css_source = (UI_DIR / "backup-selection-modal.css").read_text(encoding="utf-8")
        index_source = (UI_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn('label: "Detected changes"', model_source)
        self.assertIn('kind: "detected-changes"', model_source)
        self.assertIn('kind: "optional-sources"', model_source)
        self.assertIn("else remainingChildren.push(node)", model_source)
        self.assertIn("selectionModel.selectAll(selectionState.tree)", modal_source)
        self.assertIn("No detected changes", modal_source)
        self.assertIn('checkbox.dataset.available === "false"', modal_source)
        self.assertIn(".backup-selection-group.detected-changes", css_source)
        self.assertLess(
            index_source.index("backup-selection-model.js"),
            index_source.index("backup-selection-modal.js"),
        )

    # Confirms background scheduling cannot preempt a detected-change sync review after launch or focus.
    def test_pending_changes_remain_actionable_until_the_user_scans_or_syncs(self) -> None:
        """Honor persisted scan recency and skip only automatic scans while changes are pending."""

        mode_source = (UI_DIR / "backup-mode.js").read_text(encoding="utf-8")

        self.assertIn("function latestScanStartedAt(backup)", mode_source)
        self.assertIn('Date.parse(String((backup.scan || {}).scanned_at || ""))', mode_source)
        self.assertIn("const pendingChanges = Boolean((backup.scan || {}).has_changes)", mode_source)
        self.assertIn("Date.now() - latestScanStartedAt(backup) >= SCAN_INTERVAL_MS", mode_source)
        self.assertIn("!backup.latest_snapshot || pendingChanges", mode_source)
        self.assertIn('await runAction("scanBackupChanges", {}, "Backup changes scanned")', mode_source)


if __name__ == "__main__":
    unittest.main()
