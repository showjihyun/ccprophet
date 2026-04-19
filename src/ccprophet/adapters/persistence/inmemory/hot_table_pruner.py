"""InMemory adapter for `HotTablePruner`.

Peers with `InMemoryRepositorySet`: directly pokes each repository's internal
list/dict so tests can assert "rows are really gone" after a rollup.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ccprophet.domain.values import SessionId
from ccprophet.ports.hot_table_pruner import PruneCounts

if TYPE_CHECKING:
    from ccprophet.adapters.persistence.inmemory.repositories import (
        InMemoryRepositorySet,
    )


class InMemoryHotTablePruner:
    def __init__(self, repos: InMemoryRepositorySet) -> None:
        self._repos = repos

    def delete_for_sessions(self, sids: Sequence[SessionId]) -> PruneCounts:
        targets = {sid.value for sid in sids}
        if not targets:
            return PruneCounts()

        events_before = len(self._repos.events._events)
        self._repos.events._events = [
            e for e in self._repos.events._events if e.session_id.value not in targets
        ]
        # Rebuild dedup hash set so the pruned rows can be re-ingested later.
        self._repos.events._hashes = {e.raw_hash.value for e in self._repos.events._events}
        events_deleted = events_before - len(self._repos.events._events)

        tcalls_before = len(self._repos.tool_calls._store)
        self._repos.tool_calls._store = [
            tc for tc in self._repos.tool_calls._store if tc.session_id.value not in targets
        ]
        tcalls_deleted = tcalls_before - len(self._repos.tool_calls._store)

        tdefs_deleted = 0
        for sid_val in list(self._repos.tool_defs._store.keys()):
            if sid_val in targets:
                tdefs_deleted += len(self._repos.tool_defs._store[sid_val])
                del self._repos.tool_defs._store[sid_val]

        phases_deleted = 0
        for sid_val in list(self._repos.phases._store.keys()):
            if sid_val in targets:
                phases_deleted += len(self._repos.phases._store[sid_val])
                del self._repos.phases._store[sid_val]

        # file_reads: no InMemory repo exists yet — report 0. Contract test
        # verifies that the DuckDB adapter handles this table correctly.
        return PruneCounts(
            events=events_deleted,
            tool_calls=tcalls_deleted,
            tool_defs_loaded=tdefs_deleted,
            file_reads=0,
            phases=phases_deleted,
        )
