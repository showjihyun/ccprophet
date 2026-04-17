from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from ccprophet.domain.entities import ToolDef
from ccprophet.domain.services.postmortem import (
    PostmortemAnalyzer,
    PostmortemInputs,
)
from ccprophet.domain.values import SessionId, TaskType, TokenCount
from tests.fixtures.builders import SessionBuilder, ToolCallBuilder


def _session(sid: str, *, compacted: bool = False):
    return replace(SessionBuilder().with_id(sid).build(), compacted=compacted)


def test_no_findings_when_failed_matches_cluster() -> None:
    failed = _session("fail")
    successes = tuple(_session(f"ok-{i}") for i in range(3))
    inputs = PostmortemInputs(
        failed_session=failed,
        task_type=TaskType("t"),
        failed_tool_calls=[],
        failed_tool_defs=[],
        success_sessions=successes,
        success_tool_calls={s.session_id.value: [] for s in successes},
        success_tool_defs={s.session_id.value: [] for s in successes},
    )
    report = PostmortemAnalyzer.analyze(inputs)
    assert report.findings == ()


def test_task_overrun_detected() -> None:
    failed = _session("fail")
    successes = tuple(_session(f"ok-{i}") for i in range(3))
    failed_calls = [
        ToolCallBuilder().in_session(SessionId("fail")).for_tool("Task").build()
        for _ in range(5)
    ]
    inputs = PostmortemInputs(
        failed_session=failed,
        task_type=TaskType("t"),
        failed_tool_calls=failed_calls,
        failed_tool_defs=[],
        success_sessions=successes,
        success_tool_calls={s.session_id.value: [] for s in successes},
        success_tool_defs={s.session_id.value: [] for s in successes},
    )
    report = PostmortemAnalyzer.analyze(inputs)
    assert any(f.kind == "task_overrun" for f in report.findings)


def test_unused_mcp_detected() -> None:
    failed = _session("fail")
    tool_defs = [
        ToolDef("mcp__linear_y", TokenCount(400), "mcp:linear"),
        ToolDef("mcp__github_x", TokenCount(500), "mcp:github"),
    ]
    calls = [
        ToolCallBuilder()
        .in_session(SessionId("fail"))
        .for_tool("mcp__github_x")
        .build()
    ]
    inputs = PostmortemInputs(
        failed_session=failed,
        task_type=TaskType("t"),
        failed_tool_calls=calls,
        failed_tool_defs=tool_defs,
        success_sessions=(),
        success_tool_calls={},
        success_tool_defs={},
    )
    report = PostmortemAnalyzer.analyze(inputs)
    assert any(f.kind == "unused_mcp" and "linear" in f.detail for f in report.findings)


def test_compacted_failed_yields_clear_suggestion() -> None:
    failed = _session("fail", compacted=True)
    inputs = PostmortemInputs(
        failed_session=failed,
        task_type=None,
        failed_tool_calls=[],
        failed_tool_defs=[],
        success_sessions=(),
        success_tool_calls={},
        success_tool_defs={},
    )
    report = PostmortemAnalyzer.analyze(inputs)
    assert any("clear" in s.lower() for s in report.suggestions)
