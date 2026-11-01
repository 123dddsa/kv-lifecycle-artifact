# Paired counterfactual replay (model-level)

Input: 200 `stale_send` action sequences recorded under separated semantics.
For each sequence, the separated model executes all actions; the merged model executes the same
sequence with each DELIVER collapsed into the preceding POLL (DELIVER skipped, by definition).

| Metric | Value |
|---|---:|
| Sequences | 200 |
| Separated witnesses | 7 |
| Merged witnesses | 0 |
| Scheduler assertions on the same records | 78 |
| Same-trace verdict flips | 7 |
| Merged replay errors | 0 |
| Separated replay errors | 0 |

Representative seed 129:

```
START POLL ABORT DELIVER POLL QUIESCE POLL DELIVER
```

The separated monitor reports C1 at the DELIVER after ABORT; under merged semantics the completion
is consumed at the POLL, so the held completion and the later delivery are not separate records.
The original run still records a real scheduler assertion.

This is a model-level counterfactual replay, not a new real-component execution.
