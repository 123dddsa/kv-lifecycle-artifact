#!/usr/bin/env bash
# Rate-estimation matrix on the rented GPU (A800). Every condition runs N
# independent server processes; rate_matrix.py records per-run summaries and
# computes the crash rate with a Wilson 95% CI.
set -u
V=${WORKDIR:-.}/venv025/bin/python
B=${WORKDIR:-.}
OUT=$B/results
mkdir -p "$OUT"
: > "$OUT/progress.txt"

run() {
  name=$1; variant=$2; conc=$3; dmin=$4; dmax=$5; reps=$6; rounds=$7
  echo "start $name $(date -u +%FT%TZ)" >> "$OUT/progress.txt"
  "$V" "$B/work/rate_matrix.py" \
    --variant "$variant" --concurrency "$conc" --dmin "$dmin" --dmax "$dmax" \
    --reps "$reps" --rounds "$rounds" --outdir "$OUT/$name" >> "$OUT/$name.log" 2>&1
  echo "done $name exit=$? $(date -u +%FT%TZ)" >> "$OUT/progress.txt"
}

# Original (unfixed) stack: crash rate vs concurrency and cancel timing.
run W0_orig_c64_5-300  original 64 0.005 0.300 20 6
run W1_orig_c1_5-300   original 1  0.005 0.300 20 6
run W2_orig_c8_5-300   original 8  0.005 0.300 20 6
run W3_orig_c64_0-30   original 64 0.000 0.030 20 6
# Guarded (fixed) stack at two conditions: negative rate.
run W4_fixed_c64_5-300 fixed    64 0.005 0.300 15 6
run W5_fixed_c64_0-30  fixed    64 0.000 0.030 15 6

echo "ALL_DONE $(date -u +%FT%TZ)" >> "$OUT/progress.txt"

