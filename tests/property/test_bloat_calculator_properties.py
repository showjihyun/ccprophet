"""Property tests — BloatCalculator domain invariants.

LAYERING.md §7.6 (Hypothesis contract): `BloatCalculator.calculate` must
preserve token conservation (unused + used == total), produce a ratio in
[0, 1], and be order-independent with respect to input sequences.
"""

from __future__ import annotations

from hypothesis import assume, given
from hypothesis import strategies as st

from ccprophet.domain.entities import ToolCall, ToolDef
from ccprophet.domain.services.bloat import BloatCalculator
from ccprophet.domain.values import SessionId, TokenCount

_SOURCES = st.sampled_from(["builtin", "subagent", "mcp:github", "mcp:filesystem"])
_TOOL_NAMES = st.text(
    alphabet=st.characters(min_codepoint=48, max_codepoint=122, whitelist_categories=["L", "N"]),
    min_size=1,
    max_size=20,
)


def _tool_def(name: str, tokens: int, source: str) -> ToolDef:
    return ToolDef(tool_name=name, source=source, tokens=TokenCount(tokens))


def _tool_call(sid: SessionId, name: str) -> ToolCall:
    from datetime import datetime, timezone

    return ToolCall(
        tool_call_id=name + "-tc",
        session_id=sid,
        tool_name=name,
        input_hash="h",
        ts=datetime(2026, 4, 18, 0, 0, 0, tzinfo=timezone.utc),
        input_tokens=TokenCount(0),
        output_tokens=TokenCount(0),
        latency_ms=0,
        success=True,
    )


@given(
    st.lists(
        st.tuples(_TOOL_NAMES, st.integers(min_value=0, max_value=100_000), _SOURCES),
        min_size=0,
        max_size=50,
        unique_by=lambda t: t[0],
    ),
    st.lists(_TOOL_NAMES, min_size=0, max_size=30),
)
def test_token_conservation(defs_spec, called_names) -> None:  # type: ignore[no-untyped-def]
    defs = [_tool_def(n, t, s) for n, t, s in defs_spec]
    sid = SessionId("prop")
    calls = [_tool_call(sid, n) for n in called_names]

    report = BloatCalculator.calculate(defs, calls)

    used_tokens = sum(i.tokens.value for i in report.items if i.used)
    assert report.bloat_tokens.value + used_tokens == report.total_tokens.value
    assert 0.0 <= report.bloat_ratio.value <= 1.0


@given(
    st.lists(
        st.tuples(_TOOL_NAMES, st.integers(min_value=1, max_value=100_000), _SOURCES),
        min_size=1,
        max_size=30,
        unique_by=lambda t: t[0],
    ),
)
def test_ratio_is_1_when_nothing_called(defs_spec) -> None:  # type: ignore[no-untyped-def]
    defs = [_tool_def(n, t, s) for n, t, s in defs_spec]
    report = BloatCalculator.calculate(defs, [])
    assert report.bloat_ratio.value == 1.0
    assert report.bloat_tokens.value == report.total_tokens.value


@given(
    st.lists(
        st.tuples(_TOOL_NAMES, st.integers(min_value=0, max_value=1000), _SOURCES),
        min_size=1,
        max_size=20,
        unique_by=lambda t: t[0],
    ),
    st.randoms(),
)
def test_order_independence(defs_spec, rng) -> None:  # type: ignore[no-untyped-def]
    assume(len(defs_spec) >= 2)
    defs_a = [_tool_def(n, t, s) for n, t, s in defs_spec]
    defs_b = list(defs_a)
    rng.shuffle(defs_b)

    a = BloatCalculator.calculate(defs_a, [])
    b = BloatCalculator.calculate(defs_b, [])
    assert a.total_tokens == b.total_tokens
    assert a.bloat_tokens == b.bloat_tokens
    assert a.bloat_ratio == b.bloat_ratio
