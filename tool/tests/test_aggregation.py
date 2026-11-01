"""Aggregation audit tests: child uniqueness + all-children quorum."""

from __future__ import annotations

import unittest
from pathlib import Path

from kvc_lifecycle.aggregation import (
    PREMATURE_AGGREGATE,
    audit_aggregation,
    load_schedules,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class AggregationTest(unittest.TestCase):
    def test_non_duplicate_two_children(self) -> None:
        result = audit_aggregation({"a": [True, False], "b": [False, True]})
        self.assertFalse(result.premature)
        self.assertEqual(result.legacy_codes, [])
        self.assertEqual(result.strict_codes, [])
        self.assertFalse(result.conflict)

    def test_duplicate_child_is_missed_by_aggregate_only(self) -> None:
        # a duplicates, but the aggregate stream forwards one request-level
        # completion; legacy misses the child duplicate, strict catches it.
        result = audit_aggregation({"a": [True, True, False], "b": [False, True, False]})
        self.assertFalse(result.premature)
        self.assertEqual(result.legacy_codes, [])
        self.assertIn("I_SEND_DUPLICATE", result.strict_codes)
        self.assertTrue(result.conflict)

    def test_premature_aggregate_is_flagged(self) -> None:
        result = audit_aggregation({"a": [True, True, False], "b": [False, False, True]})
        self.assertTrue(result.premature)
        self.assertIn(PREMATURE_AGGREGATE, result.legacy_codes)
        self.assertIn(PREMATURE_AGGREGATE, result.strict_codes)

    def test_load_example(self) -> None:
        schedules = load_schedules(EXAMPLES / "aggregation_duplicate.json")
        self.assertEqual(set(schedules), {"a", "b"})
        result = audit_aggregation(schedules)
        self.assertTrue(result.conflict)

    def test_mismatched_lengths_rejected(self) -> None:
        with self.assertRaises(ValueError):
            audit_aggregation({"a": [True], "b": [True, False]})

    def test_empty_schedules_rejected(self) -> None:
        with self.assertRaises(ValueError):
            audit_aggregation({})


if __name__ == "__main__":
    unittest.main()
