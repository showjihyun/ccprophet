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

# Hook payloads above this size are dropped silently (AP-3). A legit Claude
# Code hook is a few KB; anything north of 2 MB is a malformed / adversarial
# stream and loading it would stall the hook process or OOM on the hot path.
_MAX_HOOK_BYTES = 2 * 1024 * 1024


def read_hook_payload() -> tuple[str, dict[str, object]] | None:
    try:
        # Read via the binary buffer so we explicitly decode UTF-8 regardless
        # of the shell locale (Windows cp949 / cp1252 would otherwise raise
        # UnicodeDecodeError on non-ASCII tool names or file paths).
        buf = sys.stdin.buffer if hasattr(sys.stdin, "buffer") else None
        if buf is not None:
            data_bytes = buf.read(_MAX_HOOK_BYTES + 1)
            if len(data_bytes) > _MAX_HOOK_BYTES:
                return None  # oversize: drop silently
            raw = data_bytes.decode("utf-8", errors="replace")
        else:
            raw = sys.stdin.read(_MAX_HOOK_BYTES + 1)
            if len(raw) > _MAX_HOOK_BYTES:
                return None
        if not raw.strip():
            return None
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        event_type = _event_type_from(data)
        return event_type, data
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None


def _event_type_from(data: dict[str, object]) -> str:
    for key in ("hook_event_name", "event", "event_type"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown"
