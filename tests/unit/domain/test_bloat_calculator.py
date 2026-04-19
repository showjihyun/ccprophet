from __future__ import annotations

from ccprophet.domain.services.bloat import BloatCalculator
from ccprophet.domain.values import BloatRatio
from tests.fixtures.builders import ToolCallBuilder, ToolDefBuilder


class TestBloatCalculator:
    def test_all_loaded_never_called_is_full_bloat(self) -> None:
        loaded = [
            ToolDefBuilder()
            .named("mcp__github")
            .with_tokens(1400)
            .from_source("mcp:github")
            .build()
        ]
        called = []

        report = BloatCalculator.calculate(loaded, called)

        assert report.bloat_tokens.value == 1400
        assert report.bloat_ratio == BloatRatio(1.0)
        assert report.used_sources == frozenset()
        assert report.bloat_count == 1
        assert report.used_count == 0

    def test_all_loaded_all_called_is_zero_bloat(self) -> None:
        loaded = [ToolDefBuilder().named("Read").with_tokens(100).build()]
        called = [ToolCallBuilder().for_tool("Read").build()]

        report = BloatCalculator.calculate(loaded, called)

        assert report.bloat_tokens.value == 0
        assert report.bloat_ratio == BloatRatio(0.0)
        assert report.used_count == 1

    def test_mixed_loaded_partial_called(self) -> None:
        loaded = [
            ToolDefBuilder().named("Read").with_tokens(100).from_source("system").build(),
            ToolDefBuilder().named("Bash").with_tokens(200).from_source("system").build(),
            ToolDefBuilder().named("mcp__jira").with_tokens(910).from_source("mcp:jira").build(),
        ]
        called = [ToolCallBuilder().for_tool("Read").build()]

        report = BloatCalculator.calculate(loaded, called)

        assert report.bloat_tokens.value == 200 + 910
        assert report.total_tokens.value == 100 + 200 + 910
        assert "system" in report.used_sources

    def test_empty_loaded_yields_zero(self) -> None:
        report = BloatCalculator.calculate([], [])

        assert report.bloat_ratio == BloatRatio(0.0)
        assert report.total_tokens.value == 0
        assert report.bloat_tokens.value == 0
        assert report.items == ()

    def test_items_sorted_by_tokens_descending(self) -> None:
        loaded = [
            ToolDefBuilder().named("A").with_tokens(100).build(),
            ToolDefBuilder().named("B").with_tokens(500).build(),
            ToolDefBuilder().named("C").with_tokens(300).build(),
        ]
        report = BloatCalculator.calculate(loaded, [])

        assert [i.tool_name for i in report.items] == ["B", "C", "A"]

    def test_by_source_groups_correctly(self) -> None:
        loaded = [
            ToolDefBuilder().named("Read").with_tokens(100).from_source("system").build(),
            ToolDefBuilder().named("Bash").with_tokens(200).from_source("system").build(),
            ToolDefBuilder().named("mcp__gh").with_tokens(700).from_source("mcp:github").build(),
        ]
        called = [ToolCallBuilder().for_tool("Read").build()]

        report = BloatCalculator.calculate(loaded, called)
        by_src = report.by_source()

        assert "system" in by_src
        assert "mcp:github" in by_src
        assert by_src["mcp:github"].bloat_tokens.value == 700
        assert by_src["mcp:github"].bloat_ratio == BloatRatio(1.0)
        assert by_src["system"].bloat_tokens.value == 200

    def test_duplicate_tool_calls_still_mark_as_used(self) -> None:
        loaded = [ToolDefBuilder().named("Read").with_tokens(100).build()]
        called = [
            ToolCallBuilder().for_tool("Read").build(),
            ToolCallBuilder().for_tool("Read").build(),
        ]

        report = BloatCalculator.calculate(loaded, called)

        assert report.bloat_tokens.value == 0
