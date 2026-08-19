"""Source contracts for the selected-version promotion and Markdown workspace."""

from __future__ import annotations

from pathlib import Path
import unittest

from gitdesk import frontend


# LocalVersionWorkspaceSourceTests protects integration order and sanitization invariants.
class LocalVersionWorkspaceSourceTests(unittest.TestCase):
    """Verify icon, promotion, vendor, preview, and packaging contracts."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the source surfaces without executing the desktop application."""

        cls.root = Path(__file__).resolve().parents[1]
        cls.ui = cls.root / "src" / "gitdesk" / "ui"

    # Confirms every selected-version control is converted through the shared icon registry.
    def test_selected_version_actions_are_accessible_icon_controls(self) -> None:
        """Require all action ids, labels, and icon keys in one control adapter."""

        controls = (self.ui / "local-controls.js").read_text(encoding="utf-8")
        icons = (self.ui / "toolbar-icons.js").read_text(encoding="utf-8")
        comparison = (self.ui / "local-compare.js").read_text(encoding="utf-8")
        renderer = (self.ui / "render.js").read_text(encoding="utf-8")
        expected = {
            "duplicate-local-version": "newVersion",
            "open-local-folder": "folder",
            "open-local-vscode": "vscode",
            "open-local-notes": "note",
            "sync-local-private-beta": "sync",
            "open-local-compare": "compare",
            "manage-local-shared-resources": "resources",
        }
        for control_id, icon_name in expected.items():
            self.assertIn(f'["{control_id}"', controls)
            self.assertIn(f'"{icon_name}"', controls)
        self.assertIn('button.setAttribute("aria-label", label);', controls)
        self.assertIn("button.innerHTML = primary", controls)
        self.assertIn('`${icons[iconName]}<span>${label}</span>`', controls)
        self.assertIn("const VSCODE_MARKUP = `", icons)
        self.assertIn("vscode: VSCODE_MARKUP", icons)
        self.assertIn('setTooltipText(openButton, tooltipText);', comparison)
        self.assertIn('unavailable ? `Compare project versions. ${tooltipText}`', comparison)
        self.assertIn("function setTooltipText(target, text)", renderer)
        self.assertIn("target.dataset.gitdeskTooltip = nextText;", renderer)
        self.assertIn('editorButton.dataset.editorTooltipTemplate = "Open version in {editor}";', controls)
        workspace = (self.ui / "local-version-workspace.js").read_text(encoding="utf-8")
        styles = (self.ui / "local-version-workspace.css").read_text(encoding="utf-8")
        self.assertLess(
            workspace.index('class="local-version-core-actions"'),
            workspace.index('class="local-version-more-actions"'),
        )
        self.assertIn('<summary>More tools</summary>', workspace)
        self.assertIn(".local-version-core-actions .local-icon-primary span", styles)
        self.assertIn("display: none;", styles)
        primary_rule_start = styles.index(".local-version-core-actions .local-icon-primary {")
        primary_rule_end = styles.index("}", primary_rule_start)
        primary_rule = styles[primary_rule_start:primary_rule_end]
        self.assertNotIn("grid-template-columns", primary_rule)

    # Confirms configured Public extends the embedded rail with Stage 3 and its publication checkbox.
    def test_public_stage_extends_inline_promotion(self) -> None:
        """Resolve all configured edges and save final mode through the project's chain."""

        workspace = (self.ui / "local-version-workspace.js").read_text(encoding="utf-8")
        styles = (self.ui / "local-version-workspace.css").read_text(encoding="utf-8")
        sync_source = (self.ui / "sync-chain.js").read_text(encoding="utf-8")
        actions = (self.ui / "local-actions.js").read_text(encoding="utf-8")

        self.assertIn("stages.private_beta && stages.public_beta", workspace)
        self.assertIn('"local_to_private_beta"', workspace)
        self.assertIn('"private_beta_to_public_beta"', workspace)
        self.assertIn('"public_beta_to_public"', workspace)
        self.assertIn("const hasPublic = Boolean(stages.public);", workspace)
        self.assertIn('stageMarkup("Public", stages.public', workspace)
        self.assertIn("data-local-artifacts-only", workspace)
        self.assertIn(">Built artifacts only</span>", workspace)
        self.assertIn('<div class="local-promotion-stage-title">', workspace)
        self.assertIn("<strong>${escapeHtml(label)}</strong>\n        ${optionMarkup}", workspace)
        self.assertIn("chain.artifact_only_edge", workspace)
        self.assertIn('"Publish Private Beta release artifacts to Public Beta"', workspace)
        self.assertIn('receipt.sync_mode === "release_artifacts"', workspace)
        self.assertIn("localReceipt.source_path === version.path", workspace)
        self.assertIn("Boolean(selectedReceipt && !publicBetaReceipt)", workspace)
        self.assertIn("Step 1 complete. ${label}", workspace)
        self.assertIn(".local-promotion-edge.complete:not(:disabled)", styles)
        self.assertIn("background: var(--gitdesk-success-bg);", styles)
        self.assertIn("color: var(--gitdesk-success-fg);", styles)
        self.assertIn("function chainForProject(projectPath)", sync_source)
        action_source = (self.ui / "local-version-actions.js").read_text(encoding="utf-8")
        self.assertIn("syncProjectEdge(localState.active_project, edge)", action_source)
        self.assertIn("configureProjectArtifactSync(", action_source)
        self.assertIn('`[data-local-sync-edge="${edge}"]`', action_source)
        self.assertIn('addEventListener("change", handlePromotionChange)', action_source)
        self.assertIn("async function configureProjectArtifactSync(projectPath, edge, enabled)", sync_source)
        project_config_start = sync_source.index("async function configureProjectArtifactSync")
        project_config_end = sync_source.index("// Saves the explicit final-edge mode", project_config_start)
        project_config = sync_source[project_config_start:project_config_end]
        self.assertIn("chain_id: chain.id", project_config)
        self.assertNotIn("state.activeChainId", project_config)
        export_start = sync_source.index("window.GitDeskSyncChains = {")
        export_end = sync_source.index("};", export_start)
        exports = sync_source[export_start:export_end]
        self.assertIn("  configureProjectArtifactSync,", exports)
        self.assertIn("  hasProjectNotification,", exports)
        self.assertIn("  refresh,", exports)
        self.assertIn(".local-promotion-flow.has-public", styles)
        self.assertIn(".local-promotion-flow,\n  .local-promotion-flow.has-public", styles)
        self.assertIn('#panel-local .local-promotion-artifact-option input[type="checkbox"]', styles)
        self.assertIn("width: 15px;", styles)
        self.assertIn("-webkit-text-fill-color: currentColor;", styles)
        self.assertIn("syncButton.hidden = false;", actions)
        self.assertNotIn("syncButton.hidden = hasPublicBeta;", actions)

    # Confirms Local Mode owns one visible promotion request across every state-driven rail rebuild.
    def test_inline_promotion_is_single_flight_across_rerenders(self) -> None:
        """Disable every rail action and expose progress until the exact native request settles."""

        action_source = (self.ui / "local-version-actions.js").read_text(encoding="utf-8")
        workspace = (self.ui / "local-version-workspace.js").read_text(encoding="utf-8")
        styles = (self.ui / "local-version-workspace.css").read_text(encoding="utf-8")

        self.assertIn('let pendingPromotionEdge = "";', action_source)
        self.assertIn("if (!edge || pendingPromotionEdge)", action_source)
        self.assertIn("pendingPromotionEdge = edge;", action_source)
        self.assertIn('pendingPromotionEdge = "";', action_source)
        self.assertIn("refreshPromotionState();", action_source)
        self.assertIn("{ bind, currentPendingPromotionEdge }", action_source)
        self.assertIn("actionManager.currentPendingPromotionEdge()", workspace)
        self.assertIn('rail.setAttribute("aria-busy", String(Boolean(pendingEdge)))', workspace)
        self.assertIn('aria-busy="${pending}"', workspace)
        self.assertIn('disabled || pendingEdge ? "disabled"', workspace)
        self.assertIn("Syncing Private Beta to Public Beta…", workspace)
        self.assertIn("function artifactOptionMarkup(chain, edge, disabled)", workspace)
        self.assertIn('artifactOptionMarkup(chain, "public_beta_to_public", pendingEdge)', workspace)
        self.assertIn('artifactOptionMarkup(chain, "private_beta_to_public_beta", pendingEdge)', workspace)
        self.assertIn(".local-promotion-edge.is-syncing svg", styles)

    # Confirms Marked output reaches the preview only after DOMPurify sanitization.
    def test_preview_sink_receives_only_dompurify_output(self) -> None:
        """Require parser, sanitizer, then preview sink ordering with no persisted HTML."""

        notes = (self.ui / "local-markdown-notes.js").read_text(encoding="utf-8")
        sanitizer = (self.ui / "local-markdown-sanitizer.js").read_text(encoding="utf-8")
        parse_index = sanitizer.index("markdownRenderer.parse")
        sanitize_index = sanitizer.index("purifier.sanitize", parse_index)
        sink_index = notes.index('byId("local-note-preview").innerHTML = sanitizedHtml;')

        self.assertLess(parse_index, sanitize_index)
        self.assertNotIn("rendered_html", notes)
        self.assertIn("markdownSanitizer.render(state.content)", notes)
        self.assertIn('FORBID_ATTR: ["style"]', sanitizer)
        self.assertIn('"script", "style", "iframe", "object", "embed"', sanitizer)
        self.assertGreaterEqual(sink_index, 0)

    # Confirms note binding owns a real header target and preserves visible textarea keyboard focus.
    def test_note_modal_binding_and_focus_targets_exist(self) -> None:
        """Keep the modal binder live and the primary editor visibly keyboard-focused."""

        markup = (self.ui / "local-markdown-note-ui.js").read_text(encoding="utf-8")
        styles = (self.ui / "local-markdown-notes.css").read_text(encoding="utf-8")
        self.assertIn('id="local-notes-header"', markup)
        self.assertIn("#local-note-source:focus-visible", styles)
        self.assertNotIn("#local-note-source:focus {\n  outline: 0;\n  box-shadow: none;", styles)

    # Confirms official pinned browser bundles load before the project-note controller in both registries.
    def test_vendor_versions_and_asset_order_are_locked(self) -> None:
        """Require local packages, no CDN, and matching static/assembled dependency order."""

        package_source = (self.root / "package.json").read_text(encoding="utf-8")
        vendor_source = (self.root / "scripts" / "vendor-note-dependencies.mjs").read_text(encoding="utf-8")
        workflow_source = (self.root / ".github" / "workflows" / "build-app.yml").read_text(encoding="utf-8")
        index_source = (self.ui / "index.html").read_text(encoding="utf-8")
        ordered_assets = [
            "vendor-marked.js",
            "vendor-dompurify.js",
            "local-markdown-sanitizer.js",
            "local-markdown-note-ui.js",
            "local-markdown-notes.js",
            "local-version-actions.js",
        ]

        self.assertIn('"dompurify": "3.4.13"', package_source)
        self.assertIn('"marked": "18.0.9"', package_source)
        self.assertIn('"node_modules", "marked", "LICENSE"', vendor_source)
        self.assertNotIn('"node_modules", "marked", "LICENSE.md"', vendor_source)
        self.assertIn("uses: actions/setup-node@v4", workflow_source)
        self.assertIn('node-version: "20"', workflow_source)
        self.assertLess(workflow_source.index("run: npm ci"), workflow_source.index("python -m pip install ."))
        self.assertLess(
            workflow_source.index("run: npm ci"),
            workflow_source.index('python -m unittest discover -s tests -p "test*.py"'),
        )
        self.assertNotIn("cdn.", index_source)
        self.assertEqual(
            sorted(index_source.index(asset) for asset in ordered_assets),
            [index_source.index(asset) for asset in ordered_assets],
        )
        self.assertEqual(
            sorted(frontend.INLINE_SCRIPTS.index(asset) for asset in ordered_assets),
            [frontend.INLINE_SCRIPTS.index(asset) for asset in ordered_assets],
        )

    # Confirms every first-party touched code file remains inside the repository file ceiling.
    def test_selected_version_code_files_stay_below_line_ceiling(self) -> None:
        """Keep focused backend and frontend modules at no more than 400 lines."""

        paths = [
            self.root / "src" / "gitdesk" / "localnotes.py",
            self.root / "src" / "gitdesk" / "localnote_bridge.py",
            self.ui / "local-markdown-notes.js",
            self.ui / "local-markdown-note-ui.js",
            self.ui / "local-markdown-sanitizer.js",
            self.ui / "local-markdown-notes.css",
            self.ui / "local-version-actions.js",
            self.ui / "local-version-workspace.js",
            self.ui / "local-version-workspace.css",
            self.ui / "local-compare.js",
            self.ui / "local-controls.js",
            self.ui / "render.js",
            self.ui / "toolbar-icons.js",
            self.ui / "index.html",
        ]
        for path in paths:
            with self.subTest(path=path.name):
                self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()), 400)


if __name__ == "__main__":
    unittest.main()
