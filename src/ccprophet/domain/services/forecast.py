"""Linear forecaster (F5 Phase 1).

Projects the moment the session's cumulative input token usage will cross
`context_window_size * compact_threshold_ratio` using a simple least-squares
linear regression on the most recent `window` of samples.

Pure — stdlib only, no numpy / scipy / statsmodels. Deterministic given the
same inputs. See PRD.md §6.5 F5 for Phase 1 scope and docs/ARCHITECT.md §4.6
for kernel design.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from ccprophet.domain.entities import Forecast
from ccprophet.domain.values import SessionId

DEFAULT_WINDOW = timedelta(minutes=5)
DEFAULT_COMPACT_THRESHOLD_RATIO = 0.8
MAX_HORIZON = timedelta(days=7)
MODEL_NAME = "linear_v1"


@dataclass(frozen=True, slots=True)
class TokenSample:
    """A single point on the session's cumulative input-token curve."""

    ts: datetime
    cumulative_input_tokens: int


class LinearForecaster:
    """Least-squares slope projection on recent token samples.

    Phase 1 intentionally keeps the math simple — see PRD F5 (FR-5.1).
    Phase 3 will swap the kernel for ARIMA behind the same `ForecastModel`
    port, so this service must stay a drop-in replacement target.
    """

    @staticmethod
    def predict(
        samples: Sequence[TokenSample],
        *,
        session_id: SessionId,
        context_window_size: int,
        now: datetime,
        compact_threshold_ratio: float = DEFAULT_COMPACT_THRESHOLD_RATIO,
        window: timedelta = DEFAULT_WINDOW,
    ) -> Forecast:
        threshold = context_window_size * compact_threshold_ratio
        last_cum = samples[-1].cumulative_input_tokens if samples else 0
        context_usage = (
            min(1.0, last_cum / context_window_size)
            if context_window_size > 0
            else 0.0
        )

        windowed = _filter_window(samples, now=now, window=window)
        sample_count = len(windowed)

        if sample_count < 2:
            # Not enough data to regress — return a low-confidence no-prediction.
            return _make_forecast(
                session_id=session_id,
                predicted_at=now,
                predicted_compact_at=None,
                confidence=_confidence_for(sample_count),
                input_token_rate=0.0,
                context_usage=context_usage,
            )

        slope = _slope_tokens_per_sec(windowed)

        if slope <= 0:
            # Flat or decreasing usage — no compact projected, medium confidence
            # ("steady, not projected to compact").
            return _make_forecast(
                session_id=session_id,
                predicted_at=now,
                predicted_compact_at=None,
                confidence=min(0.5, _confidence_for(sample_count)),
                input_token_rate=0.0,
                context_usage=context_usage,
            )

        remaining = threshold - last_cum
        if remaining <= 0:
            # Already past the compact threshold — project "now".
            predicted_at = now
            return _make_forecast(
                session_id=session_id,
                predicted_at=now,
                predicted_compact_at=predicted_at,
                confidence=_confidence_for(sample_count),
                input_token_rate=slope,
                context_usage=context_usage,
            )

        seconds_until = remaining / slope
        seconds_until = _clamp_horizon_seconds(seconds_until)
        predicted_compact_at = now + timedelta(seconds=seconds_until)
        return _make_forecast(
            session_id=session_id,
            predicted_at=now,
            predicted_compact_at=predicted_compact_at,
            confidence=_confidence_for(sample_count),
            input_token_rate=slope,
            context_usage=context_usage,
        )


def _filter_window(
    samples: Sequence[TokenSample], *, now: datetime, window: timedelta
) -> list[TokenSample]:
    cutoff = now - window
    # Samples are expected chronologically ordered, but defend against
    # callers that hand us unsorted data — downstream math relies on order.
    ordered = sorted(samples, key=lambda s: s.ts)
    return [s for s in ordered if s.ts >= cutoff]


def _slope_tokens_per_sec(samples: Sequence[TokenSample]) -> float:
    """Least-squares slope with time expressed in seconds from the first point."""
    t0 = samples[0].ts
    xs = [(s.ts - t0).total_seconds() for s in samples]
    ys = [float(s.cumulative_input_tokens) for s in samples]
    n = len(samples)

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


def _confidence_for(sample_count: int) -> float:
    """Confidence heuristic for Phase 1: monotone in sample count, capped at 0.95.

    Deeper statistics (R², residual stddev) are deferred to Phase 3 where a
    richer `ForecastModel` adapter replaces this kernel.
    """
    if sample_count <= 0:
        return 0.1
    if sample_count == 1:
        return 0.3
    return min(0.95, sample_count / 50)


def _clamp_horizon_seconds(seconds: float) -> float:
    if seconds < 0:
        return 0.0
    max_s = MAX_HORIZON.total_seconds()
    if seconds > max_s:
        return max_s
    return seconds


def _make_forecast(
    *,
    session_id: SessionId,
    predicted_at: datetime,
    predicted_compact_at: datetime | None,
    confidence: float,
    input_token_rate: float,
    context_usage: float,
) -> Forecast:
    return Forecast(
        forecast_id=str(uuid.uuid4()),
        session_id=session_id,
        predicted_at=predicted_at,
        predicted_compact_at=predicted_compact_at,
        confidence=confidence,
        model_used=MODEL_NAME,
        input_token_rate=input_token_rate,
        context_usage_at_pred=context_usage,
    )
