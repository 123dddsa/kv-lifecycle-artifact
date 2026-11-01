"""Random/directed search over a fresh adapter per candidate."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable

from .adapters.base import Adapter, ACTIONS


@dataclass
class CellResult:
    seed: int
    found: bool
    schedule: int | None
    actions: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    schedules_executed: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "found": self.found,
            "first_discovery_schedule": self.schedule,
            "actions": self.actions,
            "codes": self.codes,
            "schedules_executed": self.schedules_executed,
            "error": self.error,
        }


AdapterFactory = Callable[[str], Adapter]

# Target-conditioned minimum witnesses observed on the real controlled-I/O
# harness. Directed search follows the prefix when legal, then falls back to
# the first enabled action. This is a policy, not a generic planner.
DIRECTED_PREFIXES: dict[str, tuple[str, ...]] = {
    "stale_send": (
        "START",
        "IDLE",
        "POLL",
        "IDLE",
        "ABORT",
        "DELIVER",
        "QUIESCE",
        "POLL",
        "DELIVER",
    ),
    "dual_completion": ("START", "ABORT", "POLL", "DELIVER", "IDLE"),
    "permanent_proc": ("START", "ABORT", "POLL", "POLL", "POLL", "QUIESCE"),
}


def next_directed_action(adapter: Adapter, target: str, step: int) -> str:
    """Follow the target prefix when legal, otherwise pick the first enabled."""

    enabled = adapter.enabled()
    if not enabled:
        raise RuntimeError("adapter has no enabled action")
    prefix = DIRECTED_PREFIXES.get(target)
    if prefix is not None and step < len(prefix) and prefix[step] in enabled:
        return prefix[step]
    return enabled[0]


def run_random_cell(
    factory: AdapterFactory,
    *,
    target_code: str,
    seed: int,
    budget: int,
    max_steps: int = 10,
) -> CellResult:
    """Run one random-search cell; each schedule gets a fresh adapter."""

    rng = random.Random(seed)
    for schedule in range(1, budget + 1):
        adapter = factory(f"search:seed{seed}:schedule{schedule}")
        actions: list[str] = []
        try:
            for step in range(max_steps):
                enabled = adapter.enabled()
                if not enabled:
                    break
                action = rng.choice(enabled)
                adapter.apply(action, step)
                actions.append(action)
                codes = adapter.codes()
                if target_code in codes:
                    return CellResult(
                        seed=seed,
                        found=True,
                        schedule=schedule,
                        actions=actions,
                        codes=codes,
                        schedules_executed=schedule,
                    )
            codes = adapter.codes()
        except Exception as exc:  # keep one bad candidate from killing the cell
            return CellResult(
                seed=seed,
                found=False,
                schedule=None,
                actions=actions,
                schedules_executed=schedule,
                error=repr(exc),
            )
        finally:
            adapter.close()
    return CellResult(
        seed=seed,
        found=False,
        schedule=None,
        actions=actions,
        codes=codes,
        schedules_executed=budget,
    )


def run_random_seeds(
    factory: AdapterFactory,
    *,
    target_code: str,
    seeds: list[int],
    budget: int,
    max_steps: int = 10,
    method: str = "random",
    target: str = "",
) -> list[CellResult]:
    return [
        run_seed(
            factory,
            target=target,
            target_code=target_code,
            seed=seed,
            budget=budget,
            max_steps=max_steps,
            method=method,
        )
        for seed in seeds
    ]


def run_seed(
    factory: AdapterFactory,
    *,
    target: str,
    target_code: str,
    seed: int,
    budget: int,
    max_steps: int = 10,
    method: str = "random",
) -> CellResult:
    if method not in {"random", "directed"}:
        raise ValueError(f"unknown search method {method!r}")
    if method == "directed":
        return _run_directed_cell(
            factory,
            target=target,
            target_code=target_code,
            seed=seed,
            budget=budget,
            max_steps=max_steps,
        )
    return run_random_cell(
        factory,
        target_code=target_code,
        seed=seed,
        budget=budget,
        max_steps=max_steps,
    )


def _run_directed_cell(
    factory: AdapterFactory,
    *,
    target: str,
    target_code: str,
    seed: int,
    budget: int,
    max_steps: int,
) -> CellResult:
    for schedule in range(1, budget + 1):
        adapter = factory(f"directed:seed{seed}:schedule{schedule}")
        actions: list[str] = []
        try:
            for step in range(max_steps):
                action = next_directed_action(adapter, target, step)
                adapter.apply(action, step)
                actions.append(action)
                codes = adapter.codes()
                if target_code in codes:
                    return CellResult(
                        seed=seed,
                        found=True,
                        schedule=schedule,
                        actions=actions,
                        codes=codes,
                        schedules_executed=schedule,
                    )
            codes = adapter.codes()
        except Exception as exc:
            return CellResult(
                seed=seed,
                found=False,
                schedule=None,
                actions=actions,
                schedules_executed=schedule,
                error=repr(exc),
            )
        finally:
            adapter.close()
    return CellResult(
        seed=seed,
        found=False,
        schedule=None,
        actions=actions,
        codes=codes,
        schedules_executed=budget,
    )


def replay_actions(adapter: Adapter, actions: list[str]) -> dict[str, Any]:
    """Apply an action list to one adapter and return its result."""

    for step, action in enumerate(actions):
        if action not in adapter.enabled():
            raise ValueError(f"illegal action {action!r} at step {step}")
        adapter.apply(action, step)
    return adapter.result()
