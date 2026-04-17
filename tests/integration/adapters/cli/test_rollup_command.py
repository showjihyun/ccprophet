from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ccprophet.adapters.cli.rollup import parse_older_than, run_rollup_command
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


def _wire(old_sid: str = "old-1", started: datetime | None = None):  # type: ignore[no-untyped-def]
    from dataclasses import replace

    repos = InMemoryRepositorySet()
    base = SessionBuilder().with_id(old_sid).build()
    repos.sessions.upsert(replace(
        base, started_at=started or datetime(2026, 1, 1, tzinfo=timezone.utc)
    ))
    repos.tool_defs.bulk_add(
        SessionId(old_sid),
        [ToolDefBuilder().named("Read").with_tokens(100).build()],
    )
    repos.tool_calls.append(
        ToolCallBuilder().in_session(old_sid).for_tool("Read").build()
    )
    uc = RollupSessionsUseCase(
        sessions=repos.sessions,
        tool_calls=repos.tool_calls,
        tool_defs=repos.tool_defs,
        phases=repos.phases,
        session_summaries=repos.session_summaries,
        hot_pruner=repos.hot_pruner,
        clock=FrozenClock(NOW),
    )
    return repos, uc


class TestRollupCommand:
    def test_parse_older_than_accepts_nd(self) -> None:
        from datetime import timedelta

        assert parse_older_than("90d") == timedelta(days=90)
        assert parse_older_than("0d") == timedelta(days=0)

    def test_parse_older_than_rejects_garbage(self) -> None:
        with pytest.raises(ValueError):
            parse_older_than("90days")

    def test_dry_run_json_has_plan_and_does_not_delete(self, capsys) -> None:  # type: ignore[no-untyped-def]
        repos, uc = _wire()
        code = run_rollup_command(
            uc, older_than_days=90, apply=False, as_json=True, now=NOW
        )
        assert code == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["applied"] is False
        assert payload["session_count"] == 1
        assert payload["session_ids"] == ["old-1"]
        assert payload["rows_deleted"]["total"] == 0
        # Rows should still be there.
        assert list(repos.tool_calls.list_for_session(SessionId("old-1")))

    def test_apply_json_deletes_rows(self, capsys) -> None:  # type: ignore[no-untyped-def]
        repos, uc = _wire()
        code = run_rollup_command(
            uc, older_than_days=90, apply=True, as_json=True, now=NOW
        )
        assert code == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["applied"] is True
        assert payload["rows_deleted"]["tool_calls"] == 1
        assert list(repos.tool_calls.list_for_session(SessionId("old-1"))) == []

    def test_apply_returns_1_when_empty(self, capsys) -> None:  # type: ignore[no-untyped-def]
        repos = InMemoryRepositorySet()
        # Only a "recent" session; cutoff 90d before NOW excludes it.
        from dataclasses import replace
        base = SessionBuilder().with_id("recent").build()
        repos.sessions.upsert(replace(
            base, started_at=datetime(2026, 4, 16, tzinfo=timezone.utc)
        ))
        uc = RollupSessionsUseCase(
            sessions=repos.sessions,
            tool_calls=repos.tool_calls,
            tool_defs=repos.tool_defs,
            phases=repos.phases,
            session_summaries=repos.session_summaries,
            hot_pruner=repos.hot_pruner,
            clock=FrozenClock(NOW),
        )
        code = run_rollup_command(
            uc, older_than_days=90, apply=True, as_json=True, now=NOW
        )
        assert code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["session_count"] == 0

    def test_dry_run_empty_plan_returns_0(self, capsys) -> None:  # type: ignore[no-untyped-def]
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
        code = run_rollup_command(
            uc, older_than_days=0, apply=False, as_json=True, now=NOW
        )
        # Empty dry-run is still a successful plan (no apply attempted).
        assert code == 0
