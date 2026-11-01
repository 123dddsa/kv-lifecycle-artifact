# kvc-lifecycle — anonymous artifact

Anonymous artifact for double-blind review. The repository contains the tool, raw data,
and reproduction scripts for a study of scoped lifecycle contracts for asynchronous
KV-cache transfers. It does not identify the authors, and it should not be cited before
publication.

The artifact contains only the material needed to check the paper's claims:

```
tool/                     kvc-lifecycle 0.8.0 (source, tests, examples, packaging script)
tla/                      TLA+ models, configs, and TLC logs (merged / separated / identity k=2,3)
FULL_PROOFS.md            complete proofs for soundness, counting, merged unreachability,
                          impossibility, separation sufficiency, identity necessity,
                          geometric law + non-adaptive lower bound, audit completeness
QUANTITATIVE_AUDIT.md     25-issue detection/attribution audit
issues.json               the 25 verified upstream reports (URLs, evidence level, fix status)
repro/README.md           three-host reproduction guide
repro/regenerate/         one-command regeneration of the calibration/delivery/tool numbers
data/                     raw calibration, POLL/DELIVER and tool-measurement data
REGENERATE.md             map from paper numbers to raw files
repro/5090/               RTX 5090 scripts + results: smoke, guard-negative, incidence,
                          burst-size trigger law, cross-hardware rate, pip freeze
repro/a800/               A800 scripts + results: W0-W3 rate tables, W6-W7 Qwen3-8B runs
repro/local/              laptop scripts + results: 1,200-cell calibration, GRIEF baseline,
                          0.31 component trace, tool evaluation
data/gpu/                 raw GPU runs: Llama-8B and vLLM-0.31 rates, SGLang/NIXL boundary probes
analysis/                 baseline matrix, component-ablations, process-level statistics
```

## Quick start (tool only, no GPU)

Recompute the calibration, POLL/DELIVER and tool-measurement numbers from the raw files: `python repro/regenerate/regenerate.py` (see `REGENERATE.md`).

```bash
python -m pip install -e "tool[dev]"
kvc check tool/examples/vllm_0251_stale_send.jsonl    # exits 1 with I_COMPLETION_AFTER_FREE
pytest tool/tests -q                                  # 68 tests + 7 subtests
```

## Key results (regenerate from `data/` with `repro/regenerate/regenerate.py`)

| Claim | File |
|---|---|
| merged oracle: 0/200 monitor findings vs 74/200 real assertions | `repro/5090/results/SUMMARY.md` (context), `FULL_PROOFS.md` |
| A800 conditional rate: 20/20, 100%, CI 83.9-100% | `repro/a800/results/conditions/W0_orig_c64_5-300/` |
| A800 Qwen3-8B: 12/12, CI 75.8-100% | `repro/a800/results/conditions/W6_8b_c64_5-300/`, `W7_8b_c1_5-300/` |
| Llama-3.1-8B (A800): 12/12, CI 75.8-100%, median 36.7 s | `data/gpu/llama8b/` |
| RTX 5090 rate: 12/12, CI 75.8-100%, median 22.2 s | `repro/5090/results/W0_5090_rate_results.json` |
| guard negative: 8/8 (6 rounds x 64 cancels) | `repro/5090/results/guard_rows.jsonl` |
| mixed-load incidence: 43 trials, 1 crash | `repro/5090/results/incidence_rows.jsonl` |
| burst trigger law: 0/16 (k<=4), 1/8 (k=16), 32/32 (k>=24), delay-independent | `repro/5090/results/burst_rows.jsonl`, `sweep_rows.jsonl` |
| 1,200-cell calibration: stale median 26.5 (CI 22-32); 6,000-cell replication: 25.0 (CI 23.0-27.5) | `data/real_200/`, `data/scale_1000/` |
| vLLM 0.31.0 system-level rate: 12/12, CI 75.8-100%, median 39.2 s | `data/gpu/vllm031/` |
| Llama-3.1-8B cross-model rate: 12/12, CI 75.8-100%, median 36.7 s | `data/gpu/llama8b/` |
| NIXL pull (P/D) boundary: 0/384 aborts | `data/gpu/nixl_pd/` |
| SGLang + LMCache boundary: 0/384 aborts | `data/gpu/sglang/` |
| Paired counterfactual replay: 7/200 vs 0/200 witnesses, 7 flips, 78 assertions | `analysis/PAIRED_COUNTERFACTUAL.md` |
| TLA+: merged no C1; separated 6-step counterexample; identity counting k=2,3 | `tla/` |
| 25 reports: 18/25 contract-expressible, 7/25 outside | `QUANTITATIVE_AUDIT.md` |

## Reproduction notes

- Scripts take machine paths from environment variables (`WORKDIR`, `REPO`, `LOCAL_WORKSPACE`,
  `DATA_DIR`), so the same files run on any host; see `repro/README.md`.
- The GPU runs used vLLM 0.25.1 + LMCache 0.5.1 + torch 2.11.0+cu130 on an A800 80GB and an
  RTX 5090 32GB; on sm_120 set `VLLM_USE_FLASHINFER_SAMPLER=0` (documented in the reproduction
  guide).
- Raw per-iteration logs, the local SSH helpers, credentials, and `tla2tools.jar` are not
  included; the last is a public download from the TLA+ release page.





