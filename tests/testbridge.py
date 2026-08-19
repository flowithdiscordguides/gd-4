"""Regression coverage for GitDesk's WebUI callback dispatch boundary."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from gitdesk.bridge import BridgeController
from gitdesk.errors import AppError


# FakeWebUiEvent records the response returned through WebUI's ctypes callback object.
class FakeWebUiEvent:
    """Provide the request and response methods used by the native bridge callback."""

    # Stores one raw request and an initially empty response value.
    def __init__(self, request: str) -> None:
        """Create a fake WebUI event for one serialized JavaScript request."""

        self.request = request
        self.response = ""

    # Returns the JavaScript request exactly as WebUI supplied it.
    def get_string(self) -> str:
        """Return the stored request string."""

        return self.request

    # Records the serialized response that would be returned to JavaScript.
    def return_string(self, response: str) -> None:
        """Store the bridge response string without invoking native code."""

        self.response = response


# BridgeDispatchTests protects the executor-free callback path used during normal operation and shutdown.
class BridgeDispatchTests(unittest.TestCase):
    """Verify WebUI's event thread invokes request processing directly."""

    # Confirms dispatch cannot queue a cancellable future between WebUI and the request handler.
    def test_native_callback_processes_request_without_secondary_executor(self) -> None:
        """Return one response directly from process_request on the active callback thread."""

        controller = object.__new__(BridgeController)
        controller.process_request = mock.Mock(return_value={"requestId": "request-1", "ok": True, "data": {}})
        event = FakeWebUiEvent('{"requestId":"request-1"}')

        controller.handle_native_invoke(event)

        controller.process_request.assert_called_once_with('{"requestId":"request-1"}')
        self.assertEqual(json.loads(event.response), {"requestId": "request-1", "ok": True, "data": {}})

    # Path authorization must use saved account ownership without opening missing Git metadata first.
    def test_repository_path_validation_does_not_require_live_git_metadata(self) -> None:
        """Return an exact account-owned saved path before any repository operation is attempted."""

        controller = object.__new__(BridgeController)
        controller.settings_store = mock.Mock()
        controller.settings_store.load.return_value = {
            "active_account": "example",
            "repository_path": "/repos/public-app",
            "managed_repositories": {
                "example": [{"path": "/repos/public-app"}],
            },
        }

        result = controller.repository_path_from_payload({
            "path": "/repos/public-app",
            "account_login": "example",
        })

        self.assertEqual(result, "/repos/public-app")

    # Refresh repairs only the missing Git metadata and then performs the requested status read.
    def test_refresh_repairs_app_cloned_repository_before_retry(self) -> None:
        """Retry status after exact metadata restoration for the selected managed clone."""

        controller = object.__new__(BridgeController)
        controller.git_service = mock.Mock()
        controller.git_service.status.side_effect = [
            AppError("invalid", "REPOSITORY_INVALID"),
            {"summary": {"changed": 0}},
        ]
        controller.repository_path_from_payload = mock.Mock(return_value="/repos/public-app")
        record = {"path": "/repos/public-app", "owner": "example", "repo": "public-app", "source": "cloned"}
        controller.managed_repository_record = mock.Mock(return_value=record)
        controller.account_for_owner = mock.Mock(return_value={"login": "example"})
        payload = {"account_login": "example"}

        with mock.patch("gitdesk.bridge.repair_cloned_repository_metadata") as repair:
            result = controller.handle_refresh_status(payload)

        controller.account_for_owner.assert_called_once_with("example", payload, required=False)
        repair.assert_called_once_with("/repos/public-app", record, "example")
        self.assertEqual(result, {"summary": {"changed": 0}})


if __name__ == "__main__":
    unittest.main()
