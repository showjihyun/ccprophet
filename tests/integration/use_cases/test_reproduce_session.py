from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore
from ccprophet.adapters.snapshot.filesystem import FilesystemSnapshotStore
from ccprophet.domain.entities import OutcomeLabel, ToolDef
from ccprophet.domain.errors import InsufficientSamples
from ccprophet.domain.services.settings_patch import KEY_DISABLED_MCPS
from ccprophet.domain.values import (
    OutcomeLabelValue,
    RecommendationKind,
    SessionId,
    TaskType,
    TokenCount,
)
from ccprophet.use_cases.apply_pruning import ApplyPruningUseCase
from ccprophet.use_cases.prune_tools import PruneToolsUseCase
from ccprophet.use_cases.reproduce_session import ReproduceSessionUseCase
from tests.fixtures.builders import (
    PricingRateBuilder,
    SessionBuilder,
    ToolCallBuilder,
)

FROZEN = datetime(2026, 4, 17, tzinfo=timezone.utc)


def _seed(repos: InMemoryRepositorySet, n: int = 3) -> None:
    for i in range(n):
        sid = f"s-{i}"
        session = replace(
            SessionBuilder().with_id(sid).build(),
            model="claude-opus-4-6",
            total_input_tokens=TokenCount(100_000),
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
                labeled_at=FROZEN,
            )
        )
        repos.tool_calls.append(
            ToolCallBuilder().in_session(SessionId(sid)).for_tool("Read").build()
        )
        repos.tool_defs.bulk_add(
            SessionId(sid),
            [
                ToolDef("mcp__linear_y", TokenCount(400), "mcp:linear"),
            ],
        )
    repos.pricing.add(PricingRateBuilder().for_model("claude-opus-4-6").build())


def _wire(tmp_path):  # type: ignore[no-untyped-def]
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"theme": "dark"}) + "\n", encoding="utf-8")
    repos = InMemoryRepositorySet()

    settings = JsonFileSettingsStore()
    snap_store = FilesystemSnapshotStore(tmp_path / "snaps")
    (tmp_path / "snaps").mkdir()
    preview = PruneToolsUseCase(recommendations=repos.recommendations, settings=settings)
    apply = ApplyPruningUseCase(
        prune=preview,
        settings=settings,
        snapshot_store=snap_store,
        snapshots=repos.snapshots,
        recommendations=repos.recommendations,
        clock=FrozenClock(FROZEN),
    )
    reproduce = ReproduceSessionUseCase(
        outcomes=repos.outcomes,
        tool_calls=repos.tool_calls,
        tool_defs=repos.tool_defs,
        recommendations=repos.recommendations,
        apply=apply,
        clock=FrozenClock(FROZEN),
    )
    return repos, reproduce, settings_path


def test_reproduce_dry_run_returns_recs_without_writing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos, reproduce, path = _wire(tmp_path)
    _seed(repos, n=3)
    before = path.read_bytes()
    outcome = reproduce.execute(TaskType("refactor"), target_path=path)
    assert len(outcome.recommendations) == 1
    assert outcome.recommendations[0].kind == RecommendationKind.PRUNE_MCP
    assert outcome.apply_outcome is None
    assert path.read_bytes() == before


def test_reproduce_apply_writes_via_auto_fix(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos, reproduce, path = _wire(tmp_path)
    _seed(repos, n=3)
    outcome = reproduce.execute(TaskType("refactor"), target_path=path, apply=True)
    assert outcome.apply_outcome is not None
    assert outcome.apply_outcome.written is True
    new_content = json.loads(path.read_text(encoding="utf-8"))
    assert new_content[KEY_DISABLED_MCPS] == ["linear"]


def test_reproduce_insufficient_samples(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos, reproduce, path = _wire(tmp_path)
    _seed(repos, n=2)
    with pytest.raises(InsufficientSamples):
        reproduce.execute(TaskType("refactor"), target_path=path)
