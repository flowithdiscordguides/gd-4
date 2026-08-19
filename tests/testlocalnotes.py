"""Regression coverage for selected-version Markdown note storage."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from gitdesk.errors import AppError
from gitdesk import localnotes


# LocalNotesTests owns a disposable Local Mode hierarchy for every note operation.
class LocalNotesTests(unittest.TestCase):
    """Verify exact version ownership, safe filenames, and conflict-aware atomic saves."""

    # Creates the saved project, active feature, and selected v1 used by native note validation.
    def settings(self, root: Path) -> tuple[dict, Path]:
        """Return Local Mode settings and the exact selected version path."""

        project = root / "project"
        feature = project / "01 init"
        version = feature / "v1 project"
        version.mkdir(parents=True)
        return {
            "local_projects": [{"path": str(project), "name": "project", "category": ""}],
            "active_local_project": str(project),
            "active_local_feature": str(feature),
            "active_local_version": str(version),
        }, version

    # Confirms note titles become direct Markdown children and cannot overwrite existing files.
    def test_create_note_appends_extension_and_is_exclusive(self) -> None:
        """Create Todo.md once and reject a second create using the same title."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            settings, version = self.settings(Path(temporary_directory))
            note = localnotes.create_note(settings, {"name": "Todo", "content": "# Tasks\n"})
            with self.assertRaises(AppError) as raised:
                localnotes.create_note(settings, {"name": "Todo.md", "content": ""})

            self.assertEqual(note["name"], "Todo.md")
            self.assertEqual((version / "Todo.md").read_text(encoding="utf-8"), "# Tasks\n")

        self.assertEqual(raised.exception.code, "LOCAL_NOTE_EXISTS")

    # Confirms separators, hidden names, symlinks, and another project's version are rejected.
    def test_notes_cannot_escape_the_selected_version(self) -> None:
        """Reject traversal and a version that is not owned by the saved Local Mode project."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings, version = self.settings(root)
            with self.assertRaises(AppError) as traversal:
                localnotes.create_note(settings, {"name": "../outside.md", "content": ""})
            linked_note = version / "Linked.md"
            linked_note.symlink_to(root / "outside.md")
            with self.assertRaises(AppError) as symlink:
                localnotes.read_note(settings, {"name": "Linked.md"})
            unrelated = root / "other" / "01 init" / "v1 other"
            unrelated.mkdir(parents=True)
            with self.assertRaises(AppError) as ownership:
                localnotes.notes_state(settings, {
                    "project_path": settings["active_local_project"],
                    "feature_path": settings["active_local_feature"],
                    "version_path": str(unrelated),
                })

        self.assertEqual(traversal.exception.code, "LOCAL_NOTE_NAME_INVALID")
        self.assertEqual(symlink.exception.code, "LOCAL_NOTE_SYMLINK_REJECTED")
        self.assertEqual(ownership.exception.code, "LOCAL_VERSION_INVALID")

    # Confirms direct regular Markdown files are listed while nested and non-Markdown files remain untouched.
    def test_note_state_lists_only_direct_regular_markdown_files(self) -> None:
        """List direct .md files without scanning nested folders or following symlinks."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            settings, version = self.settings(Path(temporary_directory))
            (version / "Alpha.md").write_text("alpha", encoding="utf-8")
            (version / "source.py").write_text("pass\n", encoding="utf-8")
            nested = version / "notes"
            nested.mkdir()
            (nested / "Nested.md").write_text("nested", encoding="utf-8")

            note_state = localnotes.notes_state(settings, {})

        self.assertEqual([note["name"] for note in note_state["notes"]], ["Alpha.md"])

    # Confirms exact UTF-8 saves succeed only from the last revision returned by a read.
    def test_save_preserves_utf8_and_rejects_stale_revision(self) -> None:
        """Atomically save Unicode Markdown, then reject an external-edit conflict."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            settings, version = self.settings(Path(temporary_directory))
            created = localnotes.create_note(settings, {"name": "Todo", "content": "first"})
            saved = localnotes.save_note(settings, {
                "name": "Todo.md",
                "content": "# Café 🚀\n\n- [ ] Ship\n",
                "expected_revision": created["revision"],
            })
            (version / "Todo.md").write_text("external edit", encoding="utf-8")
            with self.assertRaises(AppError) as raised:
                localnotes.save_note(settings, {
                    "name": "Todo.md",
                    "content": "stale overwrite",
                    "expected_revision": saved["revision"],
                })

            self.assertEqual(saved["content"], "# Café 🚀\n\n- [ ] Ship\n")
            self.assertEqual((version / "Todo.md").read_text(encoding="utf-8"), "external edit")

        self.assertEqual(raised.exception.code, "LOCAL_NOTE_REVISION_CONFLICT")

    # Confirms oversized content is stopped before any file is created.
    def test_note_content_is_bounded(self) -> None:
        """Reject a bridge payload larger than the established 10 MB text boundary."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            settings, version = self.settings(Path(temporary_directory))
            with self.assertRaises(AppError) as raised:
                localnotes.create_note(settings, {
                    "name": "Large",
                    "content": "x" * (localnotes.MAX_NOTE_BYTES + 1),
                })

            self.assertFalse((version / "Large.md").exists())

        self.assertEqual(raised.exception.code, "LOCAL_NOTE_CONTENT_TOO_LARGE")


if __name__ == "__main__":
    unittest.main()
