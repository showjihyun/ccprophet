"""Replay timeline shaper for PRD F9 (Session Replay).

Split from ``shapers.py`` to respect AP-5 (≤300 LOC per file). Converts an
already-ingested session's phases + tool_calls into a time-ordered event
stream plus per-step node-visibility snapshots that the Web DAG viewer can
scrub through without re-executing anything (FR-9.1).
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from ccprophet.adapters.web.shapers import iso, session_to_dict
from ccprophet.domain.entities import BloatReport, Phase, Session, ToolCall

# Highlight timeline steps whose proxy bloat ratio jumps by more than this
# delta versus the previous step. Used to draw slider tick marks (PRD F9).
BLOAT_SPIKE_DELTA = 0.05


def _phase_for_ts(ts: datetime, phases: list[Phase]) -> Phase | None:
    for p in phases:
        if ts >= p.start_ts and (p.end_ts is None or ts <= p.end_ts):
            return p
    return None


def _event_stream(
    phases: list[Phase], tool_calls: list[ToolCall]
) -> list[tuple[datetime, str, dict[str, Any]]]:
    """Merge phases + tool_calls into a stable chronological stream.

    Tie-break order at equal ``ts``: phase_start < tool_call < phase_end so
    that a tool call appears under the phase it belongs to even if the phase
    boundary shares its timestamp.
    """
    events: list[tuple[datetime, str, dict[str, Any]]] = []
    for p in phases:
        events.append((p.start_ts, "phase_start", {"phase": p}))
        if p.end_ts is not None:
            events.append((p.end_ts, "phase_end", {"phase": p}))
    for tc in tool_calls:
        events.append((tc.ts, "tool_call", {"tool_call": tc}))
    rank = {"phase_start": 0, "tool_call": 1, "phase_end": 2}
    events.sort(key=lambda row: (row[0], rank[row[1]]))
    return events


def build_replay(
    session: Session,
    phases: list[Phase],
    tool_calls: Iterable[ToolCall],
    bloat_report: BloatReport,
) -> dict[str, Any]:
    """Timeline + per-step node visibility for the Replay viewer (PRD F9).

    The payload is derived *purely from already-ingested events* (FR-9.1).
    Snapshots are pre-computed server-side so the slider can seek in O(1).

    Nodes are identified by the same id scheme as :func:`build_dag`
    (``session:<sid>`` / ``phase:<pid>`` / ``tool:<tcid>``) so the UI can
    toggle opacity on the existing force-simulation graph without rebuilding
    it.

    ``bloat_ratio_at`` is a cheap proxy — ``final_ratio * (cumulative_tokens
    / total_tokens)``. Refining it per step would mean re-running
    :class:`BloatCalculator` for each slice, which is not worth the cost for
    a UI-only hint; the *final* number still matches the bloat endpoint.
    """
    sid = session.session_id.value
    calls_sorted = sorted(tool_calls, key=lambda t: t.ts)
    phases_sorted = sorted(phases, key=lambda p: p.start_ts)
    events = _event_stream(phases_sorted, calls_sorted)

    total_tokens = max(bloat_report.total_tokens.value, 1)
    final_ratio = bloat_report.bloat_ratio.value

    # Session node is visible from t=0; phase/tool nodes appear at their ts.
    visible: set[str] = {f"session:{sid}"}

    timeline: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    cumulative = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None

    for ts, kind, payload in events:
        first_ts = first_ts if first_ts is not None else ts
        last_ts = ts
        entry: dict[str, Any] = {
            "ts": iso(ts),
            "kind": kind,
            "phase_id": None,
            "phase_type": None,
            "tool_name": None,
            "tool_call_id": None,
            "tokens": 0,
            "cumulative_tokens": cumulative,
            "bloat_ratio_at": None,
        }
        if kind in ("phase_start", "phase_end"):
            p: Phase = payload["phase"]
            entry["phase_id"] = p.phase_id
            entry["phase_type"] = p.phase_type.value
            if kind == "phase_start":
                visible.add(f"phase:{p.phase_id}")
        else:
            tc: ToolCall = payload["tool_call"]
            tc_tokens = tc.input_tokens.value + tc.output_tokens.value
            cumulative += tc_tokens
            entry["tool_name"] = tc.tool_name
            entry["tool_call_id"] = tc.tool_call_id
            entry["tokens"] = tc_tokens
            entry["cumulative_tokens"] = cumulative
            bucket = _phase_for_ts(tc.ts, phases_sorted)
            if bucket is not None:
                entry["phase_id"] = bucket.phase_id
                entry["phase_type"] = bucket.phase_type.value
                visible.add(f"phase:{bucket.phase_id}")
            visible.add(f"tool:{tc.tool_call_id}")

        entry["bloat_ratio_at"] = round(
            final_ratio * min(cumulative / total_tokens, 1.0), 4
        )
        timeline.append(entry)
        snapshots.append(
            {"ts": iso(ts), "visible_node_ids": sorted(visible)}
        )

    # Delta markers — UI can draw a spike tick on the slider at these steps.
    prev_ratio = 0.0
    for step in timeline:
        ratio = step["bloat_ratio_at"] or 0.0
        step["bloat_spike"] = (ratio - prev_ratio) >= BLOAT_SPIKE_DELTA
        prev_ratio = ratio

    duration = 0.0
    if first_ts is not None and last_ts is not None:
        duration = max((last_ts - first_ts).total_seconds(), 0.0)

    return {
        "session": session_to_dict(session),
        "timeline": timeline,
        "node_snapshots": snapshots,
        "total_duration_sec": duration,
        "total_tokens": total_tokens,
        "final_bloat_ratio": final_ratio,
    }
