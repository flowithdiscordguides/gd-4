"""Regression coverage for GitDesk's multi-project commit activity aggregation."""

from __future__ import annotations

# Standard-library test tools isolate dates and temporary filesystem state.
from datetime import date
from pathlib import Path
import tempfile
from typing import Any
import unittest

# GitPython creates real repository roots for discovery coverage.
from git import Repo

# The activity module exposes pure boundaries and aggregation for focused regression checks.
from gitdesk.activity_tracker import aggregate_activity, known_project_records, recover_first_use_date, resolve_range


# ActivityTrackerTests isolates registry and Git discovery checks inside temporary project folders.
class ActivityTrackerTests(unittest.TestCase):
    """Verify date boundaries, repository grouping, and copied-history de-duplication."""

    # Protects the frontend from launching duplicate full-history scans during overlapping startup refreshes.
    def test_frontend_coalesces_overlapping_activity_refreshes(self) -> None:
        """Require all concurrent refresh callers to reuse one in-flight native request."""

        root = Path(__file__).resolve().parents[1]
        source = (root / "src" / "gitdesk" / "ui" / "activity-tracker.js").read_text(encoding="utf-8")

        guard_index = source.index("if (state.refreshPromise)")
        request_index = source.index('state.refreshPromise = callNative("projectActivity"')
        self.assertLess(guard_index, request_index)
        self.assertIn("return state.refreshPromise;", source)
        self.assertIn("state.refreshPromise = null;", source)

    # Confirms rolling windows cannot predate the durable first-use boundary.
    def test_range_is_clamped_to_first_use(self) -> None:
        """Clamp a year view when GitDesk has been used for less than one year."""

        preset, start, end = resolve_range(
            "year",
            "",
            date(2026, 6, 15),
            date(2026, 7, 10),
        )

        self.assertEqual(preset, "year")
        self.assertEqual(start, date(2026, 6, 15))
        self.assertEqual(end, date(2026, 7, 10))

    # Confirms custom dates before first use and after today are both constrained safely.
    def test_custom_range_respects_both_boundaries(self) -> None:
        """Keep custom activity queries inside the user's actual usage period."""

        _, early_start, _ = resolve_range(
            "custom",
            "2020-01-01",
            date(2026, 5, 1),
            date(2026, 7, 10),
        )
        _, future_start, _ = resolve_range(
            "custom",
            "2030-01-01",
            date(2026, 5, 1),
            date(2026, 7, 10),
        )

        self.assertEqual(early_start, date(2026, 5, 1))
        self.assertEqual(future_start, date(2026, 7, 10))

    # Confirms settings-file creation metadata is used when no durable date has been saved yet.
    def test_first_use_falls_back_to_existing_settings_metadata(self) -> None:
        """Recover a first-use date without allowing a future filesystem timestamp."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_path = Path(temporary_directory) / "settings.json"
            settings_path.write_text("{}", encoding="utf-8")

            recovered = recover_first_use_date("", [settings_path], date(2026, 7, 10))

            self.assertLessEqual(recovered, date(2026, 7, 10))

    # Confirms a managed repository inside a Local Mode project is grouped under that project once.
    def test_overlapping_registry_paths_create_one_project(self) -> None:
        """Merge overlapping Local Mode and managed repository records by filesystem ownership."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "project-one"
            version_root = project_root / "01 init" / "v1 project-one"
            version_root.mkdir(parents=True)
            Repo.init(version_root)
            settings = {
                "local_projects": [{"path": str(project_root), "name": "project-one", "category": ""}],
                "managed_repositories": {
                    "octocat": [{"path": str(version_root), "name": "repo", "full_name": "octocat/repo"}],
                },
            }

            projects = known_project_records(settings)

            self.assertEqual(len(projects), 1)
            self.assertEqual(projects[0]["name"], "project-one")

    # Confirms the same SHA observed in copied version repositories counts only once for its project.
    def test_aggregate_de_duplicates_commit_shas_per_project(self) -> None:
        """Count copied Git history once while retaining distinct commits on the same day."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_repo = root / "v1"
            second_repo = root / "v2"
            Repo.init(first_repo)
            Repo.init(second_repo)
            # Production repository discovery returns canonical roots, so fixtures must compare the same path form.
            first_repo_root = first_repo.resolve()
            project = {
                "id": "project-one",
                "name": "Project One",
                "root": root,
                "candidates": [first_repo, second_repo],
            }

            def commit_reader(repository_path: Path, start: date, end: date) -> list[dict[str, Any]]:
                """Return shared and unique fixture commits for the requested repository."""

                shared = [{
                    "sha": "shared-sha",
                    "date": date(2026, 7, 9),
                    "committed_timestamp": 1783605600,
                    "committed_at": "2026-07-09T09:00:00-05:00",
                    "summary": "Shared history",
                    "author_name": "Xander",
                    "author_email": "xander@example.test",
                    "repository": repository_path.name,
                }]
                if repository_path == first_repo_root:
                    return [*shared, {
                        "sha": "first-only",
                        "date": date(2026, 7, 9),
                        "committed_timestamp": 1783609200,
                        "committed_at": "2026-07-09T10:00:00-05:00",
                        "summary": "First repository change",
                        "author_name": "Xander",
                        "author_email": "xander@example.test",
                        "repository": repository_path.name,
                    }]
                return [*shared, {
                    "sha": "second-only",
                    "date": date(2026, 7, 10),
                    "committed_timestamp": 1783699200,
                    "committed_at": "2026-07-10T11:00:00-05:00",
                    "summary": "Second repository change",
                    "author_name": "Xander",
                    "author_email": "xander@example.test",
                    "repository": repository_path.name,
                }]

            payload = aggregate_activity(
                [project],
                date(2026, 7, 9),
                date(2026, 7, 10),
                commit_reader,
            )

            self.assertEqual(payload["totals"]["commits"], 3)
            self.assertEqual([day["total"] for day in payload["days"]], [2, 1])
            self.assertEqual(sum(len(day["commits"]) for day in payload["days"]), 3)
            first_commit = payload["days"][0]["commits"][0]
            self.assertEqual(first_commit["sha"], "shared-sha")
            self.assertEqual(first_commit["summary"], "Shared history")
            self.assertEqual(first_commit["project_name"], "Project One")
            self.assertEqual(first_commit["author_email"], "xander@example.test")


if __name__ == "__main__":
    unittest.main()
