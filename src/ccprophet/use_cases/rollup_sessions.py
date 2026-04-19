from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ccprophet.domain.entities import SessionSummary
from ccprophet.domain.services.bloat import BloatCalculator
from ccprophet.domain.services.session_aggregator import SessionAggregator
from ccprophet.domain.values import SessionId
from ccprophet.ports.clock import Clock
from ccprophet.ports.hot_table_pruner import HotTablePruner, PruneCounts
from ccprophet.ports.repositories import (
    PhaseRepository,
    SessionRepository,
    ToolCallRepository,
    ToolDefRepository,
)
from ccprophet.ports.session_summary import SessionSummaryRepository

# Sentinel used when the caller means "from the dawn of time". A timezone-aware
# minimum keeps comparisons consistent with the rest of the app.
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class RollupPlan:
    session_ids: tuple[str, ...]
    summaries: tuple[SessionSummary, ...]

    @property
    def is_empty(self) -> bool:
        return len(self.session_ids) == 0


@dataclass(frozen=True, slots=True)
class RollupOutcome:
    plan: RollupPlan
    applied: bool
    rows_deleted: PruneCounts = field(default_factory=PruneCounts)
    archive_path: Path | None = None


@dataclass(frozen=True)
class RollupSessionsUseCase:
    sessions: SessionRepository
    tool_calls: ToolCallRepository
    tool_defs: ToolDefRepository
    phases: PhaseRepository
    session_summaries: SessionSummaryRepository
    hot_pruner: HotTablePruner
    clock: Clock

    def execute(
        self,
        *,
        older_than: datetime,
        apply: bool,
    ) -> RollupOutcome:
        # Snapshot all sessions whose `started_at < older_than`.
        # `SessionRepository.list_in_range(start, end)` filters [start, end),
        # so pass the epoch as start.
        now = self.clock.now()
        candidates = list(self.sessions.list_in_range(_EPOCH, older_than))

        summaries: list[SessionSummary] = []
        for session in candidates:
            tool_calls = list(self.tool_calls.list_for_session(session.session_id))
            tool_defs = list(self.tool_defs.list_for_session(session.session_id))
            phases = list(self.phases.list_for_session(session.session_id))
            # file_reads has no Repository Port yet; summarize as 0 rather
            # than invent a port purely for the rollup. The DuckDB pruner
            # still deletes the hot rows. See TODO below.
            bloat = BloatCalculator.calculate(tool_defs, tool_calls)
            summary = SessionAggregator.summarize(
                session,
                tool_calls,
                tool_defs,
                phases_count=len(phases),
                file_reads_count=0,
                bloat_report=bloat,
                summarized_at=now,
            )
            summaries.append(summary)
            self.session_summaries.upsert(summary)

        plan = RollupPlan(
            session_ids=tuple(s.session_id.value for s in candidates),
            summaries=tuple(summaries),
        )

        if not apply or plan.is_empty:
            return RollupOutcome(plan=plan, applied=False)

        # Destructive step — caller is responsible for taking the Parquet
        # archive (via the CLI) before calling `apply=True`.
        sids = [SessionId(v) for v in plan.session_ids]
        counts = self.hot_pruner.delete_for_sessions(sids)

        # Mark summaries as "source rows deleted" so later audits show that
        # the hot tables no longer contain these sessions.
        for sid in sids:
            existing = self.session_summaries.get(sid)
            if existing is None:
                continue
            from dataclasses import replace

            self.session_summaries.upsert(replace(existing, source_rows_deleted=True))

        return RollupOutcome(plan=plan, applied=True, rows_deleted=counts)
