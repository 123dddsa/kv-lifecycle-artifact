# NIXL P/D cancellation test (vLLM native connector, A800)

Date: 2026-11-20. Follow-up to the inconclusive single-instance probe.

## Setup

- GPU: A800 80GB, driver 595, no RDMA; NIXL UCX/TCP path.
- Two vLLM 0.25.1 instances on Qwen3-0.6B:
  - prefill: port 8100, `{"kv_connector":"NixlConnector","kv_role":"kv_producer","engine_id":"prefill","kv_ip":"127.0.0.1","kv_port":14579}`, side channel 5600;
  - decode: port 8200, same connector with `kv_role":"kv_consumer"`, `engine_id":"decode"`, side channel 5601.
- Client:
  1. prefill request with `kv_transfer_params={"do_remote_decode": true}`,
  2. take returned `kv_transfer_params` (remote_engine_id `prefill`, remote_block_ids, remote_host/port, remote_num_tokens),
  3. decode request with `do_remote_prefill=true` and those fields,
  4. after 0-2 ms, close the decode stream (abort);
  5. prompt ~3,000 tokens so the KV transfer is non-trivial; 64 concurrent, 6 rounds.

The handshake demonstrably worked: every round returned `remote_engine_id="prefill"`, and prefill/decode both stayed healthy.

## Result

| Metric | Value |
|---|---|
| Rounds x concurrency | 6 x 64 = 384 requested cancellations |
| Prefill handshakes succeeded | 384/384 |
| Decode aborts issued | 384/384 |
| Decode server alive after each round | 6/6 |
| `assert req_id in self.requests` in decode log | **0** |
| Errors | 0 |

**NIXL's engine-driven pull connector did not reproduce the LMCache MP completion-after-free crash in 384 aborts.**

## Interpretation

- This is a **connector-level distinction**, not evidence that "all engine-driven connectors are safe":
  - vLLM + **LMCacheMPConnector** (engine-driven, custom connector) crashes 20/20 on the same
    cancellation workload;
  - vLLM + **NIXLConnector** (native, pull-based, with its own abort/free handling) survives
    384 aborts.
- The likely difference is where completion/free ordering is handled: vLLM's native NIXL path
  has abort-aware block handling (cf. upstream PR #32255 "Delay freeing blocks of aborted async
  loads"), while the LMCache MP connector path delivers its completion after the scheduler has
  already freed the request.
- We therefore cannot claim "engine-driven connector contract is universally broken"; the honest
  statement is: the failure is specific to the LMCache MP connector path on the pinned vLLM
  version pair, and does not reproduce with vLLM's native NIXL connector under the same client
  cancellation workload.

## Limits

- Single node, UCX/TCP (no RDMA), Qwen3-0.6B, 3,000-token prompts, abort at 0-2 ms.
- NIXL may still have other windows (e.g., different abort timing, RDMA, longer transfers);
  we only state what this run shows.

## Files

- `client.log` (6 rounds; all alive, 384 cancels)
- `decode.log` (0 assertions)
- `prefill.log`
