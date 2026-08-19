"""Frontend document assembly for GitDesk's WebUI desktop shell."""

from __future__ import annotations

from html import escape
from pathlib import Path


# The package-relative UI path keeps markup, styles, and scripts bundled with the Python package.
UI_DIR = Path(__file__).resolve().parent / "ui"

# Source checkouts keep the canonical app artwork under media, while packaged apps use the UI copy.
MEDIA_APP_ICON = Path(__file__).resolve().parents[2] / "media" / "app icon" / "app-icon.svg"

# The package-data app icon is the packaged fallback when the source media folder is not present.
UI_APP_ICON = UI_DIR / "app-icon.svg"

# Styles are inlined so visual layout and theme do not depend on extra WebUI asset requests.
INLINE_STYLES = (
    "styles.css",
    "repositories.css",
    "debug.css",
    "theme.css",
    "polish.css",
    "overview.css",
    "guide.css",
    "settings.css",
    "category-folders.css",
    "changed-file-tree.css",
    "glass.css",
    "project-hub.css",
    "activity-tracker.css",
    "new-project-modal.css",
    "sync-chain.css",
    "sync-chain-delete.css",
    "sync-chain-stage-three.css",
    "sync-ignore.css",
    "pull-requests.css",
    "backup-mode.css",
    "backup-selection-modal.css",
    "backup-transfer-modal.css",
    "workspace-mode.css",
    "local.css",
    "media.css",
    "media-album-navigation.css",
    "media-preview.css",
    "media-intake.css",
    "local-project-layout.css",
    "local-project-metadata.css",
    "local-project-picker.css",
    "local-feature-picker.css",
    "local-project-library.css",
    "local-version-detail.css",
    "local-version-workspace.css",
    "local-markdown-notes.css",
    "local-compare.css",
    "local-version-modal.css",
    "shared-resources.css",
    "document-builder.css",
    "document-builder-layout.css",
    "repetitive-workflows.css",
    "deployment-site-control.css",
    "pages-deployment.css",
    "actions-deployment.css",
    "actions-step-logs.css",
    "header.css",
    "badges.css",
    "overview-workflow.css",
    "list-layout.css",
    "accent-theme.css",
    "accent-settings.css",
    "theme-color-wheel.css",
    "theme-gradient-editor.css",
    "theme-profile-manager.css",
    "editor-settings.css",
    "theme-gradient-application.css",
)

# Scripts are inlined in dependency order so edit fallbacks and click handlers bind from startup.
INLINE_SCRIPTS = (
    "debug.js",
    "theme.js",
    "editing.js",
    "native.js",
    "render.js",
    "editor-settings.js",
    "toolbar-icons.js",
    "accounts.js",
    "repositories-catalog.js",
    "repositories-render.js",
    "repositories.js",
    "pull-requests-ui.js",
    "pull-requests.js",
    "changed-file-tree.js",
    "overview.js",
    "aiskills.js",
    "release-alerts.js",
    "action-jingles.js",
    "deployment-site-control.js",
    "pages-deployment.js",
    "pages.js",
    "actions-issues.js",
    "actions-step-logs.js",
    "actions-deployment.js",
    "actions-detail.js",
    "actions-refresh.js",
    "actions.js",
    "releases.js",
    "project-hub-ui.js",
    "project-hub-render.js",
    "activity-viewport.js",
    "activity-tracker.js",
    "project-hub.js",
    "sync-chain-ui.js",
    "sync-chain-render.js",
    "sync-chain-artifact-job.js",
    "sync-chain.js",
    "sync-chain-delete.js",
    "sync-chain-stage-three.js",
    "vendor-marked.js",
    "vendor-dompurify.js",
    "local-markdown-sanitizer.js",
    "local-parent-favorites.js",
    "local-version-workspace.js",
    "local-actions.js",
    "local-sync.js",
    "local-controls.js",
    "local-markdown-note-ui.js",
    "local-markdown-notes.js",
    "local-version-actions.js",
    "shared-resources.js",
    "local-version-detail.js",
    "local-version-delete.js",
    "local-render.js",
    "local-organizer.js",
    "local-project-picker.js",
    "local-feature-picker.js",
    "local-project-library.js",
    "local-project-identity.js",
    "local-project-selection.js",
    "local-compare.js",
    "local.js",
    "sync-ignore.js",
    "media-render.js",
    "media-album-navigation.js",
    "media-intake.js",
    "media-clipboard.js",
    "media-item-move.js",
    "media.js",
    "backup-destination-modal.js",
    "backup-skipped-items.js",
    "backup-transfer-modal.js",
    "backup-selection-model.js",
    "backup-selection-modal.js",
    "backup-mode.js",
    "workspace-mode.js",
    "local-category-scan.js",
    "local-permissions.js",
    "document-builder-ui.js",
    "document-builder-render.js",
    "document-builder-organizer.js",
    "document-builder.js",
    "settings-tabs.js",
    "metadata-settings.js",
    "category-folders.js",
    "theme-settings-model.js",
    "theme-gradient-model.js",
    "theme-color-wheel.js",
    "theme-gradient-editor.js",
    "theme-profile-manager.js",
    "accent-settings.js",
    "updater.js",
    "app.js",
)


# Reads one bundled frontend asset as UTF-8 text.
def read_asset(asset_name: str) -> str:
    """Return the text contents for a single bundled frontend asset."""

    return (UI_DIR / asset_name).read_text(encoding="utf-8")


# Escapes closing style tags so inlined CSS cannot terminate the generated style block early.
def safe_style_source(source: str) -> str:
    """Return CSS text that is safe to place inside an HTML style block."""

    return source.replace("</style", "<\\/style")


# Escapes closing script tags so inlined JavaScript cannot terminate the generated script block early.
def safe_script_source(source: str) -> str:
    """Return JavaScript text that is safe to place inside an HTML script block."""

    return source.replace("</script", "<\\/script")


# Reads the canonical app icon from media in source checkouts, then falls back to bundled UI package data.
def app_icon_source() -> str:
    """Return the SVG source used for the GitDesk brand mark."""

    icon_path = MEDIA_APP_ICON if MEDIA_APP_ICON.exists() else UI_APP_ICON
    return icon_path.read_text(encoding="utf-8").strip()


# Adds the CSS class and accessibility attributes needed when the standalone SVG is embedded in HTML.
def html_app_icon_source() -> str:
    """Return the app icon SVG adjusted for inline use in the app shell."""

    source = app_icon_source()
    if not source.startswith("<svg "):
        return source
    return source.replace("<svg ", '<svg class="brand-icon" aria-hidden="true" ', 1)


# Indents an inline SVG so the generated HTML remains readable during source inspection.
def indented_app_icon_source() -> str:
    """Return the app icon SVG indented to match the header markup."""

    return "\n".join(f"            {line}" for line in html_app_icon_source().splitlines())


# Replaces the static image fallback with the actual SVG source so packaged WebViews avoid image requests.
def inline_app_icon(document: str) -> str:
    """Return the frontend document with the brand app icon inlined."""

    image_tag = '            <img class="brand-icon" src="./app-icon.svg" alt="" draggable="false">'
    return document.replace(image_tag, indented_app_icon_source())


# Replaces stylesheet links with inline style blocks to remove runtime asset-load fragility.
def inline_styles(document: str) -> str:
    """Return the frontend document with bundled stylesheet links replaced by style blocks."""

    for asset_name in INLINE_STYLES:
        link_tag = f'<link rel="stylesheet" href="./{asset_name}">'
        style_block = (
            f'    <style data-gitdesk-asset="{escape(asset_name)}">\n'
            f"{safe_style_source(read_asset(asset_name))}\n"
            "    </style>"
        )
        document = document.replace(link_tag, style_block)
    return document


# Builds the exact external script group currently present in index.html.
def external_script_group() -> str:
    """Return the contiguous script tags that should be replaced by inline scripts."""

    return "\n".join(f'    <script src="./{asset_name}"></script>' for asset_name in INLINE_SCRIPTS)


# Builds one inline script block for a bundled frontend asset.
def inline_script_block(asset_name: str) -> str:
    """Return one script block containing a bundled JavaScript asset."""

    return (
        f'    <script data-gitdesk-asset="{escape(asset_name)}">\n'
        f"{safe_script_source(read_asset(asset_name))}\n"
        "    </script>"
    )


# Builds the inline script group used by the assembled WebUI document.
def inline_script_group() -> str:
    """Return inlined frontend scripts in dependency order for the WebUI document."""

    return "\n".join(inline_script_block(asset_name) for asset_name in INLINE_SCRIPTS)


# Appends new bundled scripts when the static HTML is intentionally left unchanged.
def append_missing_scripts(document: str, blocks: list[str]) -> str:
    """Return the document with missing inline scripts appended near the end of the body."""

    if not blocks:
        return document

    block_group = "\n".join(blocks)
    if "  </body>" in document:
        return document.replace("  </body>", f"{block_group}\n  </body>")
    return f"{document}\n{block_group}"


# Replaces app script tags with inline scripts so button binding does not wait on asset requests.
def inline_scripts(document: str) -> str:
    """Return the frontend document with bundled application scripts inlined."""

    external_group = external_script_group()
    if external_group in document:
        return document.replace(external_group, inline_script_group())

    for asset_name in INLINE_SCRIPTS:
        script_tag = f'<script src="./{asset_name}"></script>'
        script_block = inline_script_block(asset_name)
        if script_tag in document:
            document = document.replace(script_tag, script_block)
        else:
            document = append_missing_scripts(document, [script_block])
    return document


# Builds the complete document passed directly to WebUI at startup.
def render_frontend_document() -> str:
    """Return GitDesk's fully assembled HTML document for the desktop window."""

    document = read_asset("index.html")
    document = inline_app_icon(document)
    document = inline_styles(document)
    return inline_scripts(document)
