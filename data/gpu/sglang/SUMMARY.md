# SGLang second-path probe (A800, 2026-11-20)

## Setup

- GPU: A800 80GB, driver 595.71.05, sm_80.
- SGLang **0.5.23** (separate venv), Qwen3-0.6B, `--enable-lmcache`,
  `--context-length 4096`, `--max-running-requests 64`, `--mem-fraction-static 0.3`.
- LMCache **0.5.7.post1** full install in a separate venv runs the standalone MP server:
  `lmcache server --port 5555 --supported-transfer-mode auto --l1-size-gb 1 --eviction-policy LRU`.
  `LMCACHE_MP_HOST=127.0.0.1`, `LMCACHE_MP_PORT=5555`.
- SGLang initialises `LMCacheUnifiedRadixCache` and the connector reports
  `UnifiedLMCacheMPConnector initialized succeed`; the MP server log shows
  `Registered KV cache ... lmcache_driven_transfer`.

## Workload

The SGLang API differs from vLLM's OpenAI streaming cancellation, so the client uses
SGLang's native path:

1. `POST /generate` with an explicit `rid`, `stream=true`, `max_new_tokens=512`;
2. after a random 5-300 ms delay, `POST /abort_request` with that `rid` (SGLang's abort path);
3. 64 concurrent requests per round, 6 rounds = **384 cancellations**;
4. health checked after every round (`/model_info`).

## Result

| Metric | Value |
|---|---|
| Rounds x concurrency | 6 x 64 = 384 cancellations |
| Aborts accepted (`/abort_request` HTTP 200) | **384/384** |
| Server alive after each round | **yes, 6/6** |
| `AssertionError` / scheduler assertion in SGLang log | **0** |
| LMCache activity | KV cache registered; 512/512 tokens stored in one sample |

**No completion-after-free crash was observed on the SGLang + LMCache unified path.**

## Interpretation and boundary

This is a **negative result**, not a failure to run the experiment:

- The SGLang path uses `LMCacheUnifiedRadixCache` with an **LMCache-driven** transfer mode
  (`lmcache_driven_transfer`), while the vLLM failure occurs in the engine-driven
  completion-delivery connector (`LMCacheMPConnector`, `register_kv_cache_engine_driven_context`).
- In the SGLang path the LMCache MP server owns the KV transfer and the abort completes through
  the server's own lifecycle; the vLLM-specific "deliver a completion after the scheduler has
  released the request" window is not exposed in the same form.
- We therefore cannot claim cross-engine replication of the failure. The correct paper statement is:
  the failure is specific to the asynchronous **engine-driven connector** contract (vLLM +
  LMCache MP connector); SGLang's LMCache integration uses a different ownership/transfer model
  and did not reproduce it in 384 aborts.
- We also cannot claim SGLang is safe in general: only that our workload did not trigger the
  vLLM-style window on this version pair.

## Files

- `abort_rounds.log` (client rounds; 384 aborts, all alive)
- `sglang_server.log` (server log; 0 AssertionError)
- `lmcache_server.log` (MP server log; KV registration, store)
