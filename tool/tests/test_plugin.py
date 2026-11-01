"""Tests for the optional pytest plugin helpers (no pytest special machinery)."""

from __future__ import annotations

import unittest
from pathlib import Path

from kvc_lifecycle.pytest_plugin import check_trace, dumps

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class PluginTest(unittest.TestCase):
    def test_check_normal(self) -> None:
        payload = check_trace(EXAMPLES / "normal_recv.jsonl")
        self.assertTrue(payload["pass"])
        self.assertEqual(payload["codes"], [])

    def test_check_stale(self) -> None:
        payload = check_trace(EXAMPLES / "stale_send.jsonl")
        self.assertFalse(payload["pass"])
        self.assertEqual(payload["codes"], ["I_COMPLETION_AFTER_FREE"])

    def test_check_scoped(self) -> None:
        payload = check_trace(
            EXAMPLES / "scoped_children.jsonl",
            identity_scope="child_request_attempt",
        )
        self.assertTrue(payload["pass"])

    def test_unknown_scope_rejected(self) -> None:
        with self.assertRaises(ValueError):
            check_trace(EXAMPLES / "normal_recv.jsonl", identity_scope="nope")

    def test_dumps_is_json(self) -> None:
        self.assertIn('"pass": true', dumps({"pass": True}))


if __name__ == "__main__":
    unittest.main()
