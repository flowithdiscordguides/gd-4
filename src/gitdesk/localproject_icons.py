"""Validation, preview encoding, and metadata updates for Local Mode project artwork."""

from __future__ import annotations

import base64
from pathlib import Path
import re
from typing import Any
from xml.etree import ElementTree

from gitdesk import localfeatures
from gitdesk.errors import AppError
from gitdesk.localproject_records import clean_local_project_list


# Project artwork stays bounded before it is encoded into a WebUI response.
MAX_PROJECT_ICON_BYTES = 5 * 1024 * 1024

# Automatic project artwork has one canonical location inside the current physical version.
AUTOMATIC_APP_ICON_PATH = Path("media") / "app-icon.svg"

# These formats have stable WebView support and can be verified without an image-decoding dependency.
ICON_MIME_TYPES = {
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}

# SVG elements capable of scripting, foreign markup, or nested browsing are excluded from image previews.
UNSAFE_SVG_ELEMENTS = {
    "animate", "animatemotion", "animatetransform", "audio", "discard", "embed", "foreignobject",
    "iframe", "object", "script", "set", "style", "video",
}

# URL-bearing style properties may reference internal SVG definitions but not external content.
STYLE_URL_PATTERN = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)


# Resolves an icon selected by the user and proves it is a regular file inside the active project.
def validated_project_icon_path(project_path_value: Any, icon_path_value: Any) -> Path:
    """Return a safe in-project image path or raise a structured validation error."""

    raw_project_value = str(project_path_value or "").strip()
    raw_icon_value = str(icon_path_value or "").strip()
    if not raw_icon_value:
        raise AppError("Choose an image from the active project folder.", "LOCAL_PROJECT_ICON_EMPTY")
    try:
        project_path = Path(raw_project_value).expanduser().resolve()
        raw_icon_path = Path(raw_icon_value).expanduser()
        if not project_path.is_dir():
            raise AppError("The selected local project folder is unavailable.", "LOCAL_PROJECT_PATH_INVALID")
        if raw_icon_path.is_symlink():
            raise AppError("Project icons cannot be symbolic links.", "LOCAL_PROJECT_ICON_SYMLINK")
        icon_path = raw_icon_path.resolve()
    except AppError:
        raise
    except (OSError, RuntimeError) as error:
        raise AppError("The selected project icon path is unavailable.", "LOCAL_PROJECT_ICON_MISSING") from error

    try:
        icon_path.relative_to(project_path)
    except ValueError as error:
        raise AppError(
            "Choose an image stored inside the active project folder.",
            "LOCAL_PROJECT_ICON_OUTSIDE_PROJECT",
        ) from error
    try:
        is_file = icon_path.is_file()
        file_size = icon_path.stat().st_size if is_file else 0
    except OSError as error:
        raise AppError("The selected project icon file is unavailable.", "LOCAL_PROJECT_ICON_MISSING") from error
    if not is_file:
        raise AppError("The selected project icon file is unavailable.", "LOCAL_PROJECT_ICON_MISSING")
    if icon_path.suffix.lower() not in ICON_MIME_TYPES:
        raise AppError(
            "Choose a PNG, JPEG, GIF, WebP, BMP, ICO, or SVG image.",
            "LOCAL_PROJECT_ICON_TYPE_INVALID",
        )
    if file_size > MAX_PROJECT_ICON_BYTES:
        raise AppError("Project icons must be 5 MB or smaller.", "LOCAL_PROJECT_ICON_TOO_LARGE")
    return icon_path


# Confirms raster signatures so renamed arbitrary files never reach the WebView as images.
def validate_raster_bytes(icon_path: Path, content: bytes) -> None:
    """Raise an AppError when raster bytes do not match the selected file extension."""

    suffix = icon_path.suffix.lower()
    valid = {
        ".bmp": content.startswith(b"BM"),
        ".gif": content.startswith((b"GIF87a", b"GIF89a")),
        ".ico": content.startswith(b"\x00\x00\x01\x00"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
    }.get(suffix, False)
    if not valid:
        raise AppError("The selected image content is invalid.", "LOCAL_PROJECT_ICON_CONTENT_INVALID")


# Reads the local XML name from an SVG tag or namespaced attribute.
def svg_local_name(value: str) -> str:
    """Return a lowercase SVG element or attribute name without its namespace."""

    return value.rsplit("}", 1)[-1].lower()


# Rejects active SVG content and network-capable references before the source reaches an image element.
def validate_svg_bytes(content: bytes) -> None:
    """Raise an AppError unless SVG bytes are well-formed, passive, and self-contained."""

    try:
        source = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise AppError("The selected SVG is not valid UTF-8.", "LOCAL_PROJECT_ICON_CONTENT_INVALID") from error
    lowered_source = source.lower()
    if any(marker in lowered_source for marker in ("<!doctype", "<!entity", "<?xml-stylesheet")):
        raise AppError("Project SVG icons cannot declare document entities.", "LOCAL_PROJECT_ICON_SVG_UNSAFE")
    try:
        root = ElementTree.fromstring(source)
    except ElementTree.ParseError as error:
        raise AppError("The selected SVG is not valid XML.", "LOCAL_PROJECT_ICON_CONTENT_INVALID") from error
    if svg_local_name(root.tag) != "svg":
        raise AppError("The selected file is not an SVG image.", "LOCAL_PROJECT_ICON_CONTENT_INVALID")

    for element in root.iter():
        if svg_local_name(element.tag) in UNSAFE_SVG_ELEMENTS:
            raise AppError("Project SVG icons must contain passive artwork only.", "LOCAL_PROJECT_ICON_SVG_UNSAFE")
        for raw_name, raw_value in element.attrib.items():
            name = svg_local_name(raw_name)
            value = str(raw_value or "").strip()
            lowered_value = value.lower()
            if name.startswith("on") or "javascript:" in lowered_value:
                raise AppError("Project SVG icons cannot contain scripts.", "LOCAL_PROJECT_ICON_SVG_UNSAFE")
            if name in {"href", "src"} and value and not value.startswith("#"):
                raise AppError("Project SVG icons cannot load external content.", "LOCAL_PROJECT_ICON_SVG_UNSAFE")
            references = [match.group(2).strip() for match in STYLE_URL_PATTERN.finditer(value)]
            if any(reference and not reference.startswith("#") for reference in references):
                raise AppError(
                    "Project SVG icons cannot load external content.",
                    "LOCAL_PROJECT_ICON_SVG_UNSAFE",
                )


# Validates image bytes and returns a self-contained URL that never exposes filesystem access to the WebView.
def project_icon_data_url(project_path_value: Any, icon_path_value: Any) -> str:
    """Return a validated image data URL for one project icon."""

    icon_path = validated_project_icon_path(project_path_value, icon_path_value)
    try:
        content = icon_path.read_bytes()
    except OSError as error:
        raise AppError("The selected project icon could not be read.", "LOCAL_PROJECT_ICON_READ_FAILED") from error
    if icon_path.suffix.lower() == ".svg":
        validate_svg_bytes(content)
    else:
        validate_raster_bytes(icon_path, content)
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{ICON_MIME_TYPES[icon_path.suffix.lower()]};base64,{encoded}"


# Produces one fallback-safe preview without letting stale artwork block Local Mode rendering.
def project_icon_preview(
    project: dict[str, Any],
    features: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Return custom, automatic, or empty artwork metadata for one frontend project record."""

    icon_path = str(project.get("icon_path") or "")
    if icon_path:
        try:
            data_url = project_icon_data_url(project.get("path"), icon_path)
        except AppError:
            data_url = ""
        return {
            "icon_path": icon_path,
            "icon_name": Path(icon_path).name,
            "icon_data_url": data_url,
            "icon_source": "custom",
        }

    current_version = localfeatures.latest_project_version(features or [])
    if current_version:
        automatic_icon_path = current_version / AUTOMATIC_APP_ICON_PATH
        try:
            data_url = project_icon_data_url(project.get("path"), automatic_icon_path)
        except AppError:
            data_url = ""
        if data_url:
            return {
                "icon_path": "",
                "icon_name": automatic_icon_path.name,
                "icon_data_url": data_url,
                "icon_source": "app",
            }
    return {"icon_path": "", "icon_name": "", "icon_data_url": "", "icon_source": ""}


# Builds the full-screen library's artwork response without changing normal active-only preview encoding.
def project_icon_previews(projects_value: Any) -> list[dict[str, str]]:
    """Return validated custom or current-version preview data for every saved project."""

    previews = []
    # Scan versions only when no definitive custom path exists, keeping custom artwork both first and inexpensive.
    for project in clean_local_project_list(projects_value):
        features = []
        if not project.get("icon_path"):
            try:
                features = localfeatures.list_features(project["path"])
            except (AppError, OSError):
                features = []
        preview = project_icon_preview(project, features)
        previews.append({
            "path": project["path"],
            "icon_data_url": preview["icon_data_url"],
        })
    return previews


# Updates only the matched project record so selection, category, and every unrelated registry field remain intact.
def local_project_icon_update(
    settings: dict[str, Any],
    project_path_value: Any,
    icon_path_value: Any,
) -> dict[str, Any]:
    """Return LocalApp registry updates that set or clear one project's custom icon path."""

    project_path = str(project_path_value or "").strip()
    icon_path = ""
    if str(icon_path_value or "").strip():
        icon_path = str(validated_project_icon_path(project_path, icon_path_value))
        project_icon_data_url(project_path, icon_path)

    projects = []
    matched = False
    for record in clean_local_project_list(settings.get("local_projects")):
        if record["path"] == project_path:
            record = {**record, "icon_path": icon_path}
            matched = True
        projects.append(record)
    if not matched:
        raise AppError("Select a saved local project first.", "LOCAL_PROJECT_NOT_FOUND")
    return {"local_projects": projects}
