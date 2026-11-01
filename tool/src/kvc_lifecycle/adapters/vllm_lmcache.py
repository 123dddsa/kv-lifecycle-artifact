"""vLLM + LMCache controlled-I/O adapter.

This adapter is optional: it lazily imports the research harness from a
user-supplied checkout, so the core package has no vLLM/LMCache dependency.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .base import ACTIONS, Adapter

TARGET_CODES = {
    "stale_send": "I_COMPLETION_AFTER_FREE",
    "dual_completion": "I_ABORTED_DUAL_COMPLETION",
    "permanent_proc": "I_RECV_NEVER_COMPLETED",
}


class VLLMLMCacheAdapter(Adapter):
    """Translate the six abstract actions onto the real component replayer."""

    def __init__(self, root: str | Path, target: str, replay_id: str) -> None:
        if target not in TARGET_CODES:
            raise ValueError(f"unknown target {target!r}; choose {sorted(TARGET_CODES)}")
        self.root = Path(root)
        if not self.root.exists():
            raise FileNotFoundError(f"harness root not found: {self.root}")
        root_str = str(self.root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        try:
            import replay_real_traces  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "cannot import replay_real_traces from "
                f"{self.root}; pass --root pointing at <LOCAL_WORKSPACE>"
            ) from exc
        self._runner = replay_real_traces.RealTraceReplayer(target, replay_id)
        self.target = target
        self._closed = False
        self.events: list[dict[str, Any]] = []
        self._freed_emitted = False

    def enabled(self) -> tuple[str, ...]:
        runner = self._runner
        if not runner.started:
            return ("START",)
        allowed = {"IDLE", "QUIESCE", "POLL"}
        if not runner.terminal:
            allowed.add("ABORT")
        if runner.held_send or runner.held_recv:
            allowed.add("DELIVER")
        return tuple(action for action in ACTIONS if action in allowed)

    def apply(self, action: str, step: int) -> None:
        runner = self._runner
        request_id = runner.request.request_id
        held_send_before = set(runner.held_send)
        held_recv_before = set(runner.held_recv)
        runner.apply(action, step)

        if action == "ABORT":
            snapshot = runner.monitor.snapshot()
            delay_free = request_id in set(snapshot["delay_free"])
            self.events.append(
                {
                    "event": "request_finished",
                    "request_id": request_id,
                    "delay_free": delay_free,
                }
            )
        elif action == "DELIVER":
            self.events.append(
                {
                    "event": "observe",
                    "sending": sorted(held_send_before),
                    "recving": sorted(held_recv_before),
                }
            )
            snapshot = runner.monitor.snapshot()
            if (
                not self._freed_emitted
                and request_id in snapshot["freed_at"]
            ):
                self.events.append({"event": "free", "request_id": request_id})
                self._freed_emitted = True
        elif action == "QUIESCE":
            pending = sorted(runner._pending_recvs())
            self.events.append(
                {
                    "event": "quiescence",
                    "pending_recvs": pending,
                    "delay_free_drained": True,
                }
            )

    def record(self, actions: list[str]) -> list[dict[str, Any]]:
        """Replay an action list and return the equivalent JSONL trace events."""

        for step, action in enumerate(actions):
            if action not in self.enabled():
                raise ValueError(f"illegal action {action!r} at step {step}")
            self.apply(action, step)
        return list(self.events)

    def codes(self) -> list[str]:
        snapshot = self._runner.monitor.snapshot()
        return sorted({item["code"] for item in snapshot["violations"]})

    def result(self) -> dict[str, Any]:
        payload = self._runner.result()
        payload["target_code"] = TARGET_CODES[self.target]
        return payload

    def close(self) -> None:
        self._closed = True
