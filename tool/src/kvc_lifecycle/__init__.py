"""kvc-lifecycle: contract-first checks for KV-cache transfer completion."""

from __future__ import annotations

from .core.monitor import ContractMonitor, IdentityScope, Operation, Violation
from .core.trace import TraceError, load_trace, parse_event

__all__ = [
    "ContractMonitor",
    "Violation",
    "TraceError",
    "load_trace",
    "parse_event",
    "TOOL_VERSION",
]

TOOL_VERSION = "0.8.0"








