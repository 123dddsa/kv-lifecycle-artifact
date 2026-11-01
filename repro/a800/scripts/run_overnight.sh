#!/usr/bin/env bash
# Single overnight chain for the A800 (no waiters, no races):
#   1) W6/W7: Qwen3-8B rate estimation (12 reps each)
#   2) incidence matrix (5 configs, 43 trials)
#   3) guarded-stack overlay trials (the W4/W5 replacement, time-boxed)
#   4) W8 extra rate condition if >= 12 minutes remain
#   5) finalize results
set -u
B=${WORKDIR:-.}
V=$B/venv025/bin/python
OUT=$B/results
SHUTDOWN_UTC='2026-11-17 18:00:00'

echo "overnight start $(date -u +%FT%TZ)" >> "$OUT/overnight.log"

"$V" "$B/work/rate_matrix.py" --variant original --model Qwen/Qwen3-8B --hf-home "$B/hf8b" \
  --concurrency 64 --dmin 0.005 --dmax 0.300 --reps 12 --rounds 6 \
  --outdir "$OUT/W6_8b_c64_5-300" >> "$OUT/W6_8b_c64_5-300.log" 2>&1
echo "W6 exit=$? $(date -u +%FT%TZ)" >> "$OUT/overnight.log"

"$V" "$B/work/rate_matrix.py" --variant original --model Qwen/Qwen3-8B --hf-home "$B/hf8b" \
  --concurrency 1 --dmin 0.005 --dmax 0.300 --reps 12 --rounds 6 \
  --outdir "$OUT/W7_8b_c1_5-300" >> "$OUT/W7_8b_c1_5-300.log" 2>&1
echo "W7 exit=$? $(date -u +%FT%TZ)" >> "$OUT/overnight.log"

bash "$B/work/run_incidence_matrix.sh" >> "$OUT/incidence_chain.log" 2>&1
echo "incidence exit=$? $(date -u +%FT%TZ)" >> "$OUT/overnight.log"

bash "$B/work/run_guard_overlay.sh" >> "$OUT/guard_chain.log" 2>&1
echo "guard exit=$? $(date -u +%FT%TZ)" >> "$OUT/overnight.log"

now=$(date -u +%s)
shutdown=$(date -u -d "$SHUTDOWN_UTC" +%s 2>/dev/null || echo 0)
remaining=$((shutdown - now))
echo "remaining_before_W8=$remaining" >> "$OUT/overnight.log"
if [ "$remaining" -gt 720 ]; then
  "$V" "$B/work/rate_matrix.py" --variant original --concurrency 32 --dmin 0.005 --dmax 0.300 \
    --reps 12 --rounds 6 --outdir "$OUT/W8_orig_c32_5-300" >> "$OUT/W8_orig_c32_5-300.log" 2>&1
  echo "W8 exit=$? $(date -u +%FT%TZ)" >> "$OUT/overnight.log"
else
  echo "skipped W8 (remaining=$remaining)" >> "$OUT/overnight.log"
fi

bash "$B/work/finalize_results.sh" >> "$OUT/finalize_overnight.log" 2>&1
echo "OVERNIGHT_DONE $(date -u +%FT%TZ)" >> "$OUT/overnight.log"

