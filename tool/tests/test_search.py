"""Search and replay engine tests with a fake adapter (no GPU)."""

from __future__ import annotations

import unittest

from kvc_lifecycle.adapters.base import Adapter
from kvc_lifecycle.search import replay_actions, run_random_cell


class FakeAdapter(Adapter):
    """A tiny lifecycle: START -> POLL -> DELIVER triggers the target code."""

    def __init__(self, target_code: str = "I_COMPLETION_AFTER_FREE") -> None:
        self.target_code = target_code
        self.actions: list[str] = []
        self.done = False
        self.closed = False

    def enabled(self) -> tuple[str, ...]:
        if not self.actions:
            return ("START",)
        if "DELIVER" in self.actions:
            return ("IDLE",)
        if "POLL" in self.actions:
            return ("DELIVER", "IDLE")
        return ("POLL", "ABORT", "IDLE")

    def apply(self, action: str, step: int) -> None:
        self.actions.append(action)
        if action == "DELIVER":
            self.done = True

    def codes(self) -> list[str]:
        return [self.target_code] if self.done else []

    def result(self) -> dict[str, object]:
        return {"actions": self.actions, "codes": self.codes()}

    def close(self) -> None:
        self.closed = True


class SearchTest(unittest.TestCase):
    def test_random_cell_finds_target(self) -> None:
        created: list[FakeAdapter] = []

        def factory(_: str) -> FakeAdapter:
            adapter = FakeAdapter()
            created.append(adapter)
            return adapter

        result = run_random_cell(
            factory,
            target_code="I_COMPLETION_AFTER_FREE",
            seed=0,
            budget=200,
            max_steps=10,
        )
        self.assertTrue(result.found)
        self.assertIsNotNone(result.schedule)
        self.assertIn("DELIVER", result.actions)
        self.assertTrue(all(adapter.closed for adapter in created))

    def test_random_cell_does_not_loop_forever(self) -> None:
        def factory(_: str) -> FakeAdapter:
            return FakeAdapter(target_code="NEVER")

        result = run_random_cell(
            factory,
            target_code="NEVER_FOUND",
            seed=1,
            budget=3,
            max_steps=2,
        )
        self.assertFalse(result.found)
        self.assertEqual(result.schedules_executed, 3)

    def test_replay_rejects_illegal_action(self) -> None:
        adapter = FakeAdapter()
        with self.assertRaises(ValueError):
            replay_actions(adapter, ["DELIVER"])

    def test_replay_returns_result(self) -> None:
        adapter = FakeAdapter()
        result = replay_actions(adapter, ["START", "POLL", "DELIVER"])
        self.assertEqual(result["codes"], ["I_COMPLETION_AFTER_FREE"])


if __name__ == "__main__":
    unittest.main()
