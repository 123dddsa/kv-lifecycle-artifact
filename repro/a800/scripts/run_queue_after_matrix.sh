#!/usr/bin/env bash
# After the main rate matrix finishes, continue the A800 queue unattended:
#   1) Qwen3-8B model-scale rate estimation at c=64 and c=1
#   2) stop and report
set -u
V=${WORKDIR:-.}/venv025/bin/python
B=${WORKDIR:-.}
OUT=$B/results
mkdir -p "$OUT"
: > "$OUT/queue.log"

echo "queue started $(date -u +%FT%TZ)" >> "$OUT/queue.log"
# wait for the matrix driver to finish
while ! grep -q 'ALL_DONE' "$OUT/progress.txt" 2>/dev/null; do
  sleep 60
done
echo "matrix done, starting 8B $(date -u +%FT%TZ)" >> "$OUT/queue.log"

run() {
  name=$1; conc=$2; reps=$3
  echo "start $name $(date -u +%FT%TZ)" >> "$OUT/queue.log"
  "$V" "$B/work/rate_matrix.py" \
    --variant original --model Qwen/Qwen3-8B --hf-home ${WORKDIR:-.}/hf8b \
    --concurrency "$conc" --dmin 0.005 --dmax 0.300 \
    --reps "$reps" --rounds 6 --outdir "$OUT/$name" >> "$OUT/$name.log" 2>&1
  echo "done $name exit=$? $(date -u +%FT%TZ)" >> "$OUT/queue.log"
}

run W6_8b_c64_5-300 64 15
run W7_8b_c1_5-300  1  15

echo "QUEUE_DONE $(date -u +%FT%TZ)" >> "$OUT/queue.log"

