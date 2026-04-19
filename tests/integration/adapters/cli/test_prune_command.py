from __future__ import annotations

import json
from datetime import datetime, timezone

from ccprophet.adapters.cli.prune import run_prune_command
from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore
from ccprophet.adapters.snapshot.filesystem import FilesystemSnapshotStore
from ccprophet.domain.services.settings_patch import KEY_DISABLED_MCPS
from ccprophet.domain.values import RecommendationKind
from ccprophet.use_cases.apply_pruning import ApplyPruningUseCase
from ccprophet.use_cases.prune_tools import PruneToolsUseCase
from tests.fixtures.builders import RecommendationBuilder, SessionBuilder

FROZEN = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


def _wire(tmp_path):  # type: ignore[no-untyped-def]
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"theme": "dark"}) + "\n", encoding="utf-8")

    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("s-1").build())

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
    return repos, preview, apply, path


def _seed(repos) -> None:  # type: ignore[no-untyped-def]
    rec = (
        RecommendationBuilder()
        .in_session("s-1")
        .kind(RecommendationKind.PRUNE_MCP)
        .target("mcp__github__create")
        .build()
    )
    repos.recommendations.save_all([rec])


def test_dry_run_default_does_not_write(capsys, tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos, preview, apply, path = _wire(tmp_path)
    _seed(repos)
    before = path.read_bytes()
    code = run_prune_command(preview, apply, target_path=path, as_json=True)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["added_mcps"] == ["github"]
    assert path.read_bytes() == before


def test_apply_yes_writes_and_records_snapshot(capsys, tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos, preview, apply, path = _wire(tmp_path)
    _seed(repos)
    code = run_prune_command(
        preview,
        apply,
        target_path=path,
        apply=True,
        assume_yes=True,
        as_json=True,
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["written"] is True
    assert payload["snapshot_id"] is not None
    assert json.loads(path.read_text(encoding="utf-8"))[KEY_DISABLED_MCPS] == ["github"]


def test_apply_confirm_declined_returns_1(capsys, tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos, preview, apply, path = _wire(tmp_path)
    _seed(repos)
    before = path.read_bytes()

    code = run_prune_command(
        preview,
        apply,
        target_path=path,
        apply=True,
        assume_yes=False,
        as_json=True,
        confirm=lambda _msg: False,
    )
    assert code == 1
    assert path.read_bytes() == before


def test_apply_with_no_changes_is_noop(capsys, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _repos, preview, apply, path = _wire(tmp_path)
    code = run_prune_command(
        preview,
        apply,
        target_path=path,
        apply=True,
        assume_yes=True,
        as_json=True,
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_changes"] is False
    # nothing was written — file bytes unchanged
    assert path.read_text(encoding="utf-8") == json.dumps({"theme": "dark"}) + "\n"
