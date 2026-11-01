# kvc-lifecycle

A small, contract-first checker for **asynchronous KV-cache transfer completion** in
LLM serving systems (vLLM / LMCache / NIXL / SGLang-style connectors).

The checker consumes only public lifecycle facts:

- `request_finished(request_id, delay_free)`
- `free(request_id)`
- `observe(sending, recving)`
- `quiescence(pending_recvs, delay_free_drained)`

and reports violations such as `I_COMPLETION_AFTER_FREE`, `I_SEND_DUPLICATE`,
`I_RECV_DUPLICATE`, `I_SEND_NOT_FINISHED`, `I_ABORTED_DUAL_COMPLETION`,
`I_DELAY_FREE_NEVER_COMPLETED`, `I_RECV_NEVER_COMPLETED`, `I_FREE_DUPLICATE`.

> The package is deliberately small: no GPU, no upstream forks, no network.
> Adapters, rarity search, and oracle auditing are included as separate modules.

## Install

```bash
pip install -e .
```

Python 3.10+. No runtime dependencies.

## Quickstart

```bash
kvc check examples/stale_send.jsonl
```

Text output:

```text
trace: examples/stale_send.jsonl
events: 4
violations: 1
  [I_COMPLETION_AFTER_FREE] r step=2 completion after free at step 1
FAIL
```

Machine-readable:

```bash
kvc check examples/stale_send.jsonl --format json --report report.json
```

Exit code is `1` when violations are found (use `--no-fail` to always exit `0`).

## Trace format

One JSON object per line. `step` is optional and only informational; the monitor
numbers `observe` batches itself.

```json
{"event": "request_finished", "request_id": "r", "delay_free": false}
{"event": "observe", "sending": [], "recving": ["r"]}
{"event": "free", "request_id": "r"}
{"event": "observe", "sending": ["r"], "recving": []}
{"event": "quiescence", "pending_recvs": [], "delay_free_drained": true}
```

Supported events:

| event | fields |
|---|---|
| `request_finished` | `request_id`, `delay_free` (default false) |
| `free` | `request_id` |
| `observe` | `sending` list, `recving` list |
| `quiescence` | `pending_recvs` list, `delay_free_drained` (default true) |

## Golden examples

- `examples/normal_recv.jsonl` — normal receive, zero violations
- `examples/stale_send.jsonl` — cross-step stale send, `I_COMPLETION_AFTER_FREE`
- `examples/duplicate_send.jsonl` — duplicate completion, `I_SEND_DUPLICATE`
- `examples/permanent_recv.jsonl` — pending receive at quiescence, `I_RECV_NEVER_COMPLETED`

## Scoped identity

Completion identity is `(child, request, attempt, direction)`. The
`--identity-scope` option selects how much of that tuple identifies an
operation:

- `child_request_attempt` (default): children and attempts are distinct.
- `request_attempt`: attempts are distinct.
- `request`: legacy request-level identity; `k` children/attempts sharing one
  request produce `k-1` duplicate alerts.

```bash
kvc check examples/scoped_children.jsonl --identity-scope request            # FAIL: I_SEND_DUPLICATE
kvc check examples/scoped_children.jsonl --identity-scope child_request_attempt  # PASS
```

The same trace can express scoped operations in `sending`/`recving`/
`pending_recvs` as objects:

```json
{"event": "observe", "sending": [{"request_id": "r", "child": "c1", "attempt": 0}], "recving": []}
```

## Replay/search on the real controlled-I/O harness

The optional `vllm-lmcache` adapter drives the real LMCache/vLLM component
replayer. It requires a checkout containing `replay_real_traces.py` and the
matching source vLLM environment (no GPU E2E; controlled transfer I/O).

```bash
export KVC_NOVELTY_ROOT=/path/to/<LOCAL_WORKSPACE>

# Random search: fresh real components per schedule
kvc search --target stale_send --budget 200 --seeds 1 --max-steps 10

# Replay a witness through the real scheduler/connector methods
kvc replay --target stale_send \
  --actions START,IDLE,POLL,IDLE,ABORT,DELIVER,QUIESCE,POLL,DELIVER
```

The replay exits `1` when the target code is observed. Both commands emit JSON
with `--format json`; the adapter is created fresh per candidate, so a failed
candidate never contaminates the next one.

Record a replay as a JSONL trace (the resulting trace can be checked offline):

```bash
kvc record --target stale_send \
  --actions START,IDLE,POLL,IDLE,ABORT,DELIVER,QUIESCE,POLL,DELIVER \
  --out examples/vllm_0251_stale_send.jsonl
```

Directed search follows a target-conditioned witness prefix when legal:

```bash
kvc search --target stale_send --method directed --seeds 0 --budget 10
```

## Oracle audit (M3, minimal)

`kvc audit` re-evaluates the same trace under a finite assumption space:
identity scope (`request`, `request_attempt`, `child_request_attempt`) and the
delayed-free drain gate (`true`, `false`). It reports whether the verdict is
sensitive to those assumptions and where the conflict is.

```bash
kvc audit examples/scoped_children.jsonl
kvc audit examples/delay_free.jsonl --fail-on-conflict
```

The output is a variant table plus `verdict: assumption-sensitive|assumption-stable`,
`conflict`, `sensitive`, and an `input_digest`. Axes: identity scope, delayed-free
drain gate, and a fairness poll bound (`--fairness-bounds 0,3`). This is
assumption sensitivity, not a full proof of monitor soundness; aggregation and
delivery-mode enumeration are the next slice.

## Exact cost model (M4)

`kvc cost` computes the exact hitting probability `q_H` by exhaustive DP over
uniform-random legal actions, and the implied geometric discovery cost:

```bash
kvc cost --target stale_send --horizon 10
kvc cost --target stale_send --wait 8 --horizon 30
```

Reported fields: `q`, `median_schedules`, `q1/q3`, expected actions per
candidate, and `reachable`. `q=0` is reported as horizon-unreachable, never
smoothed. `--delivery merged` evaluates the POLL/DELIVER-merged counterfactual:
stale send becomes unreachable (`q=0`), dual completion stays reachable, and
permanent PROC is unchanged.

## Aggregation audit (M6)

`kvc aggregate` compares aggregate-only and child-scoped quorum oracles on the
same child schedule:

```bash
kvc aggregate examples/aggregation_duplicate.json --fail-on-conflict
```

It reports the derived aggregate outputs, children seen by poll, legacy/strict
codes, `premature` (`I_PREMATURE_AGGREGATE`), and `conflict`. This is the E3
aggregation slice; it is separate from the raw trace monitor because the
aggregate stream is a derived view.

## pytest plugin

Installing the package exposes a `pytest11` entry point:

```bash
pip install -e ".[dev]"
pytest --kvc-trace examples/normal_recv.jsonl
pytest --kvc-trace examples/normal_recv.jsonl \
       --kvc-trace examples/duplicate_send.jsonl \
       --kvc-audit
```

Options: `--kvc-trace` (repeatable), `--kvc-identity-scope`, `--kvc-audit`,
`--kvc-fail-on-violation`. The session exits non-zero when a trace violates the
contract and `--kvc-fail-on-violation` is set. A `kvc_check(path, scope)` fixture
is also available for ordinary test functions.

## Design boundaries

- The monitor is connector-independent; scoped identity and the real
  vLLM/LMCache adapter are implemented in this package.
- `quiescence(delay_free_drained=False)` suppresses only the delayed-free
  verdict; pending receives keep their independent bounded-liveness check.
- The monitor is an oracle, not a scheduler patch: it can be wrong if the
  connector hides facts or if the fairness assumptions do not hold.
