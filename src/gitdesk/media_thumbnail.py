"""Create transient pixel-bounded Media Mode thumbnails without exposing original bytes."""

from __future__ import annotations

# Standard-library helpers keep image and video thumbnail responses in memory and process-bounded.
from io import BytesIO
from pathlib import Path
import subprocess
from typing import Any
import warnings

from gitdesk.errors import AppError


# A 512-pixel edge is sufficient for retina contact-sheet tiles without full-resolution WebView decoding.
MAX_THUMBNAIL_EDGE = 512

# Pillow handles modest raster sources in-process; larger and video sources use a short-lived decoder process.
MAX_THUMBNAIL_SOURCE_PIXELS = 16_000_000

# Encoded output remains far below this ceiling at 512 pixels, even for noisy source frames.
MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024

# A stuck or malformed decoder must not keep a preview worker alive indefinitely.
THUMBNAIL_TIMEOUT_SECONDS = 15

# Pillow-supported formats take the lower-overhead path before the format-aware FFmpeg fallback.
EXPECTED_IMAGE_FORMATS = {
    ".avif": {"AVIF"},
    ".bmp": {"BMP"},
    ".gif": {"GIF"},
    ".ico": {"ICO"},
    ".jpeg": {"JPEG"},
    ".jpg": {"JPEG"},
    ".png": {"PNG"},
    ".tif": {"TIFF"},
    ".tiff": {"TIFF"},
    ".webp": {"WEBP"},
}


# Returns whether a decoded frame needs an alpha-preserving PNG thumbnail.
def image_has_alpha(image: Any) -> bool:
    """Return whether the image has an alpha channel or palette transparency."""

    return "A" in image.getbands() or "transparency" in image.info


# Encodes a decoded bounded image as a safe static PNG or JPEG response.
def encode_thumbnail(image: Any) -> dict[str, object]:
    """Return encoded thumbnail bytes and dimensions for one decoded image."""

    buffer = BytesIO()
    if image_has_alpha(image):
        output = image.convert("RGBA")
        mime_type = "image/png"
        save_options = {"format": "PNG", "optimize": True}
    else:
        output = image.convert("RGB")
        mime_type = "image/jpeg"
        save_options = {"format": "JPEG", "quality": 82, "optimize": True}
    try:
        output.save(buffer, **save_options)
    finally:
        output.close()
    content = buffer.getvalue()
    if not content or len(content) > MAX_THUMBNAIL_BYTES:
        raise AppError("Generated media preview is invalid.", "MEDIA_PREVIEW_INVALID")
    return {
        "content": content,
        "mime_type": mime_type,
        "width": image.width,
        "height": image.height,
    }


# Produces one modest raster thumbnail in-process, or None when another decoder path is required.
def create_pillow_thumbnail(path: Path) -> dict[str, object] | None:
    """Return a Pillow-generated raster thumbnail when the source can be decoded safely in-process."""

    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as error:
        raise AppError(
            "Media thumbnail support is not installed.",
            "MEDIA_PREVIEW_DEPENDENCY_MISSING",
        ) from error
    suffix = path.suffix.lower()
    expected_formats = EXPECTED_IMAGE_FORMATS.get(suffix)
    if not expected_formats:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                source_format = str(source.format or "").upper()
                width, height = source.size
                if source_format not in expected_formats:
                    raise AppError("Selected image content is invalid.", "MEDIA_PREVIEW_INVALID")
                if width <= 0 or height <= 0 or width * height > MAX_THUMBNAIL_SOURCE_PIXELS:
                    return None
                source.seek(0)
                source.thumbnail(
                    (MAX_THUMBNAIL_EDGE, MAX_THUMBNAIL_EDGE),
                    Image.Resampling.LANCZOS,
                    reducing_gap=2.0,
                )
                thumbnail = ImageOps.exif_transpose(source)
                try:
                    thumbnail.load()
                    return encode_thumbnail(thumbnail)
                finally:
                    if thumbnail is not source:
                        thumbnail.close()
    except AppError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        return None
    except (OSError, UnidentifiedImageError, ValueError):
        return None


# Uses the packaged FFmpeg executable to rasterize one image or first video frame directly to stdout.
def create_ffmpeg_thumbnail(path: Path) -> dict[str, object] | None:
    """Return a cross-format JPEG thumbnail without creating a cache or temporary preview file."""

    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise AppError(
            "Media thumbnail support is not installed.",
            "MEDIA_PREVIEW_DEPENDENCY_MISSING",
        ) from error
    try:
        executable = imageio_ffmpeg.get_ffmpeg_exe()
        command = [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-threads",
            "1",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-frames:v",
            "1",
            "-vf",
            f"scale={MAX_THUMBNAIL_EDGE}:{MAX_THUMBNAIL_EDGE}:force_original_aspect_ratio=decrease",
            "-f",
            "image2pipe",
            "-c:v",
            "mjpeg",
            "-q:v",
            "5",
            "pipe:1",
        ]
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=THUMBNAIL_TIMEOUT_SECONDS,
            creationflags=creation_flags,
        )
    except subprocess.TimeoutExpired as error:
        raise AppError("Media preview generation timed out.", "MEDIA_PREVIEW_TIMEOUT") from error
    except (OSError, RuntimeError) as error:
        raise AppError("Media preview decoder is unavailable.", "MEDIA_PREVIEW_DECODER_FAILED") from error
    if result.returncode != 0 or not result.stdout or len(result.stdout) > MAX_THUMBNAIL_BYTES:
        return None
    try:
        from PIL import Image, UnidentifiedImageError

        with Image.open(BytesIO(result.stdout)) as generated:
            if generated.format != "JPEG" or max(generated.size) > MAX_THUMBNAIL_EDGE:
                return None
            generated.load()
            return {
                "content": result.stdout,
                "mime_type": "image/jpeg",
                "width": generated.width,
                "height": generated.height,
            }
    except (OSError, UnidentifiedImageError, ValueError):
        return None


# Selects the low-overhead image path first, then cross-format in-memory frame extraction.
def create_media_thumbnail(path: Path, kind: str) -> dict[str, object] | None:
    """Return one static image or video thumbnail without storing generated preview data."""

    if kind == "image":
        thumbnail = create_pillow_thumbnail(path)
        if thumbnail:
            return thumbnail
    return create_ffmpeg_thumbnail(path)
