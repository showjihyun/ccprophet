from __future__ import annotations

import json

from ccprophet.adapters.filewatch.jsonl_reader import JsonlReader


def _write_lines(path, lines) -> None:  # type: ignore[no-untyped-def]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_skips_blank_and_invalid_lines(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "s.jsonl"
    _write_lines(
        path,
        [
            "",
            "not-json",
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "s-1",
                    "uuid": "u1",
                    "timestamp": "2026-04-17T09:00:00Z",
                    "message": {"role": "user", "content": "hi"},
                }
            ),
        ],
    )
    records = list(JsonlReader().read_file(path))
    assert len(records) == 1
    assert records[0].event_type == "UserPromptSubmit"
    assert records[0].session_id == "s-1"


def test_emits_synthetic_tool_use(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "s.jsonl"
    line = json.dumps(
        {
            "type": "assistant",
            "sessionId": "s-2",
            "uuid": "u-a",
            "timestamp": "2026-04-17T09:01:00Z",
            "message": {
                "content": [
                    {"type": "text", "text": "ok"},
                    {
                        "type": "tool_use",
                        "id": "tc-1",
                        "name": "Read",
                        "input": {"file_path": "/x.py"},
                    },
                ]
            },
        }
    )
    _write_lines(path, [line])
    records = list(JsonlReader().read_file(path))
    assert [r.event_type for r in records] == [
        "AssistantResponse",
        "PostToolUse",
    ]
    tool_rec = records[1]
    assert tool_rec.payload["tool_name"] == "Read"
    assert tool_rec.uuid == "tc-1"
    assert tool_rec.session_id == "s-2"


def test_skips_records_without_session_id(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "s.jsonl"
    _write_lines(
        path,
        [json.dumps({"type": "permission-mode", "permissionMode": "default"})],
    )
    assert list(JsonlReader().read_file(path)) == []


def test_skips_records_without_timestamp(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "s.jsonl"
    _write_lines(
        path,
        [json.dumps({"type": "user", "sessionId": "s-1", "uuid": "u"})],
    )
    assert list(JsonlReader().read_file(path)) == []
