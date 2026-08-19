"""Focused source and service contracts for transient Media Mode previews."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from gitdesk.media_thumbnail import MAX_THUMBNAIL_EDGE, create_ffmpeg_thumbnail


class MediaPreviewTests(unittest.TestCase):
    """Protect cross-format frame extraction and active-only frontend preview retention."""

    # Builds one valid bounded JPEG response without executing an external decoder.
    def test_ffmpeg_preview_uses_stdout_without_a_cache_file(self) -> None:
        """Require fixed argument-list decoding and validate the generated in-memory frame."""

        with BytesIO() as buffer:
            with Image.new("RGB", (320, 180), (35, 65, 95)) as image:
                image.save(buffer, format="JPEG", quality=80)
            output = buffer.getvalue()
        completed = SimpleNamespace(returncode=0, stdout=output, stderr=b"")
        fake_module = SimpleNamespace(get_ffmpeg_exe=lambda: "/packaged/ffmpeg")
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "clip.mp4"
            source.write_bytes(b"video fixture")
            with patch.dict(sys.modules, {"imageio_ffmpeg": fake_module}):
                with patch("gitdesk.media_thumbnail.subprocess.run", return_value=completed) as run:
                    thumbnail = create_ffmpeg_thumbnail(source)

        command = run.call_args.args[0]
        self.assertEqual(command[0], "/packaged/ffmpeg")
        self.assertIn("pipe:1", command)
        self.assertNotIn("-y", command)
        self.assertEqual(thumbnail["content"], output)
        self.assertLessEqual(max(thumbnail["width"], thumbnail["height"]), MAX_THUMBNAIL_EDGE)

    # Verifies the renderer never keeps generated data URLs in controller state or persistent storage.
    def test_frontend_previews_are_active_only_and_open_originals_directly(self) -> None:
        """Require viewport scans, source release, video eligibility, and one Open control per tile."""

        root = Path(__file__).resolve().parents[1]
        controller = (root / "src" / "gitdesk" / "ui" / "media.js").read_text(encoding="utf-8")
        renderer = (root / "src" / "gitdesk" / "ui" / "media-render.js").read_text(encoding="utf-8")
        library = (root / "src" / "gitdesk" / "media_library.py").read_text(encoding="utf-8")
        thumbnail = (root / "src" / "gitdesk" / "media_thumbnail.py").read_text(encoding="utf-8")

        self.assertIn("getBoundingClientRect()", controller)
        self.assertIn("image.removeAttribute(\"src\")", renderer)
        self.assertIn("data-media-open-path", renderer)
        self.assertIn('openItem(openButton.dataset.mediaOpenPath)', controller)
        self.assertNotIn("IntersectionObserver", controller)
        self.assertNotIn("localStorage", controller + renderer)
        self.assertIn('"preview_available": stat.st_size <=', library)
        self.assertIn('"0:v:0"', thumbnail)
        self.assertIn('"pipe:1"', thumbnail)


if __name__ == "__main__":
    unittest.main()
