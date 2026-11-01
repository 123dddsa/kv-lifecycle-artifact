# Experiment 5: statistics and offline overhead

## Independence and denominators

`rate_matrix.py` implements one **independent server process per repetition**; the denominators
below are process-level, not request-level.

| Condition | Crashes / independent processes | Rate (Wilson 95% CI) |
|---|---|---|
| A800 c=64 (W0) | 20/20 | 100.0% (83.9%-100.0%) |
| A800 c=1 (W1) | 20/20 | 100.0% (83.9%-100.0%) |
| A800 c=8 (W2) | 20/20 | 100.0% (83.9%-100.0%) |
| A800 c=64, 0-30 ms (W3) | 20/20 | 100.0% (83.9%-100.0%) |
| A800 8B c=64 (W6) | 12/12 | 100.0% (75.8%-100.0%) |
| A800 8B c=1 (W7) | 12/12 | 100.0% (75.8%-100.0%) |
| RTX 5090 c=64 | 12/12 | 100.0% (75.8%-100.0%) |

## Conditional rate vs natural incidence (kept separate)

- Conditional, cancellation-heavy: A800 c=64 **20/20 = 100.0%** (20 independent processes).
- Natural mixed load on 5090: **1/43 = 2.3%** (Wilson 95% CI 0.4%-12.1%);
  controls at p(cancel)=0: 5 trials, 0 crashes.

## Negative configurations retained

- Guard-negative on 5090: 8/8 runs without the target failure (6 rounds x 64 cancellations).
- Burst k<=4: 0/16 crashes; k>=24: 32/32 crashes.
- Delay windows at k=64: early, late and full all crash (4/4 each).
- Strict negative-control reports: 0/214; calibration right-censoring: 1/200 (1,200-cell) and 2/1000 (6,000-cell).
- W4/W5 guard attempts on A800 are excluded (environment failure `lmcache_server_start_failed`, not a target outcome).

## KS test

Removed from the paper and the calibration table: first-discovery counts are discrete with ties
and censoring, so a continuous-KS p-value is not meaningful (dual/PROC p=1.00 with large D is the
expected artefact). Reported quantities are medians, bootstrap CIs and candidate-level hit-rate
intervals; `data/scale_1000/REPORT.md` says this explicitly.

## Offline overhead (measured on CPU, this host)

- In-process monitor: **0.05 ms/check**, **20049 checks/s**, **100246 events/s** (1000 iterations of a 5-event trace).
- Peak Python memory for one check: **3.5 KB**.
- End-to-end CLI (`kvc check`): **229 ms**, dominated by Python startup.
- Trace storage: **355 bytes** for 5 events (**71 bytes/event**).

## Claims we deliberately do not make

- No online monitoring/TTFT/TPOT claim: the tool is an offline regression checker.
- No production incidence or MTBF claim: 1/43 is a harness measurement under mixed synthetic load.
- No distribution-equality claim (KS withdrawn).
