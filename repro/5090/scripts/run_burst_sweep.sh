#!/usr/bin/env bash
# Trigger-characterization sweeps: burst size threshold and cancel-delay window.
set -u
V=${WORKDIR:-.}/venv025/bin/python
B=${WORKDIR:-.}
M=$B/hf_ms/models/Qwen--Qwen3-0.6B/snapshots/master
OUT=$B/results/burst_sweep
mkdir -p "$OUT"
: > "$OUT/sweep_rows.jsonl"
export VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_ATTENTION_BACKEND=FLASH_ATTN
export KVC_MODEL=$M

run_trial() {
  label=$1; k=$2; dmin=$3; dmax=$4; trial=$5
  port=$((8800 + trial))
  dir=$OUT/${label}_t${trial}
  mkdir -p "$dir"
  ipc=$(mktemp -d "$B/ipc.XXXXXX")
  HF_HOME=$B/hf KILL_GATE_E2E_PORT=$port KILL_GATE_E2E_LOG_DIR=$dir VLLM_RPC_BASE_PATH=$ipc \
    timeout 480 "$V" "$B/work/run_burst.py" --burst-k "$k" --rounds 3 --concurrency 64 \
    --dmin "$dmin" --dmax "$dmax" --gpu-memory-utilization 0.35 > "$dir/driver.log" 2>&1
  rc=$?
  row=$(grep -h 'burst_result' "$dir/driver.log" | tail -1)
  echo "{\"label\": \"$label\", \"k\": $k, \"dmin\": $dmin, \"dmax\": $dmax, \"trial\": $trial, \"rc\": $rc, \"row\": $row}" >> "$OUT/sweep_rows.jsonl"
  rm -rf "$ipc"
  sleep 3
}

# Burst-size threshold, between 16 (never triggered) and 64 (triggered).
for k in 24 32 48; do
  for t in 1 2 3 4; do run_trial "k${k}" "$k" 0.005 0.300 "$t"; done
done

# Delay-window sweep at k=64: early, late, and full window.
for t in 1 2 3 4; do run_trial "early" 64 0.005 0.050 "$t"; done
for t in 1 2 3 4; do run_trial "late"  64 0.150 0.300 "$t"; done
for t in 1 2 3 4; do run_trial "full"  64 0.005 0.300 "$t"; done

echo "SWEEP_DONE $(date -u +%FT%TZ)" >> "$OUT/run_info.txt"
echo SWEEP_DONE

