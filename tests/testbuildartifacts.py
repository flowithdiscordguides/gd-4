"""Regression coverage for architecture-specific macOS build and update artifacts."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from gitdesk.errors import AppError
from gitdesk import updater


# BuildArtifactTests protects native macOS matrix labels, verification, and updater asset routing.
class BuildArtifactTests(unittest.TestCase):
    """Verify Apple Silicon and Intel builds remain distinct from CI through self-update selection."""

    # Returns the checked-in workflow text so matrix assertions use the same source GitHub executes.
    def workflow_source(self) -> str:
        """Return the desktop build workflow as UTF-8 text without invoking GitHub Actions."""

        workflow_path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "build-app.yml"
        return workflow_path.read_text(encoding="utf-8")

    # Returns the verifier source so its architecture boundary is covered without running macOS tools.
    def bundle_verifier_source(self) -> str:
        """Return the macOS bundle verifier as UTF-8 text for platform-neutral source assertions."""

        verifier_path = Path(__file__).resolve().parents[1] / "packaging" / "verify-macos-bundle.py"
        return verifier_path.read_text(encoding="utf-8")

    # Returns the WebUI staging helper so native runtime selection is covered without invoking macOS tools.
    def webui_stager_source(self) -> str:
        """Return the macOS WebUI staging helper as UTF-8 text for source contract assertions."""

        stager_path = Path(__file__).resolve().parents[1] / "packaging" / "stage-macos-webui-runtime.py"
        return stager_path.read_text(encoding="utf-8")

    # Returns the OpenSSL staging helper so the native-library collision fix is covered on every test platform.
    def openssl_stager_source(self) -> str:
        """Return the macOS OpenSSL staging helper as UTF-8 text for source contract assertions."""

        stager_path = Path(__file__).resolve().parents[1] / "packaging" / "stage-macos-openssl-runtime.py"
        return stager_path.read_text(encoding="utf-8")

    # Returns canonical dependency metadata so the native cryptography ABI cannot drift between CI runs.
    def dependency_manifest_source(self) -> str:
        """Return pyproject.toml as UTF-8 text for exact packaging dependency assertions."""

        manifest_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        return manifest_path.read_text(encoding="utf-8")

    # Returns the frozen diagnostic source so SSL and cryptography coexistence remains part of publication checks.
    def packaged_self_check_source(self) -> str:
        """Return the packaged self-check module as UTF-8 text for source contract assertions."""

        self_check_path = Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "selfcheck.py"
        return self_check_path.read_text(encoding="utf-8")

    # Returns the updater bridge source so anonymous action routing is covered without a live WebUI process.
    def updater_bridge_source(self) -> str:
        """Return the updater bridge as UTF-8 text for public check/install boundary assertions."""

        bridge_path = Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "updater_bridge.py"
        return bridge_path.read_text(encoding="utf-8")

    # Returns the updater controller source so separate Settings controls remain part of regression coverage.
    def updater_ui_source(self) -> str:
        """Return the Settings updater JavaScript as UTF-8 text for action-state assertions."""

        ui_path = Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "ui" / "updater.js"
        return ui_path.read_text(encoding="utf-8")

    # Confirms native hosted runners create separately named single-architecture macOS DMGs.
    def test_workflow_declares_distinct_apple_silicon_and_intel_builds(self) -> None:
        """Keep runner, PyInstaller, artifact, volume, and verifier labels architecture-specific."""

        workflow = self.workflow_source()

        self.assertIn("name: macOS arm64", workflow)
        self.assertIn("os: macos-15", workflow)
        self.assertIn("--target-arch arm64", workflow)
        self.assertIn("artifact_name: GitDesk-macOS-arm64", workflow)
        self.assertIn("artifact_path: dist/GitDesk-macOS-arm64.dmg", workflow)
        self.assertIn("dmg_volume_name: GitDesk Apple Silicon", workflow)
        self.assertIn("name: macOS Intel", workflow)
        self.assertIn("os: macos-15-intel", workflow)
        self.assertIn("--target-arch x86_64", workflow)
        self.assertIn("artifact_name: GitDesk-macOS-x86_64", workflow)
        self.assertIn("artifact_path: dist/GitDesk-macOS-x86_64.dmg", workflow)
        self.assertIn("dmg_volume_name: GitDesk Intel", workflow)
        self.assertIn('"${{ matrix.macos_architecture }}"', workflow)
        self.assertIn('"${{ matrix.artifact_path }}"', workflow)
        self.assertIn("webui_runtime_folder: webui-macos-clang-arm64", workflow)
        self.assertIn("webui_runtime_folder: webui-macos-clang-x64", workflow)
        self.assertIn("python packaging/stage-macos-webui-runtime.py", workflow)
        self.assertIn("${{ matrix.webui_pyinstaller_args }}", workflow)

    # Confirms every desktop build collects the current neutral catalog and has no retired folder dependency.
    def test_workflow_packages_only_shared_resource_catalog(self) -> None:
        """Package Shared Resources from its canonical source directory on every matrix target."""

        workflow = self.workflow_source()

        self.assertIn(
            '--add-data "Shared-Resources/categories${{ matrix.data_separator }}Shared-Resources/categories"',
            workflow,
        )
        self.assertNotIn("AI-Skills/categories", workflow)

    # Confirms the Intel job replaces PyInstaller's colliding libssl while other targets keep native defaults.
    def test_intel_workflow_stages_and_installs_cryptography_openssl_pair(self) -> None:
        """Require the known-good x86_64 OpenSSL pair before analysis and again before app signing."""

        workflow = self.workflow_source()

        self.assertIn("stage_macos_openssl: true", workflow)
        self.assertIn("build/openssl-runtime/x86_64/libssl.3.dylib:.", workflow)
        self.assertIn("build/openssl-runtime/x86_64/libcrypto.3.dylib:.", workflow)
        self.assertIn("python packaging/stage-macos-openssl-runtime.py stage", workflow)
        self.assertIn('install dist/GitDesk.app "${{ matrix.macos_architecture }}"', workflow)
        self.assertIn("${{ matrix.openssl_pyinstaller_args }}", workflow)
        self.assertNotIn("--collect-all cryptography", workflow)

    # Confirms the extension ABI inspected by staging cannot change independently on a future package resolution.
    def test_cryptography_native_runtime_version_is_pinned(self) -> None:
        """Keep cryptography 49 aligned with the OpenSSL symbol and bundle verification contract."""

        manifest = self.dependency_manifest_source()

        self.assertIn('"cryptography==49.0.0"', manifest)
        self.assertNotIn('"cryptography>=45.0.0"', manifest)

    # Confirms packaged verification initializes Python ssl before secrets imports cryptography's native extension.
    def test_packaged_self_check_requires_shared_openssl_3_runtime(self) -> None:
        """Require the frozen report to prove Python ssl and cryptography can share the replacement library pair."""

        self_check = self.packaged_self_check_source()

        self.assertLess(self_check.index("import ssl"), self_check.index("from gitdesk.secrets"))
        self.assertIn('ssl.OPENSSL_VERSION.startswith("OpenSSL 3.")', self_check)
        self.assertIn('"ssl_runtime": {', self_check)
        self.assertIn('"configured": ssl_runtime_configured', self_check)

    # Confirms bundle verification rejects the wrong or universal architecture before DMG creation.
    def test_bundle_verifier_requires_exact_declared_architecture(self) -> None:
        """Keep both supported labels and the exact single-architecture comparison in the verifier."""

        verifier = self.bundle_verifier_source()

        self.assertIn('SUPPORTED_ARCHITECTURES = {"arm64", "x86_64"}', verifier)
        self.assertIn("architectures != {expected_architecture}", verifier)
        self.assertIn("verify_architecture(executable_path, argv[2])", verifier)
        self.assertIn("verify_webui_runtime(app_path, argv[2])", verifier)
        self.assertIn("verify_openssl_runtime(app_path, argv[2])", verifier)
        self.assertNotIn('EXPECTED_ARCHITECTURE = "arm64"', verifier)

    # Confirms final bundle verification checks the actual Intel dylib and not merely the staged source copy.
    def test_bundle_verifier_requires_cryptography_compatible_intel_libssl(self) -> None:
        """Reject a final x86_64 bundle whose selected libssl still lacks cryptography's required symbol."""

        verifier = self.bundle_verifier_source()

        self.assertIn('OPENSSL_RUNTIME_FILENAMES = ("libssl.3.dylib", "libcrypto.3.dylib")', verifier)
        self.assertIn('REQUIRED_INTEL_SSL_SYMBOL = "_SSL_get0_group_name"', verifier)
        self.assertIn('if expected_architecture != "x86_64":', verifier)
        self.assertIn('["nm", "-gU", str(binary_path)]', verifier)
        self.assertIn("verify_architecture(runtime_path, expected_architecture)", verifier)
        self.assertIn('ssl_runtime.get("configured") is not True', verifier)

    # Confirms each macOS job stages only the WebUI dylib matching its declared Mach-O architecture.
    def test_webui_stager_maps_runtime_folders_to_exact_architectures(self) -> None:
        """Keep WebUI's x64 folder label mapped to x86_64 without bundling the ARM64 dylib beside it."""

        stager = self.webui_stager_source()

        self.assertIn('"webui-macos-clang-arm64": "arm64"', stager)
        self.assertIn('"webui-macos-clang-x64": "x86_64"', stager)
        self.assertIn("architectures != {expected_architecture}", stager)
        self.assertIn("shutil.copy2(source_path, destination_path)", stager)

    # Confirms staging derives both libraries from the successful cryptography import rather than a fixed runner path.
    def test_openssl_stager_uses_loaded_pair_and_replaces_finished_bundle(self) -> None:
        """Keep dyld provenance, architecture thinning, local links, and post-PyInstaller replacement together."""

        stager = self.openssl_stager_source()

        self.assertIn('import_module("cryptography.hazmat.bindings._rust")', stager)
        self.assertIn("_dyld_get_image_name", stager)
        self.assertIn('("libssl.3.dylib", "libcrypto.3.dylib")', stager)
        self.assertIn('"-thin", expected_architecture', stager)
        self.assertIn('"@rpath/libcrypto.3.dylib"', stager)
        self.assertIn("destination_path.is_symlink()", stager)
        self.assertIn("shutil.copy2(source_path, destination_path)", stager)
        self.assertIn('REQUIRED_SSL_SYMBOL = "_SSL_get0_group_name"', stager)

    # Confirms a failed packaged process cannot hide its report or captured loader/import diagnostics.
    def test_bundle_verifier_preserves_packaged_self_check_failure_evidence(self) -> None:
        """Require status-one reports and pre-report stderr to produce distinct actionable verifier failures."""

        verifier = self.bundle_verifier_source()

        self.assertIn("def runtime_process_details(", verifier)
        self.assertIn("result.stdout", verifier)
        self.assertIn("result.stderr", verifier)
        self.assertIn("if report_path.is_file():", verifier)
        self.assertIn("verify_runtime_report(payload)", verifier)
        self.assertIn("before writing its report", verifier)
        self.assertIn('payload.get("frozen") is not True', verifier)
        self.assertIn('payload.get("storage_paths_share_parent") is not True', verifier)
        self.assertIn('payload.get("credential_store_configured") is not True', verifier)

    # Confirms platform detection maps each supported Mac CPU family to its separately labeled installer.
    def test_platform_target_distinguishes_apple_silicon_and_intel(self) -> None:
        """Return ARM64 for Apple Silicon and x86_64 for Intel macOS processes."""

        expected_targets = {
            "arm64": ("arm64", "GitDesk-macOS-arm64.dmg"),
            "x86_64": ("x86_64", "GitDesk-macOS-x86_64.dmg"),
        }
        for machine_name, expected in expected_targets.items():
            with (
                self.subTest(machine=machine_name),
                mock.patch.object(updater.sys, "platform", "darwin"),
                mock.patch.object(updater.platform, "machine", return_value=machine_name),
            ):
                target = updater.platform_update_target()

            self.assertEqual((target["architecture"], target["expected_asset"]), expected)

    # Confirms a release containing both DMGs never sends the other CPU architecture to the current Mac.
    def test_release_selection_uses_only_the_detected_macos_architecture(self) -> None:
        """Select the exact ARM64 or x86_64 DMG from a release that contains both builds."""

        release = {
            "assets": [
                {"name": "GitDesk-macOS-arm64.dmg", "state": "uploaded", "url": "arm"},
                {"name": "GitDesk-macOS-x86_64.dmg", "state": "uploaded", "url": "intel"},
            ],
        }
        targets = [
            {
                "platform": "macos",
                "architecture": "arm64",
                "label": "macOS Apple Silicon",
                "expected_asset": "GitDesk-macOS-arm64.dmg",
            },
            {
                "platform": "macos",
                "architecture": "x86_64",
                "label": "macOS Intel",
                "expected_asset": "GitDesk-macOS-x86_64.dmg",
            },
        ]

        for target in targets:
            with self.subTest(architecture=target["architecture"]):
                selected = updater.select_asset(release, target)

            self.assertEqual(selected["name"], target["expected_asset"])

    # Confirms the updater fails honestly when a release omits the current Mac's architecture.
    def test_release_selection_rejects_the_other_macos_architecture(self) -> None:
        """Raise UPDATER_ASSET_MISSING instead of cross-serving an ARM64 DMG to an Intel Mac."""

        release = {
            "assets": [
                {"name": "GitDesk-macOS-arm64.dmg", "state": "uploaded", "url": "arm"},
            ],
        }
        intel_target = {
            "platform": "macos",
            "architecture": "x86_64",
            "label": "macOS Intel",
            "expected_asset": "GitDesk-macOS-x86_64.dmg",
        }

        with self.assertRaises(AppError) as raised:
            updater.select_asset(release, intel_target)

        self.assertEqual(raised.exception.code, "UPDATER_ASSET_MISSING")
        self.assertEqual(raised.exception.details["expected_asset"], "GitDesk-macOS-x86_64.dmg")

    # Confirms app updates can come only from the requested public repository and never add a PAT header.
    def test_updater_uses_anonymous_gd_public_release_source(self) -> None:
        """Keep public release discovery independent from saved GitHub account credentials."""

        session = updater.release_session()

        self.assertEqual(updater.UPDATE_OWNER, "xandlab")
        self.assertEqual(updater.UPDATE_REPO, "gd-public")
        self.assertEqual(updater.UPDATE_RELEASES_URL, "https://github.com/xandlab/gd-public/releases")
        self.assertEqual(
            updater.LATEST_RELEASE_URL,
            "https://api.github.com/repos/xandlab/gd-public/releases/latest",
        )
        self.assertNotIn("Authorization", session.headers)

    # Confirms the check action reports release state without invoking the installer download path.
    def test_check_latest_update_returns_state_without_downloading(self) -> None:
        """Keep Check for updates read-only even when a newer release is available."""

        expected_state = {
            "status": "available",
            "update_available": True,
            "latest_version": "v0.1.4",
        }
        with (
            mock.patch.object(updater, "latest_update_state", return_value=(mock.Mock(), expected_state)),
            mock.patch.object(updater, "download_asset") as download_asset,
        ):
            result = updater.check_latest_update()

        self.assertIs(result, expected_state)
        download_asset.assert_not_called()

    # Confirms an install request cannot drift to a newer or replaced release after the user's explicit check.
    def test_install_requires_the_exact_checked_release_version(self) -> None:
        """Reject missing and stale checked tags before any update asset can be downloaded."""

        state = {"status": "available", "latest_version": "v0.1.5"}
        invalid_versions = ["", "v0.1.4"]
        expected_codes = ["UPDATER_CHECK_REQUIRED", "UPDATER_RELEASE_CHANGED"]

        with (
            mock.patch.object(updater, "latest_update_state", return_value=(mock.Mock(), state)),
            mock.patch.object(updater, "download_asset") as download_asset,
        ):
            for version_value, expected_code in zip(invalid_versions, expected_codes):
                with self.subTest(version=version_value), self.assertRaises(AppError) as raised:
                    updater.install_latest_update(version_value)

                self.assertEqual(raised.exception.code, expected_code)

        download_asset.assert_not_called()
        updater.validate_checked_version(state, "v0.1.5")

    # Confirms the native surface exposes separate public check and install actions without private-token routing.
    def test_updater_bridge_separates_actions_and_omits_token_access(self) -> None:
        """Keep updater bridge registration split and independent from account credential methods."""

        bridge = self.updater_bridge_source()

        self.assertIn('"checkGitDeskUpdate": handle_check_gitdesk_update', bridge)
        self.assertIn('"installGitDeskUpdate": handle_install_gitdesk_update', bridge)
        self.assertNotIn("downloadGitDeskUpdate", bridge)
        self.assertNotIn("optional_update_token", bridge)
        self.assertNotIn("token_for_account", bridge)
        self.assertNotIn("account_from_payload", bridge)

    # Confirms Settings preserves the check-before-install gate in markup, events, and native payloads.
    def test_updater_ui_has_separate_gated_check_and_install_buttons(self) -> None:
        """Require separate controls and the checked version in every installation request."""

        ui_source = self.updater_ui_source()

        self.assertIn('id="check-gitdesk-update"', ui_source)
        self.assertIn('id="install-gitdesk-update" class="primary" type="button" disabled', ui_source)
        self.assertIn('role="status" aria-live="polite"', ui_source)
        self.assertIn('callNative("checkGitDeskUpdate", {})', ui_source)
        self.assertIn('callNative("installGitDeskUpdate", { expected_version: checkedUpdateVersion })', ui_source)
        self.assertNotIn("Check and install", ui_source)


if __name__ == "__main__":
    unittest.main()
