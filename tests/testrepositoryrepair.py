"""Regression coverage for exact metadata repair of app-cloned managed repositories."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from git import Repo

from gitdesk.errors import AppError
from gitdesk.repositoryrepair import repair_cloned_repository_metadata


class RepositoryRepairTests(unittest.TestCase):
    """Verify repair restores Git history metadata without replacing working-tree files."""

    def test_repair_clones_only_git_metadata_into_existing_worktree(self) -> None:
        """Keep current files while rebuilding .git from the exact saved GitHub origin."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            donor = root / "donor"
            target = root / "target"
            donor.mkdir()
            target.mkdir()
            donor_repo = Repo.init(donor)
            donor_repo.create_remote("origin", "https://github.com/example/public-app.git")
            (target / "artifact.bin").write_bytes(b"current artifact")

            def clone_metadata(_url: str, clone_path: Path, **_kwargs: object) -> Repo:
                shutil.copytree(donor / ".git", Path(clone_path) / ".git")
                return Repo(clone_path)

            record = {
                "owner": "example",
                "repo": "public-app",
                "source": "cloned",
            }
            with mock.patch("gitdesk.repositoryrepair.Repo.clone_from", side_effect=clone_metadata):
                result = repair_cloned_repository_metadata(str(target), record, None)

            self.assertEqual(result["method"], "origin_clone")
            self.assertTrue((target / ".git").is_dir())
            self.assertEqual((target / "artifact.bin").read_bytes(), b"current artifact")

    def test_repair_refuses_a_folder_not_recorded_as_an_app_clone(self) -> None:
        """Never synthesize Git metadata for an added, created, or unregistered folder."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory) / "target"
            target.mkdir()
            record = {"owner": "example", "repo": "public-app", "source": "added"}

            with mock.patch("gitdesk.repositoryrepair.Repo.clone_from") as clone:
                with self.assertRaises(AppError) as raised:
                    repair_cloned_repository_metadata(str(target), record, None)

        self.assertEqual(raised.exception.code, "REPOSITORY_REPAIR_UNAVAILABLE")
        clone.assert_not_called()


if __name__ == "__main__":
    unittest.main()
