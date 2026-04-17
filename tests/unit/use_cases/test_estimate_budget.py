from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.entities import OutcomeLabel, ToolDef
from ccprophet.domain.errors import InsufficientSamples
from ccprophet.domain.values import (
    OutcomeLabelValue,
    SessionId,
    TaskType,
    TokenCount,
)
from ccprophet.use_cases.estimate_budget import EstimateBudgetUseCase
from tests.fixtures.builders import (
    PricingRateBuilder,
    SessionBuilder,
    ToolCallBuilder,
)


def _seed_success_cluster(
    repos: InMemoryRepositorySet, task: str = "refactor", n: int = 3
) -> None:
    for i in range(n):
        sid = f"s-{i}"
        session = replace(
            SessionBuilder().with_id(sid).build(),
            model="claude-opus-4-6",
            project_slug="p1",
            total_input_tokens=TokenCount(100_000 * (i + 1)),
            total_output_tokens=TokenCount(10_000 * (i + 1)),
        )
        repos.sessions.upsert(session)
        repos.outcomes.set_label(
            OutcomeLabel(
                session_id=SessionId(sid),
                label=OutcomeLabelValue.SUCCESS,
                task_type=TaskType(task),
                source="manual",
                reason=None,
                labeled_at=datetime(2026, 4, 10, tzinfo=timezone.utc),
            )
        )
        repos.tool_calls.append(
            ToolCallBuilder().in_session(SessionId(sid)).for_tool("Read").build()
        )
        repos.tool_defs.bulk_add(
            SessionId(sid),
            [
                ToolDef("mcp__github_x", TokenCount(500), "mcp:github"),
                ToolDef("mcp__linear_y", TokenCount(400), "mcp:linear"),
            ],
        )
    repos.pricing.add(PricingRateBuilder().for_model("claude-opus-4-6").build())


def _uc(repos: InMemoryRepositorySet) -> EstimateBudgetUseCase:
    return EstimateBudgetUseCase(
        outcomes=repos.outcomes,
        tool_calls=repos.tool_calls,
        tool_defs=repos.tool_defs,
        pricing=repos.pricing,
    )


def test_raises_when_fewer_than_3_successes() -> None:
    repos = InMemoryRepositorySet()
    _seed_success_cluster(repos, n=2)
    with pytest.raises(InsufficientSamples):
        _uc(repos).execute(TaskType("refactor"))


def test_envelope_populates_stats_and_risk_flags() -> None:
    repos = InMemoryRepositorySet()
    _seed_success_cluster(repos, n=3)
    env = _uc(repos).execute(TaskType("refactor"))
    assert env.sample_size == 3
    assert env.estimated_input_tokens_mean.value > 0
    assert env.estimated_cost.amount > 0
    # linear is loaded but never called → dropped
    assert "linear" in env.best_config.dropped_mcps
    assert any("MCP" in f for f in env.risk_flags)


def test_picks_only_success_cluster_for_task() -> None:
    repos = InMemoryRepositorySet()
    _seed_success_cluster(repos, task="refactor", n=3)
    # Add a fail session in same task — should be excluded
    repos.sessions.upsert(SessionBuilder().with_id("fail-x").build())
    repos.outcomes.set_label(
        OutcomeLabel(
            session_id=SessionId("fail-x"),
            label=OutcomeLabelValue.FAIL,
            task_type=TaskType("refactor"),
            source="manual",
            reason=None,
            labeled_at=datetime(2026, 4, 10, tzinfo=timezone.utc),
        )
    )
    env = _uc(repos).execute(TaskType("refactor"))
    assert env.sample_size == 3
