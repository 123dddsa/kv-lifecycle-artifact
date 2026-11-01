# vLLM 0.31.0 system-level rate (A800, 2026-11-20)

## Setup

- GPU: NVIDIA A800 80GB PCIe, driver 595.71.05, MIG disabled (sm_80).
- Stack: **vLLM 0.31.0 + LMCache 0.5.7.post1 (g1181bea5)**
  (`<HOME>/venv031`; LMCache installed from the Huawei PyPI mirror).
- Model: Qwen3-0.6B (local snapshot).
- Workload identical to the 0.25.1 runs: 64 concurrent streaming requests, cancel 5-300 ms
  after headers, 6 rounds, `max_model_len=4096`, `max_num_seqs=64`,
  `gpu_memory_utilization=0.3`.
- Harness: `rate_matrix_031.py`, one independent server process per repetition; 12 repetitions.
- LMCache MP server launched with `--supported-transfer-mode engine_driven` (required by
  0.5.7; without it the engine aborts with `operation_not_enabled`).

## Result

| Metric | Value |
|---|---|
| Crashes / independent processes | **12/12** |
| Crash rate (Wilson 95% CI) | **100% (75.8%-100%)** |
| Median wall per process | 39.2 s |
| Exit code | 10 (harness classification) |
| Server evidence | `assert req_id in self.requests` then `AssertionError` in the vLLM 0.31 EngineCore log |

The smoke round also reported `target_crash: true` and `EngineDeadError`. This closes the
"0.31 only has a component-level trace" gap: the same completion-after-free failure is
system-level reproducible on 0.31 as well.

## Scope

- Conditional rate under the cancellation-heavy workload; not natural incidence.
- Same engine family (vLLM) on a second version pair; this is **not** a cross-engine claim.
- LMCache version differs from the 0.25.1 stack (0.5.7.post1 vs 0.5.1); state this explicitly. The torch version is reported by the setup record but was not captured in the raw instance log, so it is not a paper claim. An earlier 0.31.0 run with LMCache 0.5.7.dev96 (g90a4ae2f) is a separate one-process observation, not this 12-process series.
  in the paper rather than reusing the old version pair.

## Files

- `rate_results.json`, `rate_rows.csv`
- `vllm_run001.log` (target assertion)
- `driver.log`, `smoke.log`

