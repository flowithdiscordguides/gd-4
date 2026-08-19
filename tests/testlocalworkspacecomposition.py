"""Source regression coverage for the Local Mode project ribbon and connected workbench."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "src" / "gitdesk" / "ui"


def ui_source(filename: str) -> str:
    """Read one frontend source file without launching the desktop runtime."""

    return (UI_ROOT / filename).read_text(encoding="utf-8")


class LocalWorkspaceCompositionTests(unittest.TestCase):
    """Protect the compact hierarchy, stable workflows, and frontend assembly order."""

    def test_ribbon_precedes_full_width_version_workspace(self) -> None:
        """Require compact project/feature context above one connected version region."""

        source = ui_source("local-render.js")
        ribbon_index = source.index('class="local-project-identity-card local-project-ribbon"')
        workbench_index = source.index('class="local-workbench"')
        version_index = source.index('id="local-versions-card"')
        self.assertLess(ribbon_index, workbench_index)
        self.assertLess(workbench_index, version_index)
        self.assertNotIn('id="local-features-card"', source)
        self.assertNotIn('id="local-feature-list"', source)
        self.assertNotIn('class="local-left-pane"', source)

    def test_progressive_disclosures_keep_secondary_commands_quiet(self) -> None:
        """Keep maintenance, feature creation, and occasional version tools in their intended disclosures."""

        render_source = ui_source("local-render.js")
        picker_source = ui_source("local-feature-picker.js")
        action_source = ui_source("local-version-workspace.js")
        self.assertIn('<summary>Maintenance</summary>', render_source)
        self.assertIn('<span>New project</span>', render_source)
        self.assertIn('<label for="local-feature-name">Create new feature</label>', picker_source)
        self.assertIn('placeholder="Feature name"', picker_source)
        self.assertIn('<summary>More tools</summary>', action_source)
        core_index = action_source.index('class="local-version-core-actions"')
        more_index = action_source.index('class="local-version-more-actions"')
        self.assertLess(core_index, more_index)

    def test_header_and_toolbar_controls_use_restrained_visual_emphasis(self) -> None:
        """Keep the active state clear without stripes, toolbar halos, or an oversized New project action."""

        polish_source = ui_source("polish.css")
        accent_source = ui_source("accent-theme.css")
        badge_source = ui_source("badges.css")
        layout_source = ui_source("local-project-layout.css")
        self.assertNotIn(".tab-button.active::before", polish_source)
        self.assertNotIn(".sidebar.toolbar .tab-button::before", accent_source)
        self.assertNotIn(".tab-button.has-success-notification", badge_source)
        self.assertIn("height: 36px;", layout_source)
        self.assertIn("min-height: 36px;", layout_source)
        self.assertIn("box-shadow: none;", layout_source)

    def test_project_identity_is_compact_and_editing_remains_modal(self) -> None:
        """Require picker-based project context, category, action dock, and focused metadata editing."""

        render_source = ui_source("local-render.js")
        identity_source = ui_source("local-project-identity.js")
        controls_source = ui_source("local-controls.js")
        detail_source = ui_source("local-version-detail.js")
        self.assertIn("local-project-metadata-list", render_source)
        self.assertIn("<dt>Project</dt>", render_source)
        self.assertIn("<dt>Category</dt>", render_source)
        self.assertIn('id="local-project-picker-trigger"', render_source)
        self.assertIn('class="local-project-action-dock"', render_source)
        self.assertNotIn('id="local-active-project-name"', render_source)
        self.assertNotIn('id="local-project-path"', render_source)
        self.assertIn('role="dialog" aria-modal="true"', identity_source)
        self.assertIn('id="local-project-metadata-name"', identity_source)
        self.assertIn('id="local-project-metadata-category"', identity_source)
        self.assertIn("await callbacks.onRename(activeProjectPath, nextName);", identity_source)
        self.assertIn("await callbacks.onCategoryChange(activeProjectPath, nextCategory);", identity_source)
        self.assertIn('["choose-local-project-icon-modal", "Choose project icon", "image", false]', controls_source)
        self.assertIn('["clear-local-project-icon", "Use automatic icon", "folder", false]', controls_source)
        self.assertIn('status.textContent = "Latest version app icon";', identity_source)
        self.assertIn("removeButton.innerHTML = versionDetail.trashIcon();", controls_source)
        self.assertIn("window.GitDeskLocalVersionDetail = { bind, render, trashIcon };", detail_source)

    def test_project_identity_orders_artwork_project_feature_and_right_context(self) -> None:
        """Match the screenshot's artwork-first Project/Feature path and far-right Category sequence."""

        render_source = ui_source("local-render.js")
        layout_source = ui_source("local-project-layout.css")
        metadata_source = ui_source("local-project-metadata.css")
        selector_index = render_source.index('class="local-project-metadata-list local-project-selection-list"')
        artwork_index = render_source.index('class="local-project-artwork"')
        feature_index = render_source.index('class="local-project-metadata-list local-feature-selection-list"')
        category_index = render_source.index('class="local-project-category-block"')
        self.assertLess(artwork_index, selector_index)
        self.assertLess(selector_index, feature_index)
        self.assertLess(feature_index, category_index)
        self.assertIn(
            "grid-template-columns: 62px minmax(220px, 360px) minmax(220px, 1fr) minmax(260px, max-content);",
            layout_source,
        )
        self.assertIn("grid-template-columns: minmax(0, 1fr);", layout_source)
        self.assertIn("justify-self: end;", metadata_source)
        self.assertIn("grid-column: 1 / -1;", metadata_source)

    def test_project_artwork_is_centered_from_the_frame_midpoint(self) -> None:
        """Require symmetric compact image sizing and explicit midpoint positioning."""

        source = ui_source("local-project-layout.css")
        self.assertIn("top: 50%;", source)
        self.assertIn("left: 50%;", source)
        self.assertIn("width: calc(100% - 16px);", source)
        self.assertIn("height: calc(100% - 16px);", source)
        self.assertIn("object-position: center center;", source)
        self.assertIn("transform: translate(-50%, -50%);", source)

    def test_version_inspector_preserves_context_and_stable_action_ids(self) -> None:
        """Keep factual inspector fields and every established version command while reprioritizing them."""

        render_source = ui_source("local-render.js")
        action_source = ui_source("local-version-workspace.js")
        list_index = render_source.index('id="local-version-list"')
        detail_index = render_source.index('id="local-version-detail"')
        self.assertLess(list_index, detail_index)
        for identifier in (
            "local-selected-version-name",
            "local-selected-version-project",
            "local-selected-version-feature",
            "local-selected-version-path",
            "local-selected-version-resources",
        ):
            self.assertIn(f'id="{identifier}"', render_source)
        for identifier in (
            "duplicate-local-version",
            "open-local-folder",
            "open-local-vscode",
            "name-local-v1",
            "open-local-notes",
            "sync-local-private-beta",
            "open-sync-ignore",
            "manage-local-shared-resources",
            "local-version-sync-rail",
        ):
            self.assertIn(f'id="{identifier}"', action_source)

    def test_project_picker_keeps_downward_expansion_and_editor_shortcut(self) -> None:
        """Preserve deterministic project ordering, downward placement, and row-local editor launching."""

        picker_source = ui_source("local-project-picker.js")
        render_source = ui_source("local-render.js")
        picker_style = ui_source("local-project-picker.css")
        identity_source = ui_source("local-project-identity.js")
        controller_source = ui_source("local.js")
        action_source = ui_source("local-version-actions.js")
        below_index = picker_source.index("triggerRect.bottom + MENU_TRIGGER_GAP")
        fixed_top_index = picker_source.index("menu.style.top = `${top}px`;")
        centered_index = picker_source.index("const targetCenter = target")
        self.assertIn("compareLabels(left.category, right.category)", picker_source)
        self.assertIn("compareLabels(left.name, right.name)", picker_source)
        self.assertIn("const ADDITIONAL_OPTION_COUNT = 5;", picker_source)
        self.assertIn("window.innerHeight - top - VIEWPORT_MARGIN", picker_source)
        self.assertLess(below_index, fixed_top_index)
        self.assertLess(fixed_top_index, centered_index)
        self.assertIn('aria-haspopup="menu"', render_source)
        self.assertNotIn('id="local-project-select"', render_source)
        self.assertIn('class="local-project-picker-option-row"', picker_source)
        self.assertIn('data-version-path="${escapeHtml(versionPath)}"', picker_source)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto;", picker_style)
        self.assertIn("onOpenCurrentVersion: (path)", identity_source)
        self.assertIn("onOpenCurrentVersion: openVSCode", controller_source)
        self.assertIn('addEventListener("click", () => controller.onOpenVSCode())', action_source)

    def test_sparse_lists_and_frontend_dependency_order_remain_stable(self) -> None:
        """Keep content-sized rows, independent inspector scrolling, and matching asset order."""

        list_source = ui_source("list-layout.css")
        layout_source = ui_source("local-project-layout.css")
        detail_source = ui_source("local-version-detail.css")
        controller_source = ui_source("local.js")
        self.assertIn('[class$="-list"]', list_source)
        self.assertIn("grid-auto-rows: max-content", list_source)
        self.assertIn("align-content: start", list_source)
        self.assertNotIn("height: calc(100vh - 218px)", layout_source)
        self.assertIn("scrollbar-gutter: stable", detail_source)
        self.assertNotIn("minmax(16px, 1fr)", detail_source)
        self.assertNotIn("state.accordions.versions = true", controller_source)
        index_source = ui_source("index.html")
        frontend_source = (ROOT / "src" / "gitdesk" / "frontend.py").read_text(encoding="utf-8")
        for source in (index_source, frontend_source):
            self.assertLess(source.index("local.css"), source.index("local-project-layout.css"))
            self.assertLess(source.index("local-project-layout.css"), source.index("local-project-metadata.css"))
            self.assertLess(source.index("local-project-picker.css"), source.index("local-feature-picker.css"))
            self.assertLess(source.index("local-feature-picker.css"), source.index("local-version-detail.css"))
            self.assertLess(source.index("local-version-detail.js"), source.index("local-render.js"))
            self.assertLess(source.index("local-project-picker.js"), source.index("local-feature-picker.js"))
            self.assertLess(source.index("local-feature-picker.js"), source.index("local.js"))
            self.assertLess(source.index("local-project-identity.js"), source.index("local.js"))

    def test_workbench_modules_remain_below_the_physical_line_ceiling(self) -> None:
        """Keep redesigned responsibilities modular instead of growing near-limit source files."""

        paths = [
            UI_ROOT / "local-render.js",
            UI_ROOT / "local-feature-picker.js",
            UI_ROOT / "local-feature-picker.css",
            UI_ROOT / "local-project-layout.css",
            UI_ROOT / "local-project-metadata.css",
            UI_ROOT / "local-version-detail.css",
            UI_ROOT / "local-version-workspace.css",
            UI_ROOT / "gitdesk-guide-topics-local.js",
            UI_ROOT / "gitdesk-guide-topics-secondary.js",
            Path(__file__),
        ]
        for path in paths:
            with self.subTest(path=path.name):
                self.assertLess(len(path.read_text(encoding="utf-8").splitlines()), 400)


if __name__ == "__main__":
    unittest.main()
