from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from ccprophet.adapters.clock.system import SystemClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore
from ccprophet.domain.values import Money, RecommendationKind, SnapshotId
from ccprophet.use_cases.compute_savings import (
    KNOWN_ENV_VARS,
    ComputeSavingsUseCase,
)
from tests.fixtures.builders import RecommendationBuilder, SessionBuilder

FROZEN = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)


def _uc(repos: InMemoryRepositorySet, settings_path):  # type: ignore[no-untyped-def]
    # Use real clock so that InMemory's `mark_applied` (which stamps
    # applied_at with real now) falls inside our window.
    return ComputeSavingsUseCase(
        recommendations=repos.recommendations,
        settings=JsonFileSettingsStore(),
        clock=SystemClock(),
        settings_path=settings_path,
    )


def _write_settings(path, content: dict) -> None:  # type: ignore[no-untyped-def, type-arg]
    path.write_text(json.dumps(content) + "\n", encoding="utf-8")


def test_empty_repo_reports_zero(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    summary = _uc(repos, tmp_path / "settings.json").execute()
    assert summary.applied_count == 0
    assert summary.pending_count == 0
    assert summary.applied_total == Money.zero()
    assert summary.pending_total == Money.zero()


def test_pending_recommendation_counted(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("s-1").build())
    rec = RecommendationBuilder().in_session("s-1").build()
    repos.recommendations.save_all([rec])
    summary = _uc(repos, tmp_path / "settings.json").execute()
    assert summary.pending_count == 1
    assert summary.pending_total.amount == Decimal("0.021")


def test_applied_recommendation_counted(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("s-1").build())
    rec = RecommendationBuilder().in_session("s-1").build()
    repos.recommendations.save_all([rec])
    repos.recommendations.mark_applied([rec.rec_id], SnapshotId("snap-1"))
    summary = _uc(repos, tmp_path / "settings.json").execute()
    assert summary.applied_count == 1
    assert summary.applied_total.amount == Decimal("0.021")


def test_env_vars_from_settings_json(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = tmp_path / "settings.json"
    _write_settings(settings, {"env": {"MAX_THINKING_TOKENS": "10000"}})
    repos = InMemoryRepositorySet()
    summary = _uc(repos, settings).execute()
    names = {e.name for e in summary.active_env_vars}
    assert "MAX_THINKING_TOKENS" in names
    assert all(e.source == "settings.json" for e in summary.active_env_vars)


def test_opportunities_exclude_already_active(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = tmp_path / "settings.json"
    _write_settings(settings, {"env": {"MAX_THINKING_TOKENS": "10000"}})
    repos = InMemoryRepositorySet()
    summary = _uc(repos, settings).execute()
    opp_names = {o.name for o in summary.opportunity_env_vars}
    assert "MAX_THINKING_TOKENS" not in opp_names
    # The other two known vars remain as opportunities
    assert len(opp_names) == len(KNOWN_ENV_VARS) - 1


def test_opportunities_exclude_pending_env_recs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("s-1").build())
    rec = (
        RecommendationBuilder()
        .in_session("s-1")
        .kind(RecommendationKind.SET_ENV_VAR)
        .target("MAX_THINKING_TOKENS=10000")
        .build()
    )
    repos.recommendations.save_all([rec])
    summary = _uc(repos, tmp_path / "settings.json").execute()
    opp_names = {o.name for o in summary.opportunity_env_vars}
    assert "MAX_THINKING_TOKENS" not in opp_names  # shown in pending, not opportunities


def test_total_potential_is_applied_plus_pending(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("s-1").build())
    recs = [
        RecommendationBuilder().in_session("s-1").build(),
        RecommendationBuilder().in_session("s-1").build(),
    ]
    repos.recommendations.save_all(recs)
    repos.recommendations.mark_applied([recs[0].rec_id], SnapshotId("snap"))
    summary = _uc(repos, tmp_path / "settings.json").execute()
    assert summary.applied_count == 1
    assert summary.pending_count == 1
    # applied + pending = 0.021 + 0.021
    assert summary.total_potential.amount == Decimal("0.042")
