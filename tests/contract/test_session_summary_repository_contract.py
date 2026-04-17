from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

import pytest

from ccprophet.domain.entities import SessionSummary
from ccprophet.domain.values import BloatRatio, SessionId, TokenCount


def _summary(sid: str, *, started: datetime) -> SessionSummary:
    return SessionSummary(
        session_id=SessionId(sid),
        project_slug="p",
        model="claude-opus-4-6",
        started_at=started,
        ended_at=None,
        summarized_at=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
        total_input_tokens=TokenCount(1000),
        total_output_tokens=TokenCount(200),
        compacted=False,
        tool_call_count=5,
        unique_tools_used=3,
        loaded_tool_def_tokens=TokenCount(400),
        bloat_tokens=TokenCount(120),
        bloat_ratio=BloatRatio(0.3),
        file_read_count=2,
        phase_count=4,
        source_rows_deleted=False,
    )


class SessionSummaryRepositoryContract(ABC):
    @pytest.fixture
    @abstractmethod
    def repository(self):  # type: ignore[no-untyped-def]
        ...

    def test_upsert_then_get(self, repository) -> None:  # type: ignore[no-untyped-def]
        s = _summary("a", started=datetime(2026, 1, 1, tzinfo=timezone.utc))
        repository.upsert(s)

        got = repository.get(SessionId("a"))
        assert got is not None
        assert got.tool_call_count == 5
        assert got.bloat_tokens.value == 120
        assert got.loaded_tool_def_tokens.value == 400

    def test_upsert_is_idempotent(self, repository) -> None:  # type: ignore[no-untyped-def]
        s = _summary("a", started=datetime(2026, 1, 1, tzinfo=timezone.utc))
        repository.upsert(s)
        repository.upsert(s)  # second insert must not raise.

        got = repository.get(SessionId("a"))
        assert got is not None

    def test_get_unknown_returns_none(self, repository) -> None:  # type: ignore[no-untyped-def]
        assert repository.get(SessionId("missing")) is None

    def test_list_in_range_filters_and_orders(self, repository) -> None:  # type: ignore[no-untyped-def]
        a = _summary("a", started=datetime(2026, 1, 1, tzinfo=timezone.utc))
        b = _summary("b", started=datetime(2026, 2, 1, tzinfo=timezone.utc))
        c = _summary("c", started=datetime(2026, 3, 1, tzinfo=timezone.utc))
        repository.upsert(c)
        repository.upsert(a)
        repository.upsert(b)

        rows = list(repository.list_in_range(
            datetime(2026, 1, 15, tzinfo=timezone.utc),
            datetime(2026, 4, 1, tzinfo=timezone.utc),
        ))

        assert [r.session_id.value for r in rows] == ["b", "c"]

    def test_list_in_range_empty_when_no_match(self, repository) -> None:  # type: ignore[no-untyped-def]
        repository.upsert(
            _summary("a", started=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        rows = list(repository.list_in_range(
            datetime(2027, 1, 1, tzinfo=timezone.utc),
            datetime(2027, 2, 1, tzinfo=timezone.utc),
        ))
        assert rows == []


class TestInMemorySessionSummaryRepository(SessionSummaryRepositoryContract):
    @pytest.fixture
    def repository(self):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.inmemory.repositories import (
            InMemorySessionSummaryRepository,
        )
        return InMemorySessionSummaryRepository()


class TestDuckDBSessionSummaryRepository(SessionSummaryRepositoryContract):
    @pytest.fixture
    def repository(self, tmp_path):  # type: ignore[no-untyped-def]
        import duckdb

        from ccprophet.adapters.persistence.duckdb.migrations import ensure_schema
        from ccprophet.adapters.persistence.duckdb.v5_repositories import (
            DuckDBSessionSummaryRepository,
        )

        conn = duckdb.connect(str(tmp_path / "ccprophet.duckdb"))
        ensure_schema(conn)
        return DuckDBSessionSummaryRepository(conn)
