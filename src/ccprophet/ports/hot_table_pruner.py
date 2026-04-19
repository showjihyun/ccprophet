from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ccprophet.domain.values import SessionId


@dataclass(frozen=True, slots=True)
class PruneCounts:
    """Row counts deleted per hot table during a rollup --apply step."""

    events: int = 0
    tool_calls: int = 0
    tool_defs_loaded: int = 0
    file_reads: int = 0
    phases: int = 0

    @property
    def total(self) -> int:
        return self.events + self.tool_calls + self.tool_defs_loaded + self.file_reads + self.phases


class HotTablePruner(Protocol):
    """Driven port that bulk-deletes session-scoped rows across hot tables.

    One port (rather than `delete_for_sessions` on every repository) keeps the
    rollup use case SQL-free: it passes session IDs in, gets a `PruneCounts`
    out. Adapters decide whether to use a single `DELETE ... WHERE session_id
    IN (...)` or per-table loops.
    """

    def delete_for_sessions(self, sids: Sequence[SessionId]) -> PruneCounts: ...
