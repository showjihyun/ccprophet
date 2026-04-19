"""Phase 3 ARIMA autocompact forecaster adapter.

Wraps `statsmodels.tsa.arima.model.ARIMA(1,1,1)` behind the `ForecastModel`
port. When the statsmodels optional extra is not installed, the sample count
is too low for the model to fit reliably, or `.fit()` / `.forecast()` itself
raises, this adapter transparently falls back to `LinearForecastModel` and
relabels the returned `Forecast.model_used` to ``"linear_v1_fallback"`` so
callers can tell ARIMA bailed out.

Import is lazy: merely importing this module does NOT require statsmodels.
This keeps the base install lightweight (AP-4) and the Clean Architecture
forbidden-module contract (pyproject.toml [tool.importlinter]) satisfied
everywhere except inside this single adapter file.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta

from ccprophet.adapters.forecast.linear import LinearForecastModel
from ccprophet.domain.entities import Forecast
from ccprophet.domain.services.forecast import TokenSample
from ccprophet.domain.values import SessionId
from ccprophet.ports.forecast_model import ForecastModel

MODEL_NAME = "arima_v2"
FALLBACK_MODEL_NAME = "linear_v1_fallback"
DEFAULT_ORDER: tuple[int, int, int] = (1, 1, 1)
DEFAULT_MIN_SAMPLES = 10
DEFAULT_COMPACT_THRESHOLD_RATIO = 0.8
N_FORECAST_STEPS = 60
INTERVAL_WINDOW = 5  # last K samples used to estimate seconds-per-step
MAX_HORIZON = timedelta(days=7)


class ArimaForecastModel:
    """ARIMA-based `ForecastModel` with a linear fallback.

    Fallback decision tree (checked in order):
      1. ``len(samples) < min_samples``                -> linear fallback
      2. ``import statsmodels`` raises ``ImportError`` -> linear fallback
      3. ``ARIMA(order).fit()`` raises                 -> linear fallback
      4. ``fit.forecast(steps=N)`` raises              -> linear fallback
      5. otherwise                                     -> ARIMA prediction
    """

    def __init__(
        self,
        *,
        order: tuple[int, int, int] = DEFAULT_ORDER,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        compact_threshold_ratio: float = DEFAULT_COMPACT_THRESHOLD_RATIO,
        fallback: ForecastModel | None = None,
    ) -> None:
        self._order = order
        self._min_samples = min_samples
        self._compact_threshold_ratio = compact_threshold_ratio
        self._fallback: ForecastModel = fallback or LinearForecastModel()

    def predict(
        self,
        samples: Sequence[TokenSample],
        *,
        session_id: SessionId,
        context_window_size: int,
        now: datetime,
    ) -> Forecast:
        # (1) Too few samples — ARIMA(1,1,1) would over-fit noise.
        if len(samples) < self._min_samples:
            return self._relabel_fallback(
                samples,
                session_id=session_id,
                context_window_size=context_window_size,
                now=now,
            )

        # (2) Optional extra not installed — lazy import guard.
        try:
            import statsmodels.tsa.arima.model as _arima_mod
        except ImportError:
            return self._relabel_fallback(
                samples,
                session_id=session_id,
                context_window_size=context_window_size,
                now=now,
            )

        sorted_samples = sorted(samples, key=lambda s: s.ts)
        y = [float(s.cumulative_input_tokens) for s in sorted_samples]

        # (3) Fit can fail on degenerate input (flat series, singular matrix).
        try:
            fit = _arima_mod.ARIMA(y, order=self._order).fit()
        except Exception:
            return self._relabel_fallback(
                samples,
                session_id=session_id,
                context_window_size=context_window_size,
                now=now,
            )

        # (4) Forecast can fail on numerical blow-up.
        try:
            forecasted = fit.forecast(steps=N_FORECAST_STEPS)
        except Exception:
            return self._relabel_fallback(
                samples,
                session_id=session_id,
                context_window_size=context_window_size,
                now=now,
            )

        threshold = context_window_size * self._compact_threshold_ratio
        hit_step: int | None = None
        for step, predicted_y in enumerate(forecasted, start=1):
            if float(predicted_y) >= threshold:
                hit_step = step
                break

        seconds_per_step = _estimate_seconds_per_step(sorted_samples, INTERVAL_WINDOW)
        predicted_compact_at: datetime | None
        if hit_step is not None and seconds_per_step > 0:
            horizon = min(
                hit_step * seconds_per_step,
                MAX_HORIZON.total_seconds(),
            )
            predicted_compact_at = now + timedelta(seconds=horizon)
        else:
            predicted_compact_at = None

        last_cumulative = int(y[-1])
        first_cumulative = float(y[0])
        span_seconds = max(
            (sorted_samples[-1].ts - sorted_samples[0].ts).total_seconds(),
            1.0,
        )
        rate = (y[-1] - first_cumulative) / span_seconds
        context_usage = (
            min(1.0, last_cumulative / context_window_size) if context_window_size > 0 else 0.0
        )
        confidence = min(
            0.95,
            0.5 + 0.01 * (len(samples) - self._min_samples),
        )

        return Forecast(
            forecast_id=str(uuid.uuid4()),
            session_id=session_id,
            predicted_at=now,
            predicted_compact_at=predicted_compact_at,
            confidence=confidence,
            model_used=MODEL_NAME,
            input_token_rate=rate,
            context_usage_at_pred=context_usage,
        )

    def _relabel_fallback(
        self,
        samples: Sequence[TokenSample],
        *,
        session_id: SessionId,
        context_window_size: int,
        now: datetime,
    ) -> Forecast:
        base = self._fallback.predict(
            samples,
            session_id=session_id,
            context_window_size=context_window_size,
            now=now,
        )
        return replace(base, model_used=FALLBACK_MODEL_NAME)


def _estimate_seconds_per_step(samples: Sequence[TokenSample], k: int) -> float:
    """Average inter-sample gap (in seconds) over the last ``k`` samples.

    Defaults to 60s when we cannot estimate (fewer than 2 points or all
    timestamps identical), matching the typical assistant-turn cadence.
    """
    if len(samples) < 2:
        return 60.0
    recent = samples[-k:] if len(samples) > k else samples
    gaps = [(recent[i].ts - recent[i - 1].ts).total_seconds() for i in range(1, len(recent))]
    if not gaps:
        return 60.0
    avg = sum(gaps) / len(gaps)
    return avg if avg > 0 else 60.0
