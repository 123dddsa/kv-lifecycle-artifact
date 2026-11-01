#!/usr/bin/env bash
# One 0.6B end-to-end smoke on the RTX 5090: must reproduce the target crash.
set -u
B=${WORKDIR:-.}
V=$B/venv025/bin/python
OUT=$B/results/SMOKE
mkdir -p "$OUT"
STATUS=$B/work/status.txt
rm -rf "$OUT"; mkdir -p "$OUT"
echo "SMOKE_START $(date -u +%FT%TZ)" >> "$STATUS"
ipc=$(mktemp -d "$B/ipc.XXXXXX")
HF_HOME=$B/hf KILL_GATE_E2E_PORT=8111 KILL_GATE_E2E_LOG_DIR="$OUT" VLLM_RPC_BASE_PATH=$ipc \
  VLLM_WSL2_ENABLE_PIN_MEMORY=1 VLLM_USE_FLASHINFER_SAMPLER=0 \
  timeout 900 "$V" "$B/work/scripts/run_e2e_conditions.py" --rounds 2 --concurrency 4 \
  --gpu-memory-utilization 0.30 > "$OUT/driver.log" 2>&1
rc=$?
if grep -q 'assert req_id in self.requests' "$OUT/vllm.log" 2>/dev/null; then hit=true; else hit=false; fi
rounds=$(grep -o '"round_id": [0-9]*' "$OUT/driver.log" 2>/dev/null | tail -1 | grep -o '[0-9]*')
echo "SMOKE_RESULT rc=$rc target_assertion=$hit last_round=${rounds:-null} $(date -u +%FT%TZ)" >> "$STATUS"
rm -rf "$ipc"
if [ "$hit" = "true" ]; then echo "SMOKE_DONE ok" >> "$STATUS"; else echo "SMOKE_DONE fail" >> "$STATUS"; fi
echo "SMOKE_FINISHED"

