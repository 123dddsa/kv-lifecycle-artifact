"""Assumption-space audit for the lifecycle monitor.

M4 is still deliberately finite: identity scope, delayed-free drain gate, and a
fairness bound on quiescence. It re-evaluates the *same* input under each
assumption and reports whether the verdict is sensitive to that assumption.
Aggregation and delivery-mode enumeration are the next slice.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .core.monitor import ContractMonitor, IdentityScope
from .core.trace import load_trace

IDENTITY_SCOPES = (
    IdentityScope.REQUEST.value,
    IdentityScope.REQUEST_ATTEMPT.value,
    IdentityScope.CHILD_REQUEST_ATTEMPT.value,
)
FAIRNESS_BOUNDS = (0, 3)


@dataclass(frozen=True)
class AuditVariant:
    assumptions: dict[str, Any]
    codes: list[str]
    violation_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumptions": self.assumptions,
            "codes": self.codes,
            "violation_count": self.violation_count,
        }


def _digest(events: Iterable[dict[str, Any]]) -> str:
    canonical = json.dumps(list(events), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _run_variant(
    events: list[dict[str, Any]],
    *,
    scope: str,
    drain: bool,
    fairness_bound: int,
) -> AuditVariant:
    mutated = copy.deepcopy(events)
    polls = 0
    effective: list[dict[str, Any]] = []
    for event in mutated:
        if event["event"] == "observe":
            polls += 1
            effective.append(event)
        elif event["event"] == "quiescence":
            event["delay_free_drained"] = drain
            if polls >= fairness_bound:
                effective.append(event)
        else:
            effective.append(event)
    monitor = ContractMonitor(scope).run(effective)
    report = monitor.report()
    return AuditVariant(
        assumptions={
            "identity_scope": scope,
            "delay_free_drained": drain,
            "fairness_bound": fairness_bound,
        },
        codes=list(report["codes"]),
        violation_count=int(report["violation_count"]),
    )


def _axis_sensitive(variants: list[AuditVariant], axis: str) -> bool:
    """True if changing ``axis`` changes the verdict with other axes fixed."""

    axes = ("identity_scope", "delay_free_drained", "fairness_bound")
    other_axes = [name for name in axes if name != axis]
    groups: dict[tuple[str, ...], dict[str, set[tuple[str, ...]]]] = {}
    for variant in variants:
        key = tuple(str(variant.assumptions[name]) for name in other_axes)
        value = str(variant.assumptions[axis])
        groups.setdefault(key, {}).setdefault(value, set()).add(tuple(variant.codes))
    return any(
        len(by_value) > 1 and len({frozenset(codes) for codes in by_value.values()}) > 1
        for by_value in groups.values()
    )


def audit_events(
    events: list[dict[str, Any]],
    *,
    identity_scopes: Iterable[str] = IDENTITY_SCOPES,
    drain_gates: Iterable[bool] = (True, False),
    fairness_bounds: Iterable[int] = FAIRNESS_BOUNDS,
) -> dict[str, Any]:
    """Re-evaluate one input under an explicit, finite assumption space."""

    scopes = list(identity_scopes)
    gates = list(drain_gates)
    bounds = list(fairness_bounds)
    unknown = [scope for scope in scopes if scope not in IDENTITY_SCOPES]
    if unknown:
        raise ValueError(f"unknown identity scope(s): {unknown}")
    if not scopes or not gates or not bounds:
        raise ValueError("assumption space must be non-empty")
    if any(bound < 0 for bound in bounds):
        raise ValueError("fairness bounds must be non-negative")

    variants = [
        _run_variant(events, scope=scope, drain=drain, fairness_bound=bound)
        for scope in scopes
        for drain in gates
        for bound in bounds
    ]
    code_sets = {tuple(variant.codes) for variant in variants}
    sensitive = {
        "identity_scope": _axis_sensitive(variants, "identity_scope"),
        "delay_free_drained": _axis_sensitive(variants, "delay_free_drained"),
        "fairness_bound": _axis_sensitive(variants, "fairness_bound"),
    }
    return {
        "tool": "kvc-lifecycle",
        "mode": "audit",
        "input_digest": _digest(events),
        "event_count": len(events),
        "assumption_space": {
            "identity_scopes": scopes,
            "drain_gates": gates,
            "fairness_bounds": bounds,
        },
        "variant_count": len(variants),
        "variants": [variant.to_dict() for variant in variants],
        "conflict": len(code_sets) > 1,
        "sensitive": sensitive,
        "verdict": "assumption-sensitive" if len(code_sets) > 1 else "assumption-stable",
    }


def audit_file(
    path: str | Path,
    *,
    identity_scopes: Iterable[str] = IDENTITY_SCOPES,
    drain_gates: Iterable[bool] = (True, False),
    fairness_bounds: Iterable[int] = FAIRNESS_BOUNDS,
) -> dict[str, Any]:
    events = load_trace(path)
    payload = audit_events(
        events,
        identity_scopes=identity_scopes,
        drain_gates=drain_gates,
        fairness_bounds=fairness_bounds,
    )
    payload["trace"] = str(path)
    return payload

