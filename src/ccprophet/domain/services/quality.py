"""Quality Watch domain services (F12).

Two pure services:

- `QualityTracker.series_from_sessions(...)` rolls per-session observations
  into one `DailyQualityPoint` per (day, model).
- `RegressionDetector.detect(...)` splits that series into a recent window
  and a baseline, computes each metric's z-score, and flags the ones that
  drift ≥ threshold sigma. No IO; the use case loads the inputs.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from ccprophet.domain.entities import (
    DailyQualityPoint,
    OutcomeLabel,
    QualitySeries,
    RegressionFlag,
    RegressionReport,
    Session,
    ToolCall,
)
from ccprophet.domain.values import OutcomeLabelValue, SessionId

REPEAT_READ_THRESHOLD = 5
READ_TOOLS = frozenset({"Read", "Glob", "Grep"})

# (metric_name, "higher_is_better") — direction for regression interpretation
METRIC_DIRECTIONS: dict[str, bool] = {
    "avg_output_tokens": True,
    "tool_call_success_rate": True,
    "autocompact_rate": False,
    "avg_tool_calls": False,
    "repeat_read_rate": False,
    "outcome_fail_rate": False,
    "avg_input_output_ratio": False,
}


@dataclass(frozen=True, slots=True)
class QualityInputs:
    model: str
    sessions: Sequence[Session]
    tool_calls_by_session: Mapping[str, Sequence[ToolCall]]
    outcomes_by_session: Mapping[str, OutcomeLabel]


class QualityTracker:
    @staticmethod
    def series_from_sessions(inputs: QualityInputs) -> QualitySeries:
        sessions_by_day: dict[date, list[Session]] = {}
        for s in inputs.sessions:
            if s.model != inputs.model:
                continue
            day = s.started_at.date()
            sessions_by_day.setdefault(day, []).append(s)

        points = tuple(
            _build_point(
                day, day_sessions, inputs.tool_calls_by_session,
                inputs.outcomes_by_session, inputs.model,
            )
            for day, day_sessions in sorted(sessions_by_day.items())
        )
        return QualitySeries(model=inputs.model, points=points)


def _build_point(
    day: date,
    sessions: Sequence[Session],
    tool_calls_by_session: Mapping[str, Sequence[ToolCall]],
    outcomes_by_session: Mapping[str, OutcomeLabel],
    model: str,
) -> DailyQualityPoint:
    n = len(sessions)
    output_tokens = [s.total_output_tokens.value for s in sessions]
    io_ratios = [
        s.total_input_tokens.value / s.total_output_tokens.value
        for s in sessions
        if s.total_output_tokens.value > 0
    ]
    tool_call_counts: list[int] = []
    tool_calls_flat: list[ToolCall] = []
    repeat_read_sessions = 0
    for s in sessions:
        calls = list(tool_calls_by_session.get(s.session_id.value, []))
        tool_call_counts.append(len(calls))
        tool_calls_flat.extend(calls)
        if _has_repeat_reads(calls):
            repeat_read_sessions += 1

    success_rate = (
        sum(1 for tc in tool_calls_flat if tc.success) / len(tool_calls_flat)
        if tool_calls_flat
        else 1.0
    )
    autocompact_rate = sum(1 for s in sessions if s.compacted) / n
    repeat_read_rate = repeat_read_sessions / n

    labeled = [
        outcomes_by_session.get(s.session_id.value) for s in sessions
    ]
    labeled_nonnull = [label for label in labeled if label is not None]
    fail_rate: float | None = None
    if labeled_nonnull:
        fail_rate = sum(
            1 for label in labeled_nonnull
            if label.label == OutcomeLabelValue.FAIL
        ) / len(labeled_nonnull)

    return DailyQualityPoint(
        day=day,
        model=model,
        sample_size=n,
        avg_output_tokens=_mean(output_tokens),
        avg_tool_calls=_mean(tool_call_counts),
        tool_call_success_rate=success_rate,
        autocompact_rate=autocompact_rate,
        outcome_fail_rate=fail_rate,
        repeat_read_rate=repeat_read_rate,
        avg_input_output_ratio=_mean(io_ratios),
    )


def _has_repeat_reads(calls: Sequence[ToolCall]) -> bool:
    counts: dict[str, int] = {}
    for tc in calls:
        if tc.tool_name not in READ_TOOLS:
            continue
        counts[tc.input_hash] = counts.get(tc.input_hash, 0) + 1
        if counts[tc.input_hash] >= REPEAT_READ_THRESHOLD:
            return True
    return False


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


class RegressionDetector:
    @staticmethod
    def detect(
        series: QualitySeries,
        *,
        window_days: int,
        baseline_days: int,
        threshold_sigma: float = 2.0,
    ) -> RegressionReport:
        points = list(series.points)
        recent = points[-window_days:] if window_days > 0 else []
        baseline = (
            points[-(window_days + baseline_days):-window_days]
            if window_days > 0
            else points[-baseline_days:]
        )

        flags: list[RegressionFlag] = []
        for metric_name, higher_is_better in METRIC_DIRECTIONS.items():
            flag = _metric_flag(
                metric_name,
                higher_is_better,
                recent,
                baseline,
                threshold_sigma,
            )
            if flag is not None:
                flags.append(flag)

        return RegressionReport(
            model=series.model,
            window_days=window_days,
            baseline_days=baseline_days,
            window_sample_size=sum(p.sample_size for p in recent),
            baseline_sample_size=sum(p.sample_size for p in baseline),
            flags=tuple(flags),
            series=series,
        )


def _metric_flag(
    metric_name: str,
    higher_is_better: bool,
    recent: Sequence[DailyQualityPoint],
    baseline: Sequence[DailyQualityPoint],
    threshold_sigma: float,
) -> RegressionFlag | None:
    recent_values = _metric_values(metric_name, recent)
    baseline_values = _metric_values(metric_name, baseline)
    if len(baseline_values) < 3 or not recent_values:
        return None

    recent_mean = _mean(recent_values)
    baseline_mean = _mean(baseline_values)
    baseline_stddev = _stddev(baseline_values, baseline_mean)

    # Floor stddev at 10% of baseline mean so a perfectly-flat baseline can
    # still trigger a flag when recent drifts meaningfully.
    effective_stddev = (
        baseline_stddev if baseline_stddev > 0 else abs(baseline_mean) * 0.1
    )
    if effective_stddev == 0:
        return None
    z_score = (recent_mean - baseline_mean) / effective_stddev

    direction = _direction(z_score, higher_is_better, threshold_sigma)
    if direction == "stable":
        return None

    explanation = _explain(
        metric_name, direction, recent_mean, baseline_mean, z_score
    )
    return RegressionFlag(
        metric_name=metric_name,
        baseline_mean=baseline_mean,
        recent_mean=recent_mean,
        baseline_stddev=baseline_stddev,
        z_score=z_score,
        direction=direction,
        explanation=explanation,
    )


def _metric_values(
    name: str, points: Sequence[DailyQualityPoint]
) -> list[float]:
    values: list[float] = []
    for p in points:
        v = getattr(p, name)
        if v is None:
            continue
        values.append(float(v))
    return values


def _stddev(values: Sequence[float], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _direction(
    z_score: float, higher_is_better: bool, threshold_sigma: float
) -> str:
    if abs(z_score) < threshold_sigma:
        return "stable"
    improved = z_score > 0 if higher_is_better else z_score < 0
    return "improved" if improved else "degraded"


def _explain(
    metric_name: str,
    direction: str,
    recent_mean: float,
    baseline_mean: float,
    z_score: float,
) -> str:
    delta = recent_mean - baseline_mean
    pct = (delta / baseline_mean * 100) if baseline_mean else 0.0
    tag = "DEGRADED" if direction == "degraded" else "IMPROVED"
    return (
        f"[{tag}] {metric_name}: {baseline_mean:.3f} → {recent_mean:.3f} "
        f"({pct:+.1f}%, {z_score:+.2f}σ)"
    )
