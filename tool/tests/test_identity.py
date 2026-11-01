"""Scoped identity tests: the k-1 counting law."""

from __future__ import annotations

import unittest

from kvc_lifecycle.core.monitor import ContractMonitor, IdentityScope, Operation


class ScopedIdentityTest(unittest.TestCase):
    def test_bare_request_identity_counts_children_as_duplicates(self) -> None:
        monitor = ContractMonitor(IdentityScope.REQUEST)
        monitor.request_finished("r", False, child="c1")
        monitor.request_finished("r", False, child="c2")
        monitor.observe([Operation("r", child="c1")], [])
        monitor.observe([Operation("r", child="c2")], [])
        self.assertEqual(monitor.codes(), ["I_SEND_DUPLICATE"])
        self.assertEqual(monitor.report()["violation_count"], 1)

    def test_scoped_child_identity_has_no_duplicate(self) -> None:
        monitor = ContractMonitor(IdentityScope.CHILD_REQUEST_ATTEMPT)
        monitor.request_finished("r", False, child="c1")
        monitor.request_finished("r", False, child="c2")
        monitor.observe([Operation("r", child="c1")], [])
        monitor.observe([Operation("r", child="c2")], [])
        self.assertEqual(monitor.codes(), [])

    def test_attempt_identity(self) -> None:
        bare = ContractMonitor(IdentityScope.REQUEST)
        bare.request_finished("r", False)
        bare.observe([Operation("r", attempt=0)], [])
        bare.observe([Operation("r", attempt=1)], [])
        self.assertEqual(bare.codes(), ["I_SEND_DUPLICATE"])

        scoped = ContractMonitor(IdentityScope.REQUEST_ATTEMPT)
        scoped.request_finished("r", False, attempt=0)
        scoped.request_finished("r", False, attempt=1)
        scoped.observe([Operation("r", attempt=0)], [])
        scoped.observe([Operation("r", attempt=1)], [])
        self.assertEqual(scoped.codes(), [])

    def test_composition_k4_counts_three_duplicates_bare(self) -> None:
        monitor = ContractMonitor(IdentityScope.REQUEST)
        monitor.request_finished("r", False)
        for child in ("c1", "c2", "c3", "c4"):
            monitor.observe([Operation("r", child=child)], [])
        self.assertEqual(monitor.codes(), ["I_SEND_DUPLICATE"])
        self.assertEqual(monitor.report()["violation_count"], 3)

    def test_composition_k4_scoped_zero(self) -> None:
        monitor = ContractMonitor(IdentityScope.CHILD_REQUEST_ATTEMPT)
        for child in ("c1", "c2", "c3", "c4"):
            monitor.request_finished("r", False, child=child)
            monitor.observe([Operation("r", child=child)], [])
        self.assertEqual(monitor.codes(), [])

    def test_completion_after_free_is_per_scope(self) -> None:
        monitor = ContractMonitor(IdentityScope.CHILD_REQUEST_ATTEMPT)
        monitor.request_finished("r", False, child="c1")
        monitor.request_finished("r", False, child="c2")
        monitor.free("r", child="c1")
        monitor.observe([Operation("r", child="c1")], [])
        monitor.observe([Operation("r", child="c2")], [])
        self.assertEqual(monitor.codes(), ["I_COMPLETION_AFTER_FREE"])
        self.assertEqual(monitor.report()["violation_count"], 1)

    def test_direction_separates_send_and_recv(self) -> None:
        monitor = ContractMonitor(IdentityScope.CHILD_REQUEST_ATTEMPT)
        monitor.request_finished("r", False, child="c1")
        monitor.observe([Operation("r", child="c1")], [])
        monitor.observe([], [Operation("r", child="c1")])
        self.assertEqual(monitor.codes(), [])

    def test_report_exposes_scope(self) -> None:
        monitor = ContractMonitor(IdentityScope.CHILD_REQUEST_ATTEMPT)
        self.assertEqual(monitor.report()["identity_scope"], "child_request_attempt")


if __name__ == "__main__":
    unittest.main()

