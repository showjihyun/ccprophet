from __future__ import annotations

import pytest

from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.values import SessionId
from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
from tests.fixtures.builders import SessionBuilder, ToolCallBuilder, ToolDefBuilder


class TestAnalyzeBloatUseCase:
    def test_returns_report_for_known_session(
        self, analyze_bloat: AnalyzeBloatUseCase, inmemory_repos: InMemoryRepositorySet
    ) -> None:
        sid = SessionId("s1")
        inmemory_repos.sessions.upsert(SessionBuilder().with_id("s1").build())
        inmemory_repos.tool_defs.bulk_add(
            sid,
            [
                ToolDefBuilder()
                .named("mcp__github")
                .with_tokens(1400)
                .from_source("mcp:github")
                .build(),
                ToolDefBuilder().named("Read").with_tokens(1250).from_source("system").build(),
            ],
        )
        inmemory_repos.tool_calls.append(ToolCallBuilder().in_session(sid).for_tool("Read").build())

        report = analyze_bloat.execute(sid)

        assert report.bloat_tokens.value == 1400
        assert "system" in report.used_sources
        assert report.used_count == 1
        assert report.bloat_count == 1

    def test_raises_for_unknown_session(self, analyze_bloat: AnalyzeBloatUseCase) -> None:
        with pytest.raises(SessionNotFound):
            analyze_bloat.execute(SessionId("nonexistent"))

    def test_execute_current_uses_latest_active(
        self, analyze_bloat: AnalyzeBloatUseCase, inmemory_repos: InMemoryRepositorySet
    ) -> None:
        inmemory_repos.sessions.upsert(SessionBuilder().with_id("s1").build())
        inmemory_repos.tool_defs.bulk_add(
            SessionId("s1"),
            [
                ToolDefBuilder().named("Read").with_tokens(100).build(),
            ],
        )

        report = analyze_bloat.execute_current()

        assert report.total_tokens.value == 100

    def test_execute_current_raises_when_no_active(
        self, analyze_bloat: AnalyzeBloatUseCase
    ) -> None:
        with pytest.raises(SessionNotFound):
            analyze_bloat.execute_current()

    def test_session_with_no_tools_returns_empty_report(
        self, analyze_bloat: AnalyzeBloatUseCase, inmemory_repos: InMemoryRepositorySet
    ) -> None:
        inmemory_repos.sessions.upsert(SessionBuilder().with_id("empty").build())

        report = analyze_bloat.execute(SessionId("empty"))

        assert report.total_tokens.value == 0
        assert report.bloat_count == 0
