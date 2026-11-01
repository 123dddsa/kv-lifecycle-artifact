"""Connector-independent lifecycle contract monitor.

The monitor consumes only public facts: request_finished, block free, and the
(finished_sending, finished_recving) sets. It has no connector-specific
branches.

Completion identity is scoped as ``(child, request, attempt, direction)``. The
``identity_scope`` selects how much of that tuple participates in ownership and
uniqueness; ``direction`` always separates send from receive. The default
``request`` scope preserves the legacy request-level contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Iterable


class IdentityScope(str, Enum):
    """How much of (child, request, attempt) identifies an operation."""

    REQUEST = "request"
    REQUEST_ATTEMPT = "request_attempt"
    CHILD_REQUEST_ATTEMPT = "child_request_attempt"


@dataclass(frozen=True)
class Operation:
    """One scoped completion operation.

    ``direction`` is ``"send"`` or ``"recv"`` for completion events; it is
    ignored for lifecycle events (request_finished/free), which are
    request-owned.
    """

    request: str
    child: str = ""
    attempt: int = 0
    direction: str = ""


@dataclass(frozen=True)
class Violation:
    """A single contract violation with a minimal machine-readable payload."""

    code: str
    request_id: str
    step: int
    detail: str
    operation: str | None = None


_Value = str | Operation
_RequestKey = tuple[str, ...]
_OperationKey = tuple[str, ...]


class ContractMonitor:
    """Check completion membership, ordering, uniqueness, and quiescence."""

    def __init__(self, identity_scope: IdentityScope | str = IdentityScope.REQUEST) -> None:
        self.identity_scope = IdentityScope(identity_scope)
        self.step = 0
        self.terminal: set[_RequestKey] = set()
        self.delay_free: set[_RequestKey] = set()
        self.freed_at: dict[_RequestKey, int] = {}
        self.send_count: dict[_OperationKey, int] = {}
        self.recv_count: dict[_OperationKey, int] = {}
        self.violations: list[Violation] = []
        self._quiescence_checked = False

    # ------------------------------------------------------------------ events
    def request_finished(
        self,
        request_id: str,
        delay_free: bool,
        *,
        child: str = "",
        attempt: int = 0,
    ) -> None:
        """Record the scheduler-side terminal callback and its free decision."""

        key = self._request_key(Operation(request_id, child=child, attempt=attempt))
        self.terminal.add(key)
        if delay_free:
            self.delay_free.add(key)

    def free(self, request_id: str, *, child: str = "", attempt: int = 0) -> None:
        """Record the first scheduler block-free event for a request."""

        key = self._request_key(Operation(request_id, child=child, attempt=attempt))
        if key in self.freed_at:
            self._add(
                "I_FREE_DUPLICATE",
                request_id,
                "blocks freed more than once",
                operation=self._display(key),
            )
        else:
            self.freed_at[key] = self.step
        self.delay_free.discard(key)

    def observe(
        self,
        sending: Iterable[_Value] | None,
        recving: Iterable[_Value] | None,
    ) -> None:
        """Consume one worker/scheduler completion batch.

        Items may be bare request IDs (legacy API) or :class:`Operation`.
        """

        self.step += 1
        send_ops = [self._as_operation(item, "send") for item in (sending or ())]
        recv_ops = [self._as_operation(item, "recv") for item in (recving or ())]

        reported: set[tuple[str, _RequestKey]] = set()
        for op in send_ops + recv_ops:
            request_key = self._request_key(op)
            if request_key in self.freed_at and ("completion", request_key) not in reported:
                self._add(
                    "I_COMPLETION_AFTER_FREE",
                    op.request,
                    f"completion after free at step {self.freed_at[request_key]}",
                    operation=self._display(request_key),
                )
                reported.add(("completion", request_key))

        send_request_keys: set[_RequestKey] = set()
        for op in send_ops:
            request_key = self._request_key(op)
            operation_key = self._operation_key(op)
            send_request_keys.add(request_key)
            if request_key not in self.terminal:
                self._add(
                    "I_SEND_NOT_FINISHED",
                    op.request,
                    "finished_sending is not a subset of finished_req_ids",
                    operation=self._display(request_key),
                )
            self.send_count[operation_key] = self.send_count.get(operation_key, 0) + 1
            if self.send_count[operation_key] > 1:
                self._add(
                    "I_SEND_DUPLICATE",
                    op.request,
                    "send reported more than once",
                    operation=self._display(operation_key),
                )
            self.delay_free.discard(request_key)

        recv_request_keys: set[_RequestKey] = set()
        for op in recv_ops:
            request_key = self._request_key(op)
            operation_key = self._operation_key(op)
            recv_request_keys.add(request_key)
            self.recv_count[operation_key] = self.recv_count.get(operation_key, 0) + 1
            if self.recv_count[operation_key] > 1:
                self._add(
                    "I_RECV_DUPLICATE",
                    op.request,
                    "recv reported more than once",
                    operation=self._display(operation_key),
                )

        for request_key in sorted(send_request_keys & recv_request_keys & self.terminal):
            self._add(
                "I_ABORTED_DUAL_COMPLETION",
                request_key[0],
                "aborted request appears in recv and send in one scheduler batch",
                operation=self._display(request_key),
            )

    def check_quiescence(
        self,
        pending_recvs: Iterable[_Value] = (),
        *,
        delay_free_drained: bool = True,
    ) -> None:
        """Check bounded liveness with an explicit delayed-free drain gate.

        ``delay_free_drained=False`` suppresses only the delayed-free verdict:
        completion delivery may still be in progress. Pending receives retain
        their independent bounded-liveness check.
        """

        self._quiescence_checked = True
        if delay_free_drained:
            for key in sorted(self.delay_free):
                self._add(
                    "I_DELAY_FREE_NEVER_COMPLETED",
                    key[0],
                    "delay_free was requested but no terminal send arrived",
                    operation=self._display(key),
                )
        seen: set[_OperationKey] = set()
        for item in pending_recvs:
            op = self._as_operation(item, "recv")
            operation_key = self._operation_key(op)
            if operation_key in seen:
                continue
            seen.add(operation_key)
            self._add(
                "I_RECV_NEVER_COMPLETED",
                op.request,
                "receive remains pending at the scenario quiescence bound",
                operation=self._display(operation_key),
            )

    # ------------------------------------------------------------------- API
    def run(self, events: Iterable[dict[str, Any]]) -> "ContractMonitor":
        """Apply a normalized event stream and return ``self`` for chaining."""

        for event in events:
            kind = event["event"]
            if kind == "request_finished":
                self.request_finished(
                    event["request_id"],
                    event["delay_free"],
                    child=event.get("child", ""),
                    attempt=event.get("attempt", 0),
                )
            elif kind == "free":
                self.free(
                    event["request_id"],
                    child=event.get("child", ""),
                    attempt=event.get("attempt", 0),
                )
            elif kind == "observe":
                self.observe(event["sending"], event["recving"])
            elif kind == "quiescence":
                self.check_quiescence(
                    event["pending_recvs"],
                    delay_free_drained=event["delay_free_drained"],
                )
            else:  # pragma: no cover - parse_event already rejects unknown kinds
                raise ValueError(f"unknown event: {kind!r}")
        return self

    def codes(self) -> list[str]:
        """Return sorted, deduplicated violation codes (stable for CI)."""

        return sorted({item.code for item in self.violations})

    def snapshot(self) -> dict[str, object]:
        """Return a JSON-serializable monitor state."""

        return {
            "step": self.step,
            "identity_scope": self.identity_scope.value,
            "terminal": sorted(self._display(key) for key in self.terminal),
            "delay_free": sorted(self._display(key) for key in self.delay_free),
            "freed_at": {self._display(key): value for key, value in self.freed_at.items()},
            "send_count": {
                self._display(key): value for key, value in self.send_count.items()
            },
            "recv_count": {
                self._display(key): value for key, value in self.recv_count.items()
            },
            "violations": [asdict(item) for item in self.violations],
        }

    def report(self) -> dict[str, object]:
        """Return the stable check report used by the CLI."""

        return {
            "pass": not self.violations,
            "violation_count": len(self.violations),
            "codes": self.codes(),
            "violations": [asdict(item) for item in self.violations],
            "step": self.step,
            "identity_scope": self.identity_scope.value,
            "quiescence_checked": self._quiescence_checked,
        }

    # -------------------------------------------------------------- internals
    def _request_key(self, op: Operation) -> _RequestKey:
        if self.identity_scope is IdentityScope.REQUEST:
            return (op.request,)
        if self.identity_scope is IdentityScope.REQUEST_ATTEMPT:
            return (op.request, str(op.attempt))
        return (op.child, op.request, str(op.attempt))

    def _operation_key(self, op: Operation) -> _OperationKey:
        direction = op.direction or ""
        return self._request_key(op) + (direction,)

    def _display(self, key: tuple[str, ...]) -> str:
        if self.identity_scope is IdentityScope.REQUEST:
            return key[0]
        if self.identity_scope is IdentityScope.REQUEST_ATTEMPT:
            return f"{key[0]}@a{key[1]}"
        return f"{key[1]}#{key[0]}@a{key[2]}" if key[0] else f"{key[1]}@a{key[2]}"

    def _as_operation(self, item: _Value, direction: str) -> Operation:
        if isinstance(item, Operation):
            return Operation(
                request=item.request,
                child=item.child,
                attempt=item.attempt,
                direction=item.direction or direction,
            )
        if isinstance(item, dict):
            return Operation(
                request=item["request_id"],
                child=item.get("child", ""),
                attempt=item.get("attempt", 0),
                direction=direction,
            )
        if isinstance(item, str):
            return Operation(request=item, direction=direction)
        raise TypeError(f"completion item must be str, Operation or dict, got {type(item)!r}")

    def _add(
        self,
        code: str,
        request_id: str,
        detail: str,
        *,
        operation: str | None = None,
    ) -> None:
        self.violations.append(Violation(code, request_id, self.step, detail, operation))
