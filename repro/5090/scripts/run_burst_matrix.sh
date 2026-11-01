#!/usr/bin/env bash
# Burst-cancellation matrix on the 5090: k simultaneous in-flight cancellations,
# repeated trials, to find the minimum burst that hits the race.
set -u
V=${WORKDIR:-.}/venv025/bin/python
B=${WORKDIR:-.}
OUT=$B/results/burst
M=$B/hf_ms/models/Qwen--Qwen3-0.6B/snapshots/master
mkdir -p "$OUT"
: > "$OUT/burst_rows.jsonl"
export VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_ATTENTION_BACKEND=FLASH_ATTN
export KVC_MODEL=$M
echo "burst start $(date -u +%FT%TZ)" >> "$OUT/run_info.txt"
for k in 1 4 16 64; do
  for t in 1 2 3 4 5 6 7 8; do
    port=$((8700 + t))
    dir=$OUT/k${k}_t${t}
    mkdir -p "$dir"
    ipc=$(mktemp -d "$B/ipc.XXXXXX")
    HF_HOME=$B/hf KILL_GATE_E2E_PORT=$port KILL_GATE_E2E_LOG_DIR=$dir VLLM_RPC_BASE_PATH=$ipc \
      timeout 480 "$V" "$B/work/run_burst.py" --burst-k "$k" --rounds 3 --concurrency 64 \
      --gpu-memory-utilization 0.35 > "$dir/driver.log" 2>&1
    rc=$?
    row=$(grep -h 'burst_result' "$dir/driver.log" | tail -1)
    echo "{\"k\": $k, \"trial\": $t, \"rc\": $rc, \"row\": $row}" >> "$OUT/burst_rows.jsonl"
    rm -rf "$ipc"
    sleep 3
  done
done
echo "BURST_DONE $(date -u +%FT%TZ)" >> "$OUT/run_info.txt"
echo BURST_DONE

