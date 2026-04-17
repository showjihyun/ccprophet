"""Restore files from a snapshot captured by ApplyPruningUseCase.

Writes raw bytes verbatim (preserves original formatting). Marks the snapshot's
`restored_at` so the audit log shows it. Does NOT take a fresh pre-restore
snapshot in the MVP — advanced "undo restore" is future work.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ccprophet.domain.errors import SnapshotMissing
from ccprophet.domain.values import SnapshotId
from ccprophet.ports.settings import SettingsStore
from ccprophet.ports.snapshots import SnapshotRepository, SnapshotStore


@dataclass(frozen=True, slots=True)
class RestoreOutcome:
    snapshot_id: SnapshotId
    restored_paths: tuple[str, ...]


@dataclass(frozen=True)
class RestoreSnapshotUseCase:
    settings: SettingsStore
    snapshot_store: SnapshotStore
    snapshots: SnapshotRepository

    def execute(self, snapshot_id: SnapshotId) -> RestoreOutcome:
        meta = self.snapshots.get(snapshot_id)
        if meta is None:
            raise SnapshotMissing(f"Snapshot not found in DB: {snapshot_id}")

        files = self.snapshot_store.restore(snapshot_id)
        paths: list[str] = []
        for original_path, data in files.items():
            self.settings.write_bytes_atomic(Path(original_path), data)
            paths.append(original_path)

        self.snapshots.mark_restored(snapshot_id)
        return RestoreOutcome(
            snapshot_id=snapshot_id, restored_paths=tuple(paths)
        )
