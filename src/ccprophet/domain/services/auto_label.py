"""Heuristic classifier that maps (session, tool_calls) → OutcomeLabelValue.

Pure domain: no IO. The use case supplies the tool calls it already fetched.

Returns `None` when no rule matches confidently. We prefer "don't label" to
"mislabel" — users manually override anything we got wrong, and the
downstream Outcome Engine tolerates unlabeled sessions.

Rules (conservative):

- **success** — session is finished (ended_at set), not compacted, ran at least
  N meaningful tool calls, and tool-call success rate ≥ 0.9.
- **fail** — session was compacted, or tool-call success rate dropped below 0.5
  with ≥ 10 calls, or repeat-read rate crossed the quality threshold.
- **None** — session still active, too few tool calls, or signals conflict.
"""
from __future__ import annotations

from collections.abc import Sequence

from ccprophet.domain.entities import Session, ToolCall
from ccprophet.domain.services.quality import READ_TOOLS, REPEAT_READ_THRESHOLD
from ccprophet.domain.values import OutcomeLabelValue

MIN_CALLS_FOR_SUCCESS = 5
MIN_CALLS_FOR_FAIL = 10
SUCCESS_RATE_FLOOR = 0.9
FAIL_RATE_CEILING = 0.5


def classify(session: Session, tool_calls: Sequence[ToolCall]) -> OutcomeLabelValue | None:
    if session.is_active:
        return None

    total = len(tool_calls)
    if session.compacted:
        return OutcomeLabelValue.FAIL

    if total < MIN_CALLS_FOR_SUCCESS:
        return None

    success_rate = sum(1 for tc in tool_calls if tc.success) / total

    if total >= MIN_CALLS_FOR_FAIL and success_rate < FAIL_RATE_CEILING:
        return OutcomeLabelValue.FAIL

    if _has_repeat_reads(tool_calls):
        return OutcomeLabelValue.FAIL

    if success_rate >= SUCCESS_RATE_FLOOR:
        return OutcomeLabelValue.SUCCESS

    return None


def _has_repeat_reads(calls: Sequence[ToolCall]) -> bool:
    counts: dict[str, int] = {}
    for tc in calls:
        if tc.tool_name not in READ_TOOLS:
            continue
        counts[tc.input_hash] = counts.get(tc.input_hash, 0) + 1
        if counts[tc.input_hash] >= REPEAT_READ_THRESHOLD:
            return True
    return False
