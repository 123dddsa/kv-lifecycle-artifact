"""Audit tests: the same input must be re-evaluated under explicit assumptions."""

from __future__ import annotations

import unittest
from pathlib import Path

from kvc_lifecycle.audit import audit_events, audit_file
from kvc_lifecycle.core.trace import load_trace

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class AuditTest(unittest.TestCase):
    def test_identity_scope_is_sensitive_on_scoped_trace(self) -> None:
        payload = audit_file(EXAMPLES / "scoped_children.jsonl")
        self.assertTrue(payload["conflict"])
        self.assertTrue(payload["sensitive"]["identity_scope"])
        self.assertEqual(payload["verdict"], "assumption-sensitive")
        request_scope = [
            variant
            for variant in payload["variants"]
            if variant["assumptions"]["identity_scope"] == "request"
            and variant["assumptions"]["delay_free_drained"] is True
            and variant["assumptions"]["fairness_bound"] == 0
        ][0]
        self.assertEqual(request_scope["codes"], ["I_SEND_DUPLICATE"])

    def test_drain_gate_is_sensitive(self) -> None:
        payload = audit_file(EXAMPLES / "delay_free.jsonl")
        self.assertTrue(payload["conflict"])
        self.assertTrue(payload["sensitive"]["delay_free_drained"])
        codes_by_gate = {
            variant["assumptions"]["delay_free_drained"]: variant["codes"]
            for variant in payload["variants"]
            if variant["assumptions"]["identity_scope"] == "request"
            and variant["assumptions"]["fairness_bound"] == 0
        }
        self.assertEqual(codes_by_gate[True], ["I_DELAY_FREE_NEVER_COMPLETED"])
        self.assertEqual(codes_by_gate[False], [])

    def test_fairness_bound_is_sensitive_when_quiescence_is_premature(self) -> None:
        payload = audit_file(EXAMPLES / "delay_free.jsonl")
        self.assertTrue(payload["sensitive"]["fairness_bound"])
        codes_by_bound = {
            variant["assumptions"]["fairness_bound"]: variant["codes"]
            for variant in payload["variants"]
            if variant["assumptions"]["identity_scope"] == "request"
            and variant["assumptions"]["delay_free_drained"] is True
        }
        self.assertEqual(codes_by_bound[0], ["I_DELAY_FREE_NEVER_COMPLETED"])
        self.assertEqual(codes_by_bound[3], [])

    def test_stable_trace_has_no_conflict(self) -> None:
        payload = audit_events(load_trace(EXAMPLES / "normal_recv.jsonl"))
        self.assertFalse(payload["conflict"])
        self.assertEqual(payload["verdict"], "assumption-stable")
        self.assertFalse(any(payload["sensitive"].values()))

    def test_empty_space_rejected(self) -> None:
        with self.assertRaises(ValueError):
            audit_events([], identity_scopes=[], drain_gates=[True])

    def test_unknown_scope_rejected(self) -> None:
        with self.assertRaises(ValueError):
            audit_events([], identity_scopes=["nope"], drain_gates=[True])

    def test_negative_fairness_bound_rejected(self) -> None:
        with self.assertRaises(ValueError):
            audit_events([], fairness_bounds=[-1])

    def test_digest_is_stable(self) -> None:
        events = load_trace(EXAMPLES / "normal_recv.jsonl")
        first = audit_events(events)
        second = audit_events(events)
        self.assertEqual(first["input_digest"], second["input_digest"])


if __name__ == "__main__":
    unittest.main()

