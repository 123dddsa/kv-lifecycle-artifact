# Experiments 3-5: outputs and how to use them

Generated 2026-11-19 by `build_345.py` (CPU only, from existing raw evidence).

## Files

```
baseline_comparison/REPORT.md   experiment 3: fair baseline matrix
baseline_comparison/baseline.json
ablation/REPORT.md              experiment 4: component-removal table
ablation/ablation.json
stats_overhead/REPORT.md        experiment 5: process-level statistics + offline overhead
stats_overhead/stats.json
```

## Headline numbers

**Experiment 3 (baseline).** Native assertions: failure detected only after crash (20/20 E2E,
78/200 candidate assertions, no attribution, no witness). Request/response test: no pre-failure
signal. Request-level monitor: finds C1 (7/200) but produces duplicate false positives in
4/4 identity cells (alerts 3/7/7/15 vs 0 scoped). Aggregate-only: 0/2 planted defects. Full
method: 7/200 target witnesses, 7/7 attributed, 0/214 strict false positives; merged observation
loses the target witness (0/200) while 74/200 assertions persist. GRIEF: crash reached at
iteration 53 (~8 min), 0/1 attributed, 0/1 minimized; not an equal-budget row.

**Experiment 4 (ablation).** Removing separation loses the target witness; removing scoped
identity reintroduces duplicate false positives; removing the child dimension leaves fan-out
collisions; removing child-scoped aggregation loses 2/2 planted defects; removing the coupled
guard lets all 3/3 single-factor variants crash; removing the drain gate makes delay-free traces
ambiguous. Random vs directed changes only cost (median 26.5 vs 1 schedule; 200/200 directed
one-shot), not the verdict.

**Experiment 5 (statistics/overhead).** Every repetition in the rate matrices is an independent
server process: A800 20/20 at c=64/c=1/c=8 and 20/20 at 0-30 ms; 8B 12/12 at c=64 and c=1;
5090 12/12. Conditional rate 100% (83.9-100%) vs natural mixed load 1/43 = 2.3% (0.4-12.1%),
kept separate. Negative configurations retained: guard 8/8 negative, burst k<=4 0/16, k>=24
32/32, delay windows 4/4 each. Offline overhead: 0.06 ms/check in-process, ~279 ms end-to-end
CLI (startup-dominated), 3.5 KB peak Python memory, 71 bytes/event trace storage. KS is withdrawn
(discrete support).

## What still needs a decision

- Whether to add Table IV-bis (baseline matrix) to the 10-page paper, replacing weaker prose;
  the ablation table can be an appendix/artifact table rather than main text.
- The GRIEF row must stay a feasibility note, not a detection-rate competitor.
- Experiment 5's process-level statement should replace any "independent requests" phrasing in §7.
