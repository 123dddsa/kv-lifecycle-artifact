# Regenerating the paper's numbers

All raw files needed for the calibration, POLL/DELIVER and tool-measurement
numbers are under `data/`; this directory recomputes those aggregates. Standard
library only. It does **not** re-run the GPU experiments or regenerate the audit, identity-composition,
case-study or policy-frontier numbers; those are documented in
`QUANTITATIVE_AUDIT.md`, `FULL_PROOFS.md` and the paper.

```bash
python repro/regenerate/regenerate.py
```

Expected output shape:

```
== External calibration (random arm, 200 seeds per target) ==
stale_send       cells=200 censored=1 median=26.5 CI95=[22.0,32.0] predicted=25
dual_completion  cells=200 censored=0 median=2.0  CI95=[2.0,2.0]   predicted=2
permanent_proc   cells=200 censored=0 median=3.0  CI95=[3.0,3.0]   predicted=3
...
```

## Map from paper numbers to files

| Paper item | Raw file(s) |
|---|---|
| 1,200-cell calibration (400 cells/family) | `data/real_200/real_search_by_seed.csv`, `analysis_results.json` |
| 6,000-cell replication (1,000 seeds/family) | `data/scale_1000/real_search_by_seed.csv`, `REPORT.md` |
| Table IV (POLL/DELIVER counterfactual) | `data/delivery_separation/real_rows.jsonl`, `validation.json` |
| tool install / pytest / overhead | `data/tool_eval/pytest_runs.jsonl`, `quickstart_runs.jsonl` |
| rate matrices (A800 / 5090) | `repro/a800/results/conditions/*/rate_results.json`, `repro/5090/results/W0_5090_rate_results.json` |
| burst trigger law | `repro/5090/results/burst_rows.jsonl`, `sweep_rows.jsonl` |
| guard negative | `repro/5090/results/guard_rows.jsonl` |
| mixed-load incidence | `repro/5090/results/incidence_rows.jsonl` |
| GPU rates (Llama-8B, vLLM-0.31) | `data/gpu/llama8b/rate_results.json`, `data/gpu/vllm031/rate_results.json` |
| NIXL / SGLang boundary probes | `data/gpu/nixl_pd/SUMMARY.md`, `data/gpu/sglang/SUMMARY.md` |
| baseline / ablation / statistics | `analysis/*/REPORT.md` |
| TLA+ checks | `tla/TLC_*.log` (re-run: download `tla2tools.jar` from the official release) |

## Notes

- The calibration CSV has one row per (method, target, seed); the random arm is
  the 200 cells/family used for medians, the directed arm is a one-schedule policy.
- `found=false` rows are right-censored at the per-cell schedule budget and are
  excluded from the median, as stated in the paper.
- The 0.31 component trace and the three case studies are summarised in
  `data/real_200/REPORT.md` and in the paper; their raw logs are not shipped
  (they contain host-local absolute paths).
