"""Golden trace checks: the examples are the public contract examples."""

from __future__ import annotations

import unittest
from pathlib import Path

from kvc_lifecycle.core.monitor import ContractMonitor
from kvc_lifecycle.core.trace import load_trace

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

CASES = {
    "normal_recv.jsonl": set(),
    "stale_send.jsonl": {"I_COMPLETION_AFTER_FREE"},
    "duplicate_send.jsonl": {"I_SEND_DUPLICATE"},
    "permanent_recv.jsonl": {"I_RECV_NEVER_COMPLETED"},
}


class GoldenTraceTest(unittest.TestCase):
    def test_examples(self) -> None:
        for name, expected in CASES.items():
            with self.subTest(name=name):
                monitor = ContractMonitor().run(load_trace(EXAMPLES / name))
                self.assertEqual(set(monitor.codes()), expected)


if __name__ == "__main__":
    unittest.main()
