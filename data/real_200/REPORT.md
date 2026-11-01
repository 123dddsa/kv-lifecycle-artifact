# External calibration: 200 fresh real-component cells per target

Real LMCache/vLLM connector/scheduler methods with controlled transfer I/O; fresh seeds 20..219.
No regression; prediction is the geometric median implied by exact DP q10.

| target | q10 | predicted median | observed median (95% CI) | ratio | median tail p | KS vs geometric(q), p |
|---|---:|---:|---|---:|---:|---|
| stale_send | 0.027920 | 25 | 26.5 (22.0-32.0) | 0.94 | 0.591 | 0.560 |
| dual_completion | 0.375537 | 2 | 2.0 (2.0-3.0) | 1.00 | 1.000 | 1.000 |
| permanent_proc | 0.225931 | 3 | 3.0 (2.0-3.0) | 1.00 | 1.000 | 1.000 |

| target | candidates | hits | empirical q (Wilson 95%) | median implied by empirical q |
|---|---:|---:|---|---:|
| stale_send | 6962 | 199 | 0.0286 (0.0249-0.0328) | 24 |
| dual_completion | 546 | 200 | 0.3663 (0.3270-0.4075) | 2 |
| permanent_proc | 852 | 200 | 0.2347 (0.2075-0.2644) | 3 |

Reading:
- If the observed median returns to the predicted value and the KS p-value is not small, the
  exact model is externally calibrated on real components rather than only internally consistent.
- If the observed median remains at the old value, the model is rejected at this sample size;
  the candidate-level empirical q then gives the model-free geometric cost and identifies the
  direction of the discrepancy (real action distribution vs abstract legal-action distribution).
- CIs, tail p and KS p describe this fixed controlled harness, not production incidence.
