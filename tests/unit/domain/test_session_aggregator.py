from __future__ import annotations

from datetime import datetime, timezone

from ccprophet.domain.services.bloat import BloatCalculator
from ccprophet.domain.services.session_aggregator import SessionAggregator
from tests.fixtures.builders import (
    SessionBuilder,
    ToolCallBuilder,
    ToolDefBuilder,
)

NOW = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)


class TestSessionAggregator:
    def test_counts_tool_calls_and_unique_tools(self) -> None:
        session = SessionBuilder().with_id("s1").build()
        tool_calls = [
            ToolCallBuilder().in_session("s1").for_tool("Read").build(),
            ToolCallBuilder().in_session("s1").for_tool("Read").build(),
            ToolCallBuilder().in_session("s1").for_tool("Bash").build(),
        ]
        tool_defs = [ToolDefBuilder().named("Read").with_tokens(100).build()]
        report = BloatCalculator.calculate(tool_defs, tool_calls)

        summary = SessionAggregator.summarize(
            session,
            tool_calls,
            tool_defs,
            phases_count=2,
            file_reads_count=5,
            bloat_report=report,
            summarized_at=NOW,
        )

        assert summary.tool_call_count == 3
        assert summary.unique_tools_used == 2
        assert summary.phase_count == 2
        assert summary.file_read_count == 5
        assert summary.summarized_at == NOW

    def test_loaded_tool_def_tokens_is_sum(self) -> None:
        session = SessionBuilder().with_id("s1").build()
        tool_defs = [
            ToolDefBuilder().named("a").with_tokens(100).build(),
            ToolDefBuilder().named("b").with_tokens(250).build(),
            ToolDefBuilder().named("c").with_tokens(50).build(),
        ]
        tool_calls = [ToolCallBuilder().in_session("s1").for_tool("a").build()]
        report = BloatCalculator.calculate(tool_defs, tool_calls)

        summary = SessionAggregator.summarize(
            session,
            tool_calls,
            tool_defs,
            phases_count=0,
            file_reads_count=0,
            bloat_report=report,
            summarized_at=NOW,
        )

        assert summary.loaded_tool_def_tokens.value == 400

    def test_bloat_ratio_matches_report(self) -> None:
        session = SessionBuilder().with_id("s1").build()
        tool_defs = [
            ToolDefBuilder().named("used").with_tokens(100).build(),
            ToolDefBuilder().named("unused").with_tokens(300).build(),
        ]
        tool_calls = [ToolCallBuilder().in_session("s1").for_tool("used").build()]
        report = BloatCalculator.calculate(tool_defs, tool_calls)

        summary = SessionAggregator.summarize(
            session,
            tool_calls,
            tool_defs,
            phases_count=0,
            file_reads_count=0,
            bloat_report=report,
            summarized_at=NOW,
        )

        assert summary.bloat_tokens.value == 300
        assert summary.bloat_ratio.value == report.bloat_ratio.value

    def test_empty_session_yields_zero_aggregates(self) -> None:
        session = SessionBuilder().with_id("empty").build()
        report = BloatCalculator.calculate([], [])

        summary = SessionAggregator.summarize(
            session,
            [],
            [],
            phases_count=0,
            file_reads_count=0,
            bloat_report=report,
            summarized_at=NOW,
        )

        assert summary.tool_call_count == 0
        assert summary.unique_tools_used == 0
        assert summary.loaded_tool_def_tokens.value == 0
        assert summary.bloat_tokens.value == 0
        assert summary.source_rows_deleted is False

    def test_carries_session_token_totals(self) -> None:
        session = SessionBuilder().with_id("s1").build()
        report = BloatCalculator.calculate([], [])

        summary = SessionAggregator.summarize(
            session,
            [],
            [],
            phases_count=0,
            file_reads_count=0,
            bloat_report=report,
            summarized_at=NOW,
        )

        assert summary.total_input_tokens.value == session.total_input_tokens.value
        assert summary.total_output_tokens.value == session.total_output_tokens.value
        assert summary.compacted == session.compacted
