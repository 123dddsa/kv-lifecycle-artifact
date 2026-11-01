#!/usr/bin/env python3
"""Regenerate the paper's key numbers from the raw files in data/.

Standard library only. Run from the repository root:

    python repro/regenerate/regenerate.py
"""
from __future__ import annotations

import csv
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
TARGETS = ("stale_send", "dual_completion", "permanent_proc")


def calibration() -> None:
    print("== External calibration (random arm, 200 seeds per target) ==")
    rows = list(csv.DictReader((DATA / "real_200" / "real_search_by_seed.csv").open(encoding="utf-8")))
    analysis = json.loads((DATA / "real_200" / "analysis_results.json").read_text(encoding="utf-8"))
    canonical = {t["target"]: t for t in analysis["targets"]}
    for target in TARGETS:
        cells = [r for r in rows if r["target"] == target and r["method"] == "random"]
        values = []
        censored = 0
        for r in cells:
            if r["found"] == "True":
                values.append(float(r["first_discovery_schedule"]))
            else:
                censored += 1
                values.append(float(r["discovery_cost_censored"]))
        med = statistics.median(values)
        c = canonical.get(target, {})
        ci = c.get("observed", {}).get("ci95")
        print(f"{target:16s} cells={len(cells)} censored={censored} median={med:.1f} "
              f"canonical_CI95={ci} predicted={c.get('predicted_median')}")


def scale1000() -> None:
    print("\n== 6,000-cell replication (random arm, 1,000 seeds per target) ==")
    rows = list(csv.DictReader((DATA / "scale_1000" / "real_search_by_seed.csv").open(encoding="utf-8")))
    for target in TARGETS:
        cells = [r for r in rows if r["target"] == target and r["method"] == "random"]
        values = []
        censored = 0
        for r in cells:
            if r["found"] == "True":
                values.append(float(r["first_discovery_schedule"]))
            else:
                censored += 1
                values.append(float(r["discovery_cost_censored"]))
        med = statistics.median(values)
        print(f"{target:16s} cells={len(cells)} censored={censored} median={med:.1f} "
              f"(canonical CI and KS discussion: data/scale_1000/REPORT.md)")


def delivery() -> None:
    print("\n== POLL/DELIVER counterfactual (200 candidates per mode and target) ==")
    rows = [json.loads(line) for line in (DATA / "delivery_separation" / "real_rows.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    for mode in ("separated", "merged"):
        for target in TARGETS:
            cells = [r for r in rows if r["mode"] == mode and r["target"] == target]
            found = sum(1 for r in cells if r.get("found"))
            assertions = sum(1 for r in cells if r.get("scheduler_assertion"))
            errors = sum(1 for r in cells if r.get("harness_error"))
            print(f"{mode:9s} {target:16s} candidates={len(cells)} found={found} "
                  f"assertions={assertions} harness_errors={errors}")


def tool_eval() -> None:
    print("\n== Tool evaluation ==")
    pytest_rows = [json.loads(line) for line in (DATA / "tool_eval" / "pytest_runs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    inner = []
    for r in pytest_rows:
        m = re.search(r"in ([0-9.]+)s", r.get("tail", ""))
        if m:
            inner.append(float(m.group(1)))
    print(f"pytest runs={len(pytest_rows)} exit_all_zero={all(r['exit'] == 0 for r in pytest_rows)} "
          f"median_internal_s={statistics.median(inner):.2f}")
    installs = [json.loads(line) for line in (DATA / "tool_eval" / "install_runs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    pip = [r["pip_install_s"] for r in installs]
    venv = [r["venv_create_s"] for r in installs]
    print(f"install runs={len(installs)} median_venv_s={statistics.median(venv):.2f} "
          f"median_pip_s={statistics.median(pip):.2f} range_pip=[{min(pip):.1f},{max(pip):.1f}]")
    quick = [json.loads(line) for line in (DATA / "tool_eval" / "quickstart_runs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    totals = [r["total_e2e_s"] for r in quick]
    print(f"quickstart runs={len(quick)} median_total_s={statistics.median(totals):.2f}")


if __name__ == "__main__":
    calibration()
    scale1000()
    delivery()
    tool_eval()
