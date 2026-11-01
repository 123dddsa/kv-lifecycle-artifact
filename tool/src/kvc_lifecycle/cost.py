"""Exact state-dependent witness rarity and geometric discovery-cost prediction.

The model is deliberately small and explicit: the same six lifecycle actions as
the search harness, a completion-delivery wait ``w``, and the connector-independent
contract monitor. The DP is exact over the reachable state space for a bounded
horizon; it is not a claim about natural incidence.
"""

from __future__ import annotations

import copy
import math
from typing import Any

from .core.monitor import ContractMonitor

ACTIONS = ("START", "ABORT", "POLL", "DELIVER", "IDLE", "QUIESCE")

TARGETS: dict[str, dict[str, Any]] = {
    "stale_send": {
        "connector": "lmcache_like",
        "transport": "DONE",
        "send_outstanding": False,
        "code": "I_COMPLETION_AFTER_FREE",
    },
    "dual_completion": {
        "connector": "nixl_like",
        "transport": "DONE",
        "send_outstanding": True,
        "code": "I_ABORTED_DUAL_COMPLETION",
    },
    "permanent_proc": {
        "connector": "nixl_like",
        "transport": "PROC",
        "send_outstanding": False,
        "code": "I_RECV_NEVER_COMPLETED",
    },
}


class LifecycleModel:
    """Explicit lifecycle state; the monitor supplies the target predicate."""

    def __init__(self, target: str) -> None:
        if target not in TARGETS:
            raise ValueError(f"unknown target {target!r}")
        self.target = target
        self.config = TARGETS[target]
        self.monitor = ContractMonitor()
        self.started = False
        self.terminal = False
        self.freed = False
        self.pending_recv = False
        self.recv_was_polled = False
        self.send_returned = False
        self.held_send: set[str] = set()
        self.held_recv: set[str] = set()
        self.polls = 0

    def enabled(self) -> tuple[str, ...]:
        if not self.started:
            return ("START",)
        allowed = {"IDLE", "QUIESCE", "POLL"}
        if not self.terminal:
            allowed.add("ABORT")
        if self.held_send or self.held_recv:
            allowed.add("DELIVER")
        return tuple(action for action in ACTIONS if action in allowed)

    def apply(self, action: str) -> None:
        if action not in self.enabled():
            raise ValueError(f"illegal action {action!r}")
        if action == "START":
            self.started = True
            self.pending_recv = True
        elif action == "ABORT":
            self.terminal = True
            self.monitor.request_finished("r", False)
        elif action == "POLL":
            self._poll()
        elif action == "DELIVER":
            self._deliver()
        elif action == "QUIESCE" and self.terminal and self.polls >= 3:
            pending = {"r"} if self.pending_recv else set()
            self.monitor.check_quiescence(pending)

    def _poll(self) -> None:
        self.polls += 1
        if self.pending_recv and self.config["transport"] == "DONE":
            self.pending_recv = False
            self.recv_was_polled = True
            self.held_recv.add("r")
        should_send = False
        if self.terminal and not self.send_returned:
            if self.config["connector"] == "lmcache_like" and self.recv_was_polled:
                should_send = True
            if self.config["connector"] == "nixl_like" and self.config["send_outstanding"]:
                should_send = True
        if should_send:
            self.held_send.add("r")
            self.send_returned = True

    def _deliver(self) -> None:
        sending, recving = self.held_send, self.held_recv
        self.monitor.observe(sending, recving)
        if recving and self.terminal:
            self.freed = True
            self.monitor.free("r")
        elif sending:
            self.freed = True
            self.monitor.free("r")
        self.held_send = set()
        self.held_recv = set()

    def found(self) -> bool:
        return self.config["code"] in {item.code for item in self.monitor.violations}


class MergedLifecycleModel(LifecycleModel):
    """Counterfactual oracle: POLL both observes and consumes (no held window)."""

    def __init__(self, target: str) -> None:
        super().__init__(target)
        self.wait = 0
        self.delivery_credits = 0

    def enabled(self) -> tuple[str, ...]:
        enabled = [action for action in super().enabled() if action != "DELIVER"]
        return tuple(action for action in ACTIONS if action in enabled)

    def _poll(self) -> None:
        super()._poll()
        if self.held_send or self.held_recv:
            self._deliver()


class DelayedLifecycleModel(LifecycleModel):
    """Frozen model plus an explicit post-completion delivery wait."""

    def __init__(self, target: str, wait: int) -> None:
        super().__init__(target)
        self.wait = wait
        self.delivery_credits = 0

    def enabled(self) -> tuple[str, ...]:
        enabled = list(super().enabled())
        if "DELIVER" in enabled and self.delivery_credits < self.wait:
            enabled.remove("DELIVER")
        return tuple(action for action in ACTIONS if action in enabled)

    def apply(self, action: str) -> None:
        before_send = set(self.held_send)
        before_recv = set(self.held_recv)
        super().apply(action)
        new_completion = bool(
            (self.held_send - before_send) or (self.held_recv - before_recv)
        )
        if not self.held_send and not self.held_recv:
            self.delivery_credits = 0
        elif new_completion:
            self.delivery_credits = 0
        else:
            self.delivery_credits += 1


def _state_key(model: DelayedLifecycleModel) -> tuple[Any, ...]:
    monitor = model.monitor
    snapshot = monitor.snapshot()
    return (
        model.target,
        model.started,
        model.terminal,
        model.freed,
        model.pending_recv,
        model.recv_was_polled,
        model.send_returned,
        tuple(sorted(model.held_send)),
        tuple(sorted(model.held_recv)),
        model.polls,
        model.wait,
        model.delivery_credits,
        tuple(snapshot["terminal"]),
        tuple(snapshot["delay_free"]),
        tuple(sorted(snapshot["freed_at"].items())),
        tuple(sorted(snapshot["send_count"].items())),
        tuple(sorted(snapshot["recv_count"].items())),
        tuple(
            sorted(
                (
                    item["code"],
                    item["request_id"],
                    item["step"],
                    item["detail"],
                    item.get("operation"),
                )
                for item in snapshot["violations"]
            )
        ),
    )


def geometric_quantile(probability: float, quantile: float) -> int | None:
    """Smallest k with P(first hit <= k) >= quantile; None if q=0."""

    if probability <= 0:
        return None
    if probability >= 1:
        return 1
    if not 0 < quantile < 1:
        raise ValueError("quantile must be in (0, 1)")
    return math.ceil(math.log1p(-quantile) / math.log1p(-probability))


def exact_dp(
    target: str,
    wait: int = 0,
    horizon: int = 10,
    *,
    delivery: str = "separated",
) -> dict[str, Any]:
    """Exact hitting probability over uniform-random legal actions."""

    if delivery not in {"separated", "merged"}:
        raise ValueError(f"unknown delivery mode {delivery!r}")
    if delivery == "merged":
        initial = MergedLifecycleModel(target)
    else:
        initial = DelayedLifecycleModel(target, wait)
    distribution: dict[tuple[Any, ...], list[Any]] = {_state_key(initial): [1.0, initial]}
    hit_mass = [0.0] * (horizon + 1)
    survival = [1.0]
    state_counts = [1]
    transitions = 0

    for depth in range(horizon):
        following: dict[tuple[Any, ...], list[Any]] = {}
        for probability, model in distribution.values():
            if probability == 0:
                continue
            legal = model.enabled()
            if not legal:
                raise RuntimeError(f"state has no legal action: {target}/{wait}/{depth}")
            branch = probability / len(legal)
            for action in legal:
                child = copy.deepcopy(model)
                child.apply(action)
                transitions += 1
                if child.found():
                    hit_mass[depth + 1] += branch
                else:
                    key = _state_key(child)
                    if key not in following:
                        following[key] = [0.0, child]
                    following[key][0] += branch
        distribution = following
        survival.append(sum(item[0] for item in distribution.values()))
        state_counts.append(len(distribution))

    q = sum(hit_mass)
    if abs(q + survival[-1] - 1.0) > 1e-12:
        raise RuntimeError(f"DP mass not conserved: {target}/{wait}")
    expected_actions = sum(survival[:-1])
    return {
        "target": target,
        "wait": wait,
        "horizon": horizon,
        "delivery": delivery,
        "hit_probability_q": q,
        "predicted_median_schedules": geometric_quantile(q, 0.5),
        "predicted_q1_schedules": geometric_quantile(q, 0.25),
        "predicted_q3_schedules": geometric_quantile(q, 0.75),
        "expected_schedules": 1 / q if q else None,
        "expected_actions_per_candidate": expected_actions,
        "expected_actions_to_discovery": expected_actions / q if q else None,
        "hit_probability_by_step": hit_mass,
        "survival_by_step": survival,
        "dp_state_counts_by_depth": state_counts,
        "dp_transitions": transitions,
        "reachable_within_horizon": q > 0,
    }


def predict(
    target: str,
    *,
    wait: int = 0,
    horizon: int = 10,
    delivery: str = "separated",
) -> dict[str, Any]:
    """Public cost prediction used by CLI/CI; no regression fitted."""

    dp = exact_dp(target, wait=wait, horizon=horizon, delivery=delivery)
    return {
        "target": target,
        "wait": wait,
        "horizon": horizon,
        "delivery": delivery,
        "q": dp["hit_probability_q"],
        "median_schedules": dp["predicted_median_schedules"],
        "q1_schedules": dp["predicted_q1_schedules"],
        "q3_schedules": dp["predicted_q3_schedules"],
        "expected_actions_per_candidate": dp["expected_actions_per_candidate"],
        "reachable": dp["reachable_within_horizon"],
        "method": "exact exhaustive DP over uniform-random legal actions",
    }
