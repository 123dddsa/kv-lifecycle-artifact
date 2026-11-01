#!/usr/bin/env bash
set -u
ROOT=${EXPERIMENT_DATA:-.}
NG=$ROOT/${LOCAL_WORKSPACE:-.}
OUT=$ROOT/post_review_completion/e2e_conditions
mkdir -p "$OUT"
export HF_HOME="$NG/cache/huggingface"
export TMPDIR="$NG/tmp"
export PYTHONDONTWRITEBYTECODE=1
export VLLM_LOGGING_LEVEL=INFO
export VLLM_WSL2_ENABLE_PIN_MEMORY=1
export VLLM_USE_FLASHINFER_SAMPLER=0
export PYTHONHASHSEED=0
cd "$NG"
run_case() {
  name=$1; conc=$2; dmin=$3; dmax=$4; variant=$5
  dir="$OUT/$name"
  rm -rf "$dir"; mkdir -p "$dir"
  IPC=$(mktemp -d /tmp/${DATA_DIR:-./data}-vllm-ipc.XXXXXX)
  export VLLM_RPC_BASE_PATH="$IPC"
  export KILL_GATE_E2E_LOG_DIR="$dir"
  export KILL_GATE_E2E_PORT="$6"
  export KILL_GATE_CANCEL_DELAY_MIN="$dmin"
  export KILL_GATE_CANCEL_DELAY_MAX="$dmax"
  if [ "$variant" = "fixed" ]; then
    export PYTHONPATH="$NG/LMCache_fixed_e2e"
  else
    unset PYTHONPATH
  fi
  "$NG/.venv-gpu/bin/python" "$ROOT/post_review_completion/run_e2e_conditions.py" \
    --rounds 6 --concurrency "$conc" --gpu-memory-utilization 0.35 > "$dir/driver.log" 2>&1
  echo $? > "$dir/driver.exit"
  rm -rf "$IPC"
  sleep 5
}
run_case orig_c8_d5_300 8  0.005 0.300 original 8021
run_case orig_c32_d5_300 32 0.005 0.300 original 8022
run_case orig_c64_d0_30 64 0.000 0.030 original 8023
run_case orig_c64_d5_300 64 0.005 0.300 original 8024
run_case fixed_c64_d5_300 64 0.005 0.300 fixed 8025
echo DONE

