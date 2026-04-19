from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from ccprophet.domain.entities import Snapshot
from ccprophet.domain.values import SnapshotId


@dataclass(frozen=True, slots=True)
class SnapshotMeta:
    reason: str
    triggered_by: str | None = None


class SnapshotRepository(Protocol):
    """Metadata only. Actual file bytes handled by SnapshotStore."""

    def save(self, snap: Snapshot) -> None: ...
    def get(self, sid: SnapshotId) -> Snapshot | None: ...
    def list_recent(self, limit: int = 20) -> Sequence[Snapshot]: ...
    def mark_restored(self, sid: SnapshotId) -> None: ...


class SnapshotStore(Protocol):
    """File-level capture/restore of config files."""

    def capture(self, files: Mapping[str, bytes], meta: SnapshotMeta) -> Snapshot: ...
    def restore(self, sid: SnapshotId) -> Mapping[str, bytes]: ...
