"""Adapter protocol for kvc-lifecycle.

An adapter owns a *fresh* real (or simulated) component instance per candidate.
The search/replay engines only use this interface, so they never import vLLM,
LMCache, or NIXL directly.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

ACTIONS = ("START", "ABORT", "POLL", "DELIVER", "QUIESCE", "IDLE")


@runtime_checkable
class Adapter(Protocol):
    """One lifecycle execution context."""

    def enabled(self) -> tuple[str, ...]:
        """Return the currently legal abstract actions, in canonical order."""

    def apply(self, action: str, step: int) -> None:
        """Apply one legal action to the real/simulated components."""

    def codes(self) -> list[str]:
        """Return the current violation codes (deduplicated)."""

    def result(self) -> dict[str, Any]:
        """Return a JSON-serializable result payload."""

    def close(self) -> None:
        """Release any resources; safe to call more than once."""
