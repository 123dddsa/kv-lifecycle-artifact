# Example traces

All traces are JSONL lifecycle facts consumed by `kvc check` / `kvc audit`.

| file | source | notes |
|---|---|---|
| `normal_recv.jsonl` | hand-authored minimal | zero violations |
| `stale_send.jsonl` | hand-authored minimal | cross-step stale send |
| `duplicate_send.jsonl` | hand-authored minimal | duplicate send |
| `permanent_recv.jsonl` | hand-authored minimal | pending receive at quiescence |
| `delay_free.jsonl` | hand-authored minimal | delayed-free liveness |
| `scoped_children.jsonl` | hand-authored minimal | two children, one request |
| `vllm_0251_stale_send.jsonl` | **recorded** from the real controlled-I/O harness | vLLM 0.25.1 + LMCache 0.5.1; actions `START,IDLE,POLL,IDLE,ABORT,DELIVER,QUIESCE,POLL,DELIVER`; codes `I_COMPLETION_AFTER_FREE` |

## vLLM 0.31.0 fixture status

The vLLM 0.31.0 E2E run reproduces the scheduler assertion (`W2_VLLM031_RESULTS.md`),
but the component replay harness (`run_cross_connector.py`) pins the source
checkout to `gate0_lmcache_abort/vllm` (0.25.1). It cannot record a 0.31 component
trace without a separate harness port. This is an explicit pending item, not a
silently fabricated fixture.

The 0.31 evidence is therefore the E2E assertion log plus the W2 result table,
not a JSONL trace in this directory.
