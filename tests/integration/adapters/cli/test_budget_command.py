from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

from ccprophet.adapters.cli.budget import run_budget_command
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.entities import OutcomeLabel
from ccprophet.domain.values import (
    OutcomeLabelValue,
    SessionId,
    TaskType,
    TokenCount,
)
from ccprophet.use_cases.estimate_budget import EstimateBudgetUseCase
from tests.fixtures.builders import PricingRateBuilder, SessionBuilder


def _seed(repos: InMemoryRepositorySet, n: int) -> None:
    for i in range(n):
        sid = f"s-{i}"
        session = replace(
            SessionBuilder().with_id(sid).build(),
            model="claude-opus-4-6",
            total_input_tokens=TokenCount(100_000 + i * 10_000),
            total_output_tokens=TokenCount(10_000),
        )
        repos.sessions.upsert(session)
        repos.outcomes.set_label(
            OutcomeLabel(
                session_id=SessionId(sid),
                label=OutcomeLabelValue.SUCCESS,
                task_type=TaskType("refactor"),
                source="manual",
                reason=None,
                labeled_at=datetime(2026, 4, 10, tzinfo=timezone.utc),
            )
        )
    repos.pricing.add(PricingRateBuilder().for_model("claude-opus-4-6").build())


def _uc(repos: InMemoryRepositorySet) -> EstimateBudgetUseCase:
    return EstimateBudgetUseCase(
        outcomes=repos.outcomes,
        tool_calls=repos.tool_calls,
        tool_defs=repos.tool_defs,
        pricing=repos.pricing,
    )


def test_budget_insufficient_returns_3(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    _seed(repos, n=2)
    code = run_budget_command(_uc(repos), task="refactor", as_json=True)
    assert code == 3
    assert "error" in json.loads(capsys.readouterr().out)


def test_budget_json_output(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    _seed(repos, n=3)
    code = run_budget_command(_uc(repos), task="refactor", as_json=True)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sample_size"] == 3
    assert payload["estimated_input_tokens_mean"] > 0
