"""Auto-Fix write-path tests — PruneTools / ApplyPruning / RestoreSnapshot.

These operate against real files in `tmp_path` and real FilesystemSnapshotStore
but with InMemory repositories — matches the contract for the DuckDB variant
while keeping the test surface focused on the orchestration logic.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore
from ccprophet.adapters.snapshot.filesystem import FilesystemSnapshotStore
from ccprophet.domain.errors import SnapshotConflict, SnapshotMissing
from ccprophet.domain.services.settings_patch import (
    KEY_DISABLED_MCPS,
    KEY_DISABLED_TOOLS,
)
from ccprophet.domain.values import (
    RecommendationKind,
    RecommendationStatus,
    SessionId,
    SnapshotId,
)
from ccprophet.use_cases.apply_pruning import ApplyPruningUseCase
from ccprophet.use_cases.prune_tools import PruneToolsUseCase
from ccprophet.use_cases.restore_snapshot import RestoreSnapshotUseCase
from tests.fixtures.builders import RecommendationBuilder, SessionBuilder

FROZEN = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def settings_path(tmp_path):  # type: ignore[no-untyped-def]
    p = tmp_path / "settings.json"
    p.write_text(
        json.dumps({"theme": "dark", "mcpServers": {"github": {}}}, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def snapshot_root(tmp_path):  # type: ignore[no-untyped-def]
    root = tmp_path / "snapshots"
    root.mkdir()
    return root


@pytest.fixture
def wired(settings_path, snapshot_root):  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("s-1").build())
    settings = JsonFileSettingsStore()
    snap_store = FilesystemSnapshotStore(snapshot_root)
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
    restore = RestoreSnapshotUseCase(
        settings=settings, snapshot_store=snap_store, snapshots=repos.snapshots
    )
    return dict(
        repos=repos,
        settings=settings,
        prune=prune,
        apply=apply,
        restore=restore,
        path=settings_path,
    )


def _seed_pending_rec(repos, kind, target: str):  # type: ignore[no-untyped-def]
    rec = (
        RecommendationBuilder()
        .in_session("s-1")
        .kind(kind)
        .target(target)
        .build()
    )
    repos.recommendations.save_all([rec])
    return rec


def test_preview_returns_no_changes_when_no_recs(wired) -> None:  # type: ignore[no-untyped-def]
    preview = wired["prune"].execute(target_path=wired["path"])
    assert preview.has_changes is False
    assert preview.recommendations == ()


def test_preview_computes_plan_without_writing(wired) -> None:  # type: ignore[no-untyped-def]
    _seed_pending_rec(
        wired["repos"], RecommendationKind.PRUNE_MCP, "mcp__github__x"
    )
    original_bytes = wired["path"].read_bytes()
    preview = wired["prune"].execute(target_path=wired["path"])
    assert preview.has_changes is True
    assert preview.plan.added_mcps == ("github",)
    assert wired["path"].read_bytes() == original_bytes


def test_apply_writes_and_records_snapshot(wired) -> None:  # type: ignore[no-untyped-def]
    rec = _seed_pending_rec(
        wired["repos"], RecommendationKind.PRUNE_MCP, "mcp__github__x"
    )
    outcome = wired["apply"].execute(target_path=wired["path"])
    assert outcome.written is True
    assert outcome.snapshot is not None
    assert rec.rec_id in outcome.applied_rec_ids

    patched = json.loads(wired["path"].read_text(encoding="utf-8"))
    assert patched[KEY_DISABLED_MCPS] == ["github"]
    assert patched["theme"] == "dark"  # untouched

    applied = list(
        wired["repos"].recommendations.list_for_session(
            SessionId("s-1"), status=RecommendationStatus.APPLIED
        )
    )
    assert len(applied) == 1
    assert applied[0].snapshot_id == outcome.snapshot.snapshot_id


def test_apply_is_noop_when_nothing_to_do(wired) -> None:  # type: ignore[no-untyped-def]
    outcome = wired["apply"].execute(target_path=wired["path"])
    assert outcome.written is False
    assert outcome.snapshot is None
    assert outcome.applied_rec_ids == ()


def test_apply_propagates_settings_conflict(wired, snapshot_root) -> None:  # type: ignore[no-untyped-def]
    """If the SettingsStore raises SnapshotConflict, apply propagates it but
    the Snapshot is already saved — that's intentional audit behaviour."""
    _seed_pending_rec(
        wired["repos"], RecommendationKind.PRUNE_TOOL, "WebFetch"
    )

    class ConflictingStore:
        def __init__(self, real):
            self._real = real

        def read(self, path):
            return self._real.read(path)

        def write_atomic(self, path, content, *, expected_hash=None):
            raise SnapshotConflict("forced for test")

        def write_bytes_atomic(self, path, data):
            self._real.write_bytes_atomic(path, data)

    apply_with_conflict = ApplyPruningUseCase(
        prune=PruneToolsUseCase(
            recommendations=wired["repos"].recommendations,
            settings=wired["settings"],
        ),
        settings=ConflictingStore(wired["settings"]),
        snapshot_store=FilesystemSnapshotStore(snapshot_root),
        snapshots=wired["repos"].snapshots,
        recommendations=wired["repos"].recommendations,
        clock=FrozenClock(FROZEN),
    )

    with pytest.raises(SnapshotConflict):
        apply_with_conflict.execute(target_path=wired["path"])

    # Snapshot was captured (audit trail) even though write failed.
    snaps = list(wired["repos"].snapshots.list_recent())
    assert len(snaps) == 1


def test_restore_brings_original_bytes_back(wired) -> None:  # type: ignore[no-untyped-def]
    _seed_pending_rec(
        wired["repos"], RecommendationKind.PRUNE_MCP, "mcp__github__x"
    )
    original = wired["path"].read_bytes()
    outcome = wired["apply"].execute(target_path=wired["path"])
    assert outcome.snapshot is not None
    patched = wired["path"].read_bytes()
    assert patched != original

    wired["restore"].execute(outcome.snapshot.snapshot_id)
    assert wired["path"].read_bytes() == original
    meta = wired["repos"].snapshots.get(outcome.snapshot.snapshot_id)
    assert meta is not None and meta.restored_at is not None


def test_restore_unknown_snapshot_raises(wired) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SnapshotMissing):
        wired["restore"].execute(SnapshotId("no-such-id"))


def test_already_disabled_items_no_longer_dirty(wired) -> None:  # type: ignore[no-untyped-def]
    # Seed file that already has the MCP disabled
    wired["path"].write_text(
        json.dumps({KEY_DISABLED_MCPS: ["github"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    _seed_pending_rec(
        wired["repos"], RecommendationKind.PRUNE_MCP, "mcp__github__x"
    )
    outcome = wired["apply"].execute(target_path=wired["path"])
    assert outcome.written is False


def test_prune_tool_kind_writes_to_disabled_tools(wired) -> None:  # type: ignore[no-untyped-def]
    _seed_pending_rec(wired["repos"], RecommendationKind.PRUNE_TOOL, "WebFetch")
    outcome = wired["apply"].execute(target_path=wired["path"])
    assert outcome.written is True
    new = json.loads(wired["path"].read_text(encoding="utf-8"))
    assert new[KEY_DISABLED_TOOLS] == ["WebFetch"]
