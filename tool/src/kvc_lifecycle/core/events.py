"""Trace parsing and schema validation for kvc-lifecycle.

The trace is a JSONL file of lifecycle facts. The monitor never reads connector
internals; adapters are responsible for translating real events into this
schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


class TraceError(ValueError):
    """Raised when a trace line does not match the public event schema."""


def _as_optional_str(value: Any, *, name: str, line_no: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TraceError(f"line {line_no}: `{name}` must be a string")
    return value


def _as_attempt(value: Any, *, line_no: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TraceError(f"line {line_no}: `attempt` must be a non-negative integer")
    return value


def _as_completion_list(value: Any, *, name: str, line_no: int) -> list[Any]:
    """A list of request IDs, or scoped operation objects.

    Operation objects have the shape
    ``{"request_id": "r", "child": "c", "attempt": 0}``.
    """

    if value is None:
        return []
    if not isinstance(value, list):
        raise TraceError(f"line {line_no}: `{name}` must be a list")
    items: list[Any] = []
    for item in value:
        if isinstance(item, str) and item:
            items.append(item)
            continue
        if isinstance(item, dict):
            request_id = item.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                raise TraceError(
                    f"line {line_no}: `{name}` operation needs a non-empty `request_id`"
                )
            items.append(
                {
                    "request_id": request_id,
                    "child": _as_optional_str(
                        item.get("child"), name="child", line_no=line_no
                    ),
                    "attempt": _as_attempt(item.get("attempt", 0), line_no=line_no),
                }
            )
            continue
        raise TraceError(f"line {line_no}: `{name}` contains an invalid item")
    return items


def parse_event(raw: Any, *, line_no: int = 0) -> dict[str, Any]:
    """Validate one raw JSON object and return a normalized event dict."""

    if not isinstance(raw, dict):
        raise TraceError(f"line {line_no}: event must be a JSON object")
    kind = raw.get("event")
    if kind not in {"request_finished", "free", "observe", "quiescence"}:
        raise TraceError(f"line {line_no}: unknown event {kind!r}")

    event: dict[str, Any] = {"event": kind}

    if kind == "request_finished":
        request_id = raw.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise TraceError(f"line {line_no}: `request_id` must be a non-empty string")
        event["request_id"] = request_id
        event["child"] = _as_optional_str(raw.get("child"), name="child", line_no=line_no)
        event["attempt"] = _as_attempt(raw.get("attempt", 0), line_no=line_no)
        delay_free = raw.get("delay_free", False)
        if not isinstance(delay_free, bool):
            raise TraceError(f"line {line_no}: `delay_free` must be a boolean")
        event["delay_free"] = delay_free
    elif kind == "free":
        request_id = raw.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise TraceError(f"line {line_no}: `request_id` must be a non-empty string")
        event["request_id"] = request_id
        event["child"] = _as_optional_str(raw.get("child"), name="child", line_no=line_no)
        event["attempt"] = _as_attempt(raw.get("attempt", 0), line_no=line_no)
    elif kind == "observe":
        event["sending"] = _as_completion_list(
            raw.get("sending"), name="sending", line_no=line_no
        )
        event["recving"] = _as_completion_list(
            raw.get("recving"), name="recving", line_no=line_no
        )
    else:  # quiescence
        event["pending_recvs"] = _as_completion_list(
            raw.get("pending_recvs"), name="pending_recvs", line_no=line_no
        )
        drained = raw.get("delay_free_drained", True)
        if not isinstance(drained, bool):
            raise TraceError(f"line {line_no}: `delay_free_drained` must be a boolean")
        event["delay_free_drained"] = drained

    return event


def load_trace(path: str | Path) -> list[dict[str, Any]]:
    """Load and validate a JSONL trace. Blank lines are ignored."""

    source = Path(path)
    if not source.exists():
        raise TraceError(f"trace not found: {source}")
    events: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TraceError(f"line {line_no}: invalid JSON: {exc.msg}") from exc
            events.append(parse_event(raw, line_no=line_no))
    return events


def iter_events(events: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    """Yield normalized events from an in-memory iterable (validating each)."""

    for index, raw in enumerate(events, start=1):
        yield parse_event(raw, line_no=index)
