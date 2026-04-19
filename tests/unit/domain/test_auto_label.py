from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from ccprophet.domain.services.auto_label import classify
from ccprophet.domain.values import OutcomeLabelValue, SessionId
from tests.fixtures.builders import SessionBuilder, ToolCallBuilder


def _finished_session() -> object:
    return (
        SessionBuilder()
        .with_id("s-finished")
        .ended(datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc))
        .build()
    )


def _call(success: bool = True, tool: str = "Bash", input_hash: str = "h") -> object:
    tc = (
        ToolCallBuilder()
        .in_session(SessionId("s-finished"))
        .for_tool(tool)
        .build()
    )
    return replace(tc, success=success, input_hash=input_hash)


def test_active_session_returns_none() -> None:
    session = SessionBuilder().build()  # no ended_at
    assert classify(session, [_call() for _ in range(10)]) is None


def test_too_few_calls_returns_none() -> None:
    assert classify(_finished_session(), [_call() for _ in range(3)]) is None


def test_all_successful_calls_label_success() -> None:
    assert (
        classify(_finished_session(), [_call() for _ in range(6)])
        is OutcomeLabelValue.SUCCESS
    )


def test_compacted_session_labels_fail() -> None:
    session = replace(_finished_session(), compacted=True)
    assert classify(session, [_call() for _ in range(10)]) is OutcomeLabelValue.FAIL


def test_many_failed_calls_label_fail() -> None:
    calls = [_call(success=False) for _ in range(10)]
    assert classify(_finished_session(), calls) is OutcomeLabelValue.FAIL


def test_repeat_reads_label_fail() -> None:
    calls = [_call(tool="Read", input_hash="same") for _ in range(6)]
    assert classify(_finished_session(), calls) is OutcomeLabelValue.FAIL


def test_mixed_success_rate_returns_none() -> None:
    # 60% success on 5 calls — below success floor, not enough for fail.
    calls = [_call(success=(i < 3)) for i in range(5)]
    assert classify(_finished_session(), calls) is None
