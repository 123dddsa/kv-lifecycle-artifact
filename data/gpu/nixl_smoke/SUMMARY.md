# NIXL (vLLM native connector) probe — status and limits

Date: 2026-11-20. A800 80GB, driver 595, no `/dev/infiniband` (no RDMA).

## What was done

- Installed `nixl==1.5.2` (`nixl-cu12`) into the existing vLLM 0.25.1 environment.
- `vllm` reports `NIXL is available` (UCX path); driver starts.
- Ran the same cancellation workload with
  `--kv-transfer-config '{"kv_connector":"NixlConnector","kv_role":"kv_both"}'`
  (64 concurrent, 5-300 ms cancel, 1 round smoke).
- Result: server starts, 64/64 cancellations complete, `target_crash: false`,
  no `assert req_id in self.requests`; vLLM exits cleanly.

## Why this is **not** yet evidence

- vLLM itself warns that `kv_role='kv_both'` with `NixlConnector` is deprecated and that a
  real NIXL deployment uses **two instances** (`kv_producer` prefill + `kv_consumer` decode).
- With a single instance and no peer agent, there is no remote KV transfer for the connector
  to complete; the cancellation path is not exercising the NIXL completion-delivery window.
  So "no crash" here does **not** mean NIXL is safe, and it is not a valid comparison to the
  LMCache MP failure.

## What a valid NIXL test requires

1. Prefill instance: `NixlConnector`, `kv_role=kv_producer`, port A.
2. Decode instance: `NixlConnector`, `kv_role=kv_consumer`, port B.
3. Client: request prefill with `kv_transfer_params={"do_remote_decode": true, "do_remote_prefill": false}`,
   take the returned `remote_engine_id` / `remote_block_ids` / `remote_request_id`, send the
   decode request with `do_remote_prefill=true`, then abort it while the NIXL pull is in flight.
4. NIXL transport: UCX over TCP on this host (no RDMA); confirm the handshake works before
   running the cancellation series.

Estimated effort: 1-2 h including two-engine bring-up and handshake debugging.

## Files

- `smoke.log`: smoke driver output (`target_crash: false`)
- `vllm.log`: vLLM/NIXL startup log (`NIXL is available`, `kv_both` deprecation warning)
