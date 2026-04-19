from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from ccprophet.domain.entities import SessionSummary
from ccprophet.domain.values import SessionId


class SessionSummaryRepository(Protocol):
    """Driven port for the rollup `session_summary` table (V5).

    See DATAMODELING.md §6.2 for the data-lifecycle context.
    """

    def upsert(self, summary: SessionSummary) -> None: ...
    def get(self, sid: SessionId) -> SessionSummary | None: ...
    def list_in_range(self, start: datetime, end: datetime) -> Sequence[SessionSummary]: ...
