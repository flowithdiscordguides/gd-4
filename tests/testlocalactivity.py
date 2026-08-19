"""Regression coverage for Local Mode lifecycle, file activity, and work streaks."""

from __future__ import annotations

# Standard-library tools isolate private state, filesystem timestamps, and deterministic dates.
from datetime import date
import os
from pathlib import Path
import stat
import tempfile
from typing import Any
import unittest

# GitDesk activity modules expose the pure normalization and private snapshot boundaries under test.
from gitdesk.activity_tracker import project_id
from gitdesk.localactivity import enrich_activity
from gitdesk.localactivity_lifecycle import project_creation_update
from gitdesk.localactivity_store import LocalActivityStore
from gitdesk.localactivity_streaks import streak_summary


# LocalActivityTests uses temporary physical version folders without touching user configuration.
class LocalActivityTests(unittest.TestCase):
    """Verify copied-file baselines, detected edits, payload merging, and streak calculations."""

    # Builds the hierarchy context consumed by the private file activity scanner.
    def activity_context(self, project_path: Path, version_path: Path) -> list[dict[str, Any]]:
        """Return one project/feature/version context rooted in the temporary directory."""

        feature_path = version_path.parent
        return [{
            "project_id": "project-one",
            "project_path": str(project_path),
            "project_name": project_path.name,
            "features": [{"path": str(feature_path), "name": feature_path.name}],
            "versions": [{
                "path": str(version_path),
                "name": version_path.name,
                "feature_path": str(feature_path),
                "feature_name": feature_path.name,
            }],
        }]

    # Confirms one new project records its project, initial feature, and initial version as separate facts.
    def test_project_creation_records_complete_initial_hierarchy(self) -> None:
        """Create three bounded timeline records from one successful project result."""

        result = {
            "project": {"name": "project-one", "path": "/projects/project-one"},
            "feature": {"name": "01 init", "path": "/projects/project-one/01 init"},
            "version": {
                "name": "v1 project-one",
                "path": "/projects/project-one/01 init/v1 project-one",
            },
        }

        updates = project_creation_update({"project_timeline": []}, {}, result)
        events = updates["project_timeline"]

        self.assertEqual(
            {event["type"] for event in events},
            {"project_created", "feature_created", "version_created"},
        )
        self.assertTrue(all(event["project_path"] == "/projects/project-one" for event in events))

    # Confirms the first scan creates a baseline instead of labeling existing copied content as new work.
    def test_scan_baselines_existing_files_then_detects_additions_and_edits(self) -> None:
        """Detect only file states that change after a version has been baselined."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            project_path = Path(temporary_directory) / "project-one"
            version_path = project_path / "01 init" / "v1 project-one"
            version_path.mkdir(parents=True)
            existing_file = version_path / "app.py"
            existing_file.write_text("first\n", encoding="utf-8")
            store = LocalActivityStore(Path(temporary_directory) / "local-activity.json")
            contexts = self.activity_context(project_path, version_path)

            initial_events, _ = store.scan(contexts)
            self.assertEqual(initial_events, [])
            # Windows ACLs do not expose POSIX permission bits; Unix runners must enforce the exact private mode.
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(store.path.stat().st_mode), 0o600)

            modified_ns = existing_file.stat().st_mtime_ns + 2_000_000_000
            existing_file.write_text("second\n", encoding="utf-8")
            os.utime(existing_file, ns=(modified_ns, modified_ns))
            modified_events, _ = store.scan(contexts)
            self.assertEqual([event["kind"] for event in modified_events], ["file_modified"])

            added_file = version_path / "new-file.txt"
            added_file.write_text("new\n", encoding="utf-8")
            added_ns = modified_ns + 2_000_000_000
            os.utime(added_file, ns=(added_ns, added_ns))
            final_events, _ = store.scan(contexts)
            self.assertEqual({event["kind"] for event in final_events}, {"file_added", "file_modified"})

    # Confirms dependency output cannot inflate local work counts.
    def test_scan_prunes_generated_dependency_directories(self) -> None:
        """Ignore files created under a known generated dependency folder."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            project_path = Path(temporary_directory) / "project-one"
            version_path = project_path / "01 init" / "v1 project-one"
            generated_path = version_path / "node_modules" / "package" / "index.js"
            generated_path.parent.mkdir(parents=True)
            generated_path.write_text("generated\n", encoding="utf-8")
            store = LocalActivityStore(Path(temporary_directory) / "local-activity.json")

            events, _ = store.scan(self.activity_context(project_path, version_path))

            self.assertEqual(events, [])
            self.assertEqual(store.load()["files"][str(version_path)], {})

    # Confirms streaks count consecutive work days and reset when today has no activity.
    def test_streak_summary_requires_factual_activity_today(self) -> None:
        """Calculate current and longest runs from an explicit set of active dates."""

        active_dates = {
            date(2026, 7, 6),
            date(2026, 7, 7),
            date(2026, 7, 9),
            date(2026, 7, 10),
            date(2026, 7, 11),
        }

        active_today = streak_summary(active_dates, date(2026, 7, 11))
        inactive_today = streak_summary(active_dates, date(2026, 7, 12))

        self.assertEqual(active_today["current"], 3)
        self.assertEqual(active_today["longest"], 3)
        self.assertEqual(inactive_today["current"], 0)
        self.assertEqual(inactive_today["last_active"], "2026-07-11")

    # Confirms a Local Mode lifecycle event makes a project active without any Git repository or commit.
    def test_enrichment_includes_local_project_activity_without_git(self) -> None:
        """Merge a project-created timeline event into an otherwise empty Git activity payload."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            project_path = Path(temporary_directory) / "project-one"
            version_path = project_path / "01 init" / "v1 project-one"
            version_path.mkdir(parents=True)
            local_project_id = project_id("local", project_path.resolve())
            settings = {
                "workspace_mode": "local",
                "local_projects": [{"path": str(project_path), "name": "project-one", "category": ""}],
                "project_timeline": [{
                    "timestamp": "2026-07-11T12:00:00Z",
                    "type": "project_created",
                    "title": "Created project-one",
                    "detail": "Local Mode project created.",
                    "project_path": str(project_path),
                    "feature_path": str(version_path.parent),
                    "version_path": str(version_path),
                    "status": "success",
                }],
            }
            payload = {
                "range": {"start": "2026-07-11", "end": "2026-07-11"},
                "projects": [{
                    "id": local_project_id,
                    "name": "project-one",
                    "commits": 0,
                    "repositories": 0,
                }],
                "days": [{"date": "2026-07-11", "total": 0, "projects": [], "commits": []}],
                "totals": {"commits": 0, "active_days": 0, "projects": 0},
                "warnings": [],
            }

            enriched = enrich_activity(
                settings,
                payload,
                Path(temporary_directory) / "settings.json",
                date(2026, 7, 11),
            )

            kinds = [activity["kind"] for activity in enriched["days"][0]["activities"]]
            self.assertEqual(kinds.count("project_created"), 1)
            self.assertEqual(enriched["totals"]["commits"], 0)
            self.assertGreater(enriched["totals"]["local_events"], 0)
            self.assertEqual(enriched["totals"]["current_streak"], 1)


if __name__ == "__main__":
    unittest.main()
