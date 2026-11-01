#!/usr/bin/env bash
# Guarded-stack trials using the two-file overlay (no PYTHONPATH fixed tree).
# Each trial: fresh server, 6 rounds x 64 cancellations; a trial is NEGATIVE if
# the target assertion never appears. Time-boxed: stops if < 5 minutes remain.
set -u
V=${WORKDIR:-.}/venv025/bin/python
B=${WORKDIR:-.}
OUT=$B/results/guard_overlay
mkdir -p "$OUT"
: > "$OUT/guard_rows.jsonl"
SHUTDOWN_UTC='2026-11-17 18:00:00'

bash "$B/work/guard_overlay.sh" apply >> "$OUT/run.log" 2>&1
ok=$?
echo "overlay_apply_exit=$ok $(date -u +%FT%TZ)" >> "$OUT/run.log"
if [ "$ok" -ne 0 ]; then
  echo "GUARD_OVERLAY_APPLY_FAILED" >> "$OUT/run.log"
  exit 0
fi

trial=0
while [ "$trial" -lt 8 ]; do
  now=$(date -u +%s)
  shutdown=$(date -u -d "$SHUTDOWN_UTC" +%s 2>/dev/null || echo 0)
  remaining=$((shutdown - now))
  if [ "$remaining" -lt 360 ]; then
    echo "guard_stop_remaining=$remaining" >> "$OUT/run.log"
    break
  fi
  trial=$((trial + 1))
  port=$((8600 + trial))
  ipc=$(mktemp -d "$B/ipc.XXXXXX")
  dir=$OUT/trial$(printf '%02d' "$trial")
  mkdir -p "$dir"
  timeout 720 env HF_HOME=$B/hf KILL_GATE_E2E_PORT=$port KILL_GATE_E2E_LOG_DIR=$dir VLLM_RPC_BASE_PATH=$ipc \
    VLLM_WSL2_ENABLE_PIN_MEMORY=1 VLLM_USE_FLASHINFER_SAMPLER=0 \
    "$V" "$B/work/scripts/run_e2e_conditions.py" --rounds 6 --concurrency 64 \
    --gpu-memory-utilization 0.30 > "$dir/driver.log" 2>&1
  rc=$?
  if grep -q 'assert req_id in self.requests' "$dir/vllm.log" 2>/dev/null; then hit=true; else hit=false; fi
  rounds=$(grep -o '"round_id": [0-9]*' "$dir/driver.log" 2>/dev/null | tail -1 | grep -o '[0-9]*')
  echo "{\"trial\": $trial, \"exit\": $rc, \"target_assertion\": $hit, \"last_round\": ${rounds:-null}}" >> "$OUT/guard_rows.jsonl"
  rm -rf "$ipc"
  sleep 4
done

bash "$B/work/guard_overlay.sh" restore >> "$OUT/run.log" 2>&1
echo "GUARD_OVERLAY_DONE $(date -u +%FT%TZ)" >> "$OUT/run.log"
exit 0


