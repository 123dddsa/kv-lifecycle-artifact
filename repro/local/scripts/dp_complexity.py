"""Report exact-DP state/transition complexity for the three frozen targets.

Produces the numbers used in the paper's theory section (Thm 5, complexity):
state counts per depth, total transitions, and the implied O(H*|S|*|En|) bound.
Runs on CPU with the tool's cost model; no GPU.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOL_SRC = Path(__file__).resolve().parents[3] / "tool" / "src"
sys.path.insert(0, str(TOOL_SRC))

from kvc_lifecycle.cost import exact_dp  # noqa: E402

TARGETS = ("stale_send", "dual_completion", "permanent_proc")
HORIZONS = (6, 10, 15, 20, 25, 30)


def main() -> int:
    rows = []
    for target in TARGETS:
        for h in HORIZONS:
            r = exact_dp(target, horizon=h)
            states = r["dp_state_counts_by_depth"]
            rows.append(
                {
                    "target": target,
                    "horizon": h,
                    "q": r["hit_probability_q"],
                    "reachable": r["reachable_within_horizon"],
                    "median": r["predicted_median_schedules"],
                    "max_states_per_depth": max(states),
                    "sum_states_by_depth": sum(states),
                    "transitions": r["dp_transitions"],
                }
            )
    # transition/state ratio and a conservative complexity witness
    for row in rows:
        row["transitions_per_state_sum"] = (
            round(row["transitions"] / row["sum_states_by_depth"], 3)
            if row["sum_states_by_depth"]
            else None
        )
    out = Path(__file__).resolve().parent / "dp_complexity.json"
    out.write_text(json.dumps({"rows": rows}, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        if row["horizon"] in (10, 30):
            print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

