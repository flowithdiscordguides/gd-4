"""Regression coverage for Document Builder hierarchy safety, numbering, and registry persistence."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from gitdesk import documentbuilder
from gitdesk.documentstore import DocumentStore
from gitdesk.errors import AppError


# DocumentBuilderTests isolates every physical hierarchy operation inside a disposable directory.
class DocumentBuilderTests(unittest.TestCase):
    """Verify safe names, ownership, numbering, text writes, state, rename, and metadata recovery."""

    # Confirms user-entered sequence prefixes are replaced by the app's authoritative next number.
    def test_folder_and_file_names_increment_automatically(self) -> None:
        """Create two numbered folders and sequential files without accepting manual sequence control."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = documentbuilder.create_document(str(root), "Research")
            first_folder = documentbuilder.create_folder(document["path"], "", "99 Sources")
            second_folder = documentbuilder.create_folder(document["path"], "", "Findings")
            first_file = documentbuilder.create_file(
                document["path"],
                first_folder["path"],
                "42 notes.md",
                "first",
            )
            second_file = documentbuilder.create_file(
                document["path"],
                first_folder["path"],
                "summary.txt",
                "second",
            )

            self.assertEqual(Path(first_folder["path"]).name, "01 Sources")
            self.assertEqual(Path(second_folder["path"]).name, "02 Findings")
            self.assertEqual(Path(first_file["path"]).name, "01 notes.md")
            self.assertEqual(Path(second_file["path"]).name, "02 summary.txt")

    # Confirms the next number follows the highest existing managed file instead of reusing a gap.
    def test_file_number_uses_highest_existing_sequence(self) -> None:
        """Continue at 08 when numbered files 01 and 07 already exist."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = documentbuilder.create_document(str(root), "Manual")
            folder = documentbuilder.create_folder(document["path"], "", "Chapter")
            folder_path = Path(folder["path"])
            (folder_path / "01 intro.md").write_text("intro", encoding="utf-8")
            (folder_path / "07 appendix.md").write_text("appendix", encoding="utf-8")

            created = documentbuilder.create_file(
                document["path"],
                folder["path"],
                "closing.md",
                "closing",
            )

            self.assertEqual(Path(created["path"]).name, "08 closing.md")

    # Confirms root siblings and nested children each maintain sequences scoped to their own parent.
    def test_nested_folder_numbering_is_parent_scoped(self) -> None:
        """Create 01, 02, and 03 at root while nested folders start their own 01 sequence."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            document = documentbuilder.create_document(temporary_directory, "Nested")
            overview = documentbuilder.create_folder(document["path"], "", "Overview")
            test = documentbuilder.create_folder(document["path"], "", "Test")
            cat = documentbuilder.create_folder(document["path"], "", "Cat")
            nested_first = documentbuilder.create_folder(document["path"], overview["path"], "Research")
            nested_second = documentbuilder.create_folder(document["path"], overview["path"], "Drafts")

            self.assertEqual(Path(overview["path"]).name, "01 Overview")
            self.assertEqual(Path(test["path"]).name, "02 Test")
            self.assertEqual(Path(cat["path"]).name, "03 Cat")
            self.assertEqual(Path(nested_first["path"]).name, "01 Research")
            self.assertEqual(Path(nested_second["path"]).name, "02 Drafts")

            registry = {"documents": [document], "active_document": document["path"]}
            state = documentbuilder.documents_state(registry)
            root_folders = state["documents"][0]["folders"]
            self.assertEqual([item["name"] for item in root_folders], ["01 Overview", "02 Test", "03 Cat"])
            self.assertEqual(
                [item["name"] for item in root_folders[0]["folders"]],
                ["01 Research", "02 Drafts"],
            )

    # Confirms pasted Unicode text reaches the physical file exactly as UTF-8.
    def test_file_content_is_saved_exactly(self) -> None:
        """Preserve whitespace, line endings, and Unicode content in a newly created file."""

        content = "Heading\n\nIndented text: café\n"
        with tempfile.TemporaryDirectory() as temporary_directory:
            document = documentbuilder.create_document(temporary_directory, "Notes")
            folder = documentbuilder.create_folder(document["path"], "", "Drafts")
            file = documentbuilder.create_file(document["path"], folder["path"], "draft.md", content)

            self.assertEqual(Path(file["path"]).read_text(encoding="utf-8"), content)

    # Confirms separators, hidden names, and traversal markers cannot become managed path components.
    def test_invalid_names_are_rejected(self) -> None:
        """Reject names that could escape or obscure the managed document hierarchy."""

        for name in ("../escape", "nested/file.md", "nested\\file.md", ".hidden"):
            with self.subTest(name=name):
                with self.assertRaises(AppError):
                    documentbuilder.clean_name(name, "file")

    # Confirms a folder from another document cannot receive a file through a forged payload path.
    def test_file_folder_must_belong_to_selected_document(self) -> None:
        """Reject a valid folder when it is not a direct child of the supplied document root."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            first = documentbuilder.create_document(temporary_directory, "First")
            second = documentbuilder.create_document(temporary_directory, "Second")
            second_folder = documentbuilder.create_folder(second["path"], "", "Private")

            with self.assertRaises(AppError) as raised:
                documentbuilder.create_file(first["path"], second_folder["path"], "escape.md", "blocked")

            self.assertEqual(raised.exception.code, "DOCUMENT_FOLDER_PATH_INVALID")

    # Confirms symlink folders and files are excluded from the managed state returned to the frontend.
    def test_state_ignores_symbolic_links(self) -> None:
        """Do not expose symlink targets as managed hierarchy children."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = documentbuilder.create_document(str(root), "Links")
            folder = documentbuilder.create_folder(document["path"], "", "Normal")
            outside = root / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            link = Path(folder["path"]) / "02 linked.txt"
            try:
                link.symlink_to(outside)
            except (NotImplementedError, OSError):
                self.skipTest("Symbolic links are unavailable on this platform")
            registry = {
                "documents": [document],
                "active_document": document["path"],
                "active_folder": folder["path"],
                "active_file": str(link),
            }

            state = documentbuilder.documents_state(registry)

            self.assertEqual(state["documents"][0]["folders"][0]["files"], [])
            self.assertEqual(state["active_file"], "")

    # Confirms renaming moves the physical root while keeping all child content intact.
    def test_rename_document_preserves_hierarchy(self) -> None:
        """Rename only the document root and preserve its numbered folder and file contents."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            document = documentbuilder.create_document(temporary_directory, "Old Name")
            folder = documentbuilder.create_folder(document["path"], "", "Folder")
            file = documentbuilder.create_file(document["path"], folder["path"], "notes.md", "kept")

            renamed = documentbuilder.rename_document(document["path"], "New Name")
            moved_file = Path(renamed["target"]) / Path(folder["path"]).name / Path(file["path"]).name

            self.assertFalse(Path(renamed["source"]).exists())
            self.assertEqual(moved_file.read_text(encoding="utf-8"), "kept")

    # Confirms document metadata survives owner-only registry serialization and sanitization.
    def test_document_store_persists_registry(self) -> None:
        """Round-trip document, category, and active hierarchy metadata through documents.json."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = DocumentStore()
            store.config_path = root / "documents.json"
            document_path = str(root / "Guide")
            saved = store.save({
                "documents": [{"path": document_path, "name": "Guide", "category": "Docs"}],
                "categories": ["Docs"],
                "active_document": document_path,
                "active_folder": str(root / "Guide" / "01 Drafts"),
                "active_file": str(root / "Guide" / "01 Drafts" / "01 guide.md"),
            })

            loaded = store.load()

            self.assertEqual(loaded, saved)
            self.assertEqual(json.loads(store.config_path.read_text(encoding="utf-8")), saved)

    # Confirms malformed registry bytes are backed up and a complete leading object is recovered.
    def test_document_store_recovers_malformed_json(self) -> None:
        """Recover valid document metadata from trailing corruption without discarding the registry."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = DocumentStore()
            store.config_path = root / "documents.json"
            store.config_path.write_text(
                '{"documents": [{"path": "/Docs/Guide", "name": "Guide", "category": "Docs"}]} trailing',
                encoding="utf-8",
            )

            loaded = store.load()

            self.assertEqual(loaded["documents"][0]["name"], "Guide")
            self.assertTrue(list(root.glob("documents.json.invalid.recovered*")))

    # Protects the Local Projects-aligned composition from regressing to three independent hierarchy columns.
    def test_frontend_uses_two_pane_document_workspace(self) -> None:
        """Require the left identity/folder stack, right file detail, and final layout asset order."""

        project_root = Path(__file__).resolve().parents[1]
        ui_source = (project_root / "src/gitdesk/ui/document-builder-ui.js").read_text(encoding="utf-8")
        render_source = (project_root / "src/gitdesk/ui/document-builder-render.js").read_text(encoding="utf-8")
        base_source = (project_root / "src/gitdesk/ui/document-builder.css").read_text(encoding="utf-8")
        layout_source = (project_root / "src/gitdesk/ui/document-builder-layout.css").read_text(encoding="utf-8")
        index_source = (project_root / "src/gitdesk/ui/index.html").read_text(encoding="utf-8")
        frontend_source = (project_root / "src/gitdesk/frontend.py").read_text(encoding="utf-8")

        self.assertIn('<div class="document-builder-left-pane">', ui_source)
        self.assertLess(ui_source.index("document-identity-card"), ui_source.index("document-folder-card"))
        self.assertLess(ui_source.index("document-folder-card"), ui_source.index("document-file-card"))
        self.assertIn('<div class="document-file-workspace">', ui_source)
        self.assertIn('<aside class="document-file-detail"', ui_source)
        self.assertIn('class="document-folder-list" role="list"', ui_source)
        self.assertIn('class="document-folder-branch${branchClass}" role="listitem"', render_source)
        self.assertIn('class="document-folder-children" role="list"', render_source)
        self.assertIn('src="./folder-icon.svg"', render_source)
        self.assertNotIn("--document-folder-depth", render_source + base_source)
        self.assertNotIn('const indent = "- ".repeat', render_source)
        self.assertIn("min-height: 36px;", base_source)
        self.assertIn(".document-folder-children", base_source)
        self.assertIn("overflow-x: auto;", layout_source)
        self.assertIn("grid-template-columns: minmax(370px, 0.82fr) minmax(430px, 1.18fr);", layout_source)
        self.assertIn("grid-template-rows: minmax(260px, 1fr) minmax(190px, 1fr);", layout_source)
        self.assertIn("grid-template-columns: minmax(160px, 0.72fr) minmax(200px, 1.28fr);", layout_source)
        self.assertNotIn("minmax(240px, 0.52fr)", base_source + layout_source)
        self.assertLess(index_source.index("document-builder.css"), index_source.index("document-builder-layout.css"))
        self.assertLess(
            frontend_source.index('"document-builder.css"'),
            frontend_source.index('"document-builder-layout.css"'),
        )


if __name__ == "__main__":
    unittest.main()
