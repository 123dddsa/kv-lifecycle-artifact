# 25-issue benchmark: quantitative coverage audit

Generated from `issues.json` (25 verified URLs, fetched 2026-11-17).

Detection means the kvc-lifecycle monitor can express and flag the violation with a witness trace; attribution means the report names the violated rule, the scoped operation, and (where applicable) the exact scheduler code. Local reproduction levels: LR = real components (GPU E2E or real connector/scheduler methods), FI = fault injection only, ER = external report only.

## Cluster-level audit

| Cluster | Category | Members | Evidence | Detection | Attribution | Local reproduction |
|---|---|---:|---|---|---|---|
| K1 | C1 completion-after-free | 10 | ER+LR | yes: C1 predicate + 6-action witness | exact code + scoped owner + replayable trace | LR: GPU E2E on two version pairs + recorded trace + component cells |
| K2 | C2 duplicate completion | 4 | ER+LR | yes: C2 predicate + same-step witness | exact code + recv/send separation | LR: real NIXL pull connector + real vLLM scheduler (controlled I/O); 65/200 monitor hits, 73 real assertions |
| K3 | C3 liveness (pending receive) | 2 | ER+FI | yes: C3 pending-at-quiescence + fairness bound | liveness obligation, no crash code | FI only: permanent PROC injected; 45/200 monitor hits, 0 real assertions |
| K4 | memory safety (release-before-quiescence) | 1 | ER | no: requires physical block reuse / DMA overlap, not observable lifecycle facts | none | ER only; no RDMA, no physical reclamation measurement |
| K5 | aggregation / child identity | 2 | ER+FI | yes: identity counting law (C2 by scoped key) | counting law + scoped identity | FI: controlled child schedules; 3/7/7/15 bare alerts, scoped 0 |
| K6 | quiescence (terminal finish per attempt) | 3 | ER | partial: C4 heuristic, audited not sound | C4 audit only | ER only; no SGLang runtime; adapter-level probe only |
| K7 | role legality (scheduler-role abort) | 3 | ER | no: role/initialization invariant, outside lifecycle contract | none | ER only; no scheduler/worker dual-role fixture |

## Issue-level audit

| Issue | Cluster | Type | Evidence | Upstream state | Detected | Attributed |
|---|---|---|---|---|---|---|
| LMCache#5937 | K1 | issue | ER | closed | yes | yes |
| LMCache#4938 | K1 | issue | ER | open | yes | yes |
| LMCache#4185 | K1 | issue | ER | closed | yes | yes |
| LMCache#4939 | K1 | pull | ER | open | yes | yes |
| LMCache#5938 | K1 | pull | ER | closed/merged | yes | yes |
| vLLM#43226 | K1 | issue | ER | open | yes | yes |
| vLLM#45628 | K1 | pull | ER | closed | yes | yes |
| vLLM#48616 | K1 | pull | ER | closed | yes | yes |
| vLLM#48821 | K1 | pull | ER | closed | yes | yes |
| vLLM#55286 | K1 | pull | ER | closed | yes | yes |
| vLLM#46240 | K2 | issue | ER | open | yes | yes |
| vLLM#56089 | K2 | pull | ER | open | yes | yes |
| vLLM#57938 | K2 | issue | ER | open | yes | yes |
| vLLM#58200 | K2 | pull | ER | closed | yes | yes |
| vLLM#59872 | K3 | issue | ER | open | yes | liveness only |
| vLLM#46289 | K3 | pull | ER | open | yes | liveness only |
| vLLM#60986 | K4 | issue | ER | open | no | no |
| vLLM#42831 | K5 | issue | ER | closed | yes | yes |
| vLLM#42841 | K5 | pull | ER | closed | yes | yes |
| SGLang#40360 | K6 | issue | ER | open | heuristic | audit only |
| SGLang#40334 | K6 | pull | ER | closed | heuristic | audit only |
| SGLang#40600 | K6 | pull | ER | closed | heuristic | audit only |
| LMCache#3688 | K7 | issue | ER | closed | no | no |
| LMCache#3499 | K7 | issue | ER | closed | no | no |
| LMCache#3340 | K7 | pull | ER | closed/merged | no | no |

## Summary

- 25 verified reports across 7 clusters (LMCache 8, vLLM 14, SGLang 3).
- **18/25 (72%) belong to the four clusters the contract can express** (K1 10, K2 4, K3 2, K5 2).
- **7/25 are outside the lifecycle contract** (K4 memory-safety, K6 SGLang quiescence, K7 role legality) and are labelled ER/outside scope, not counted as detections.
- Locally reproduced: 2 clusters (K1 GPU E2E on vLLM 0.25.1+LMCache 0.5.1 and vLLM 0.31.0+LMCache dev; K2 real NIXL connector + real scheduler under controlled I/O).
- Fault-injected only: K3 (permanent PROC) and K5 (child completion schedules); these prove oracle sensitivity, not natural occurrence.
- Not reproduced: K4, K6, K7 (no RDMA, no SGLang runtime, no dual-role fixture); the paper lists them as external reports and threats to validity.
- Attribution is exact (rule + scoped operation + code/trace) for K1/K2; identity-level for K5; liveness-level for K3; heuristic (C4) for K6; none for K4/K7.