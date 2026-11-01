# Local (RTX 4060 laptop + WSL2) reproducibility notes

Third part of the bundle. This host produced the GRIEF baseline, the
1,000-cell calibration replay, the local guard negative, the component-level
0.31 traces, and all offline `kvc` tool numbers.

## Host

- Windows 11 + WSL2 Ubuntu, RTX 4060 Laptop 8GB (driver from Windows), no
  `nvcc` in WSL.
- `CPython 3.14` on Windows for the `kvc-lifecycle` package tests.
- `.venv-gpu` (WSL): vLLM 0.25.1 + LMCache 0.5.1 + torch 2.11.0+cu130.
- `.venv` (Windows): GRIEF 0.1.0 (Python 3.12).
- HF cache: `<EXPERIMENT_DATA>\<LOCAL_WORKSPACE>\cache\huggingface`
  (Qwen3-0.6B).

## Layout of this bundle

```
local/
  tool/                 # kvc-lifecycle 0.8.0 source (src, tests, scripts, examples)
  scripts/              # experiment drivers
    run_e2e_conditions.py       # end-to-end cancellation driver (0.6B, 4060)
    run_grief_campaign.sh       # GRIEF headless campaign (300 iters)
    analyze_scale_1000.py       # calibration analysis (KS, medians, CIs)
    dp_complexity.py            # exact-DP scale analysis (states/transitions)
    *.py / *.sh                 # guard variants, component port, local helpers
  results/
    SCALE_1000_REPORT.md        # 1,000-cell calibration report
    real_search_by_seed.csv     # per-seed first-discovery data (1.3MB)
    real_search_results.json    # aggregated calibration results
    GRIEF_VS_KVC.md             # same-stack GRIEF comparison (scoped claims)
    (raw GRIEF campaign log omitted: it embedded local absolute paths; see grief_findings/ and GRIEF_VS_KVC.md)
    grief_findings/             # 7 findings, signature ledger, run meta
    COMPONENT_TRACE_REPORT.md   # 0.31 component-level trace (2/2)
    ISSUE_BENCHMARK files       # issues.json, VERIFY_LOG.md, table1.tex
    CASE_STUDIES.md             # three case studies
    BASELINE_MATRIX.md          # GRIEF/KVGuard capability matrix
    TOOL_EVAL.md                # install, tests, overhead, artifact audit
    EVIDENCE_README.md          # full evidence index
```

## Commands

### (a) Tool: offline checks

```bash
# from the repo root that contains tool/
python -m pip install -e "tool[dev]"
kvc check  tool/examples/vllm_0251_stale_send.jsonl     # -> I_COMPLETION_AFTER_FREE, exit 1
kvc audit  <trace> --assumptions <space.json>
kvc cost   <model.json> --horizon 10 --wait 0
pytest tool/tests -q
```

### (b) Local end-to-end reproduce (4060, WSL)

```bash
cd evidence/remote   # or local/scripts
HF_HOME=<EXPERIMENT_DATA>/<LOCAL_WORKSPACE>/cache/huggingface \
KILL_GATE_E2E_PORT=8051 KILL_GATE_E2E_LOG_DIR=$PWD/logs/e2e \
VLLM_WSL2_ENABLE_PIN_MEMORY=1 VLLM_USE_FLASHINFER_SAMPLER=0 \
<EXPERIMENT_DATA>/<LOCAL_WORKSPACE>/.venv-gpu/bin/python run_e2e_conditions.py \
  --rounds 6 --concurrency 64 --gpu-memory-utilization 0.30
# expect: target assertion in vllm.log and exit 10
```

### (c) GRIEF same-stack baseline

```bash
# server on 127.0.0.1:8051 (run_e2e_conditions.py --server-only)
bash scripts/run_grief_campaign.sh 300 <MOUNT>/.../grief_output
# expect: campaign aborts after ~53 iterations with
# "server has been unhealthy for 10 consecutive iterations";
# results/grief_findings/ lists 7 findings / 3 anomaly classes.
```

### (d) 1,000-cell calibration replay

```bash
python scripts/analyze_scale_1000.py --input results/real_search_by_seed.csv
# expect: stale median 25.0 (95% CI 23.0-27.5), dual 2.0, PROC 3.0,
# KS D=0.048 p=0.19; matches SCALE_1000_REPORT.md
```

### (e) DP scale analysis

```bash
python scripts/dp_complexity.py    # H=10: stale 253 states / 2,328 transitions ...
```

## Results summary

| Item | Value |
|---|---|
| Calibration (1,000 cells/family) | stale median 25.0 (95% CI 23.0-27.5) vs predicted 25; dual 2.0; PROC 3.0; KS D=0.048 p=0.19 |
| GRIEF same stack | crashes at ~8 min / 53 iterations; 7 findings / 3 generic classes; no attribution; campaign aborted |
| Guard local negative | 4/4 runs negative (6 rounds x 64 cancels per run) |
| 0.31 component trace | 2/2 reproduce `I_COMPLETION_AFTER_FREE`; no rate estimate |
| Tool | 68 tests + 7 subtests in 4.4s; scoped monitor 1.15-1.67 us/action |

## Pitfalls

1. **WSL localhost proxy warning** ("检测到 localhost 代理配置") is harmless; it
   appears on every WSL invocation but does not affect the run.
2. **CRLF in shell scripts** copied from Windows: `bash: $'\r': command not found`.
   Fix with `sed -i 's/\r$//' script.sh`.
3. **`pkill -f` self-match**: `pkill -f "lmcache server"` also matches the
   invoking shell (the pattern is in its command line) and kills the session.
   Use `ps aux | grep -E "[l]mcache server"` instead.
4. **8GB VRAM**: run 0.6B with `--gpu-memory-utilization 0.30`; 8B does not fit
   on this host (use the A800/5090 for 8B).
5. **HF/Xet**: hf-mirror's Xet downloader stalls; use ModelScope or a local
   cache snapshot, and point `KVC_MODEL` at the local path.
6. **GRIEF abort semantics**: after the server dies, GRIEF keeps probing and
   aborts after 10 unhealthy iterations; this is expected and is reported as
   "campaign aborted, 7 findings written".
7. **Do not compare GRIEF's campaign numbers to its paper**: our run used a
   300-iteration budget on one 4060; the paper's 15 vulnerabilities / 2 CVEs
   are across its own campaigns. The bundle's GRIEF_VS_KVC.md states the scope.


