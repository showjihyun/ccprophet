"""Parses Claude Code's per-session JSONL transcripts.

Each line → one primary `JsonlRecord`. Assistant messages that carry `tool_use`
content blocks also emit synthetic `PostToolUse` records so the downstream
analyses (bloat, phase, recommender) see the same tool_calls they would if
the hook had captured them live.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from ccprophet.ports.jsonl import JsonlRecord

TYPE_MAP = {
    "user": "UserPromptSubmit",
    "assistant": "AssistantResponse",
    "permission-mode": "PermissionMode",
    "file-history-snapshot": "FileHistorySnapshot",
    "system": "SystemEvent",
}


class JsonlReader:
    def read_file(self, path: Path) -> Iterator[JsonlRecord]:
        with open(path, "rb") as fh:
            for raw_line in fh:
                record = self._parse_line(raw_line)
                if record is None:
                    continue
                yield record
                yield from self._synthetic_tool_uses(record)

    @staticmethod
    def _parse_line(raw_line: bytes) -> JsonlRecord | None:
        stripped = raw_line.strip()
        if not stripped:
            return None
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None

        session_id = _str_or_none(data.get("sessionId"))
        if not session_id:
            return None

        raw_type = _str_or_none(data.get("type")) or "unknown"
        ts = _parse_timestamp(data.get("timestamp"))
        if ts is None:
            return None

        raw_uuid = _str_or_none(data.get("uuid")) or hashlib.sha256(stripped).hexdigest()[:16]
        raw_hash = hashlib.sha256(stripped).hexdigest()

        return JsonlRecord(
            raw_hash_hex=raw_hash,
            session_id=session_id,
            event_type=TYPE_MAP.get(raw_type, raw_type),
            ts=ts,
            uuid=raw_uuid,
            payload=data,
        )

    @staticmethod
    def _synthetic_tool_uses(record: JsonlRecord) -> Iterator[JsonlRecord]:
        if record.event_type != "AssistantResponse":
            return
        message = record.payload.get("message")
        if not isinstance(message, dict):
            return
        content = message.get("content")
        if not isinstance(content, list):
            return

        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            block_id = _str_or_none(block.get("id")) or record.uuid
            tool_name = _str_or_none(block.get("name")) or "unknown"
            tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
            synthetic_payload: dict[str, object] = {
                "session_id": record.session_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "parent_uuid": record.uuid,
            }
            raw_hash = hashlib.sha256(
                f"{record.raw_hash_hex}::{block_id}".encode()
            ).hexdigest()
            yield JsonlRecord(
                raw_hash_hex=raw_hash,
                session_id=record.session_id,
                event_type="PostToolUse",
                ts=record.ts,
                uuid=block_id,
                payload=synthetic_payload,
            )


def _str_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
