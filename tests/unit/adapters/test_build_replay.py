"""Unit tests for the replay JSON shaper (PRD F9)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import pairwise

from ccprophet.adapters.web.replay_shaper import BLOAT_SPIKE_DELTA, build_replay
from ccprophet.domain.entities import BloatReport, Phase, ToolCall
from ccprophet.domain.values import (
    BloatRatio,
    PhaseType,
    SessionId,
    TokenCount,
)
from tests.fixtures.builders import SessionBuilder, ToolCallBuilder

T0 = datetime(2026, 4, 16, 9, 0, 0, tzinfo=timezone.utc)


def _empty_bloat(total: int = 1000, ratio: float = 0.25) -> BloatReport:
    return BloatReport(
        items=(),
        total_tokens=TokenCount(total),
        bloat_tokens=TokenCount(int(total * ratio)),
        bloat_ratio=BloatRatio(ratio),
        used_sources=frozenset({"system"}),
    )


def _phase(sid: str, ptype: PhaseType, start: datetime, end: datetime) -> Phase:
    return Phase(
        phase_id=f"p-{sid}-{ptype.value}-{int(start.timestamp())}",
        session_id=SessionId(sid),
        phase_type=ptype,
        start_ts=start,
        end_ts=end,
    )


def _tc(sid: str, name: str, ts: datetime, tokens: int = 100) -> ToolCall:
    return ToolCall(
        tool_call_id=f"tc-{name}-{int(ts.timestamp())}",
        session_id=SessionId(sid),
        tool_name=name,
        input_hash="h",
        ts=ts,
        input_tokens=TokenCount(tokens // 2),
        output_tokens=TokenCount(tokens // 2),
    )


def test_build_replay_returns_expected_top_level_keys() -> None:
    session = SessionBuilder().with_id("s1").build()

    payload = build_replay(session, [], [], _empty_bloat(total=1, ratio=0.0))

    assert set(payload.keys()) >= {
        "session",
        "timeline",
        "node_snapshots",
        "total_duration_sec",
        "total_tokens",
        "final_bloat_ratio",
    }
    assert payload["session"]["session_id"] == "s1"
    assert payload["timeline"] == []
    assert payload["node_snapshots"] == []
    assert payload["total_duration_sec"] == 0.0


def test_timeline_orders_phase_start_before_tool_call_at_same_ts() -> None:
    session = SessionBuilder().with_id("s1").build()
    phase = _phase("s1", PhaseType.PLANNING, T0, T0 + timedelta(minutes=5))
    call = _tc("s1", "Read", T0)  # same ts as phase start

    payload = build_replay(session, [phase], [call], _empty_bloat())

    kinds = [step["kind"] for step in payload["timeline"]]
    # phase_start sorted before tool_call at equal ts, phase_end last
    assert kinds == ["phase_start", "tool_call", "phase_end"]


def test_cumulative_tokens_are_monotonically_non_decreasing() -> None:
    session = SessionBuilder().with_id("s1").build()
    phase = _phase("s1", PhaseType.PLANNING, T0, T0 + timedelta(minutes=10))
    calls = [
        _tc("s1", "Read", T0 + timedelta(minutes=1), tokens=100),
        _tc("s1", "Edit", T0 + timedelta(minutes=2), tokens=200),
        _tc("s1", "Bash", T0 + timedelta(minutes=3), tokens=50),
    ]

    payload = build_replay(session, [phase], calls, _empty_bloat(total=1000))

    cumulative = [step["cumulative_tokens"] for step in payload["timeline"]]
    assert cumulative == sorted(cumulative)


def test_total_duration_sec_matches_span() -> None:
    session = SessionBuilder().with_id("s1").build()
    phase = _phase("s1", PhaseType.PLANNING, T0, T0 + timedelta(seconds=120))

    payload = build_replay(session, [phase], [], _empty_bloat())

    assert payload["total_duration_sec"] == 120.0


def test_node_snapshots_grow_monotonically() -> None:
    session = SessionBuilder().with_id("s1").build()
    phase = _phase("s1", PhaseType.IMPLEMENTATION, T0, T0 + timedelta(minutes=3))
    calls = [
        _tc("s1", "Read", T0 + timedelta(seconds=10)),
        _tc("s1", "Edit", T0 + timedelta(seconds=20)),
    ]

    payload = build_replay(session, [phase], calls, _empty_bloat())

    snaps = [set(s["visible_node_ids"]) for s in payload["node_snapshots"]]
    for prev, curr in pairwise(snaps):
        assert prev.issubset(curr), f"snapshot shrank: {prev} -> {curr}"
    # Final snapshot contains session + phase + all tool calls
    assert f"session:{session.session_id.value}" in snaps[-1]
    assert any(nid.startswith("phase:") for nid in snaps[-1])
    assert sum(1 for nid in snaps[-1] if nid.startswith("tool:")) == 2


def test_timeline_is_sorted_by_ts_ascending() -> None:
    session = SessionBuilder().with_id("s1").build()
    phase = _phase("s1", PhaseType.PLANNING, T0, T0 + timedelta(minutes=10))
    # Intentionally out of order
    calls = [
        _tc("s1", "Late", T0 + timedelta(minutes=5)),
        _tc("s1", "Early", T0 + timedelta(minutes=1)),
    ]

    payload = build_replay(session, [phase], calls, _empty_bloat())

    stamps = [step["ts"] for step in payload["timeline"]]
    assert stamps == sorted(stamps)


def test_bloat_ratio_at_never_exceeds_final_ratio() -> None:
    session = SessionBuilder().with_id("s1").build()
    phase = _phase("s1", PhaseType.PLANNING, T0, T0 + timedelta(minutes=10))
    calls = [
        _tc("s1", "A", T0 + timedelta(minutes=1), tokens=200),
        _tc("s1", "B", T0 + timedelta(minutes=2), tokens=300),
    ]

    payload = build_replay(session, [phase], calls, _empty_bloat(total=1000, ratio=0.4))

    for step in payload["timeline"]:
        assert step["bloat_ratio_at"] <= 0.4 + 1e-9


def test_bloat_spike_flag_is_set_when_delta_exceeds_threshold() -> None:
    session = SessionBuilder().with_id("s1").build()
    # One giant call will jump the proxy ratio from 0 -> large
    phase = _phase("s1", PhaseType.PLANNING, T0, T0 + timedelta(minutes=5))
    calls = [_tc("s1", "Huge", T0 + timedelta(minutes=1), tokens=800)]

    payload = build_replay(session, [phase], calls, _empty_bloat(total=1000, ratio=0.5))

    spikes = [s for s in payload["timeline"] if s["bloat_spike"]]
    assert spikes, "expected at least one bloat_spike"
    # threshold constant is re-exported for the UI
    assert 0.0 < BLOAT_SPIKE_DELTA < 1.0


def test_tool_call_outside_any_phase_has_null_phase_id() -> None:
    session = SessionBuilder().with_id("s1").build()
    phase = _phase(
        "s1",
        PhaseType.PLANNING,
        T0,
        T0 + timedelta(minutes=1),
    )
    orphan = _tc("s1", "Orphan", T0 + timedelta(minutes=10))

    payload = build_replay(session, [phase], [orphan], _empty_bloat())

    orphan_step = next(s for s in payload["timeline"] if s["tool_name"] == "Orphan")
    assert orphan_step["phase_id"] is None


def test_node_ids_use_dag_id_scheme() -> None:
    """UI toggles opacity on the existing DAG graph, so ids must match."""
    session = SessionBuilder().with_id("sX").build()
    phase = _phase("sX", PhaseType.PLANNING, T0, T0 + timedelta(minutes=1))
    call = (
        ToolCallBuilder().in_session("sX").for_tool("Read").at(T0 + timedelta(seconds=30)).build()
    )

    payload = build_replay(session, [phase], [call], _empty_bloat())

    all_ids: set[str] = set()
    for snap in payload["node_snapshots"]:
        all_ids.update(snap["visible_node_ids"])
    assert "session:sX" in all_ids
    assert any(nid.startswith("phase:") for nid in all_ids)
    assert f"tool:{call.tool_call_id}" in all_ids
