"""Trace parsing/schema tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kvc_lifecycle.core.trace import TraceError, load_trace, parse_event


class TraceTest(unittest.TestCase):
    def test_parse_request_finished_defaults_delay_free_false(self) -> None:
        event = parse_event({"event": "request_finished", "request_id": "r"})
        self.assertEqual(
            event,
            {
                "event": "request_finished",
                "request_id": "r",
                "child": "",
                "attempt": 0,
                "delay_free": False,
            },
        )

    def test_parse_request_finished_scoped_fields(self) -> None:
        event = parse_event(
            {
                "event": "request_finished",
                "request_id": "r",
                "child": "c1",
                "attempt": 2,
                "delay_free": True,
            }
        )
        self.assertEqual(event["child"], "c1")
        self.assertEqual(event["attempt"], 2)
        self.assertTrue(event["delay_free"])

    def test_parse_observe_normalizes_none_to_empty(self) -> None:
        event = parse_event({"event": "observe", "sending": None, "recving": ["r"]})
        self.assertEqual(event["sending"], [])
        self.assertEqual(event["recving"], ["r"])

    def test_parse_observe_accepts_scoped_operations(self) -> None:
        event = parse_event(
            {
                "event": "observe",
                "sending": [{"request_id": "r", "child": "c1", "attempt": 2}],
                "recving": [],
            }
        )
        self.assertEqual(event["sending"][0]["child"], "c1")
        self.assertEqual(event["sending"][0]["attempt"], 2)

    def test_parse_observe_rejects_bad_operation(self) -> None:
        with self.assertRaises(TraceError):
            parse_event({"event": "observe", "sending": [{"child": "c1"}], "recving": []})

    def test_unknown_event_rejected(self) -> None:
        with self.assertRaises(TraceError):
            parse_event({"event": "nope"})

    def test_non_string_id_rejected(self) -> None:
        with self.assertRaises(TraceError):
            parse_event({"event": "free", "request_id": 3})

    def test_negative_attempt_rejected(self) -> None:
        with self.assertRaises(TraceError):
            parse_event({"event": "free", "request_id": "r", "attempt": -1})

    def test_load_trace_ignores_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            path.write_text(
                '{"event": "free", "request_id": "r"}\n\n'
                '{"event": "observe", "sending": ["r"], "recving": []}\n',
                encoding="utf-8",
            )
            events = load_trace(path)
            self.assertEqual(len(events), 2)

    def test_load_trace_missing_file(self) -> None:
        with self.assertRaises(TraceError):
            load_trace("does-not-exist.jsonl")

    def test_load_trace_invalid_json_reports_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            path.write_text('{"event": "free" "request_id": "r"}\n', encoding="utf-8")
            with self.assertRaises(TraceError) as ctx:
                load_trace(path)
            self.assertIn("line 1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
