#!/usr/bin/env bash
# GRIEF same-stack baseline campaign against vLLM 0.25.1 + LMCache 0.5.1 (original, unguarded stack).
# Starts the unchanged service stack via run_e2e_conditions.py --server-only, waits for readiness,
# then runs a GRIEF campaign against it and records server/GRIEF outcome.
set -u
ROOT=${EXPERIMENT_DATA:-.}
NG=$ROOT/${LOCAL_WORKSPACE:-.}
WS=${REPO_ROOT:-.}
GW=$WS/evidence/grief_baseline
ITERS=${1:-100}
TAG=${2:-run}
OUT=$GW/campaign_${TAG}_$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT/server" "$OUT/grief_findings" "$OUT/grief_corpus"

export HF_HOME=$NG/cache/huggingface
export HF_ENDPOINT=${HF_ENDPOINT:-https://hf-mirror.com}
export TMPDIR=$NG/tmp
export PYTHONHASHSEED=0
export VLLM_WSL2_ENABLE_PIN_MEMORY=1
export VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_LOGGING_LEVEL=INFO
export PYTHONDONTWRITEBYTECODE=1
cd "$NG"

PORT=${GRIEF_CAMPAIGN_PORT:-8051}
IPC=$(mktemp -d /tmp/${DATA_DIR:-./data}-vllm-ipc.XXXXXX)
export VLLM_RPC_BASE_PATH=$IPC
export KILL_GATE_E2E_LOG_DIR=$OUT/server
export KILL_GATE_E2E_PORT=$PORT
unset PYTHONPATH

echo "campaign=$OUT port=$PORT iters=$ITERS" | tee "$OUT/campaign_info.txt"
"$NG/.venv-gpu/bin/python" "$ROOT/post_review_completion/run_e2e_conditions.py" \
  --server-only --concurrency 64 > "$OUT/server_driver.log" 2>&1 &
SERVER_PID=$!
cleanup() {
  kill -INT "$SERVER_PID" 2>/dev/null || true
  sleep 8
  kill -9 "$SERVER_PID" 2>/dev/null || true
  rm -rf "$IPC"
}
trap cleanup EXIT

# Wait for the server-ready marker (the driver emits server_only_ready after /v1/models is healthy).
for i in $(seq 1 300); do
  grep -q 'server_only_ready' "$OUT/server_driver.log" 2>/dev/null && break
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "server_driver_died" | tee -a "$OUT/campaign_info.txt"
    exit 20
  fi
  sleep 2
done
if ! grep -q 'server_only_ready' "$OUT/server_driver.log" 2>/dev/null; then
  echo "server_ready_timeout" | tee -a "$OUT/campaign_info.txt"
  exit 21
fi
echo "server_ready" | tee -a "$OUT/campaign_info.txt"

# GRIEF campaign: same stack, its own timed-trace corpus and crash/hang/perf/corruption oracles.
"$GW/.venv/bin/grief" run \
  --base-url "http://127.0.0.1:$PORT" \
  --max-iterations "$ITERS" \
  --no-minimize \
  --findings-dir "$OUT/grief_findings" \
  --corpus-dir "$OUT/grief_corpus" \
  --request-timeout-s 120 \
  --verbose > "$OUT/grief_run.log" 2>&1
echo "grief_exit=$?" > "$OUT/grief.exit"

# Did the server survive / did it hit the target assertion?
if kill -0 "$SERVER_PID" 2>/dev/null; then
  echo "server_alive_after_grief" >> "$OUT/server_status.txt"
else
  echo "server_dead_after_grief" >> "$OUT/server_status.txt"
fi
if grep -rq 'assert req_id in self.requests' "$OUT/server" 2>/dev/null; then
  echo "target_assertion_present" >> "$OUT/server_status.txt"
else
  echo "no_target_assertion" >> "$OUT/server_status.txt"
fi
tail -5 "$OUT/server_driver.log" >> "$OUT/campaign_info.txt"
echo "DONE $OUT"


