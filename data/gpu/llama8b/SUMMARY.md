# Cross-model check: Llama-3.1-8B on the A800 (2026-11-20)

## Setup

- GPU: NVIDIA A800 80GB PCIe, driver 595.71.05, MIG disabled (sm_80).
- Stack: vLLM 0.25.1 + LMCache 0.5.1 + torch 2.11.0+cu130 (`<WORKDIR>/venv025`).
- Model: `LLM-Research/Meta-Llama-3.1-8B-Instruct` (ModelScope mirror, safetensors only),
  local path used via `model_snapshot_path`.
- Workload identical to the Qwen runs: 64 concurrent streaming requests, each cancelled
  5-300 ms after headers, 6 rounds per server process, `max_model_len=4096`,
  `max_num_seqs=64`, `gpu_memory_utilization=0.5`.
- Harness: `rate_matrix.py` (one independent server process per repetition), 12 repetitions.

## Result

| Metric | Value |
|---|---|
| Crashes / independent processes | **12/12** |
| Crash rate (Wilson 95% CI) | **100% (75.8%-100%)** |
| Median wall per process | 36.7 s |
| Exit code | 10 (harness classification) |
| Server evidence | `assert req_id in self.requests` then `AssertionError` in the vLLM EngineCore log |

Every repetition started a fresh vLLM + LMCache service, hit the same scheduler assertion
during the cancellation round, and died. This is the same failure mechanism as Qwen3-0.6B
and Qwen3-8B, now on a **different model family**.

## Why this matters

The earlier W6/W7 "8B" runs in the paper used **Qwen3-8B**, i.e. the same model family as
the 0.6B runs. The cross-family claim therefore had a real gap; this run closes it: the
conditional trigger rate is 12/12 on Llama-3.1-8B as well.

## Scope of the claim

- Conditional rate under a cancellation-heavy workload; **not** natural incidence or MTBF.
- One model family added, same engine/stack (vLLM + LMCache); not a cross-engine claim.
- Latency (36.7 s) is stack-specific and should not be compared across GPUs.

## Files

- `rate_results.json`, `rate_rows.csv`
- `vllm_run001.log` (contains the target assertion)
- `driver.log` (harness output)
