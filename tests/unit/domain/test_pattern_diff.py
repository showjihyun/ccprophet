"""Unit tests for :class:`PatternDiffAnalyzer` (PRD F9 / FR-9.3).

Each test pins a single rule. Builders are reused from
``tests/fixtures/builders.py`` to keep setup light.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ccprophet.domain.services.pattern_diff import (
    PatternDiffAnalyzer,
    PatternFinding,
)
from ccprophet.domain.values import PhaseType, SessionId, TokenCount
from tests.fixtures.builders import (
    PhaseBuilder,
    SessionBuilder,
    ToolCallBuilder,
    ToolDefBuilder,
)

T0 = datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc)


def _session(sid: str, *, input_tokens: int = 1000, compacted: bool = False):
    base = SessionBuilder().with_id(sid).build()
    return replace(
        base,
        total_input_tokens=TokenCount(input_tokens),
        compacted=compacted,
    )


def _tc(sid: str, name: str, *, input_hash: str = "h", seconds: int = 0):
    return replace(
        ToolCallBuilder().in_session(sid).for_tool(name).build(),
        input_hash=input_hash,
        ts=T0 + timedelta(seconds=seconds),
    )


def _phase(sid: str, ptype: PhaseType, *, minute: int = 0):
    return replace(
        PhaseBuilder().in_session(sid).of_type(ptype).build(),
        start_ts=T0 + timedelta(minutes=minute),
        end_ts=T0 + timedelta(minutes=minute + 1),
    )


def _analyze(a, b, *, calls_a=(), calls_b=(), defs_a=(), defs_b=(),
             phases_a=(), phases_b=()):
    return PatternDiffAnalyzer.analyze(
        a=a,
        b=b,
        calls_a=calls_a,
        calls_b=calls_b,
        defs_a=defs_a,
        defs_b=defs_b,
        phases_a=phases_a,
        phases_b=phases_b,
    )


def _kinds(findings):
    return {f.kind for f in findings}


# --- Rule 1: token delta -------------------------------------------------------


def test_token_delta_fires_on_50pct_relative_change():
    a = _session("sa", input_tokens=1000)
    b = _session("sb", input_tokens=1600)  # +60%
    report = _analyze(a, b)
    kinds = {f.kind for f in report.findings}
    assert "token_delta" in kinds
    td = next(f for f in report.findings if f.kind == "token_delta")
    assert td.severity == "warn"  # 60% falls in [50%, 100%)


def test_token_delta_critical_when_doubled_or_more():
    a = _session("sa", input_tokens=500)
    b = _session("sb", input_tokens=1200)  # +140%
    report = _analyze(a, b)
    td = next(f for f in report.findings if f.kind == "token_delta")
    assert td.severity == "critical"


def test_token_delta_silent_below_threshold():
    a = _session("sa", input_tokens=1000)
    b = _session("sb", input_tokens=1100)  # +10%, below 25%
    report = _analyze(a, b)
    assert "token_delta" not in _kinds(report.findings)


# --- Rule 2: autocompact changed ----------------------------------------------


def test_autocompact_change_is_critical():
    a = _session("sa", compacted=False)
    b = _session("sb", compacted=True)
    report = _analyze(a, b)
    ac = next(f for f in report.findings if f.kind == "autocompact_changed")
    assert ac.severity == "critical"


# --- Rule 3: tool mix shift ---------------------------------------------------


def test_tool_mix_shift_fires_on_disjoint_sets():
    a = _session("sa")
    b = _session("sb")
    calls_a = [_tc("sa", "Read"), _tc("sa", "Edit", seconds=1)]
    calls_b = [_tc("sb", "Bash"), _tc("sb", "Grep", seconds=1)]
    report = _analyze(a, b, calls_a=calls_a, calls_b=calls_b)
    shift = next(f for f in report.findings if f.kind == "tool_mix_shift")
    assert shift.severity == "warn"
    assert "Read" in shift.detail
    assert "Bash" in shift.detail


# --- Rule 4: bloat delta -------------------------------------------------------


def test_bloat_delta_warn_when_deterioration():
    a = _session("sa")
    b = _session("sb")
    # A: 1 used, 1 unused small → low bloat.
    defs_a = [
        ToolDefBuilder().named("Read").with_tokens(100).from_source("system").build(),
        ToolDefBuilder().named("unused_a").with_tokens(50).from_source("system").build(),
    ]
    # B: heavy unused MCP → high bloat.
    defs_b = [
        ToolDefBuilder().named("Read").with_tokens(100).from_source("system").build(),
        ToolDefBuilder()
        .named("mcp__heavy").with_tokens(5000).from_source("mcp:jira").build(),
    ]
    calls_a = [_tc("sa", "Read")]
    calls_b = [_tc("sb", "Read")]
    report = _analyze(
        a, b, calls_a=calls_a, calls_b=calls_b, defs_a=defs_a, defs_b=defs_b
    )
    bloat = next(f for f in report.findings if f.kind == "bloat_delta")
    assert bloat.severity == "warn"
    assert "pp" in bloat.detail


# --- Rule 5: MCP subset changed -----------------------------------------------


def test_mcp_subset_changed_reports_exclusive_servers():
    a = _session("sa")
    b = _session("sb")
    defs_a = [
        ToolDefBuilder().named("mcp__gh").with_tokens(100).from_source("mcp:github").build(),
        ToolDefBuilder().named("Read").with_tokens(50).from_source("system").build(),
    ]
    defs_b = [
        ToolDefBuilder().named("mcp__jr").with_tokens(100).from_source("mcp:jira").build(),
        ToolDefBuilder().named("Read").with_tokens(50).from_source("system").build(),
    ]
    calls_a = [_tc("sa", "mcp__gh"), _tc("sa", "Read", seconds=1)]
    calls_b = [_tc("sb", "mcp__jr"), _tc("sb", "Read", seconds=1)]
    report = _analyze(
        a, b, calls_a=calls_a, calls_b=calls_b, defs_a=defs_a, defs_b=defs_b
    )
    subset = next(f for f in report.findings if f.kind == "mcp_subset_changed")
    assert subset.severity == "info"
    assert "github" in subset.detail
    assert "jira" in subset.detail


# --- Rule 6: read-loop delta --------------------------------------------------


def test_read_loop_delta_fires_when_only_one_side_loops():
    a = _session("sa")
    b = _session("sb")
    # A has 5 reads of same hash.
    calls_a = [
        _tc("sa", "Read", input_hash="same", seconds=i) for i in range(5)
    ]
    calls_b = [_tc("sb", "Read", input_hash=f"diff-{i}", seconds=i) for i in range(5)]
    report = _analyze(a, b, calls_a=calls_a, calls_b=calls_b)
    loop = next(f for f in report.findings if f.kind == "read_loop_delta")
    assert loop.severity == "warn"
    assert "A" in loop.detail


# --- Rule 7: phase composition shift ------------------------------------------


def test_phase_shift_fires_on_20pp_or_more():
    a = _session("sa")
    b = _session("sb")
    phases_a = [
        _phase("sa", PhaseType.PLANNING, minute=0),
        _phase("sa", PhaseType.IMPLEMENTATION, minute=2),
        _phase("sa", PhaseType.IMPLEMENTATION, minute=4),
        _phase("sa", PhaseType.IMPLEMENTATION, minute=6),
        _phase("sa", PhaseType.REVIEW, minute=8),
    ]
    phases_b = [
        _phase("sb", PhaseType.DEBUGGING, minute=0),
        _phase("sb", PhaseType.DEBUGGING, minute=2),
        _phase("sb", PhaseType.DEBUGGING, minute=4),
        _phase("sb", PhaseType.DEBUGGING, minute=6),
        _phase("sb", PhaseType.DEBUGGING, minute=8),
    ]
    report = _analyze(a, b, phases_a=phases_a, phases_b=phases_b)
    shift = next(f for f in report.findings if f.kind == "phase_shift")
    assert shift.severity == "info"
    # debugging should be the biggest delta (0 -> 100%).
    assert "debugging" in shift.detail


# --- Headline / empty ---------------------------------------------------------


def test_headline_prefers_critical():
    # autocompact flip (critical) + token delta (warn) both fire; headline
    # must come from the critical finding.
    a = _session("sa", input_tokens=1000, compacted=False)
    b = _session("sb", input_tokens=1700, compacted=True)  # +70% + compaction
    report = _analyze(a, b)
    kinds = _kinds(report.findings)
    assert {"autocompact_changed", "token_delta"}.issubset(kinds)
    critical = next(f for f in report.findings if f.kind == "autocompact_changed")
    assert report.headline == critical.detail


def test_empty_when_identical():
    a = _session("sa", input_tokens=1000)
    b = _session("sb", input_tokens=1000)
    # Same tool-mix, same defs, same phases.
    calls_a = [_tc("sa", "Read")]
    calls_b = [_tc("sb", "Read")]
    defs_a = [ToolDefBuilder().named("Read").with_tokens(100).build()]
    defs_b = [ToolDefBuilder().named("Read").with_tokens(100).build()]
    report = _analyze(
        a, b, calls_a=calls_a, calls_b=calls_b, defs_a=defs_a, defs_b=defs_b
    )
    assert report.findings == ()
    assert report.headline == "No structural deltas detected."
    assert isinstance(report.session_a_id, SessionId)
