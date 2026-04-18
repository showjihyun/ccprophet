from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ccprophet.adapters.cli.cost import run_cost_command
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.values import TokenCount
from ccprophet.use_cases.compute_monthly_cost import ComputeMonthlyCostUseCase
from ccprophet.use_cases.compute_session_cost import ComputeSessionCostUseCase
from tests.fixtures.builders import PricingRateBuilder, SessionBuilder


def _wire():  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    monthly = ComputeMonthlyCostUseCase(
        sessions=repos.sessions,
        recommendations=repos.recommendations,
        pricing=repos.pricing,
    )
    session_uc = ComputeSessionCostUseCase(
        sessions=repos.sessions, pricing=repos.pricing
    )
    return repos, monthly, session_uc


def _seed(repos: InMemoryRepositorySet) -> None:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    session = replace(
        SessionBuilder().with_id("s-cost").build(),
        model="claude-opus-4-6",
        started_at=month_start + timedelta(days=2),
        total_input_tokens=TokenCount(2_000_000),
        total_output_tokens=TokenCount(500_000),
    )
    repos.sessions.upsert(session)
    repos.pricing.add(PricingRateBuilder().for_model("claude-opus-4-6").build())


def test_current_month_summary_json(capsys) -> None:  # type: ignore[no-untyped-def]
    repos, monthly, session_uc = _wire()
    _seed(repos)
    code = run_cost_command(monthly, session_uc, as_json=True)
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["session_count"] == 1
    assert payload["total_cost"]["amount"] > 0
    assert payload["by_model"][0]["model"] == "claude-opus-4-6"


def test_session_flag_shows_single_breakdown(capsys) -> None:  # type: ignore[no-untyped-def]
    repos, monthly, session_uc = _wire()
    _seed(repos)
    code = run_cost_command(
        monthly, session_uc, session="s-cost", as_json=True
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["session_id"] == "s-cost"
    assert payload["total_cost"]["amount"] > 0


def test_session_missing_returns_2(capsys) -> None:  # type: ignore[no-untyped-def]
    _repos, monthly, session_uc = _wire()
    code = run_cost_command(
        monthly, session_uc, session="nope", as_json=True
    )
    captured = capsys.readouterr()
    assert code == 2
    # Error JSON routes to stderr so `ccprophet cost ... --json | jq` stays clean
    assert captured.out == ""
    assert "error" in json.loads(captured.err)


def test_empty_month_is_zero_summary(capsys) -> None:  # type: ignore[no-untyped-def]
    _repos, monthly, session_uc = _wire()
    code = run_cost_command(
        monthly, session_uc, month="2020-01", as_json=True
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["session_count"] == 0
    assert payload["total_cost"]["amount"] == 0
