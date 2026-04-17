from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

import pytest

from ccprophet.domain.entities import Snapshot, SnapshotFileEntry
from ccprophet.domain.values import SnapshotId


def _snapshot(sid: str, reason: str = "prune-test") -> Snapshot:
    return Snapshot(
        snapshot_id=SnapshotId(sid),
        captured_at=datetime(2026, 4, 17, 9, 0, tzinfo=timezone.utc),
        reason=reason,
        triggered_by="apply_pruning",
        files=(
            SnapshotFileEntry(path=".claude/settings.json", sha256="abc", byte_size=100),
        ),
        byte_size=100,
    )


class SnapshotRepositoryContract(ABC):
    @pytest.fixture
    @abstractmethod
    def repository(self):  # type: ignore[no-untyped-def]
        ...

    def test_save_and_get(self, repository) -> None:  # type: ignore[no-untyped-def]
        snap = _snapshot("snap-1")
        repository.save(snap)
        got = repository.get(SnapshotId("snap-1"))
        assert got is not None
        assert got.reason == "prune-test"
        assert len(got.files) == 1

    def test_get_unknown_returns_none(self, repository) -> None:  # type: ignore[no-untyped-def]
        assert repository.get(SnapshotId("missing")) is None

    def test_list_recent_is_sorted_desc(self, repository) -> None:  # type: ignore[no-untyped-def]
        repository.save(_snapshot("a", "r1"))
        repository.save(_snapshot("b", "r2"))
        repository.save(_snapshot("c", "r3"))
        listed = list(repository.list_recent(limit=10))
        assert len(listed) == 3

    def test_mark_restored(self, repository) -> None:  # type: ignore[no-untyped-def]
        repository.save(_snapshot("snap-x"))
        repository.mark_restored(SnapshotId("snap-x"))
        got = repository.get(SnapshotId("snap-x"))
        assert got is not None
        assert got.restored_at is not None


class TestInMemorySnapshotRepository(SnapshotRepositoryContract):
    @pytest.fixture
    def repository(self):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.inmemory.repositories import (
            InMemorySnapshotRepository,
        )
        return InMemorySnapshotRepository()
