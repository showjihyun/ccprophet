from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ccprophet.domain.entities import Snapshot
from ccprophet.ports.snapshots import SnapshotRepository


@dataclass(frozen=True)
class ListSnapshotsUseCase:
    snapshots: SnapshotRepository

    def execute(self, limit: int = 20) -> Sequence[Snapshot]:
        return self.snapshots.list_recent(limit=limit)
