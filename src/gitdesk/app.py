"""Application bootstrap for the GitDesk webui2 desktop window."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote, urlsplit

from webui import webui

from gitdesk.config import SettingsStore
from gitdesk.bridge import BridgeController
from gitdesk.frontend import UI_DIR, render_frontend_document
from gitdesk.gitops import GitService
from gitdesk.secrets import TokenStore


# The in-app Guide panel serves the standalone guide through WebUI's asset handler.
GUIDE_FILE_NAME = "gitdesk-readme.html"

# Existing guide screenshots stay in their documentation-media source folder during editable source runs.
GUIDE_MEDIA_DIRECTORY = Path(__file__).resolve().parents[2] / "media" / "readme-html-media" / "01-start-here"
GUIDE_MEDIA_NAMES = frozenset({"1)header.png", "2) toolbar.png", "3) settings.png", "4) devtools.png"})


# WebUI's file handler needs explicit content types for the frontend assets it serves.
MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml; charset=utf-8",
}


# Converts a WebUI request path into a package-relative frontend asset path.
def frontend_asset_path(request_path: str) -> Path | None:
    """Return the bundled frontend asset path for a WebUI request path."""

    clean_path = unquote(urlsplit(request_path).path).strip()
    if clean_path in {"", "/", "."}:
        clean_path = "index.html"
    if clean_path in {"webui.js", "/webui.js"}:
        return None

    # WebUI can pass relative paths such as "./app.js"; normalize only one safe asset segment.
    path_parts = [
        part
        for part in clean_path.replace("\\", "/").split("/")
        if part not in {"", "."}
    ]
    if len(path_parts) != 1 or path_parts[0] == "..":
        return None
    asset_name = path_parts[0]
    if asset_name.startswith("."):
        return None
    packaged_asset = UI_DIR / asset_name
    # Source runs reuse the existing documentation PNGs; packaged builds copy the same names into UI_DIR.
    if asset_name in GUIDE_MEDIA_NAMES and not packaged_asset.is_file():
        return GUIDE_MEDIA_DIRECTORY / asset_name
    return packaged_asset


# Lists the trusted local guide locations GitDesk can serve without accepting a frontend-supplied path.
def guide_html_candidates() -> tuple[Path, ...]:
    """Return possible packaged and source-checkout paths for the GitDesk guide document."""

    return (
        Path(__file__).resolve().parents[2] / GUIDE_FILE_NAME,
        UI_DIR / GUIDE_FILE_NAME,
    )


# Finds the first existing guide document from the fixed app-controlled path list.
def guide_html_path() -> Path | None:
    """Return the guide document path when it exists, otherwise None."""

    for candidate in guide_html_candidates():
        if candidate.is_file():
            return candidate
    return None


# Rewrites standalone guide asset paths so the same HTML can run inside WebUI's one-segment asset router.
def render_guide_document() -> str | None:
    """Return the GitDesk guide HTML adjusted for the in-app iframe route."""

    guide_path = guide_html_path()
    if guide_path is None:
        return None

    document = guide_path.read_text(encoding="utf-8")
    return (
        document
        .replace('href="src/gitdesk/ui/', 'href="./')
        .replace('src="src/gitdesk/ui/', 'src="./')
        .replace('data-guide-asset-base="src/gitdesk/ui/"', 'data-guide-asset-base="./"')
        .replace(
            'data-guide-media-base="media/readme-html-media/01-start-here/"',
            'data-guide-media-base="./"',
        )
    )


# Builds the raw HTTP response format expected by WebUI custom file handlers.
def http_response(status: HTTPStatus, content_type: str, body: str | bytes) -> str:
    """Return a complete response whose string code points preserve the intended UTF-8 wire bytes."""

    encoded_body = body.encode("utf-8") if isinstance(body, str) else body
    headers = (
        f"HTTP/1.1 {status.value} {status.phrase}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(encoded_body)}\r\n"
        "Cache-Control: no-store\r\n"
        "\r\n"
    )
    # webui2 2.5.8 encodes handler responses as Latin-1; this reversible mapping preserves every UTF-8 byte.
    transport_body = encoded_body.decode("latin-1")
    return headers + transport_body


# Serves the bundled UI from package files instead of relying on WebUI to resolve absolute paths.
def serve_frontend_file(request_path: str) -> str | None:
    """Return an HTTP response for bundled frontend assets requested by the WebUI window."""

    asset_path = frontend_asset_path(request_path)
    if asset_path is None:
        return None

    if asset_path.name == "gitdesk-readme.html":
        guide_document = render_guide_document()
        if guide_document is None:
            return http_response(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "Guide not found")
        return http_response(HTTPStatus.OK, MIME_TYPES[".html"], guide_document)

    if not asset_path.exists() or not asset_path.is_file():
        return http_response(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "Not found")

    content_type = MIME_TYPES.get(asset_path.suffix, "text/plain; charset=utf-8")
    if asset_path.suffix == ".png":
        body = asset_path.read_bytes()
    else:
        body = render_frontend_document() if asset_path.name == "index.html" else asset_path.read_text(encoding="utf-8")
    return http_response(HTTPStatus.OK, content_type, body)


# Opens the UI in WebView mode so the desktop shell is not a normal browser window.
def show_standalone_window(window: webui.Window, document: str) -> None:
    """Show GitDesk in WebUI's non-browser WebView mode or fail clearly."""

    show_webview = getattr(window, "show_wv", None)
    if not callable(show_webview):
        raise RuntimeError("This WebUI build does not expose the required WebView API.")

    if callable(show_webview) and show_webview(document):
        return

    show_browser = getattr(window, "show_browser", None)
    browser_enum = getattr(webui, "Browser", None)
    webview_browser = getattr(browser_enum, "Webview", None)
    if callable(show_browser) and webview_browser is not None and show_browser(document, webview_browser):
        return

    raise RuntimeError("WebUI WebView mode is unavailable; refusing to open GitDesk in a normal browser.")


# Builds the bridge and window so the launch function stays focused on lifecycle order.
def create_bridge(window: webui.Window) -> BridgeController:
    """Return a BridgeController wired to the app's storage and service dependencies."""

    return BridgeController(
        window=window,
        settings_store=SettingsStore(),
        token_store=TokenStore(),
        git_service=GitService(),
    )


# Launches the WebUI desktop window and blocks until the user closes it.
def run_app() -> None:
    """Start the GitDesk desktop application with the bundled HTML frontend."""

    webui.set_config(webui.Config.ui_event_blocking, False)
    window = webui.Window()
    window.set_size(1240, 820)
    window.set_position(80, 60)
    window.set_file_handler(serve_frontend_file)

    bridge = create_bridge(window)
    bridge.bind()

    try:
        show_standalone_window(window, render_frontend_document())
        webui.wait()
    finally:
        webui.clean()
