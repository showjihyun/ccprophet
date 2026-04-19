from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

import pytest

from ccprophet.domain.values import (
    RecommendationKind,
    RecommendationStatus,
    SessionId,
    SnapshotId,
)
from tests.fixtures.builders import RecommendationBuilder


class RecommendationRepositoryContract(ABC):
    @pytest.fixture
    @abstractmethod
    def repository(self):  # type: ignore[no-untyped-def]
        ...

    def test_save_and_list_for_session(self, repository) -> None:  # type: ignore[no-untyped-def]
        r1 = RecommendationBuilder().in_session("s1").target("mcp__a").build()
        r2 = RecommendationBuilder().in_session("s1").target("mcp__b").build()
        repository.save_all([r1, r2])
        got = list(repository.list_for_session(SessionId("s1")))
        assert {r.target for r in got} == {"mcp__a", "mcp__b"}

    def test_list_pending_filters_by_status(self, repository) -> None:  # type: ignore[no-untyped-def]
        r = RecommendationBuilder().in_session("s2").build()
        repository.save_all([r])
        pending = list(repository.list_pending())
        assert any(x.rec_id == r.rec_id for x in pending)
        repository.mark_applied([r.rec_id], SnapshotId("snap-1"))
        pending_after = list(repository.list_pending())
        assert all(x.rec_id != r.rec_id for x in pending_after)

    def test_mark_applied_updates_status_and_snapshot(self, repository) -> None:  # type: ignore[no-untyped-def]
        r = RecommendationBuilder().in_session("s3").build()
        repository.save_all([r])
        repository.mark_applied([r.rec_id], SnapshotId("snap-9"))
        applied = list(
            repository.list_for_session(SessionId("s3"), status=RecommendationStatus.APPLIED)
        )
        assert len(applied) == 1
        assert applied[0].snapshot_id is not None
        assert applied[0].snapshot_id.value == "snap-9"
        assert applied[0].applied_at is not None

    def test_mark_dismissed(self, repository) -> None:  # type: ignore[no-untyped-def]
        r = RecommendationBuilder().in_session("s4").build()
        repository.save_all([r])
        repository.mark_dismissed([r.rec_id])
        dismissed = list(
            repository.list_for_session(SessionId("s4"), status=RecommendationStatus.DISMISSED)
        )
        assert len(dismissed) == 1
        assert dismissed[0].dismissed_at is not None

    def test_list_applied_in_range(self, repository) -> None:  # type: ignore[no-untyped-def]
        r = RecommendationBuilder().in_session("s-range").build()
        repository.save_all([r])
        repository.mark_applied([r.rec_id], SnapshotId("snap-r"))
        now = datetime.now(timezone.utc)
        got = list(
            repository.list_applied_in_range(now - timedelta(minutes=5), now + timedelta(minutes=5))
        )
        assert any(x.rec_id == r.rec_id for x in got)

    def test_kinds_roundtrip(self, repository) -> None:  # type: ignore[no-untyped-def]
        r = RecommendationBuilder().in_session("s5").kind(RecommendationKind.RUN_CLEAR).build()
        repository.save_all([r])
        got = list(repository.list_for_session(SessionId("s5")))
        assert got[0].kind == RecommendationKind.RUN_CLEAR


class TestInMemoryRecommendationRepository(RecommendationRepositoryContract):
    @pytest.fixture
    def repository(self):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.inmemory.repositories import (
            InMemoryRecommendationRepository,
        )

        return InMemoryRecommendationRepository()
