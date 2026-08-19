"""Storage, bridge, and source contracts for Repo Mode Actions completion jingles."""

from __future__ import annotations

import base64
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gitdesk.action_jingle_bridge import handle_replace_action_jingle
from gitdesk.action_jingle_store import ActionJingleStore, audio_signature_matches
from gitdesk.action_jingle_store import validated_audio_file
from gitdesk.errors import AppError


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "src" / "gitdesk" / "ui"


def wav_bytes() -> bytes:
    """Return a minimal signature-valid WAV payload for bounded storage tests."""

    return b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * 24


class ActionJingleStoreTests(unittest.TestCase):
    """Protect path validation, private persistence, and basename-only responses."""

    def test_store_persists_each_path_in_dedicated_json(self) -> None:
        """Require independent success and failure paths without adding them to general settings."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            success_path = root / "success.wav"
            failure_path = root / "failure.wav"
            success_path.write_bytes(wav_bytes())
            failure_path.write_bytes(wav_bytes())
            store = ActionJingleStore(root / "action-jingles.json")
            store.replace("success", success_path)
            saved = store.replace("failure", failure_path)
            self.assertEqual(saved["success_path"], str(success_path.resolve()))
            self.assertEqual(saved["failure_path"], str(failure_path.resolve()))
            self.assertEqual(store.config_path.name, "action-jingles.json")

    def test_public_state_hides_paths_and_audio_payload_uses_data_url(self) -> None:
        """Keep private paths in Python while still returning bounded playable bytes."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            audio_path = root / "private success.wav"
            content = wav_bytes()
            audio_path.write_bytes(content)
            store = ActionJingleStore(root / "action-jingles.json")
            saved = store.replace("success", audio_path)
            public = store.public_settings(saved)
            payload = store.audio_payload("success")
            self.assertEqual(public["success"]["file_name"], audio_path.name)
            self.assertNotIn(str(root), str(public))
            self.assertNotIn("path", public["success"])
            self.assertTrue(payload["data_url"].startswith("data:audio/wav;base64,"))
            self.assertEqual(base64.b64decode(payload["data_url"].split(",", 1)[1]), content)

    def test_missing_saved_file_falls_back_without_discarding_its_name(self) -> None:
        """Report unavailable custom audio so the frontend can play its built-in fallback."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = ActionJingleStore(root / "action-jingles.json")
            store.write({"success_path": str(root / "missing.mp3")})
            public = store.public_settings()
            self.assertTrue(public["success"]["custom"])
            self.assertFalse(public["success"]["available"])
            self.assertEqual(public["success"]["file_name"], "missing.mp3")

    def test_invalid_extension_content_and_symlink_are_rejected(self) -> None:
        """Reject renamed files and indirect paths before either can reach Web Audio."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            invalid_type = root / "jingle.txt"
            invalid_content = root / "jingle.mp3"
            valid_audio = root / "jingle.wav"
            symlink = root / "linked.wav"
            invalid_type.write_bytes(wav_bytes())
            invalid_content.write_bytes(b"not an mp3")
            valid_audio.write_bytes(wav_bytes())
            with self.assertRaises(AppError):
                validated_audio_file(invalid_type)
            with self.assertRaises(AppError):
                validated_audio_file(invalid_content)
            try:
                symlink.symlink_to(valid_audio)
            except (OSError, NotImplementedError):
                return
            with self.assertRaises(AppError):
                validated_audio_file(symlink)

    def test_supported_signatures_are_explicit(self) -> None:
        """Keep picker extensions and backend content checks aligned."""

        self.assertTrue(audio_signature_matches(".aac", b"\xff\xf1" + b"0" * 14))
        self.assertTrue(audio_signature_matches(".flac", b"fLaC" + b"0" * 12))
        self.assertTrue(audio_signature_matches(".m4a", b"0000ftypM4A 0000"))
        self.assertTrue(audio_signature_matches(".mp3", b"ID3" + b"0" * 13))
        self.assertTrue(audio_signature_matches(".ogg", b"OggS" + b"0" * 8 + b"OpusHead"))
        self.assertTrue(audio_signature_matches(".wav", wav_bytes()[:16]))

    def test_picker_cancellation_is_non_mutating_and_selection_is_saved(self) -> None:
        """Reuse native picker cancellation while returning refreshed basename-only state."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            audio_path = root / "success.wav"
            audio_path.write_bytes(wav_bytes())
            store = ActionJingleStore(root / "action-jingles.json")
            with mock.patch("gitdesk.action_jingle_bridge.ActionJingleStore", return_value=store):
                with mock.patch("gitdesk.action_jingle_bridge.choose_file", return_value=""):
                    cancelled = handle_replace_action_jingle({"kind": "success"})
                with mock.patch("gitdesk.action_jingle_bridge.choose_file", return_value=str(audio_path)):
                    saved = handle_replace_action_jingle({"kind": "success"})
            self.assertTrue(cancelled["cancelled"])
            self.assertFalse(saved["cancelled"])
            self.assertEqual(saved["action_jingles"]["success"]["file_name"], "success.wav")


class ActionJingleSourceTests(unittest.TestCase):
    """Protect terminal transition ownership, Settings controls, and frontend registration."""

    def test_actions_seed_history_then_sound_new_terminal_runs(self) -> None:
        """Require startup silence, success/failure mapping, reset, and serialized playback."""

        source = (UI_ROOT / "action-jingles.js").read_text(encoding="utf-8")
        actions_source = (UI_ROOT / "actions.js").read_text(encoding="utf-8")
        self.assertIn('run.status !== "completed" || !run.conclusion', source)
        self.assertIn('run.conclusion === "success" ? "success" : "failure"', source)
        self.assertIn("runTrackingReady && kind", source)
        self.assertIn("playbackQueue = playbackQueue", source)
        self.assertIn("choice && choice.custom && runActionRef", source)
        self.assertNotIn("choice.custom && choice.available", source)
        self.assertIn("function resetRuns()", source)
        self.assertIn("GitDeskActionJingles.syncRuns(state.runs)", actions_source)
        self.assertIn("GitDeskActionJingles.resetRuns()", actions_source)

    def test_settings_and_both_frontend_paths_register_jingles(self) -> None:
        """Require both replacement controls, bootstrap state, and matching script dependency order."""

        settings_source = (UI_ROOT / "settings-tabs.js").read_text(encoding="utf-8")
        app_source = (UI_ROOT / "app.js").read_text(encoding="utf-8")
        bridge_source = (ROOT / "src" / "gitdesk" / "bridge.py").read_text(encoding="utf-8")
        index_source = (UI_ROOT / "index.html").read_text(encoding="utf-8")
        frontend_source = (ROOT / "src" / "gitdesk" / "frontend.py").read_text(encoding="utf-8")
        self.assertEqual(settings_source.count(">Replace jingle</button>"), 2)
        self.assertIn("actionJingles.bind(runAction);", app_source)
        self.assertIn("actionJingles.applySettings(data.action_jingles);", app_source)
        self.assertIn('"action_jingles": action_jingle_settings()', bridge_source)
        self.assertLess(index_source.index("action-jingles.js"), index_source.index('src="./actions.js"'))
        self.assertLess(frontend_source.index('"action-jingles.js"'), frontend_source.index('"actions.js"'))


if __name__ == "__main__":
    unittest.main()
