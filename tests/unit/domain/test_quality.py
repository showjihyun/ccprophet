from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ccprophet.domain.entities import (
    DailyQualityPoint,
    QualitySeries,
    Session,
    ToolCall,
)
from ccprophet.domain.services.quality import (
    QualityInputs,
    QualityTracker,
    RegressionDetector,
)
from ccprophet.domain.values import SessionId, TokenCount
from tests.fixtures.builders import SessionBuilder, ToolCallBuilder


def _session_on_day(day: int, sid: str, *, output: int = 1000, compacted: bool = False):  # type: ignore[no-untyped-def]
    base = SessionBuilder().with_id(sid).build()
    return replace(
        base,
        started_at=datetime(2026, 4, day, 12, 0, tzinfo=timezone.utc),
        model="claude-opus-4-7",
        total_output_tokens=TokenCount(output),
        total_input_tokens=TokenCount(output * 5),
        compacted=compacted,
    )


def test_series_groups_by_day() -> None:
    sessions = [
        _session_on_day(1, "a"),
        _session_on_day(1, "b"),
        _session_on_day(2, "c"),
    ]
    series = QualityTracker.series_from_sessions(
        QualityInputs(
            model="claude-opus-4-7",
            sessions=sessions,
            tool_calls_by_session={},
            outcomes_by_session={},
        )
    )
    assert len(series.points) == 2
    assert series.points[0].sample_size == 2
    assert series.points[1].sample_size == 1


def test_detector_flags_output_token_drop() -> None:
    # Baseline days: high output. Recent days: low output → degraded.
    points = []
    for i in range(1, 11):
        output = 2000 if i <= 8 else 500  # day 1-8 baseline, 9-10 recent
        points.append(
            DailyQualityPoint(
                day=datetime(2026, 4, i).date(),
                model="m",
                sample_size=3,
                avg_output_tokens=float(output),
                avg_tool_calls=5.0,
                tool_call_success_rate=1.0,
                autocompact_rate=0.0,
                outcome_fail_rate=None,
                repeat_read_rate=0.0,
                avg_input_output_ratio=4.0,
            )
        )
    report = RegressionDetector.detect(
        QualitySeries(model="m", points=tuple(points)),
        window_days=2,
        baseline_days=8,
        threshold_sigma=1.0,
    )
    metric_flags = {f.metric_name: f for f in report.flags}
    assert "avg_output_tokens" in metric_flags
    assert metric_flags["avg_output_tokens"].direction == "degraded"
    assert report.has_regression is True


def test_detector_ignores_stable_series() -> None:
    points = []
    for i in range(1, 11):
        points.append(
            DailyQualityPoint(
                day=datetime(2026, 4, i).date(),
                model="m",
                sample_size=3,
                avg_output_tokens=1000.0,
                avg_tool_calls=5.0,
                tool_call_success_rate=1.0,
                autocompact_rate=0.0,
                outcome_fail_rate=None,
                repeat_read_rate=0.0,
                avg_input_output_ratio=4.0,
            )
        )
    report = RegressionDetector.detect(
        QualitySeries(model="m", points=tuple(points)),
        window_days=2,
        baseline_days=8,
        threshold_sigma=2.0,
    )
    assert report.flags == ()
    assert report.has_regression is False


def test_detector_needs_baseline_samples() -> None:
    points = [
        DailyQualityPoint(
            day=datetime(2026, 4, i).date(),
            model="m",
            sample_size=1,
            avg_output_tokens=float(i * 100),
            avg_tool_calls=5.0,
            tool_call_success_rate=1.0,
            autocompact_rate=0.0,
            outcome_fail_rate=None,
            repeat_read_rate=0.0,
            avg_input_output_ratio=4.0,
        )
        for i in range(1, 3)
    ]
    report = RegressionDetector.detect(
        QualitySeries(model="m", points=tuple(points)),
        window_days=1,
        baseline_days=5,
    )
    # Only 1 baseline sample → no flags
    assert report.flags == ()


def test_repeat_read_counted() -> None:
    sid = "r"
    session = _session_on_day(1, sid)
    calls = [
        ToolCallBuilder().in_session(SessionId(sid)).for_tool("Read").build()
        for _ in range(5)
    ]
    # all same input_hash (builder default) → triggers repeat_read
    series = QualityTracker.series_from_sessions(
        QualityInputs(
            model="claude-opus-4-7",
            sessions=[session],
            tool_calls_by_session={sid: calls},
            outcomes_by_session={},
        )
    )
    assert series.points[0].repeat_read_rate == 1.0


def test_tool_call_success_rate() -> None:
    sid = "t"
    session = _session_on_day(1, sid)
    calls = [
        ToolCallBuilder().in_session(SessionId(sid)).for_tool("Read").build(),
        ToolCallBuilder().in_session(SessionId(sid)).for_tool("Bash").build(),
    ]
    # both default success=True
    series = QualityTracker.series_from_sessions(
        QualityInputs(
            model="claude-opus-4-7",
            sessions=[session],
            tool_calls_by_session={sid: calls},
            outcomes_by_session={},
        )
    )
    assert series.points[0].tool_call_success_rate == 1.0
