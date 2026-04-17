from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Protocol

from ccprophet.domain.entities import Recommendation
from ccprophet.domain.values import RecommendationStatus, SessionId, SnapshotId


class RecommendationRepository(Protocol):
    def save_all(self, recs: Sequence[Recommendation]) -> None: ...
    def list_for_session(
        self, sid: SessionId, *, status: RecommendationStatus | None = None
    ) -> Iterable[Recommendation]: ...
    def list_pending(self, limit: int = 50) -> Iterable[Recommendation]: ...
    def list_applied_in_range(
        self, start: datetime, end: datetime
    ) -> Iterable[Recommendation]: ...
    def mark_applied(
        self, rec_ids: Sequence[str], snapshot_id: SnapshotId
    ) -> None: ...
    def mark_dismissed(self, rec_ids: Sequence[str]) -> None: ...
