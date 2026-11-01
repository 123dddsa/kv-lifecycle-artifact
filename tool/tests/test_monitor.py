"""Unit tests for the M1 request-scoped contract monitor."""

from __future__ import annotations

import unittest

from kvc_lifecycle.core.monitor import ContractMonitor


class ContractMonitorTest(unittest.TestCase):
    def codes(self, monitor: ContractMonitor) -> set[str]:
        return set(monitor.codes())

    def test_normal_recv(self) -> None:
        monitor = ContractMonitor()
        monitor.observe(set(), {"r"})
        monitor.check_quiescence()
        self.assertEqual(self.codes(monitor), set())

    def test_normal_delayed_send(self) -> None:
        monitor = ContractMonitor()
        monitor.request_finished("r", True)
        monitor.observe({"r"}, set())
        monitor.free("r")
        monitor.check_quiescence()
        self.assertEqual(self.codes(monitor), set())

    def test_cross_step_stale_send(self) -> None:
        monitor = ContractMonitor()
        monitor.request_finished("r", False)
        monitor.observe(set(), {"r"})
        monitor.free("r")
        monitor.observe({"r"}, set())
        self.assertEqual(self.codes(monitor), {"I_COMPLETION_AFTER_FREE"})

    def test_aborted_dual_completion(self) -> None:
        monitor = ContractMonitor()
        monitor.request_finished("r", False)
        monitor.observe({"r"}, {"r"})
        self.assertEqual(self.codes(monitor), {"I_ABORTED_DUAL_COMPLETION"})

    def test_permanent_receive(self) -> None:
        monitor = ContractMonitor()
        monitor.request_finished("r", False)
        monitor.observe(set(), set())
        monitor.check_quiescence({"r"})
        self.assertEqual(self.codes(monitor), {"I_RECV_NEVER_COMPLETED"})

    def test_undrained_quiescence_defers_only_delay_free(self) -> None:
        monitor = ContractMonitor()
        monitor.request_finished("r", True)
        monitor.check_quiescence(delay_free_drained=False)
        self.assertEqual(self.codes(monitor), set())
        monitor.check_quiescence(delay_free_drained=True)
        self.assertEqual(self.codes(monitor), {"I_DELAY_FREE_NEVER_COMPLETED"})

    def test_undrained_quiescence_preserves_receive_liveness(self) -> None:
        monitor = ContractMonitor()
        monitor.request_finished("r", True)
        monitor.check_quiescence({"other"}, delay_free_drained=False)
        self.assertEqual(self.codes(monitor), {"I_RECV_NEVER_COMPLETED"})

    def test_unadvertised_send(self) -> None:
        monitor = ContractMonitor()
        monitor.observe({"r"}, set())
        self.assertIn("I_SEND_NOT_FINISHED", self.codes(monitor))

    def test_duplicate_completion(self) -> None:
        monitor = ContractMonitor()
        monitor.request_finished("r", True)
        monitor.observe({"r"}, set())
        monitor.observe({"r"}, set())
        self.assertIn("I_SEND_DUPLICATE", self.codes(monitor))

    def test_free_duplicate(self) -> None:
        monitor = ContractMonitor()
        monitor.free("r")
        monitor.free("r")
        self.assertEqual(self.codes(monitor), {"I_FREE_DUPLICATE"})

    def test_report_shape_and_pass(self) -> None:
        monitor = ContractMonitor()
        monitor.request_finished("r", False)
        monitor.observe({"r"}, set())
        report = monitor.report()
        self.assertTrue(report["pass"])
        self.assertEqual(report["violation_count"], 0)
        self.assertEqual(report["codes"], [])
        self.assertTrue(report["quiescence_checked"] is False)


if __name__ == "__main__":
    unittest.main()
