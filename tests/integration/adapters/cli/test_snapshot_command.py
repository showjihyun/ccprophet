from __future__ import annotations

import json
from datetime import datetime, timezone

from ccprophet.adapters.cli.snapshot import run_snapshot_list_command
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.entities import Snapshot, SnapshotFileEntry
from ccprophet.domain.values import SnapshotId
from ccprophet.use_cases.list_snapshots import ListSnapshotsUseCase


def _snapshot(sid: str, reason: str = "prune") -> Snapshot:
    return Snapshot(
        snapshot_id=SnapshotId(sid),
        captured_at=datetime(2026, 4, 17, 9, 0, tzinfo=timezone.utc),
        reason=reason,
        files=(SnapshotFileEntry(path=".claude/settings.json", sha256="abc", byte_size=123),),
        byte_size=123,
    )


def test_snapshot_list_empty_returns_1(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    uc = ListSnapshotsUseCase(snapshots=repos.snapshots)
    code = run_snapshot_list_command(uc)
    assert code == 1


def test_snapshot_list_json(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    repos.snapshots.save(_snapshot("snap-a"))
    uc = ListSnapshotsUseCase(snapshots=repos.snapshots)
    code = run_snapshot_list_command(uc, as_json=True)
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload[0]["snapshot_id"] == "snap-a"
    assert payload[0]["file_count"] == 1
