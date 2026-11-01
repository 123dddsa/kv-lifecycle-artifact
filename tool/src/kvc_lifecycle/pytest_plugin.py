"""pytest plugin for kvc-lifecycle.

Usage:
    pip install -e .[dev]
    pytest --kvc-trace examples/stale_send.jsonl
    pytest --kvc-trace examples/normal_recv.jsonl --kvc-trace examples/duplicate_send.jsonl --kvc-audit

The plugin is loaded through the ``pytest11`` entry point. It is optional:
importing the core package never imports pytest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from .audit import audit_file
from .core.monitor import ContractMonitor
from .core.trace import TraceError, load_trace

SCOPES = ("request", "request_attempt", "child_request_attempt")


def check_trace(path: str | Path, identity_scope: str = "child_request_attempt") -> dict[str, Any]:
    """Check one trace; shared by the fixture and the session hook."""

    events = load_trace(path)
    monitor = ContractMonitor(identity_scope).run(events)
    payload = {
        "trace": str(path),
        "event_count": len(events),
        **monitor.report(),
    }
    return payload


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("kvc", "KV-cache lifecycle contract checks")
    group.addoption(
        "--kvc-trace",
        action="append",
        default=[],
        metavar="PATH",
        help="check a JSONL trace at session finish (repeatable)",
    )
    group.addoption(
        "--kvc-identity-scope",
        default="child_request_attempt",
        choices=SCOPES,
        help="identity scope for --kvc-trace checks",
    )
    group.addoption(
        "--kvc-audit",
        action="store_true",
        help="also run the assumption-space audit on each --kvc-trace",
    )
    group.addoption(
        "--kvc-fail-on-violation",
        action="store_true",
        help="force a non-zero session when a trace violates the contract",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "kvc: KV-cache lifecycle contract test")


@pytest.fixture
def kvc_check():
    """Return a function that checks a trace and returns its report."""

    def _check(path: str | Path, identity_scope: str = "child_request_attempt") -> dict[str, Any]:
        if identity_scope not in SCOPES:
            raise ValueError(f"unknown identity scope {identity_scope!r}")
        return check_trace(path, identity_scope)

    return _check


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    traces = config.getoption("kvc_trace") or []
    if not traces:
        return
    scope = config.getoption("kvc_identity_scope")
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    failures = 0
    for trace in traces:
        try:
            payload = check_trace(trace, scope)
        except TraceError as exc:
            failures += 1
            if reporter:
                reporter.write_line(f"KVC ERROR {trace}: {exc}")
            continue
        if payload["pass"]:
            if reporter:
                reporter.write_line(f"KVC PASS {trace}")
        else:
            failures += 1
            if reporter:
                reporter.write_line(
                    f"KVC FAIL {trace}: {','.join(payload['codes'])}"
                )
        if config.getoption("kvc_audit"):
            audit = audit_file(trace, identity_scopes=(scope,))
            if reporter:
                reporter.write_line(
                    f"KVC AUDIT {trace}: {audit['verdict']} "
                    f"conflict={audit['conflict']}"
                )
    if failures:
        session.exitstatus = 1


def pytest_report_header(config: pytest.Config) -> str | None:
    traces = config.getoption("kvc_trace") or []
    if not traces:
        return None
    return f"kvc-lifecycle: {len(traces)} trace(s), identity_scope={config.getoption('kvc_identity_scope')}"


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)

