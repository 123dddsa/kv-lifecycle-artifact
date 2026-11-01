"""Exact rarity DP tests (values frozen from the 200-cell calibration)."""

from __future__ import annotations

import unittest

from kvc_lifecycle.cost import exact_dp, geometric_quantile, predict

EXPECTED_Q = {
    "stale_send": 0.027919811037165638,
    "dual_completion": 0.37553697927562013,
    "permanent_proc": 0.22593117312603,
}
EXPECTED_MEDIAN = {"stale_send": 25, "dual_completion": 2, "permanent_proc": 3}


class CostTest(unittest.TestCase):
    def test_exact_q_matches_frozen_calibration(self) -> None:
        for target, expected in EXPECTED_Q.items():
            with self.subTest(target=target):
                dp = exact_dp(target, wait=0, horizon=10)
                self.assertAlmostEqual(dp["hit_probability_q"], expected, places=12)
                self.assertEqual(
                    dp["predicted_median_schedules"], EXPECTED_MEDIAN[target]
                )
                self.assertGreater(dp["hit_probability_q"], 0)
                self.assertLess(dp["hit_probability_q"], 1)

    def test_geometric_quantile_edges(self) -> None:
        self.assertIsNone(geometric_quantile(0.0, 0.5))
        self.assertEqual(geometric_quantile(1.0, 0.5), 1)
        self.assertEqual(geometric_quantile(0.5, 0.5), 1)
        self.assertEqual(geometric_quantile(0.25, 0.5), 3)

    def test_unreachable_horizon_is_reported_not_hidden(self) -> None:
        # stale send with an 8-action delivery wait needs a horizon of 25.
        short = predict("stale_send", wait=8, horizon=10)
        self.assertFalse(short["reachable"])
        self.assertEqual(short["q"], 0.0)
        self.assertIsNone(short["median_schedules"])
        long = predict("stale_send", wait=8, horizon=30)
        self.assertTrue(long["reachable"])
        self.assertGreater(long["q"], 0)

    def test_merged_delivery_counterfactual(self) -> None:
        # E2: merging POLL/DELIVER removes stale send, keeps dual reachable,
        # and leaves permanent PROC unchanged.
        self.assertEqual(predict("stale_send", delivery="merged")["q"], 0.0)
        self.assertAlmostEqual(
            predict("dual_completion", delivery="merged")["q"], 0.4629346826893766, places=12
        )
        self.assertAlmostEqual(
            predict("permanent_proc", delivery="merged")["q"],
            predict("permanent_proc")["q"],
            places=12,
        )

    def test_unknown_delivery_rejected(self) -> None:
        with self.assertRaises(ValueError):
            predict("stale_send", delivery="nope")

    def test_unknown_target_rejected(self) -> None:
        with self.assertRaises(ValueError):
            predict("nope")

    def test_predict_shape(self) -> None:
        payload = predict("dual_completion")
        for key in ("q", "median_schedules", "q1_schedules", "q3_schedules", "reachable"):
            self.assertIn(key, payload)


if __name__ == "__main__":
    unittest.main()
