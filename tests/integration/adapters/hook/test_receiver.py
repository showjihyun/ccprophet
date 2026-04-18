from __future__ import annotations

import io
import json

from ccprophet.adapters.hook.receiver import read_hook_payload


def _stdin(monkeypatch, data: str) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("sys.stdin", io.StringIO(data))


def test_reads_hook_event_name(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _stdin(
        monkeypatch,
        json.dumps(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "s-1",
                "tool_name": "Read",
                "tool_input": {"file_path": "/x.py"},
            }
        ),
    )
    result = read_hook_payload()
    assert result is not None
    event_type, payload = result
    assert event_type == "PostToolUse"
    assert payload["session_id"] == "s-1"


def test_falls_back_to_legacy_event_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _stdin(
        monkeypatch,
        json.dumps({"event": "Stop", "session_id": "s-2"}),
    )
    result = read_hook_payload()
    assert result is not None
    assert result[0] == "Stop"


def test_blank_stdin_returns_none(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _stdin(monkeypatch, "")
    assert read_hook_payload() is None


def test_invalid_json_returns_none(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _stdin(monkeypatch, "{not json")
    assert read_hook_payload() is None


def test_non_object_payload_returns_none(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _stdin(monkeypatch, json.dumps([1, 2, 3]))
    assert read_hook_payload() is None


def test_missing_event_fields_defaults_to_unknown(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _stdin(monkeypatch, json.dumps({"session_id": "s-3"}))
    result = read_hook_payload()
    assert result is not None
    assert result[0] == "unknown"
