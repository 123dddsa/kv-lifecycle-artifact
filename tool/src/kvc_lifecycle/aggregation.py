"""Completion-uniqueness/aggregation audit (E3 slice).

The connector aggregates child completion notifications into a request-level
completion. Two oracles are compared on the same schedule:

- ``legacy``: bare request identity on the aggregate stream (aggregate-only);
- ``strict``: per-child uniqueness plus an all-children quorum before a global
  completion is forwarded.

This module is intentionally separate from the trace monitor: the aggregate
stream is a derived view, not a raw lifecycle fact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core.monitor import ContractMonitor

PREMATURE_AGGREGATE = "I_PREMATURE_AGGREGATE"
DUPLICATE = "I_SEND_DUPLICATE"


@dataclass(frozen=True)
class AggregationResult:
    outputs: list[list[str]]
    seen_by_poll: list[list[str]]
    legacy_codes: list[str]
    strict_codes: list[str]
    premature: bool
    conflict: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "outputs": self.outputs,
            "seen_by_poll": self.seen_by_poll,
            "legacy_codes": self.legacy_codes,
            "strict_codes": self.strict_codes,
            "premature": self.premature,
            "conflict": self.conflict,
        }


def aggregate_outputs(
    schedules: dict[str, list[bool]], *, request_id: str = "req"
) -> tuple[list[list[str]], list[set[str]]]:
    """Derive the request-level completion stream from child schedules."""

    if not schedules:
        raise ValueError("schedules must be non-empty")
    lengths = {len(values) for values in schedules.values()}
    if len(lengths) != 1:
        raise ValueError("all child schedules must have the same length")
    outputs: list[list[str]] = []
    seen_by_poll: list[set[str]] = []
    seen: set[str] = set()
    extra = 1  # one extra-save allowance before the aggregate is forwarded
    for values in zip(*schedules.values()):
        sending: set[str] = set()
        for child, value in zip(schedules, values):
            if value:
                sending.add(child)
                seen.add(child)
        seen_by_poll.append(set(seen))
        if sending:
            if extra:
                extra -= 1
                outputs.append([])
            else:
                outputs.append([request_id])
        else:
            outputs.append([])
    return outputs, seen_by_poll


def audit_aggregation(
    schedules: dict[str, list[bool]], *, request_id: str = "req"
) -> AggregationResult:
    outputs, seen_by_poll = aggregate_outputs(schedules, request_id=request_id)
    expected_children = set(schedules)
    premature = any(
        output and seen_by_poll[index] != expected_children
        for index, output in enumerate(outputs)
    )

    legacy = ContractMonitor()
    legacy.request_finished(request_id, False)
    for sending in outputs:
        legacy.observe(sending, set())
    legacy_codes = legacy.codes()
    if premature:
        legacy_codes = sorted(set(legacy_codes) | {PREMATURE_AGGREGATE})

    strict_codes: set[str] = set()
    for child, values in schedules.items():
        monitor = ContractMonitor()
        child_id = f"{child}/{request_id}"
        monitor.request_finished(child_id, False)
        for value in values:
            if value:
                monitor.observe({child_id}, set())
        strict_codes.update(monitor.codes())
    if premature:
        strict_codes.add(PREMATURE_AGGREGATE)

    return AggregationResult(
        outputs=outputs,
        seen_by_poll=[sorted(value) for value in seen_by_poll],
        legacy_codes=sorted(legacy_codes),
        strict_codes=sorted(strict_codes),
        premature=premature,
        conflict=sorted(legacy_codes) != sorted(strict_codes),
    )


def load_schedules(path: str | Path) -> dict[str, list[bool]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "schedules" in payload:
        payload = payload["schedules"]
    if not isinstance(payload, dict):
        raise ValueError("schedules file must contain an object")
    schedules: dict[str, list[bool]] = {}
    for child, values in payload.items():
        if not isinstance(child, str) or not isinstance(values, list):
            raise ValueError("each schedule must be a list of booleans")
        schedules[child] = [bool(value) for value in values]
    return schedules
