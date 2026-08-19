"""Regression contracts for categorized albums, original clipboard copy, and explicit photo movement."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call, patch

from gitdesk.errors import AppError
from gitdesk.media_album_files import create_media_album
from gitdesk.media_clipboard import copy_media_item
from gitdesk.media_library_store import MEDIA_LIBRARY_SCHEMA_VERSION, MediaLibraryStore
from gitdesk.media_move import move_media_item


class MediaOrganizationTests(unittest.TestCase):
    """Protect album categories, original copying, file movement, and both navigation surfaces."""

    def setUp(self) -> None:
        """Create isolated source and destination albums with private metadata."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source_root = self.root / "Source"
        self.destination_root = self.root / "Destination"
        self.source_root.mkdir()
        self.destination_root.mkdir()
        self.store = MediaLibraryStore(self.root / "metadata" / "media-library.json")

    def tearDown(self) -> None:
        """Remove the isolated album tree."""

        self.temporary_directory.cleanup()

    def add_albums(self) -> tuple[str, str]:
        """Register categorized source and destination albums."""

        source = self.store.add_album(str(self.source_root), "Source", "Campaigns")
        source_id = source["active_album_id"]
        destination = self.store.add_album(str(self.destination_root), "Destination", "Archive")
        return source_id, destination["active_album_id"]

    def test_album_categories_persist_for_created_and_existing_albums(self) -> None:
        """Save a creation category, then update it without renaming a physical folder."""

        parent = self.root / "Albums"
        parent.mkdir()
        registry = create_media_album(str(parent), "Launch", self.store, "Client Work")
        album_id = registry["active_album_id"]
        self.store.rename_album(album_id, "Launch selects", "Finals")
        saved = self.store.load()

        self.assertEqual(saved["schema_version"], MEDIA_LIBRARY_SCHEMA_VERSION)
        self.assertEqual(saved["albums"][0]["category"], "Finals")
        self.assertEqual(saved["albums"][0]["name"], "Launch selects")
        self.assertTrue((parent / "Launch").is_dir())

    def test_photo_move_preserves_existing_destination_and_nested_source_name(self) -> None:
        """Move a nested photo to the destination root with collision-safe naming."""

        source_id, destination_id = self.add_albums()
        source = self.source_root / "nested" / "shot.png"
        source.parent.mkdir()
        source.write_bytes(b"new photo")
        existing = self.destination_root / "shot.png"
        existing.write_bytes(b"existing photo")

        # Force Windows' missing no-follow timestamp capability on every test platform.
        with patch("gitdesk.media_move.os.supports_follow_symlinks", set()):
            result = move_media_item(source_id, destination_id, "nested/shot.png", self.store)

        self.assertFalse(source.exists())
        self.assertEqual(existing.read_bytes(), b"existing photo")
        self.assertEqual((self.destination_root / "shot (2).png").read_bytes(), b"new photo")
        self.assertEqual(result["destination_path"], "shot (2).png")

    def test_photo_move_rejects_same_album_video_and_overlapping_roots(self) -> None:
        """Reject ambiguous or unsupported file movement before changing either album."""

        source_id, destination_id = self.add_albums()
        photo = self.source_root / "photo.jpg"
        video = self.source_root / "clip.mp4"
        photo.write_bytes(b"photo")
        video.write_bytes(b"video")
        nested_root = self.source_root / "Nested Album"
        nested_root.mkdir()
        nested_registry = self.store.add_album(str(nested_root), "Nested", "Campaigns")

        with self.assertRaises(AppError) as same_album:
            move_media_item(source_id, source_id, "photo.jpg", self.store)
        self.assertEqual(same_album.exception.code, "MEDIA_MOVE_SAME_ALBUM")
        with self.assertRaises(AppError) as video_move:
            move_media_item(source_id, destination_id, "clip.mp4", self.store)
        self.assertEqual(video_move.exception.code, "MEDIA_MOVE_IMAGE_REQUIRED")
        with self.assertRaises(AppError) as overlap:
            move_media_item(source_id, nested_registry["active_album_id"], "photo.jpg", self.store)
        self.assertEqual(overlap.exception.code, "MEDIA_MOVE_ALBUM_OVERLAP")
        self.assertTrue(photo.exists())
        self.assertTrue(video.exists())

    @patch("gitdesk.media_clipboard.write_desktop_clipboard_files")
    def test_media_copy_writes_contained_originals_without_exposing_paths(self, writer: Mock) -> None:
        """Copy actual image and video file references while keeping originals and responses safe."""

        source_id, unused_destination_id = self.add_albums()
        source = self.source_root / "nested" / "shot.png"
        video = self.source_root / "clip.mp4"
        source.parent.mkdir()
        source.write_bytes(b"original photo")
        video.write_bytes(b"original video")

        image_result = copy_media_item(source_id, "nested/shot.png", self.store)
        video_result = copy_media_item(source_id, "clip.mp4", self.store)

        writer.assert_has_calls([call([str(source.resolve())]), call([str(video.resolve())])])
        self.assertEqual(image_result, {"name": "shot.png", "kind": "image"})
        self.assertEqual(video_result, {"name": "clip.mp4", "kind": "video"})
        self.assertTrue(source.is_file())
        self.assertTrue(video.is_file())

    def test_frontend_uses_dropdown_library_categories_and_photo_context_move(self) -> None:
        """Require the requested album navigation and explicit right-click photo command."""

        project_root = Path(__file__).resolve().parents[1]
        ui_root = project_root / "src" / "gitdesk" / "ui"
        renderer = (ui_root / "media-render.js").read_text(encoding="utf-8")
        navigation = (ui_root / "media-album-navigation.js").read_text(encoding="utf-8")
        move_menu = (ui_root / "media-item-move.js").read_text(encoding="utf-8")
        controller = (ui_root / "media.js").read_text(encoding="utf-8")
        bridge = (project_root / "src" / "gitdesk" / "media_bridge.py").read_text(encoding="utf-8")
        guide = (ui_root / "gitdesk-guide-topics-secondary.js").read_text(encoding="utf-8")
        readme = (project_root / "README.md").read_text(encoding="utf-8")
        index = (ui_root / "index.html").read_text(encoding="utf-8")

        self.assertNotIn("media-album-pane", renderer)
        self.assertLess(renderer.index("media-album-picker-trigger"), renderer.index("create-media-album"))
        self.assertLess(renderer.index("open-media-album-library"), renderer.index("create-media-album"))
        self.assertIn('id="media-new-album-category"', (ui_root / "media-intake.js").read_text(encoding="utf-8"))
        self.assertIn('panel.id = "panel-media-album-library"', navigation)
        self.assertIn("categorizedAlbums", navigation)
        self.assertIn('event.target.closest(".media-tile")', move_menu)
        self.assertIn('data-media-copy-item>Copy</button>', move_menu)
        self.assertIn('callbacks.runAction("copyMediaItem"', move_menu)
        self.assertIn('addEventListener("contextmenu"', move_menu)
        self.assertIn('"moveMediaItem"', move_menu)
        self.assertIn('"copyMediaItem": lambda payload: handle_copy_media_item(payload)', bridge)
        self.assertIn("right-click its thumbnail and choose Copy", guide)
        self.assertIn("right-click its thumbnail and choose **Copy**", readme)
        self.assertIn("category: byId(\"media-album-category\").value", controller)
        self.assertLess(index.index("media-album-navigation.js"), index.index("media-intake.js"))
        self.assertLess(index.index("media-item-move.js"), index.index("media.js"))

    def test_new_media_code_files_stay_within_line_ceiling(self) -> None:
        """Keep organization modules within the 400-line implementation ceiling."""

        project_root = Path(__file__).resolve().parents[1]
        paths = [
            project_root / "src" / "gitdesk" / "media_move.py",
            project_root / "src" / "gitdesk" / "ui" / "media-album-navigation.js",
            project_root / "src" / "gitdesk" / "ui" / "media-album-navigation.css",
            project_root / "src" / "gitdesk" / "ui" / "media-item-move.js",
        ]
        for path in paths:
            with self.subTest(path=path.name):
                self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()), 400)


if __name__ == "__main__":
    unittest.main()
