"""Command line interface for kvc-lifecycle (M2: check/replay/search)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import TOOL_VERSION
from .adapters import make_adapter
from .adapters.vllm_lmcache import TARGET_CODES
from .aggregation import audit_aggregation, load_schedules
from .audit import audit_file
from .core.monitor import ContractMonitor
from .core.trace import TraceError, load_trace
from .cost import TARGETS as COST_TARGETS
from .cost import predict
from .search import replay_actions, run_random_seeds

CODES = [
    "I_COMPLETION_AFTER_FREE",
    "I_SEND_NOT_FINISHED",
    "I_SEND_DUPLICATE",
    "I_RECV_DUPLICATE",
    "I_ABORTED_DUAL_COMPLETION",
    "I_DELAY_FREE_NEVER_COMPLETED",
    "I_RECV_NEVER_COMPLETED",
    "I_FREE_DUPLICATE",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kvc",
        description="Contract-first checks for asynchronous KV-cache transfer completion.",
    )
    parser.add_argument("--version", action="version", version=f"kvc-lifecycle {TOOL_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="check one JSONL trace against the lifecycle contract")
    check.add_argument("trace", help="path to a JSONL trace")
    check.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    check.add_argument("--report", help="also write the JSON report to this path")
    check.add_argument(
        "--identity-scope",
        choices=("request", "request_attempt", "child_request_attempt"),
        default="child_request_attempt",
        help="how much of (child, request, attempt) identifies a completion",
    )
    check.add_argument(
        "--no-fail",
        action="store_true",
        help="exit 0 even when violations are found",
    )

    sub.add_parser("codes", help="list violation codes")
    sub.add_parser("version", help="print the tool version")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--adapter",
        default="vllm-lmcache",
        help="adapter name (default: vllm-lmcache)",
    )
    common.add_argument(
        "--root",
        default=os.environ.get("KVC_NOVELTY_ROOT"),
        help="research harness checkout (or KVC_NOVELTY_ROOT)",
    )
    common.add_argument("--target", required=True, choices=sorted(TARGET_CODES))
    common.add_argument("--format", choices=("text", "json"), default="text")

    replay = sub.add_parser("replay", parents=[common], help="replay one action list")
    replay.add_argument(
        "--actions",
        required=True,
        help="comma-separated actions, e.g. START,POLL,DELIVER",
    )

    record = sub.add_parser(
        "record", parents=[common], help="record a replay as a JSONL trace"
    )
    record.add_argument("--actions", required=True, help="comma-separated actions")
    record.add_argument("--out", required=True, help="output JSONL path")

    search = sub.add_parser(
        "search", parents=[common], help="random search for a target witness"
    )
    search.add_argument("--seeds", default="0", help="comma-separated seeds (default: 0)")
    search.add_argument("--budget", type=int, default=200, help="schedules per seed")
    search.add_argument("--max-steps", type=int, default=10, help="actions per schedule")
    search.add_argument(
        "--method",
        choices=("random", "directed"),
        default="random",
        help="search policy (default: random)",
    )
    search.add_argument(
        "--require-found",
        action="store_true",
        help="exit 1 if no seed finds the target",
    )

    audit = sub.add_parser(
        "audit", help="re-evaluate one trace under a finite assumption space"
    )
    audit.add_argument("trace")
    audit.add_argument(
        "--identity-scopes",
        default="request,request_attempt,child_request_attempt",
        help="comma-separated identity scopes",
    )
    audit.add_argument(
        "--drain-gates",
        default="true,false",
        help="comma-separated delayed-free drain gates",
    )
    audit.add_argument(
        "--fairness-bounds",
        default="0,3",
        help="comma-separated poll bounds before quiescence is evaluated",
    )
    audit.add_argument("--format", choices=("text", "json"), default="text")
    audit.add_argument("--report", help="also write the JSON report to this path")
    audit.add_argument(
        "--fail-on-conflict",
        action="store_true",
        help="exit 1 when assumptions change the verdict",
    )

    cost = sub.add_parser(
        "cost", help="exact rarity prediction and geometric discovery cost"
    )
    cost.add_argument("--target", required=True, choices=sorted(COST_TARGETS))
    cost.add_argument("--wait", type=int, default=0, help="delivery wait (default: 0)")
    cost.add_argument("--horizon", type=int, default=10, help="DP horizon (default: 10)")
    cost.add_argument(
        "--delivery",
        choices=("separated", "merged"),
        default="separated",
        help="POLL/DELIVER semantics (default: separated)",
    )
    cost.add_argument("--format", choices=("text", "json"), default="text")

    aggregate = sub.add_parser(
        "aggregate", help="compare aggregate-only and child-scoped quorum oracles"
    )
    aggregate.add_argument("input", help="JSON file with a `schedules` object")
    aggregate.add_argument("--format", choices=("text", "json"), default="text")
    aggregate.add_argument(
        "--fail-on-conflict",
        action="store_true",
        help="exit 1 when the two oracles disagree",
    )
    return parser


def _check(args: argparse.Namespace) -> int:
    try:
        events = load_trace(args.trace)
    except TraceError as exc:
        print(f"kvc: {exc}", file=sys.stderr)
        return 2

    monitor = ContractMonitor(args.identity_scope).run(events)
    report: dict[str, Any] = {
        "tool": "kvc-lifecycle",
        "version": TOOL_VERSION,
        "trace": str(args.trace),
        "event_count": len(events),
        **monitor.report(),
    }

    if args.report:
        Path(args.report).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"trace: {args.trace}")
        print(f"events: {len(events)}")
        print(f"violations: {report['violation_count']}")
        for item in report["violations"]:
            print(
                f"  [{item['code']}] {item['request_id']} "
                f"step={item['step']} {item['detail']}"
            )
        print("PASS" if report["pass"] else "FAIL")

    if report["pass"] or args.no_fail:
        return 0
    return 1


def _adapter_factory(args: argparse.Namespace):
    def factory(replay_id: str):
        return make_adapter(
            args.adapter,
            root=args.root,
            target=args.target,
            replay_id=replay_id,
        )

    return factory


def _replay(args: argparse.Namespace) -> int:
    actions = [item.strip() for item in args.actions.split(",") if item.strip()]
    try:
        adapter = make_adapter(
            args.adapter,
            root=args.root,
            target=args.target,
            replay_id="cli:replay",
        )
        result = replay_actions(adapter, actions)
        codes = adapter.codes()
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"kvc: {exc}", file=sys.stderr)
        return 2
    finally:
        try:
            adapter.close()  # type: ignore[possibly-undefined]
        except Exception:
            pass

    payload: dict[str, Any] = {
        "tool": "kvc-lifecycle",
        "version": TOOL_VERSION,
        "mode": "replay",
        "adapter": args.adapter,
        "target": args.target,
        "actions": actions,
        "codes": codes,
        "target_code": TARGET_CODES[args.target],
        "result": result,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print(f"target: {args.target}")
        print(f"actions: {','.join(actions)}")
        print(f"codes: {','.join(codes) if codes else '(none)'}")
        print(f"scheduler_assertion: {result.get('scheduler_assertion')}")
        print(f"scheduler_owns_request: {result.get('scheduler_owns_request')}")
    return 1 if TARGET_CODES[args.target] in codes else 0


def _search(args: argparse.Namespace) -> int:
    try:
        seeds = [int(item) for item in args.seeds.split(",") if item.strip()]
    except ValueError:
        print("kvc: --seeds must be comma-separated integers", file=sys.stderr)
        return 2
    try:
        results = run_random_seeds(
            _adapter_factory(args),
            target_code=TARGET_CODES[args.target],
            seeds=seeds,
            budget=args.budget,
            max_steps=args.max_steps,
            method=args.method,
            target=args.target,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"kvc: {exc}", file=sys.stderr)
        return 2

    payload = {
        "tool": "kvc-lifecycle",
        "version": TOOL_VERSION,
        "mode": "search",
        "adapter": args.adapter,
        "target": args.target,
        "target_code": TARGET_CODES[args.target],
        "budget": args.budget,
        "max_steps": args.max_steps,
        "found": any(item.found for item in results),
        "results": [item.to_dict() for item in results],
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"target: {args.target} ({TARGET_CODES[args.target]})")
        for item in payload["results"]:
            if item["found"]:
                print(
                    f"seed {item['seed']}: found at schedule "
                    f"{item['first_discovery_schedule']} in {len(item['actions'])} actions"
                )
                print(f"  actions: {','.join(item['actions'])}")
            else:
                print(f"seed {item['seed']}: not found ({item['schedules_executed']} schedules)")
    if args.require_found and not payload["found"]:
        return 1
    return 0


def _audit(args: argparse.Namespace) -> int:
    scopes = [item.strip() for item in args.identity_scopes.split(",") if item.strip()]
    gates: list[bool] = []
    for item in args.drain_gates.split(","):
        item = item.strip().lower()
        if item in {"true", "1", "yes"}:
            gates.append(True)
        elif item in {"false", "0", "no"}:
            gates.append(False)
        elif item:
            print(f"kvc: invalid drain gate {item!r}", file=sys.stderr)
            return 2
    try:
        bounds = [int(item) for item in args.fairness_bounds.split(",") if item.strip()]
    except ValueError:
        print("kvc: --fairness-bounds must be comma-separated integers", file=sys.stderr)
        return 2
    try:
        payload = audit_file(
            args.trace,
            identity_scopes=scopes,
            drain_gates=gates,
            fairness_bounds=bounds,
        )
    except (TraceError, ValueError) as exc:
        print(f"kvc: {exc}", file=sys.stderr)
        return 2

    if args.report:
        Path(args.report).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"trace: {args.trace}")
        print(f"variants: {payload['variant_count']}")
        print(f"verdict: {payload['verdict']}")
        for variant in payload["variants"]:
            assumptions = variant["assumptions"]
            print(
                f"  scope={assumptions['identity_scope']} "
                f"drain={assumptions['delay_free_drained']} "
                f"codes={variant['codes']}"
            )
    if args.fail_on_conflict and payload["conflict"]:
        return 1
    return 0


def _cost(args: argparse.Namespace) -> int:
    try:
        payload = predict(
            args.target,
            wait=args.wait,
            horizon=args.horizon,
            delivery=args.delivery,
        )
    except ValueError as exc:
        print(f"kvc: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"target: {payload['target']} "
            f"(wait={payload['wait']}, horizon={payload['horizon']}, "
            f"delivery={payload['delivery']})"
        )
        print(f"q: {payload['q']:.8f}")
        print(f"median schedules: {payload['median_schedules']}")
        print(f"IQR schedules: {payload['q1_schedules']}..{payload['q3_schedules']}")
        print(f"expected actions/candidate: {payload['expected_actions_per_candidate']:.3f}")
        print(f"reachable: {payload['reachable']}")
    return 0


def _aggregate(args: argparse.Namespace) -> int:
    try:
        schedules = load_schedules(args.input)
        result = audit_aggregation(schedules)
    except (OSError, ValueError) as exc:
        print(f"kvc: {exc}", file=sys.stderr)
        return 2
    payload = {
        "tool": "kvc-lifecycle",
        "version": TOOL_VERSION,
        "mode": "aggregate",
        "input": str(args.input),
        **result.to_dict(),
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"input: {args.input}")
        print(f"aggregate outputs: {result.outputs}")
        print(f"seen by poll: {result.seen_by_poll}")
        print(f"legacy codes: {result.legacy_codes}")
        print(f"strict codes: {result.strict_codes}")
        print(f"premature: {result.premature}")
        print(f"conflict: {result.conflict}")
    if args.fail_on_conflict and result.conflict:
        return 1
    return 0


def _record(args: argparse.Namespace) -> int:
    actions = [item.strip() for item in args.actions.split(",") if item.strip()]
    try:
        adapter = make_adapter(
            args.adapter,
            root=args.root,
            target=args.target,
            replay_id="cli:record",
        )
        events = adapter.record(actions)
        codes = adapter.codes()
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"kvc: {exc}", file=sys.stderr)
        return 2
    finally:
        try:
            adapter.close()  # type: ignore[possibly-undefined]
        except Exception:
            pass
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    payload = {
        "tool": "kvc-lifecycle",
        "version": TOOL_VERSION,
        "mode": "record",
        "adapter": args.adapter,
        "target": args.target,
        "actions": actions,
        "out": str(out),
        "event_count": len(events),
        "codes": codes,
        "target_code": TARGET_CODES[args.target],
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"recorded {len(events)} events to {out}")
        print(f"codes: {','.join(codes) if codes else '(none)'}")
    return 1 if TARGET_CODES[args.target] in codes else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        return _check(args)
    if args.command == "replay":
        return _replay(args)
    if args.command == "record":
        return _record(args)
    if args.command == "search":
        return _search(args)
    if args.command == "audit":
        return _audit(args)
    if args.command == "cost":
        return _cost(args)
    if args.command == "aggregate":
        return _aggregate(args)
    if args.command == "codes":
        for code in CODES:
            print(code)
        return 0
    if args.command == "version":
        print(TOOL_VERSION)
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


