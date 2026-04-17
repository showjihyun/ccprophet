"""Hook payload reader.

Claude Code pipes a JSON blob on stdin. The actual schema (per official docs)
is rooted at keys like `hook_event_name`, `session_id`, `tool_name`,
`tool_input`, `tool_response`. Older/custom invocations may use `event` — we
fall back to that. Returns None on blank stdin or parse error so the hook
process silently exits (AP-3).
"""
from __future__ import annotations

import json
import sys


def read_hook_payload() -> tuple[str, dict[str, object]] | None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return None
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        event_type = _event_type_from(data)
        return event_type, data
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _event_type_from(data: dict[str, object]) -> str:
    for key in ("hook_event_name", "event", "event_type"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown"
