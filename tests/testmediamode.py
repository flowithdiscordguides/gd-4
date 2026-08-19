"""Regression coverage for Media Mode albums, previews, publication, and frontend delivery."""

from __future__ import annotations

# Standard-library helpers isolate album folders, private metadata, and resource snapshots.
import base64
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

# Pillow creates and inspects real raster fixtures for bounded thumbnail and clipboard-import coverage.
from PIL import Image

# GitDesk Media services expose the persisted, paged, previewed, and published workflow under test.
from gitdesk.errors import AppError
from gitdesk.frontend import INLINE_SCRIPTS, INLINE_STYLES, render_frontend_document
from gitdesk.localprojects import clean_workspace_mode
from gitdesk.media_album_files import create_media_album, import_media_image
from gitdesk.media_clipboard import paste_media_clipboard
from gitdesk.media_library import library_state, media_preview, selected_media_path
from gitdesk.media_library_publish import publish_album
from gitdesk.media_library_store import MediaLibraryStore
from gitdesk.sharedresource_store import SharedResourceStore


# MediaModeTests keeps original album content and every app-owned registry inside one temporary tree.
class MediaModeTests(unittest.TestCase):
    """Verify non-destructive albums, bounded discovery, safe previews, and versioned publication."""

    # Creates one isolated album, catalog, and pair of private registry files.
    def setUp(self) -> None:
        """Prepare an album and patch only the writable Shared Resources roots used by the test."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.album_root = self.root / "Original Album"
        self.album_root.mkdir()
        self.catalog_root = self.root / "Shared-Resources" / "categories"
        self.catalog_root.mkdir(parents=True)
        self.media_store = MediaLibraryStore(self.root / "metadata" / "media-library.json")
        self.resource_store = SharedResourceStore(self.root / "metadata" / "shared-resources.json")
        self.catalog_patches = [
            patch("gitdesk.aiskills.category_roots", return_value=[self.catalog_root]),
            patch("gitdesk.aiskills.writable_categories_root", return_value=self.catalog_root),
        ]
        for catalog_patch in self.catalog_patches:
            catalog_patch.start()

    # Restores patched catalog roots before deleting the temporary filesystem.
    def tearDown(self) -> None:
        """Restore global helpers and remove isolated test data."""

        for catalog_patch in reversed(self.catalog_patches):
            catalog_patch.stop()
        self.temporary_directory.cleanup()

    # Writes bytes beneath the original album while retaining its nested relative organization.
    def write_media(self, relative_path: str, content: bytes) -> Path:
        """Create one album file and return its physical path."""

        path = self.album_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    # Writes one real PNG so Pillow-backed preview tests exercise actual decoded dimensions.
    def write_png(self, relative_path: str, size: tuple[int, int] = (16, 12)) -> Path:
        """Create one RGB PNG and return its physical path."""

        path = self.album_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with Image.new("RGB", size, (42, 96, 138)) as image:
            image.save(path, format="PNG", optimize=True)
        return path

    # Adds the test album and returns its persisted stable identifier.
    def add_album(self) -> str:
        """Register the original folder without copying or changing its files."""

        registry = self.media_store.add_album(str(self.album_root), "Campaign selects")
        return registry["active_album_id"]

    # Confirms only supported media reaches bounded pages and album removal never deletes originals.
    def test_album_registry_and_paging_are_non_destructive(self) -> None:
        """Page supported media, ignore unrelated files, and forget only the private folder reference."""

        self.write_media("stills/one.png", b"\x89PNG\r\n\x1a\nfirst")
        self.write_media("clips/two.mp4", b"video")
        ignored = self.write_media("notes.txt", b"keep")
        album_id = self.add_album()

        first = library_state(self.media_store, page_size_value=1)
        images = library_state(self.media_store, kind_value="image", page_size_value=80)
        self.media_store.remove_album(album_id)

        self.assertEqual(first["total_count"], 2)
        self.assertEqual(first["page_count"], 2)
        self.assertEqual(len(first["items"]), 1)
        self.assertEqual(images["filtered_count"], 1)
        self.assertEqual(images["items"][0]["kind"], "image")
        self.assertTrue(ignored.exists())
        self.assertTrue((self.album_root / "stills" / "one.png").exists())

    # Confirms new albums are direct children and Media favorites remain independent private registry state.
    def test_create_album_and_media_parent_favorites(self) -> None:
        """Create one physical album, select it, and keep its verified parent at the front of favorites."""

        parent = self.root / "Media Parents"
        other_parent = self.root / "Other Parent"
        parent.mkdir()
        other_parent.mkdir()
        self.media_store.save_parent_favorite(str(other_parent))
        self.media_store.save_parent_favorite(str(parent))
        self.media_store.save_parent_favorite(str(parent))

        registry = create_media_album(str(parent), "Launch selects", self.media_store)
        state = library_state(self.media_store)
        created = parent / "Launch selects"
        expected_favorites = [str(parent.resolve()), str(other_parent.resolve())]

        self.assertTrue(created.is_dir())
        self.assertEqual(registry["parent_favorites"], expected_favorites)
        self.assertEqual(state["active_album"]["path"], str(created.resolve()))
        self.assertEqual(state["parent_favorites"], expected_favorites)
        with self.assertRaises(AppError) as duplicate:
            create_media_album(str(parent), "Launch selects", self.media_store)
        self.assertEqual(duplicate.exception.code, "MEDIA_ALBUM_FOLDER_EXISTS")
        with self.assertRaises(AppError) as nested:
            create_media_album(str(parent), "../outside", self.media_store)
        self.assertEqual(nested.exception.code, "MEDIA_ALBUM_FOLDER_NAME_INVALID")

    # Protects the documented Media favorite limit so stale picker paths cannot grow without bound.
    def test_media_parent_favorites_keep_only_the_twelve_newest(self) -> None:
        """Keep the newest 12 verified Media parents and retire only the oldest favorite."""

        favorites = []
        for index in range(13):
            favorite = self.root / f"Favorite {index}"
            favorite.mkdir()
            favorites.append(favorite)
            self.media_store.save_parent_favorite(str(favorite))

        saved = self.media_store.load()["parent_favorites"]

        self.assertEqual(len(saved), 12)
        self.assertEqual(saved[0], str(favorites[-1].resolve()))
        self.assertNotIn(str(favorites[0].resolve()), saved)

    # Confirms imported bytes are verified and repeated names allocate new direct-child files without replacement.
    def test_image_intake_validates_content_and_never_overwrites(self) -> None:
        """Import repeated PNG names safely while rejecting traversal and renamed non-image bytes."""

        album_id = self.add_album()
        png_content = b"\x89PNG\r\n\x1a\nintake"
        data_url = "data:image/png;base64," + base64.b64encode(png_content).decode("ascii")

        first = import_media_image(album_id, "cover.png", data_url, self.media_store)
        second = import_media_image(album_id, "cover.png", data_url, self.media_store)

        self.assertEqual(first["path"], "cover.png")
        self.assertEqual(second["path"], "cover (2).png")
        self.assertEqual((self.album_root / "cover.png").read_bytes(), png_content)
        self.assertEqual((self.album_root / "cover (2).png").read_bytes(), png_content)
        with self.assertRaises(AppError) as traversal:
            import_media_image(album_id, "../outside.png", data_url, self.media_store)
        self.assertEqual(traversal.exception.code, "MEDIA_IMPORT_NAME_INVALID")
        invalid_url = "data:image/png;base64," + base64.b64encode(b"not an image").decode("ascii")
        with self.assertRaises(AppError) as invalid:
            import_media_image(album_id, "renamed.png", invalid_url, self.media_store)
        self.assertEqual(invalid.exception.code, "MEDIA_IMPORT_CONTENT_INVALID")
        mismatched_url = data_url.replace("data:image/png", "data:image/jpeg")
        with self.assertRaises(AppError) as mismatched:
            import_media_image(album_id, "mismatch.png", mismatched_url, self.media_store)
        self.assertEqual(mismatched.exception.code, "MEDIA_IMPORT_DATA_INVALID")
        self.assertFalse((self.root / "outside.png").exists())
        self.assertFalse((self.album_root / "renamed.png").exists())

    # Confirms previews are pixel-bounded data URLs and traversal cannot address files outside the selected album.
    def test_preview_is_verified_and_relative_path_is_confined(self) -> None:
        """Return a 512-pixel thumbnail while rejecting parent traversal before filesystem access."""

        self.write_png("cover.png", (2048, 1024))
        album_id = self.add_album()

        preview = media_preview(album_id, "cover.png", self.media_store)
        encoded = preview["data_url"].split(",", 1)[1]
        with Image.open(BytesIO(base64.b64decode(encoded))) as thumbnail:
            thumbnail_size = thumbnail.size

        self.assertTrue(preview["data_url"].startswith("data:image/jpeg;base64,"))
        self.assertLessEqual(max(thumbnail_size), 512)
        self.assertEqual((preview["width"], preview["height"]), thumbnail_size)
        self.assertNotIn(str(self.album_root), preview["data_url"])
        for unsafe_path in ("../outside.png", ".hidden.png", ".git/preview.png", "C:/outside.png"):
            with self.subTest(path=unsafe_path):
                with self.assertRaises(AppError) as raised:
                    selected_media_path(self.media_store, album_id, unsafe_path)
                self.assertEqual(raised.exception.code, "MEDIA_ITEM_PATH_INVALID")

    # Confirms copied Finder-style files and raw pixels use one native backend import boundary.
    def test_backend_clipboard_paste_imports_files_and_raw_images(self) -> None:
        """Preserve copied names, generate raw-image names, and never replace an existing album file."""

        album_id = self.add_album()
        source = self.root / "Finder cover.png"
        with Image.new("RGB", (24, 18), (120, 48, 32)) as image:
            image.save(source, format="PNG")

        copied = paste_media_clipboard(
            album_id,
            self.media_store,
            lambda: ([str(source)], None),
        )
        raw_image = Image.new("RGBA", (10, 8), (30, 60, 90, 180))
        raw = paste_media_clipboard(
            album_id,
            self.media_store,
            lambda: ([], raw_image),
        )
        duplicate = paste_media_clipboard(
            album_id,
            self.media_store,
            lambda: ([str(source)], None),
        )

        self.assertEqual(copied["imported"][0]["name"], "Finder cover.png")
        self.assertTrue(raw["imported"][0]["name"].startswith("Clipboard image "))
        self.assertEqual(duplicate["imported"][0]["name"], "Finder cover (2).png")
        self.assertTrue((self.album_root / "Finder cover.png").is_file())
        self.assertTrue((self.album_root / "Finder cover (2).png").is_file())

        project_root = Path(__file__).resolve().parents[1]
        clipboard_source = (project_root / "src" / "gitdesk" / "desktop_clipboard.py").read_text(encoding="utf-8")
        manifest = (project_root / "pyproject.toml").read_text(encoding="utf-8")
        workflow = (project_root / ".github" / "workflows" / "build-app.yml").read_text(encoding="utf-8")
        self.assertIn("readObjectsForClasses_options_", clipboard_source)
        self.assertIn("NSPasteboardURLReadingFileURLsOnlyKey", clipboard_source)
        self.assertIn('["/usr/bin/pbpaste"]', clipboard_source)
        self.assertIn('"/usr/bin/osascript"', clipboard_source)
        self.assertIn('"Pillow==12.3.0"', manifest)
        self.assertIn('"imageio-ffmpeg==0.6.0"', manifest)
        self.assertIn('"pyobjc-framework-Cocoa==12.2.1;', manifest)
        self.assertIn("--collect-all PIL", workflow)
        self.assertIn("--collect-all imageio_ffmpeg", workflow)
        self.assertIn("--collect-all AppKit", workflow)

    # Confirms album publication mirrors supported files into one stable namespace and advances explicit versions.
    def test_publish_album_creates_and_updates_dedicated_resource(self) -> None:
        """Record changed album contents as v2 while omitting files removed from the original folder."""

        image = self.write_media("stills/cover.png", b"\x89PNG\r\n\x1a\nfirst")
        video = self.write_media("clips/intro.mp4", b"video-one")
        album_id = self.add_album()

        first = publish_album(album_id, "Campaign Media", self.media_store, self.resource_store)
        image.write_bytes(b"\x89PNG\r\n\x1a\nsecond")
        video.unlink()
        self.write_media("stills/detail.jpg", b"\xff\xd8\xffdetail")
        second = publish_album(album_id, "", self.media_store, self.resource_store)
        target = self.catalog_root / "Campaign Media" / "media" / "Campaign Media"

        self.assertEqual(first["release"]["version"], 1)
        self.assertEqual(second["release"]["version"], 2)
        self.assertTrue((target / "stills" / "cover.png").exists())
        self.assertTrue((target / "stills" / "detail.jpg").exists())
        self.assertFalse((target / "clips" / "intro.mp4").exists())
        self.assertEqual(
            self.media_store.require_album(album_id)["resource_name"],
            "Campaign Media",
        )

    # Protects the exact third-mode identity and matching standalone/packaged asset dependency order.
    def test_frontend_exposes_media_as_a_third_workspace_mode(self) -> None:
        """Require Media controls and equivalent index and inline asset ordering."""

        project_root = Path(__file__).resolve().parents[1]
        ui_root = project_root / "src" / "gitdesk" / "ui"
        controller = (ui_root / "workspace-mode.js").read_text(encoding="utf-8")
        renderer = (ui_root / "media-render.js").read_text(encoding="utf-8")
        intake = (ui_root / "media-intake.js").read_text(encoding="utf-8")
        clipboard = (ui_root / "media-clipboard.js").read_text(encoding="utf-8")
        media_controller = (ui_root / "media.js").read_text(encoding="utf-8")
        editing = (ui_root / "editing.js").read_text(encoding="utf-8")
        index = (ui_root / "index.html").read_text(encoding="utf-8")
        frontend = (project_root / "src" / "gitdesk" / "frontend.py").read_text(encoding="utf-8")

        self.assertIn('["repo", "local", "media", "backup"]', controller)
        self.assertEqual(clean_workspace_mode("media"), "media")
        self.assertIn('data-workspace-mode-value="media"', controller)
        self.assertIn('document.getElementById("panel-media")', renderer)
        self.assertIn('panel.id = "panel-media";', renderer)
        self.assertNotIn('if (byId("panel-media"))', renderer)
        self.assertIn('id="publish-media-album"', renderer)
        self.assertIn('id="media-intake-tray"', intake)
        self.assertIn('"createMediaAlbum"', intake)
        self.assertIn('"importMediaImage"', intake)
        self.assertIn('addEventListener("drop"', intake)
        self.assertNotIn("navigator.clipboard", intake)
        self.assertNotIn('addEventListener("paste"', intake)
        self.assertNotIn('contenteditable="true"', intake)
        self.assertIn('"pasteMediaClipboard"', clipboard)
        self.assertIn('tray.addEventListener("keydown", handleKeydown);', clipboard)
        self.assertIn('tray.addEventListener("contextmenu", showPasteMenu);', clipboard)
        self.assertIn('button.textContent = "Paste";', clipboard)
        self.assertEqual(clipboard.count('button.textContent = "Paste";'), 1)
        self.assertNotIn("navigator.clipboard", clipboard)
        self.assertIn('panel.classList.contains("active")', clipboard)
        self.assertNotIn("data-native-paste-target", editing)
        self.assertIn('"readClipboardText"', editing)
        self.assertIn("pasteIntoControl", editing)
        self.assertIn("setRangeText", editing)
        self.assertNotIn('document.execCommand("paste")', editing)
        self.assertEqual(editing.count('label: "Paste"'), 1)
        self.assertIn('event.dataTransfer.files', intake)
        self.assertIn("Drop images into ${album.name} or paste from clipboard", intake)
        self.assertNotIn("IntersectionObserver", media_controller)
        self.assertIn("getBoundingClientRect()", media_controller)
        self.assertIn("mediaRender.releasePreview(item)", media_controller)
        self.assertIn("data-media-open-path", renderer)
        for source in (index, frontend):
            self.assertLess(source.index("local.js"), source.index("media-render.js"))
            self.assertLess(source.index("media-render.js"), source.index("media-intake.js"))
            self.assertLess(source.index("media-intake.js"), source.index("media-clipboard.js"))
            self.assertLess(source.index("media-clipboard.js"), source.index("media.js"))
            self.assertLess(source.index("media.js"), source.index("workspace-mode.js"))
            self.assertLess(source.index("workspace-mode.js"), source.index("local-permissions.js"))
            self.assertLess(source.index("media.css"), source.index("media-intake.css"))
            self.assertLess(source.index("media.css"), source.index("media-preview.css"))
            self.assertLess(source.index("media-preview.css"), source.index("media-intake.css"))

    # Prevents adjacent source tags from escaping the inliner and loading after their declared dependents.
    def test_packaged_frontend_inlines_every_declared_asset_once_and_in_order(self) -> None:
        """Require packaged styles and scripts to preserve their complete declared dependency order."""

        document = render_frontend_document()
        style_markers = [f'data-gitdesk-asset="{asset}"' for asset in INLINE_STYLES]
        script_markers = [f'data-gitdesk-asset="{asset}"' for asset in INLINE_SCRIPTS]

        for marker in style_markers + script_markers:
            with self.subTest(asset=marker):
                self.assertEqual(document.count(marker), 1)

        self.assertEqual([document.index(marker) for marker in style_markers], sorted(
            document.index(marker) for marker in style_markers
        ))
        self.assertEqual([document.index(marker) for marker in script_markers], sorted(
            document.index(marker) for marker in script_markers
        ))
        self.assertNotIn('<link rel="stylesheet" href="./media-intake.css">', document)
        self.assertNotIn('<script src="./media-intake.js"></script>', document)

    # Keeps every Media implementation unit within the project code-file ceiling.
    def test_media_code_files_stay_within_line_ceiling(self) -> None:
        """Require focused Media modules to stay at or below 400 lines."""

        project_root = Path(__file__).resolve().parents[1]
        paths = [
            project_root / "src" / "gitdesk" / "media_library.py",
            project_root / "src" / "gitdesk" / "media_library_store.py",
            project_root / "src" / "gitdesk" / "media_album_files.py",
            project_root / "src" / "gitdesk" / "desktop_clipboard.py",
            project_root / "src" / "gitdesk" / "desktop_clipboard_bridge.py",
            project_root / "src" / "gitdesk" / "media_clipboard.py",
            project_root / "src" / "gitdesk" / "media_library_publish.py",
            project_root / "src" / "gitdesk" / "media_bridge.py",
            project_root / "src" / "gitdesk" / "media_thumbnail.py",
            project_root / "src" / "gitdesk" / "ui" / "workspace-mode.js",
            project_root / "src" / "gitdesk" / "ui" / "media-render.js",
            project_root / "src" / "gitdesk" / "ui" / "media-intake.js",
            project_root / "src" / "gitdesk" / "ui" / "media-clipboard.js",
            project_root / "src" / "gitdesk" / "ui" / "media.js",
            project_root / "src" / "gitdesk" / "ui" / "media.css",
            project_root / "src" / "gitdesk" / "ui" / "media-preview.css",
            project_root / "src" / "gitdesk" / "ui" / "media-intake.css",
        ]
        for path in paths:
            with self.subTest(path=path.name):
                self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()), 400)


if __name__ == "__main__":
    unittest.main()
