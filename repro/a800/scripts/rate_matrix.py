#!/usr/bin/env python3
"""Rate estimation for the KV completion-after-free crash on a rented GPU.

Runs the real vLLM + LMCache service stack repeatedly under one
(concurrency, cancel-delay, variant) condition and reports the crash rate
with a Wilson 95% CI. Every repetition is an independent server process;
the harness reuses the frozen run_e2e_conditions.py driver.

Usage (on the rented instance):
  <WORKDIR>/venv025/bin/python rate_matrix.py \
      --variant original --concurrency 64 --dmin 0.005 --dmax 0.300 \
      --reps 20 --rounds 6 --outdir <WORKDIR>/results/W0_orig_c64
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
import os
from pathlib import Path

WORK = Path(os.environ.get("WORKDIR", ".")) / "work"
DRIVER = WORK / "scripts" / "run_e2e_conditions.py"
FIXED_TREE = WORK / "LMCache_fixed_e2e"


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def read_summary(run_dir: Path) -> dict:
    path = run_dir / "summary.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def target_assertion_in_log(run_dir: Path) -> bool:
    log = run_dir / "vllm.log"
    if not log.exists():
        return False
    try:
        return "assert req_id in self.requests" in log.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["original", "fixed"], required=True)
    ap.add_argument("--concurrency", type=int, required=True)
    ap.add_argument("--dmin", type=float, required=True)
    ap.add_argument("--dmax", type=float, required=True)
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--gpu-memory-utilization", type=float, default=0.30)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--model", default=None, help="override the model id recorded for the driver")
    ap.add_argument("--hf-home", default="<WORKDIR>/hf")
    ap.add_argument("--timeout-s", type=int, default=1200)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for rep in range(1, args.reps + 1):
        run_dir = outdir / f"run{rep:03d}"
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True)
        ipc = tempfile.mkdtemp(prefix="vllm-ipc-", dir="<WORKDIR>")
        env = os.environ.copy()
        env["HF_HOME"] = args.hf_home
        env["HF_ENDPOINT"] = "https://hf-mirror.com"
        if args.model:
            env["KVC_MODEL"] = args.model
        env["VLLM_LOGGING_LEVEL"] = "INFO"
        env["VLLM_WSL2_ENABLE_PIN_MEMORY"] = "1"
        env["VLLM_USE_FLASHINFER_SAMPLER"] = "0"
        env["PYTHONHASHSEED"] = "0"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["VLLM_RPC_BASE_PATH"] = ipc
        env["KILL_GATE_E2E_LOG_DIR"] = str(run_dir)
        env["KILL_GATE_E2E_PORT"] = str(8100 + (rep % 800))
        env["KILL_GATE_CANCEL_DELAY_MIN"] = str(args.dmin)
        env["KILL_GATE_CANCEL_DELAY_MAX"] = str(args.dmax)
        if args.variant == "fixed":
            env["PYTHONPATH"] = str(FIXED_TREE)
        else:
            env.pop("PYTHONPATH", None)
        cmd = [
            sys.executable,
            str(DRIVER),
            "--rounds",
            str(args.rounds),
            "--concurrency",
            str(args.concurrency),
            "--gpu-memory-utilization",
            str(args.gpu_memory_utilization),
        ]
        started = time.time()
        try:
            proc = subprocess.run(
                cmd,
                env=env,
                cwd="<WORKDIR>",
                capture_output=True,
                text=True,
                timeout=args.timeout_s,
            )
            rc = proc.returncode
            driver_log = proc.stdout + "\n" + proc.stderr
        except subprocess.TimeoutExpired as error:
            rc = 124
            driver_log = f"TIMEOUT: {error!r}"
        wall = time.time() - started
        (run_dir / "driver.log").write_text(driver_log, encoding="utf-8", errors="replace")
        summary = read_summary(run_dir)
        assertion = target_assertion_in_log(run_dir) or bool(summary.get("target_assertion"))
        row = {
            "condition": f"{args.variant}:c{args.concurrency}:{args.dmin}-{args.dmax}",
            "rep": rep,
            "exit_code": rc,
            "classification": summary.get("classification"),
            "target_assertion": assertion,
            "cancelled_requests": summary.get("cancelled_requests"),
            "completed_rounds": summary.get("completed_rounds"),
            "normal_requests": summary.get("normal_requests"),
            "normal_statuses": summary.get("normal_statuses"),
            "wall_s": round(wall, 1),
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        shutil.rmtree(ipc, ignore_errors=True)
        time.sleep(5)

    crashes = sum(1 for r in rows if r["target_assertion"])
    lo, hi = wilson(crashes, len(rows))
    result = {
        "condition": f"{args.variant}:c{args.concurrency}:{args.dmin}-{args.dmax}",
        "variant": args.variant,
        "concurrency": args.concurrency,
        "cancel_delay_s": [args.dmin, args.dmax],
        "reps": len(rows),
        "crashes": crashes,
        "crash_rate": crashes / len(rows) if rows else None,
        "crash_rate_wilson95": [lo, hi],
        "median_wall_s": sorted(r["wall_s"] for r in rows)[len(rows) // 2] if rows else None,
        "rows": rows,
    }
    (outdir / "rate_results.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (outdir / "rate_rows.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({k: result[k] for k in ("condition", "reps", "crashes", "crash_rate", "crash_rate_wilson95", "median_wall_s")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())




