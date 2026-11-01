#!/usr/bin/env bash
# Mixed-workload incidence matrix: normal traffic + a configurable fraction of
# cancellations. Each trial is an independent server process; a trial ends when
# the server crashes or the request/time budget is exhausted.
# Output: one JSON row per trial in results/incidence/incidence_rows.jsonl,
# with the config label and cancel probability attached.
set -u
export VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_ATTENTION_BACKEND=FLASH_ATTN
V=${WORKDIR:-.}/venv025/bin/python
B=${WORKDIR:-.}
OUT=$B/results/incidence
mkdir -p "$OUT"
: > "$OUT/incidence_rows.jsonl"
echo "incidence matrix start $(date -u +%FT%TZ)" >> "$OUT/run_info.txt"

run_config() {
  label=$1; prob=$2; trials=$3; maxreq=$4; conc=$5
  echo "config $label p=$prob trials=$trials maxreq=$maxreq conc=$conc $(date -u +%FT%TZ)" >> "$OUT/run_info.txt"
  for t in $(seq 1 "$trials"); do
    port=$((8400 + t))
    ipc=$(mktemp -d "$B/ipc.XXXXXX")
    dir=$OUT/${label}/trial$(printf '%02d' "$t")
    mkdir -p "$dir"
    timeout 480 env HF_HOME=$B/hf KILL_GATE_E2E_PORT=$port KILL_GATE_E2E_LOG_DIR="$dir" VLLM_RPC_BASE_PATH=$ipc \
      "$V" "$B/work/run_incidence.py" --concurrency "$conc" --cancel-prob "$prob" \
      --max-requests "$maxreq" --max-seconds 120 > "$dir/driver.log" 2>&1
    rc=$?
    row=$(grep -h 'incidence_result' "$dir/driver.log" | tail -1)
    if [ -n "$row" ]; then
      echo "$row" | sed "s/^{/{\"config\": \"$label\", \"prob\": $prob, /" >> "$OUT/incidence_rows.jsonl"
    else
      echo "{\"config\": \"$label\", \"prob\": $prob, \"trial\": $t, \"crashed\": null, \"exit\": $rc}" >> "$OUT/incidence_rows.jsonl"
    fi
    rm -rf "$ipc"
    sleep 4
  done
}

# Controls: no cancellations, must not crash.
run_config control_p0   0.0    5 512 64
# Realistic low cancellation rates (requests per crash).
run_config p0001        0.001 10 1024 64
run_config p0005        0.005 10 1024 64
run_config p001         0.01  10 512 64
run_config p005         0.05  8  256 64

echo "INCIDENCE_MATRIX_DONE $(date -u +%FT%TZ)" >> "$OUT/run_info.txt"
echo INCIDENCE_MATRIX_DONE



