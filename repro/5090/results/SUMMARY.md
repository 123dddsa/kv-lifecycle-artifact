# 5090 results summary (2026-11-18 22:20 → 2026-11-19 03:10)

Host: RTX 5090 32GB, driver 595.71.05, Ubuntu 22.04, vLLM 0.25.1 + LMCache 0.5.1
on sm_120 (torch 2.11.0+cu130). Model: Qwen3-0.6B via ModelScope snapshot.

Raw files in this directory: `status.txt`, `guard_rows.jsonl`,
`incidence_rows.jsonl`, `burst_rows.jsonl`, `sweep_rows.jsonl`,
`W0_5090_rate_results.json`, `W0_5090_rate_rows.csv`.

## 1. Smoke (stack validation)

`SMOKE_RESULT rc=10 target_assertion=true` on the first cancellation round:
vLLM 0.25.1 + LMCache 0.5.1 work on Blackwell and the target assertion
reproduces.

## 2. Guard overlay (negative control) — 8/8 negative

| trial | exit | target_assertion | rounds completed |
|---|---:|---|---:|
| 1-8 | 0 | false | 6/6 (64 cancels per round) |

The two-file overlay (`guard_overlay.sh apply`) removes the target failure while
the same workload completes; restored afterwards (`restore`).

## 3. Cross-hardware rate (W0-style, c=64, cancel 5-300ms)

| reps | crashes | rate | Wilson 95% CI | median wall |
|---:|---:|---:|---|---:|
| 12 | 12 | 100% | 75.8-100% | 22.2s |

Combined with A800 (20/20, CI 83.9-100%): the conditional trigger rate is
hardware-independent.

## 4. Mixed-load incidence (43 trials, 0/0.1/0.5/1/5% cancel probability)

| config | trials | crashes | mean requests sent |
|---|---:|---:|---:|
| control_p0 (0%) | 5 | 0 | 320 |
| p0001 (0.1%) | 10 | 0 | 326 |
| p0005 (0.5%) | 10 | 0 | 320 |
| p001 (1%) | 10 | 0 | 320 |
| p005 (5%) | 8 | 1 (at 128 requests, 4 cancels) | 240 |

Only 1/43 mixed-load trials crashed: sparse random cancellations rarely enter
the vulnerable state.

## 5. Burst-size trigger law (concurrency 64, 3 rounds per trial)

| simultaneous in-flight cancellations k | trials | crashes | trigger rate |
|---:|---:|---:|---:|
| 1 | 8 | 0 | 0% |
| 4 | 8 | 0 | 0% |
| 16 | 8 | 1 | 12.5% |
| 24 | 4 | 4 | 100% |
| 32 | 4 | 4 | 100% |
| 48 | 4 | 4 | 100% |
| 64 | 8 | 8 | 100% |

## 6. Cancel-delay window at k=64

| window | trials | crashes |
|---|---:|---:|
| early 5-50ms | 4 | 4/4 |
| late 150-300ms | 4 | 4/4 |
| full 5-300ms | 4 | 4/4 |

The delay window is irrelevant: cancelling immediately after the first token is
as effective as cancelling late. The controlling variable is the size of the
simultaneous cancellation burst.

## 7. Combined trigger statement

> The completion-after-free race is a thundering-herd phenomenon: with 64
> in-flight requests, cancelling <=4 never triggered it (0/16; 95% upper bound
> 19%), k=16 triggered it occasionally (1/8 = 12.5%, CI 2.2-47.1%), and k>=24
> triggered it in every repetition (32/32 pooled across k=24/32/48/64 and the
> three delay windows; Wilson 95% CI 89.3-100%; k=24 vs k=16 Fisher exact
> p=0.010). The transition is bracketed between 16 and 24: k=17-23 were not
> tested, so no exact threshold is claimed. At k=64 the cancellation delay
> within 5-300ms does not matter (12/12, CI 75.8-100%).

