"""Phase detection heuristic.

Splits a session's event stream into phases along UserPromptSubmit boundaries,
then classifies each segment per docs/DATAMODELING.md §4.6.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from ccprophet.domain.entities import Event, Phase
from ccprophet.domain.values import PhaseType, SessionId, TokenCount

EDIT_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})
READ_TOOLS = frozenset({"Read", "Glob", "Grep"})
PROMPT_EVENTS = frozenset({"UserPromptSubmit", "SessionStart"})
TOOL_USE_EVENT = "PostToolUse"


@dataclass(frozen=True, slots=True)
class _Segment:
    session_id: SessionId
    events: tuple[Event, ...]


class PhaseDetector:
    @staticmethod
    def detect(events: Sequence[Event]) -> list[Phase]:
        if not events:
            return []

        ordered = sorted(events, key=lambda e: e.ts)
        sid = ordered[0].session_id
        segments = _segment_by_prompt(sid, ordered)
        return [_classify(seg) for seg in segments]


def _segment_by_prompt(sid: SessionId, events: Sequence[Event]) -> list[_Segment]:
    segments: list[_Segment] = []
    current: list[Event] = []
    for e in events:
        if e.event_type in PROMPT_EVENTS and current:
            segments.append(_Segment(sid, tuple(current)))
            current = []
        current.append(e)
    if current:
        segments.append(_Segment(sid, tuple(current)))
    return segments


def _classify(segment: _Segment) -> Phase:
    start = segment.events[0].ts
    end = segment.events[-1].ts

    tool_calls = _extract_tool_calls(segment.events)
    names = [name for name, _ in tool_calls]
    counts = {
        "edit": sum(1 for n in names if n in EDIT_TOOLS),
        "read": sum(1 for n in names if n in READ_TOOLS),
        "bash": sum(1 for n in names if n == "Bash"),
        "task": sum(1 for n in names if n == "Task"),
    }
    total = len(names)
    ptype, confidence = _pick_phase_type(counts, total, tool_calls)

    return Phase(
        phase_id=str(uuid.uuid4()),
        session_id=segment.session_id,
        phase_type=ptype,
        start_ts=start,
        end_ts=end,
        input_tokens=TokenCount(0),
        output_tokens=TokenCount(0),
        tool_call_count=total,
        detection_confidence=confidence,
    )


def _extract_tool_calls(events: Sequence[Event]) -> list[tuple[str, str | None]]:
    calls: list[tuple[str, str | None]] = []
    for e in events:
        if e.event_type != TOOL_USE_EVENT:
            continue
        name = e.payload.get("tool_name")
        if not isinstance(name, str):
            continue
        raw_input = e.payload.get("tool_input")
        file_path = None
        if isinstance(raw_input, dict):
            fp = raw_input.get("file_path") or raw_input.get("path")
            if isinstance(fp, str):
                file_path = fp
        calls.append((name, file_path))
    return calls


def _pick_phase_type(
    counts: dict[str, int],
    total: int,
    tool_calls: Sequence[tuple[str, str | None]],
) -> tuple[PhaseType, float]:
    if total == 0:
        return PhaseType.PLANNING, 0.4

    if counts["task"] > 0 and counts["edit"] == 0:
        return PhaseType.PLANNING, 0.8

    if _has_repeat_reads(tool_calls) and counts["bash"] > 0:
        return PhaseType.DEBUGGING, 0.75

    edit_ratio = counts["edit"] / total
    if edit_ratio >= 0.3:
        return PhaseType.IMPLEMENTATION, 0.8

    if counts["read"] > 0 and counts["edit"] == 0:
        return PhaseType.REVIEW, 0.6

    return PhaseType.UNKNOWN, 0.3


def _has_repeat_reads(tool_calls: Sequence[tuple[str, str | None]]) -> bool:
    seen: dict[str, int] = {}
    for name, path in tool_calls:
        if name not in READ_TOOLS or path is None:
            continue
        seen[path] = seen.get(path, 0) + 1
        if seen[path] >= 2:
            return True
    return False
