"""Analyze the 1,000-cell-per-family external calibration run.

Input: real_search_by_seed.csv. Output: scale_1000_analysis.json with median,
bootstrap CI, candidate-level q with Wilson CI, KS test against geometric(q10),
and a comparison with the 200-cell campaign.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CSV = HERE / "real_search_by_seed.csv"
OUT = HERE / "scale_1000_analysis.json"

Q10 = {"stale_send": 0.027920, "dual_completion": 0.375537, "permanent_proc": 0.225931}
CENSOR = 201
B = 20000
RNG = np.random.default_rng(20261117)


def geom_median(q: float) -> int:
    return math.ceil(math.log(0.5) / math.log(1 - q))


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def median_ci(values: list[float], draws: int = B) -> dict:
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    meds = np.empty(draws)
    for i in range(draws):
        meds[i] = np.median(arr[RNG.integers(0, n, n)])
    return {
        "median": float(np.median(arr)),
        "ci95_low": float(np.percentile(meds, 2.5)),
        "ci95_high": float(np.percentile(meds, 97.5)),
        "q1": float(np.percentile(arr, 25)),
        "q3": float(np.percentile(arr, 75)),
        "n": n,
    }


def _ks_d(values: np.ndarray, q: float) -> float:
    arr = np.sort(values.astype(float))
    n = len(arr)
    cdf_emp = np.arange(1, n + 1) / n
    cdf_geo = 1 - (1 - q) ** arr
    cdf_geo_left = 1 - (1 - q) ** np.maximum(arr - 1, 0)
    return float(
        max(
            np.max(np.abs(cdf_emp - cdf_geo)),
            np.max(np.abs(cdf_emp - cdf_geo_left)),
        )
    )


def ks_vs_geometric(uncensored: list[int], q: float) -> dict:
    if not uncensored:
        return {"D": None, "p": None}
    arr = np.asarray(uncensored, dtype=float)
    d = _ks_d(arr, q)
    n = len(arr)
    sims = RNG.geometric(q, size=(2000, n)).astype(float)
    d_sims = np.array([_ks_d(sims[i], q) for i in range(2000)])
    p = float((np.sum(d_sims >= d) + 1) / (2000 + 1))
    return {"D": d, "p": p, "n": n}


def main() -> int:
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    results: dict = {"source": str(CSV.name), "rows": len(rows), "by_method_target": {}}
    for method in ("directed", "random"):
        for target in ("stale_send", "dual_completion", "permanent_proc"):
            cell = [r for r in rows if r["method"] == method and r["target"] == target]
            costs = [float(r["discovery_cost_censored"]) for r in cell]
            found = [r for r in cell if r["found"] == "True"]
            uncensored = [
                int(r["first_discovery_schedule"])
                for r in found
                if int(r["discovery_cost_censored"]) <= 200
            ]
            schedules = sum(int(r["schedules_executed"]) for r in cell)
            q = Q10[target]
            entry = {
                "n_cells": len(cell),
                "found": len(found),
                "right_censored": len(cell) - len(found),
                "discovery_rate": len(found) / len(cell),
                "discovery_rate_wilson95": wilson(len(found), len(cell)),
                "median_schedules": (
                    median_ci(costs) if method == "random" else {"median": float(np.median(costs))}
                ),
                "candidate_level": {
                    "schedules_executed": schedules,
                    "hit_cells": len(found),
                    "empirical_q": len(found) / schedules if schedules else None,
                    "empirical_q_wilson95": wilson(len(found), schedules),
                },
                "predicted_median": geom_median(q) if method == "random" else 1,
                "exact_q10": q,
                "ks_vs_geometric": ks_vs_geometric(uncensored, q) if method == "random" else None,
            }
            results["by_method_target"][f"{method}:{target}"] = entry
    results["vs_200_cell"] = {
        "stale_send": {"200_cell_median": 26.5, "200_cell_ci95": [22.0, 32.0], "predicted": 25},
        "dual_completion": {"200_cell_median": 2.0, "200_cell_ci95": [2.0, 3.0], "predicted": 2},
        "permanent_proc": {"200_cell_median": 3.0, "200_cell_ci95": [2.0, 3.0], "predicted": 3},
    }
    for target, key in (
        ("stale_send", "random:stale_send"),
        ("dual_completion", "random:dual_completion"),
        ("permanent_proc", "random:permanent_proc"),
    ):
        m = results["by_method_target"][key]["median_schedules"]
        results["vs_200_cell"][target]["1000_cell_median"] = m["median"]
        results["vs_200_cell"][target]["1000_cell_ci95"] = [m["ci95_low"], m["ci95_high"]]
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for key, entry in results["by_method_target"].items():
        if entry["ks_vs_geometric"]:
            print(
                key,
                "median", entry["median_schedules"]["median"],
                "ci", [entry["median_schedules"]["ci95_low"], entry["median_schedules"]["ci95_high"]],
                "q_emp", round(entry["candidate_level"]["empirical_q"], 5),
                "KS D", round(entry["ks_vs_geometric"]["D"], 4),
                "KS p", round(entry["ks_vs_geometric"]["p"], 4),
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
