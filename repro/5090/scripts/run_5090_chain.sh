#!/usr/bin/env bash
# 5090 overnight chain: guard overlay trials -> incidence matrix -> finalize.
set -u
B=${WORKDIR:-.}
M=$B/hf_ms/models/Qwen--Qwen3-0.6B/snapshots/master
export KVC_MODEL=$M
export HF_ENDPOINT=https://hf-mirror.com
STATUS=$B/work/status.txt

echo "CHAIN_START $(date -u +%FT%TZ)" >> "$STATUS"
sed -i "s/2026-11-17 18:00:00/2026-11-18 18:00:00/" "$B/work/run_guard_overlay.sh" 2>/dev/null
bash "$B/work/run_guard_overlay.sh" >> "$B/results/guard_5090.log" 2>&1
echo "GUARD_DONE $(date -u +%FT%TZ)" >> "$STATUS"
bash "$B/work/run_incidence_matrix.sh" >> "$B/results/incidence_5090.log" 2>&1
echo "INCIDENCE_DONE $(date -u +%FT%TZ)" >> "$STATUS"
bash "$B/work/finalize_results.sh" >> "$B/results/finalize_5090.log" 2>&1
echo "CHAIN_DONE $(date -u +%FT%TZ)" >> "$STATUS"

