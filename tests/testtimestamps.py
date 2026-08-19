"""Regression coverage for timezone-aware UTC timestamps used by persisted GitDesk metadata."""

from __future__ import annotations

import unittest
import warnings

from gitdesk.localpermissions import permission_timestamp
from gitdesk.projecthub import timeline_timestamp


# TimestampTests prevents Python 3.12 deprecation warnings from returning to CI.
class TimestampTests(unittest.TestCase):
    """Verify persisted timestamps remain UTC, second-precision, and warning-free."""

    # Treats DeprecationWarning as an error so datetime.utcnow cannot silently return.
    def test_timestamp_helpers_use_timezone_aware_utc(self) -> None:
        """Return the existing Z-suffixed storage format without deprecated datetime calls."""

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            timestamps = [permission_timestamp(), timeline_timestamp()]

        for timestamp in timestamps:
            self.assertTrue(timestamp.endswith("Z"))
            self.assertNotIn("+00:00", timestamp)
            self.assertNotIn(".", timestamp)


if __name__ == "__main__":
    unittest.main()
