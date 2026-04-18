from __future__ import annotations

from dataclasses import replace

import pytest

from ccprophet.domain.entities import ToolDef
from ccprophet.domain.errors import InsufficientSamples
from ccprophet.domain.services.cluster import (
    BestConfigExtractor,
    ClusterInputs,
    SessionClusterer,
)
from ccprophet.domain.values import SessionId, TaskType, TokenCount
from tests.fixtures.builders import SessionBuilder, ToolCallBuilder


def _session(sid: str, *, compacted: bool = False, project: str = "p1",
             model: str = "claude-opus-4-6", input_tok: int = 100_000,
             output_tok: int = 10_000):
    base = SessionBuilder().with_id(sid).build()
    return replace(
        base,
        project_slug=project,
        model=model,
        compacted=compacted,
        total_input_tokens=TokenCount(input_tok),
        total_output_tokens=TokenCount(output_tok),
    )


def test_find_similar_filters_by_project_and_model() -> None:
    sessions = [
        _session("a", project="p1", model="claude-opus-4-6"),
        _session("b", project="p2", model="claude-opus-4-6"),
        _session("c", project="p1", model="claude-sonnet-4-6"),
    ]
    got = SessionClusterer.find_similar(
        sessions, project_slug="p1", model="claude-opus-4-6"
    )
    assert [s.session_id.value for s in got] == ["a"]


def test_extract_raises_when_fewer_than_min_samples() -> None:
    sessions = (_session("a"), _session("b"))
    inputs = ClusterInputs(
        task_type=TaskType("refactor"),
        sessions=sessions,
        tool_calls_by_session={},
        tool_defs_by_session={},
    )
    with pytest.raises(InsufficientSamples):
        BestConfigExtractor.extract(inputs)


def test_common_tools_picked_above_threshold() -> None:
    sessions = tuple(_session(f"s{i}") for i in range(3))
    tool_calls = {
        "s0": [ToolCallBuilder().in_session(SessionId("s0")).for_tool("Read").build()],
        "s1": [ToolCallBuilder().in_session(SessionId("s1")).for_tool("Read").build()],
        "s2": [ToolCallBuilder().in_session(SessionId("s2")).for_tool("Bash").build()],
    }
    inputs = ClusterInputs(
        task_type=TaskType("t"),
        sessions=sessions,
        tool_calls_by_session=tool_calls,
        tool_defs_by_session={},
    )
    cfg = BestConfigExtractor.extract(inputs)
    assert "Read" in cfg.common_tools
    assert "Bash" not in cfg.common_tools


def test_dropped_mcps_are_loaded_but_underused() -> None:
    sessions = tuple(_session(f"s{i}") for i in range(3))
    tool_defs = {
        sid: [
            ToolDef("mcp__github_x", TokenCount(500), "mcp:github"),
            ToolDef("mcp__linear_y", TokenCount(400), "mcp:linear"),
        ]
        for sid in ("s0", "s1", "s2")
    }
    tool_calls = {
        "s0": [
            ToolCallBuilder().in_session(SessionId("s0")).for_tool("mcp__github_x").build()
        ],
        "s1": [
            ToolCallBuilder().in_session(SessionId("s1")).for_tool("mcp__github_x").build()
        ],
        "s2": [
            ToolCallBuilder().in_session(SessionId("s2")).for_tool("mcp__github_x").build()
        ],
    }
    inputs = ClusterInputs(
        task_type=TaskType("t"),
        sessions=sessions,
        tool_calls_by_session=tool_calls,
        tool_defs_by_session=tool_defs,
    )
    cfg = BestConfigExtractor.extract(inputs)
    assert "linear" in cfg.dropped_mcps  # never called
    assert "github" not in cfg.dropped_mcps  # used in all sessions


def test_autocompact_hit_rate() -> None:
    sessions = (
        _session("a", compacted=True),
        _session("b", compacted=False),
        _session("c", compacted=True),
    )
    inputs = ClusterInputs(
        task_type=TaskType("t"),
        sessions=sessions,
        tool_calls_by_session={},
        tool_defs_by_session={},
    )
    cfg = BestConfigExtractor.extract(inputs)
    assert cfg.autocompact_hit_rate == pytest.approx(2 / 3)


def test_averages_token_counts() -> None:
    sessions = (
        _session("a", input_tok=100_000, output_tok=10_000),
        _session("b", input_tok=200_000, output_tok=20_000),
        _session("c", input_tok=300_000, output_tok=30_000),
    )
    inputs = ClusterInputs(
        task_type=TaskType("t"),
        sessions=sessions,
        tool_calls_by_session={},
        tool_defs_by_session={},
    )
    cfg = BestConfigExtractor.extract(inputs)
    assert cfg.avg_input_tokens == TokenCount(200_000)
    assert cfg.avg_output_tokens == TokenCount(20_000)
