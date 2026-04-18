from __future__ import annotations

import json
from datetime import datetime, timezone

from ccprophet.adapters.cli.snapshot import run_snapshot_restore_command
from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore
from ccprophet.adapters.snapshot.filesystem import FilesystemSnapshotStore
from ccprophet.domain.values import RecommendationKind
from ccprophet.use_cases.apply_pruning import ApplyPruningUseCase
from ccprophet.use_cases.prune_tools import PruneToolsUseCase
from ccprophet.use_cases.restore_snapshot import RestoreSnapshotUseCase
from tests.fixtures.builders import RecommendationBuilder, SessionBuilder


def _setup(tmp_path):  # type: ignore[no-untyped-def]
    path = tmp_path / "settings.json"
    original = json.dumps({"a": 1}) + "\n"
    path.write_text(original, encoding="utf-8")

    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("s-1").build())
    rec = (
        RecommendationBuilder()
        .in_session("s-1")
        .kind(RecommendationKind.PRUNE_TOOL)
        .target("WebFetch")
        .build()
    )
    repos.recommendations.save_all([rec])

    settings = JsonFileSettingsStore()
    snap_store = FilesystemSnapshotStore(tmp_path / "snaps")
    (tmp_path / "snaps").mkdir()

    preview = PruneToolsUseCase(
        recommendations=repos.recommendations, settings=settings
    )
    apply = ApplyPruningUseCase(
        prune=preview,
        settings=settings,
        snapshot_store=snap_store,
        snapshots=repos.snapshots,
        recommendations=repos.recommendations,
        clock=FrozenClock(datetime(2026, 4, 17, tzinfo=timezone.utc)),
    )
    restore = RestoreSnapshotUseCase(
        settings=settings, snapshot_store=snap_store, snapshots=repos.snapshots
    )
    return repos, apply, restore, path, original


def test_restore_returns_zero_and_reverts_file(capsys, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _repos, apply_uc, restore_uc, path, original = _setup(tmp_path)
    outcome = apply_uc.execute(target_path=path)
    assert outcome.snapshot is not None
    assert path.read_text(encoding="utf-8") != original

    code = run_snapshot_restore_command(
        restore_uc,
        snapshot_id=outcome.snapshot.snapshot_id.value,
        as_json=True,
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["snapshot_id"] == outcome.snapshot.snapshot_id.value
    assert path.read_text(encoding="utf-8") == original


def test_restore_unknown_id_returns_2(capsys, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, _, restore_uc, _, _ = _setup(tmp_path)
    code = run_snapshot_restore_command(
        restore_uc, snapshot_id="no-such-snap", as_json=True
    )
    assert code == 2
