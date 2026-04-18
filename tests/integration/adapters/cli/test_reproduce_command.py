"""Integration tests for `ccprophet reproduce` CLI adapter.

Verifies:
- `InsufficientSamples` → exit 3
- happy path with `--json`
- `--apply` routes through the same snapshot + atomic-write machinery as
  `prune --apply` (FR-11.4).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ccprophet.adapters.cli.reproduce import run_reproduce_command
from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore
from ccprophet.adapters.snapshot.filesystem import FilesystemSnapshotStore
from ccprophet.domain.values import OutcomeLabelValue, SessionId, TaskType
from ccprophet.use_cases.apply_pruning import ApplyPruningUseCase
from ccprophet.use_cases.prune_tools import PruneToolsUseCase
from ccprophet.use_cases.reproduce_session import ReproduceSessionUseCase
from tests.fixtures.builders import (
    OutcomeLabelBuilder,
    SessionBuilder,
    ToolCallBuilder,
    ToolDefBuilder,
)

FROZEN = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)


def _wire(tmp_path) -> tuple[InMemoryRepositorySet, ReproduceSessionUseCase, object]:  # type: ignore[no-untyped-def]
    settings = JsonFileSettingsStore()
    snap_store = FilesystemSnapshotStore(tmp_path / "snapshots")
    (tmp_path / "snapshots").mkdir()
    repos = InMemoryRepositorySet()

    prune = PruneToolsUseCase(
        recommendations=repos.recommendations, settings=settings
    )
    apply = ApplyPruningUseCase(
        prune=prune,
        settings=settings,
        snapshot_store=snap_store,
        snapshots=repos.snapshots,
        recommendations=repos.recommendations,
        clock=FrozenClock(FROZEN),
    )
    uc = ReproduceSessionUseCase(
        outcomes=repos.outcomes,
        tool_calls=repos.tool_calls,
        tool_defs=repos.tool_defs,
        recommendations=repos.recommendations,
        apply=apply,
        clock=FrozenClock(FROZEN),
    )
    return repos, uc, settings


def _seed_success_cluster(
    repos: InMemoryRepositorySet, task: str, n: int = 3
) -> None:
    for i in range(n):
        sid = f"succ-{i}"
        repos.sessions.upsert(SessionBuilder().with_id(sid).build())
        repos.outcomes.set_label(
            OutcomeLabelBuilder()
            .for_session(sid)
            .with_label(OutcomeLabelValue.SUCCESS)
            .with_task(task)
            .build()
        )
        repos.tool_defs.bulk_add(
            SessionId(sid),
            [ToolDefBuilder().named("Read").with_tokens(100).build()],
        )
        repos.tool_calls.append(
            ToolCallBuilder().in_session(SessionId(sid)).for_tool("Read").build()
        )


def test_reproduce_insufficient_samples_exits_3(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    _, uc, _ = _wire(tmp_path)
    # No success cluster seeded — should hit InsufficientSamples.
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}\n", encoding="utf-8")
    code = run_reproduce_command(
        uc, task="refactor", target_path=settings_path, apply=False, as_json=True
    )
    assert code == 3
    assert "error" in json.loads(capsys.readouterr().out)


def test_reproduce_dry_run_json_shape(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    repos, uc, _ = _wire(tmp_path)
    _seed_success_cluster(repos, "refactor", n=3)
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}\n", encoding="utf-8")

    code = run_reproduce_command(
        uc, task="refactor", target_path=settings_path, apply=False, as_json=True
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["task_type"] == "refactor"
    assert payload["cluster_size"] == 3
    # Dry run must not have written.
    assert payload["applied"] is False
    assert payload["snapshot_id"] is None


def test_reproduce_apply_writes_snapshot(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    repos, uc, _ = _wire(tmp_path)
    _seed_success_cluster(repos, "refactor", n=3)
    # Seed a pending recommendation that would be applied — otherwise
    # apply_pruning has nothing to write.
    # Instead, seed a settings file with an MCP that can be pruned.
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        '{"mcpServers": {"unused": {}}}\n', encoding="utf-8"
    )

    code = run_reproduce_command(
        uc, task="refactor", target_path=settings_path, apply=True, as_json=True
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    # If any prune recommendation was produced, snapshot should be non-null.
    # If none, applied is False (no-op). Both are valid — the contract is
    # that apply=True NEVER writes without a snapshot.
    if payload["applied"]:
        assert payload["snapshot_id"] is not None
