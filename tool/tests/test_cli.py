"""CLI tests for `kvc check`."""

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from kvc_lifecycle.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTest(unittest.TestCase):
    def test_normal_example_passes(self) -> None:
        buffer = StringIO()
        with redirect_stdout(buffer):
            code = main(["check", str(EXAMPLES / "normal_recv.jsonl")])
        self.assertEqual(code, 0)
        self.assertIn("PASS", buffer.getvalue())

    def test_stale_example_fails(self) -> None:
        buffer = StringIO()
        with redirect_stdout(buffer):
            code = main(["check", str(EXAMPLES / "stale_send.jsonl")])
        self.assertEqual(code, 1)
        self.assertIn("I_COMPLETION_AFTER_FREE", buffer.getvalue())
        self.assertIn("FAIL", buffer.getvalue())

    def test_json_format_and_report_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            buffer = StringIO()
            with redirect_stdout(buffer):
                code = main(
                    [
                        "check",
                        str(EXAMPLES / "stale_send.jsonl"),
                        "--format",
                        "json",
                        "--report",
                        str(report_path),
                        "--no-fail",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertFalse(payload["pass"])
            self.assertEqual(payload["codes"], ["I_COMPLETION_AFTER_FREE"])
            self.assertEqual(payload["tool"], "kvc-lifecycle")
            self.assertTrue(report_path.exists())
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["trace"], str(EXAMPLES / "stale_send.jsonl"))

    def test_invalid_trace_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.jsonl"
            bad.write_text("not json\n", encoding="utf-8")
            code = main(["check", str(bad)])
            self.assertEqual(code, 2)

    def test_scoped_trace_scope_changes_verdict(self) -> None:
        # The trace has two children sharing one request. Bare identity reports
        # a duplicate; child-scoped identity does not.
        buffer = StringIO()
        with redirect_stdout(buffer):
            bare = main(
                [
                    "check",
                    str(EXAMPLES / "scoped_children.jsonl"),
                    "--identity-scope",
                    "request",
                    "--no-fail",
                ]
            )
        self.assertEqual(bare, 0)
        self.assertIn("I_SEND_DUPLICATE", buffer.getvalue())

        buffer = StringIO()
        with redirect_stdout(buffer):
            scoped = main(
                [
                    "check",
                    str(EXAMPLES / "scoped_children.jsonl"),
                    "--identity-scope",
                    "child_request_attempt",
                ]
            )
        self.assertEqual(scoped, 0)
        self.assertIn("PASS", buffer.getvalue())

    def test_audit_cli_reports_conflict(self) -> None:
        buffer = StringIO()
        with redirect_stdout(buffer):
            code = main(
                [
                    "audit",
                    str(EXAMPLES / "scoped_children.jsonl"),
                    "--format",
                    "json",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["conflict"])
        self.assertTrue(payload["sensitive"]["identity_scope"])
        self.assertEqual(payload["verdict"], "assumption-sensitive")

        buffer = StringIO()
        with redirect_stdout(buffer):
            code = main(
                [
                    "audit",
                    str(EXAMPLES / "scoped_children.jsonl"),
                    "--fail-on-conflict",
                ]
            )
        self.assertEqual(code, 1)

    def test_codes_and_version(self) -> None:
        buffer = StringIO()
        with redirect_stdout(buffer):
            self.assertEqual(main(["codes"]), 0)
        self.assertIn("I_COMPLETION_AFTER_FREE", buffer.getvalue())
        self.assertIn("I_RECV_NEVER_COMPLETED", buffer.getvalue())

        buffer = StringIO()
        with redirect_stdout(buffer):
            self.assertEqual(main(["version"]), 0)
        self.assertEqual(buffer.getvalue().strip(), "0.8.0")


if __name__ == "__main__":
    unittest.main()








