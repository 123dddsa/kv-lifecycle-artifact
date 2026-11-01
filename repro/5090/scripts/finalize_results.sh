#!/usr/bin/env bash
# Package the A800 experiment results (small files only) for pulling before the
# instance auto-shuts-down at 02:00 local.
set -u
B=${WORKDIR:-.}
OUT=$B/results_final
rm -rf "$OUT"; mkdir -p "$OUT"
cp -f "$B/results/progress.txt" "$OUT/" 2>/dev/null
cp -f "$B/results/queue.log" "$OUT/" 2>/dev/null
cp -f "$B/results/matrix_driver.log" "$OUT/" 2>/dev/null
cp -f "$B/results/queue_driver.log" "$OUT/" 2>/dev/null
for d in "$B"/results/W*_*/ "$B"/results/SMOKE/; do
  name=$(basename "$d")
  mkdir -p "$OUT/$name"
  cp -f "$d/rate_results.json" "$OUT/$name/" 2>/dev/null
  cp -f "$d/rate_rows.csv" "$OUT/$name/" 2>/dev/null
  cp -f "$d/rate_*.log" "$OUT/$name/" 2>/dev/null
done
# per-run files that matter for audit: rates rows + config, skip huge driver logs
cp -f "$B/results/incidence/incidence_rows.jsonl" "$OUT/incidence_rows.jsonl" 2>/dev/null
cp -rf "$B/results/incidence" "$OUT/incidence" 2>/dev/null
cp -rf "$B/results/guard_overlay" "$OUT/guard_overlay" 2>/dev/null
cp -rf "$B/results/burst" "$OUT/burst" 2>/dev/null
tar -czf "$B/results_final.tar.gz" -C "$B" results_final
du -sh "$B/results_final.tar.gz"
echo "FINALIZE_DONE $(date -u +%FT%TZ)"



