"""Regression coverage for complete, merge-forward, versioned Backup Mode snapshots."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gitdesk.backup_inventory import (
    LOCAL_BACKUP_FOLDER,
    MEDIA_BACKUP_FOLDER,
    REPO_BACKUP_FOLDER,
    SETTINGS_BACKUP_FOLDER,
    directory_source,
    metadata_source,
)
from gitdesk.backup_bridge import handle_sync_backup
from gitdesk.backup_jobs import CancellationGate
from gitdesk.backup_manifest import scan_sources
from gitdesk.backup_selection import apply_backup_selection, clean_backup_selection, selection_state
from gitdesk.backup_snapshot import create_backup_snapshot, validate_backup_destination
from gitdesk.backup_store import BackupStore, clean_parent_favorites
from gitdesk.backup_validation import validate_installed_snapshot
from gitdesk.errors import AppError
from gitdesk.frontend import INLINE_SCRIPTS, INLINE_STYLES, UI_DIR
from gitdesk.localprojects import clean_workspace_mode


# BackupModeTests builds real disposable Local, Repo, Media, settings, and destination trees.
class BackupModeTests(unittest.TestCase):
    """Verify complete grouped versions, merge-forward changes, failure boundaries, and delivery."""

    # Creates one source in every required group, including repository Git metadata.
    def sources(self, root: Path) -> tuple[list[dict[str, str]], dict[str, Path]]:
        """Return normalized source records and their physical fixture paths."""

        paths = {
            "local": root / "Local Project",
            "repo": root / "Repo Checkout",
            "media": root / "Media Album",
            "settings": root / "settings.json",
        }
        paths["local"].mkdir()
        (paths["repo"] / ".git").mkdir(parents=True)
        paths["media"].mkdir()
        paths["local"].joinpath("app.txt").write_text("local-one", encoding="utf-8")
        paths["repo"].joinpath("code.txt").write_text("repo-one", encoding="utf-8")
        paths["repo"].joinpath(".git", "config").write_text("git-data", encoding="utf-8")
        paths["media"].joinpath("cover.png").write_bytes(b"media-one")
        paths["settings"].write_text('{"theme": "dark"}\n', encoding="utf-8")
        sources = [
            directory_source(LOCAL_BACKUP_FOLDER, paths["local"], "Local Project"),
            directory_source(REPO_BACKUP_FOLDER, paths["repo"], "octocat/repo"),
            directory_source(MEDIA_BACKUP_FOLDER, paths["media"], "Media Album"),
            metadata_source(paths["settings"]),
        ]
        return sources, paths

    # Confirms the first version contains every requested group and complete repository metadata.
    def test_first_snapshot_has_complete_requested_layout(self) -> None:
        """Create one dated folder containing Local, Repo, Media, and settings backups."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = root / "Backups"
            destination.mkdir()
            sources, paths = self.sources(root)

            result = create_backup_snapshot(str(destination), sources, "")
            snapshot = Path(result["version"]["path"])
            repo_target = snapshot / sources[1]["snapshot_path"]

            self.assertTrue(snapshot.name.startswith("gitdesk backups "))
            self.assertTrue((snapshot / LOCAL_BACKUP_FOLDER).is_dir())
            self.assertTrue((snapshot / REPO_BACKUP_FOLDER).is_dir())
            self.assertTrue((snapshot / MEDIA_BACKUP_FOLDER).is_dir())
            self.assertTrue((snapshot / SETTINGS_BACKUP_FOLDER / "settings.json").is_file())
            self.assertEqual((repo_target / ".git" / "config").read_text(encoding="utf-8"), "git-data")
            self.assertEqual(paths["local"].joinpath("app.txt").read_text(encoding="utf-8"), "local-one")

    # Confirms later versions merge current changes over the prior complete snapshot without altering it.
    def test_changed_snapshot_preserves_prior_version_and_applies_deletions(self) -> None:
        """Create a second complete version with modified, added, and deleted source files."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = root / "Backups"
            destination.mkdir()
            sources, paths = self.sources(root)
            first = create_backup_snapshot(str(destination), sources, "")
            first_path = Path(first["version"]["path"])
            local_relative = Path(sources[0]["snapshot_path"]) / "app.txt"
            media_relative = Path(sources[2]["snapshot_path"]) / "cover.png"
            (first_path / "manual-junk.txt").write_text("do not inherit", encoding="utf-8")
            (first_path / LOCAL_BACKUP_FOLDER / "manual-junk.txt").write_text("remove", encoding="utf-8")
            paths["local"].joinpath("app.txt").write_text("local-two", encoding="utf-8")
            paths["repo"].joinpath("new.txt").write_text("added", encoding="utf-8")
            paths["media"].joinpath("cover.png").unlink()

            second = create_backup_snapshot(str(destination), sources, first_path)
            second_path = Path(second["version"]["path"])

            self.assertEqual((first_path / local_relative).read_text(encoding="utf-8"), "local-one")
            self.assertTrue((first_path / media_relative).is_file())
            self.assertEqual((second_path / local_relative).read_text(encoding="utf-8"), "local-two")
            self.assertFalse((second_path / media_relative).exists())
            self.assertTrue((second_path / sources[1]["snapshot_path"] / "new.txt").is_file())
            self.assertFalse((second_path / "manual-junk.txt").exists())
            self.assertFalse((second_path / LOCAL_BACKUP_FOLDER / "manual-junk.txt").exists())
            self.assertTrue(second["changes"]["has_changes"])

    # Confirms an incomplete previous folder cannot use its manifest to suppress a required replacement copy.
    def test_missing_prior_content_forces_a_fresh_complete_version(self) -> None:
        """Create a new version when unchanged live content is missing from the prior dated folder."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = root / "Backups"
            destination.mkdir()
            sources, _paths = self.sources(root)
            first = create_backup_snapshot(str(destination), sources, "")
            first_path = Path(first["version"]["path"])
            backed_file = first_path / sources[0]["snapshot_path"] / "app.txt"
            backed_file.unlink()

            second = create_backup_snapshot(str(destination), sources, first_path)
            second_file = Path(second["version"]["path"]) / sources[0]["snapshot_path"] / "app.txt"

            self.assertFalse(second["no_changes"])
            self.assertEqual(second_file.read_text(encoding="utf-8"), "local-one")

    # Confirms include/exclude rules produce an exact partial version without changing the prior complete version.
    def test_confirmed_selection_filters_snapshot_and_preserves_prior_version(self) -> None:
        """Create a later version containing only checked and explicitly re-included content."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = root / "Backups"
            source_root = root / "Project"
            destination.mkdir()
            (source_root / "nested").mkdir(parents=True)
            (source_root / "keep.txt").write_text("keep", encoding="utf-8")
            (source_root / "skip.txt").write_text("skip", encoding="utf-8")
            (source_root / "nested" / "keep.txt").write_text("nested", encoding="utf-8")
            (source_root / "nested" / "skip.txt").write_text("nested-skip", encoding="utf-8")
            source = directory_source(LOCAL_BACKUP_FOLDER, source_root, "Project")
            first = create_backup_snapshot(str(destination), [source], "")
            selection = [{
                "source_id": source["id"],
                "rules": {
                    "": True,
                    "skip.txt": False,
                    "nested": False,
                    "nested/keep.txt": True,
                },
            }]
            selected_sources, canonical = apply_backup_selection([source], selection)

            second = create_backup_snapshot(str(destination), selected_sources, first["version"]["path"])
            first_target = Path(first["version"]["path"]) / source["snapshot_path"]
            second_target = Path(second["version"]["path"]) / source["snapshot_path"]

            self.assertTrue((first_target / "skip.txt").is_file())
            self.assertTrue((first_target / "nested" / "skip.txt").is_file())
            self.assertTrue((second_target / "keep.txt").is_file())
            self.assertFalse((second_target / "skip.txt").exists())
            self.assertTrue((second_target / "nested" / "keep.txt").is_file())
            self.assertFalse((second_target / "nested" / "skip.txt").exists())
            self.assertEqual(canonical, selection)

    # Confirms the deepest selection rule controls a path and malformed records cannot broaden the scope.
    def test_backup_selection_rules_support_child_exclusion_and_reinclusion(self) -> None:
        """Evaluate nested include/exclude rules with an excluded-by-default source."""

        rules = {"": True, "folder": False, "folder/keep": True}
        cleaned = clean_backup_selection([{"source_id": "source", "rules": rules}])

        self.assertTrue(selection_state(cleaned[0]["rules"], "other.txt"))
        self.assertFalse(selection_state(cleaned[0]["rules"], "folder/skip.txt"))
        self.assertTrue(selection_state(cleaned[0]["rules"], "folder/keep/file.txt"))
        self.assertEqual(clean_backup_selection([{"source_id": "source", "rules": {"../escape": True}}]), [])

    # Confirms no caller can bypass the required review agreement by invoking the bridge directly.
    def test_backup_creation_requires_explicit_confirmation(self) -> None:
        """Reject an unconfirmed backup before reading destination or source state."""

        with self.assertRaises(AppError) as confirmation_error:
            handle_sync_backup(None, {"selection": []})

        self.assertEqual(confirmation_error.exception.code, "BACKUP_CONFIRMATION_REQUIRED")

    # Confirms byte progress comes from real phases and cancellation removes staging without installing a version.
    def test_backup_progress_is_factual_and_cancellation_removes_staging(self) -> None:
        """Cancel during a reported copy chunk and retain no dated or staging folder."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = root / "Backups"
            destination.mkdir()
            sources, _paths = self.sources(root)
            gate = CancellationGate()
            progress_events = []

            # The first physical write accepts cancellation before the next bounded copy checkpoint.
            def record_progress(progress: dict[str, object]) -> None:
                progress_events.append(dict(progress))
                if progress.get("phase") == "copying" and int(progress.get("bytes_done") or 0) > 0:
                    gate.request()

            with self.assertRaises(AppError) as cancellation_error:
                create_backup_snapshot(
                    str(destination),
                    sources,
                    "",
                    record_progress,
                    gate.requested,
                    gate.seal,
                )

            remaining = list(destination.iterdir())

        self.assertEqual(cancellation_error.exception.code, "BACKUP_CANCELLED")
        self.assertIn("preparing", [event["phase"] for event in progress_events])
        self.assertIn("copying", [event["phase"] for event in progress_events])
        self.assertEqual(remaining, [])

    # Confirms a completed transaction reports exact copy and verification totals before atomic finalization.
    def test_completed_backup_reports_copy_and_verification_totals(self) -> None:
        """Report selected manifest bytes through copying, verification, and finalization."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = root / "Backups"
            destination.mkdir()
            sources, _paths = self.sources(root)
            progress_events = []

            result = create_backup_snapshot(
                str(destination),
                sources,
                "",
                lambda progress: progress_events.append(dict(progress)),
            )

        copy_events = [event for event in progress_events if event["phase"] == "copying"]
        verify_events = [event for event in progress_events if event["phase"] == "verifying"]
        self.assertEqual(copy_events[-1]["bytes_done"], result["version"]["total_bytes"])
        self.assertEqual(copy_events[-1]["bytes_total"], result["version"]["total_bytes"])
        self.assertEqual(verify_events[-1]["bytes_total"], result["version"]["total_bytes"])
        self.assertEqual(progress_events[-1]["phase"], "finalizing")

    # Confirms unsupported removable-drive mode and timestamp fields cannot erase verified content.
    def test_destination_metadata_limitations_are_nonfatal_and_recorded(self) -> None:
        """Complete file-content backup while retaining explicit portable metadata warnings."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = root / "Backups"
            destination.mkdir()
            sources, _paths = self.sources(root)
            with patch("gitdesk.backup_copy.os.chmod", side_effect=OSError("unsupported")):
                with patch("gitdesk.backup_copy.os.utime", side_effect=OSError("unsupported")):
                    result = create_backup_snapshot(str(destination), sources, "")
            snapshot = Path(result["version"]["path"])
            self.assertTrue(result["version"]["metadata_warnings"])
            self.assertTrue((snapshot / sources[0]["snapshot_path"] / "app.txt").is_file())

    # Confirms completion validation rejects a manifest-owned item missing from the installed dated folder.
    def test_installed_snapshot_validation_requires_every_manifest_entry(self) -> None:
        """Reject an installed version whose physical tree is missing selected content."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot = Path(temporary_directory) / "gitdesk backups fixture"
            snapshot.mkdir()
            manifest = {
                "entries": {
                    "local mode backups/project/missing.txt": {
                        "kind": "file",
                        "size": 4,
                    },
                },
            }
            with self.assertRaises(AppError) as validation_error:
                validate_installed_snapshot(snapshot, manifest)

        self.assertEqual(validation_error.exception.code, "BACKUP_INSTALL_VERIFY_FAILED")

    # Confirms cancellation cannot claim success after the worker seals its atomic installation boundary.
    def test_backup_cancellation_gate_rejects_requests_after_seal(self) -> None:
        """Reject a late cancel without marking the sealed transaction cancelled."""

        gate = CancellationGate()

        self.assertTrue(gate.seal())
        self.assertFalse(gate.request())
        self.assertFalse(gate.requested())

    # Confirms recursive placement and unavailable roots stop snapshots instead of recording partial success.
    def test_recursive_destination_and_unavailable_sources_are_blocked(self) -> None:
        """Reject a destination inside a source and surface a disconnected registered root."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            sources, paths = self.sources(root)
            recursive = paths["local"] / "Backups"
            recursive.mkdir()
            missing = directory_source(LOCAL_BACKUP_FOLDER, root / "Missing", "Missing")

            with self.assertRaises(AppError) as recursive_error:
                validate_backup_destination(str(recursive), sources)
            scan = scan_sources([missing])

        self.assertEqual(recursive_error.exception.code, "BACKUP_DESTINATION_RECURSIVE")
        self.assertEqual(scan["errors"][0]["code"], "BACKUP_SOURCE_UNAVAILABLE")

    # Confirms favorites are private Backup metadata and survive destination changes and disconnected drives.
    def test_backup_parent_favorites_are_bounded_deduplicated_and_preserved(self) -> None:
        """Persist the newest parent favorite independently from active destination history."""

        disconnected = [f"/Volumes/Backup {index}" for index in range(14)]
        cleaned = clean_parent_favorites([disconnected[0].lower(), *disconnected, None])
        self.assertEqual(len(cleaned), 12)
        self.assertEqual(cleaned[0], disconnected[0].lower())

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            favorite = root / "Favorite"
            destination = root / "Destination"
            favorite.mkdir()
            destination.mkdir()
            store = BackupStore(root / "backup-state.json")

            favorite_state = store.save_parent_favorite(str(favorite))
            destination_state = store.save_destination(str(destination))
            selected_state = store.save_selection_scan(
                [{"source_id": "registered-source", "rules": {"": True}}],
                {},
            )

        self.assertEqual(favorite_state["parent_favorites"], [str(favorite.resolve())])
        self.assertEqual(destination_state["parent_favorites"], [str(favorite.resolve())])
        self.assertEqual(selected_state["selection"][0]["source_id"], "registered-source")

    # Confirms Backup is a persisted workspace and its controller loads before mode orchestration.
    def test_backup_mode_assets_and_workspace_value_are_delivered(self) -> None:
        """Package Backup Mode in the dependency order required by the dynamic workspace."""

        self.assertEqual(clean_workspace_mode("backup"), "backup")
        self.assertIn("backup-mode.css", INLINE_STYLES)
        self.assertLess(
            INLINE_STYLES.index("backup-mode.css"),
            INLINE_STYLES.index("backup-selection-modal.css"),
        )
        self.assertLess(
            INLINE_STYLES.index("backup-selection-modal.css"),
            INLINE_STYLES.index("backup-transfer-modal.css"),
        )
        self.assertLess(
            INLINE_SCRIPTS.index("backup-destination-modal.js"),
            INLINE_SCRIPTS.index("backup-transfer-modal.js"),
        )
        self.assertLess(
            INLINE_SCRIPTS.index("backup-transfer-modal.js"),
            INLINE_SCRIPTS.index("backup-selection-modal.js"),
        )
        self.assertLess(
            INLINE_SCRIPTS.index("backup-selection-modal.js"),
            INLINE_SCRIPTS.index("backup-mode.js"),
        )
        self.assertLess(
            INLINE_SCRIPTS.index("backup-mode.js"),
            INLINE_SCRIPTS.index("workspace-mode.js"),
        )
        backup_css = (UI_DIR / "backup-mode.css").read_text(encoding="utf-8")
        panel_rule = backup_css.split(".backup-header", 1)[0]
        self.assertIn("#panel-backup.panel.active", panel_rule)
        self.assertIn("overflow-y: auto", panel_rule)
        self.assertIn("padding-top: 34px", panel_rule)
        self.assertIn("padding-bottom: 34px", panel_rule)
        selection_source = (UI_DIR / "backup-selection-modal.js").read_text(encoding="utf-8")
        transfer_source = (UI_DIR / "backup-transfer-modal.js").read_text(encoding="utf-8")
        self.assertIn('id="backup-selection-confirmed"', selection_source)
        self.assertIn("transferModal.start(selection)", selection_source)
        self.assertIn('callNative("startBackupJob", { selection, confirmed: true })', transfer_source)
        self.assertIn('callNative("cancelBackupJob", { job_id: state.jobId })', transfer_source)
        self.assertIn('await waitForAcknowledgement(job)', transfer_source)
        self.assertIn('callNative("openBackupVersion", { path: version.path })', transfer_source)
        self.assertIn('Back to selection', transfer_source)
        self.assertIn('role="progressbar"', transfer_source)


if __name__ == "__main__":
    unittest.main()
