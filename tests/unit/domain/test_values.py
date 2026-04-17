from __future__ import annotations

import pytest

from ccprophet.domain.values import BloatRatio, TokenCount, ToolSource


class TestTokenCount:
    def test_valid(self) -> None:
        assert TokenCount(100).value == 100

    def test_zero(self) -> None:
        assert TokenCount(0).value == 0

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            TokenCount(-1)

    def test_addition(self) -> None:
        result = TokenCount(100) + TokenCount(200)
        assert result == TokenCount(300)

    def test_int_conversion(self) -> None:
        assert int(TokenCount(42)) == 42


class TestBloatRatio:
    def test_valid_range(self) -> None:
        assert BloatRatio(0.0).value == 0.0
        assert BloatRatio(1.0).value == 1.0
        assert BloatRatio(0.5).as_percent() == 50.0

    def test_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            BloatRatio(-0.1)
        with pytest.raises(ValueError):
            BloatRatio(1.1)


class TestToolSource:
    def test_mcp_prefix(self) -> None:
        assert ToolSource.from_string("mcp:github") == ToolSource.MCP

    def test_system(self) -> None:
        assert ToolSource.from_string("system") == ToolSource.SYSTEM

    def test_unknown_defaults_to_system(self) -> None:
        assert ToolSource.from_string("something_else") == ToolSource.SYSTEM
