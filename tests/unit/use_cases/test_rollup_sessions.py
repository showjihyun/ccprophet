from __future__ import annotations

from datetime import datetime, timezone

from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.values import SessionId
from ccprophet.use_cases.rollup_sessions import RollupSessionsUseCase
from tests.fixtures.builders import (
    SessionBuilder,
    ToolCallBuilder,
    ToolDefBuilder,
)

NOW = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)


def _wire() -> tuple[RollupSessionsUseCase, InMemoryRepositorySet]:
    repos = InMemoryRepositorySet()
    uc = RollupSessionsUseCase(
        sessions=repos.sessions,
        tool_calls=repos.tool_calls,
        tool_defs=repos.tool_defs,
        phases=repos.phases,
        session_summaries=repos.session_summaries,
        hot_pruner=repos.hot_pruner,
        clock=FrozenClock(NOW),
    )
    return uc, repos


def _session(sid: str, *, started: datetime):  # type: ignore[no-untyped-def]
    from dataclasses import replace
    base = SessionBuilder().with_id(sid).build()
    return replace(base, started_at=started)


class TestRollupSessionsUseCase:
    def test_dry_run_plan_includes_old_sessions_only(self) -> None:
        uc, repos = _wire()
        old = _session("old-1", started=datetime(2026, 1, 1, tzinfo=timezone.utc))
        recent = _session("new-1", started=datetime(2026, 4, 15, tzinfo=timezone.utc))
        repos.sessions.upsert(old)
        repos.sessions.upsert(recent)

        cutoff = datetime(2026, 3, 1, tzinfo=timezone.utc)
        outcome = uc.execute(older_than=cutoff, apply=False)

        assert outcome.plan.session_ids == ("old-1",)
        assert outcome.applied is False
        assert outcome.rows_deleted.total == 0

    def test_dry_run_does_not_delete_hot_rows(self) -> None:
        uc, repos = _wire()
        sid = SessionId("old-1")
        repos.sessions.upsert(
            _session("old-1", started=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        repos.tool_defs.bulk_add(sid, [ToolDefBuilder().named("Read").build()])
        repos.tool_calls.append(
            ToolCallBuilder().in_session(sid).for_tool("Read").build()
        )

        uc.execute(
            older_than=datetime(2026, 2, 1, tzinfo=timezone.utc), apply=False
        )

        assert list(repos.tool_calls.list_for_session(sid))  # still there
        assert list(repos.tool_defs.list_for_session(sid))

    def test_apply_deletes_hot_rows_and_upserts_summary(self) -> None:
        uc, repos = _wire()
        sid = SessionId("old-1")
        repos.sessions.upsert(
            _session("old-1", started=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        repos.tool_defs.bulk_add(sid, [
            ToolDefBuilder().named("Read").with_tokens(100).build(),
            ToolDefBuilder().named("Bash").with_tokens(200).build(),
        ])
        repos.tool_calls.append(
            ToolCallBuilder().in_session(sid).for_tool("Read").build()
        )

        outcome = uc.execute(
            older_than=datetime(2026, 2, 1, tzinfo=timezone.utc), apply=True
        )

        assert outcome.applied is True
        assert outcome.rows_deleted.tool_calls == 1
        assert outcome.rows_deleted.tool_defs_loaded == 2
        assert list(repos.tool_calls.list_for_session(sid)) == []
        assert list(repos.tool_defs.list_for_session(sid)) == []

        summary = repos.session_summaries.get(sid)
        assert summary is not None
        assert summary.tool_call_count == 1
        assert summary.loaded_tool_def_tokens.value == 300
        assert summary.source_rows_deleted is True

    def test_apply_with_no_candidates_is_noop(self) -> None:
        uc, repos = _wire()
        repos.sessions.upsert(
            _session("recent", started=datetime(2026, 4, 16, tzinfo=timezone.utc))
        )

        outcome = uc.execute(
            older_than=datetime(2026, 3, 1, tzinfo=timezone.utc), apply=True
        )

        assert outcome.plan.is_empty
        assert outcome.applied is False  # short-circuit: nothing to apply
        assert outcome.rows_deleted.total == 0

    def test_summaries_use_clock_for_summarized_at(self) -> None:
        uc, repos = _wire()
        sid = SessionId("old-1")
        repos.sessions.upsert(
            _session("old-1", started=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )

        uc.execute(
            older_than=datetime(2026, 2, 1, tzinfo=timezone.utc), apply=False
        )

        summary = repos.session_summaries.get(sid)
        assert summary is not None
        assert summary.summarized_at == NOW
