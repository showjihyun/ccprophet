"""Phase 1 linear autocompact forecaster adapter.

Delegates straight to the pure `LinearForecaster` domain service. The reason
this adapter exists at all — rather than the use case calling the service
directly — is so Phase 3 can drop in `ArimaForecastModel` (with statsmodels
imports that must stay out of `domain/` and `use_cases/`) behind the same
`ForecastModel` port without touching `ForecastCompactUseCase`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from ccprophet.domain.entities import Forecast
from ccprophet.domain.services.forecast import (
    DEFAULT_COMPACT_THRESHOLD_RATIO,
    DEFAULT_WINDOW,
    LinearForecaster,
    TokenSample,
)
from ccprophet.domain.values import SessionId


class LinearForecastModel:
    def __init__(
        self,
        *,
        window: timedelta = DEFAULT_WINDOW,
        compact_threshold_ratio: float = DEFAULT_COMPACT_THRESHOLD_RATIO,
    ) -> None:
        self._window = window
        self._compact_threshold_ratio = compact_threshold_ratio

    def predict(
        self,
        samples: Sequence[TokenSample],
        *,
        session_id: SessionId,
        context_window_size: int,
        now: datetime,
    ) -> Forecast:
        return LinearForecaster.predict(
            samples,
            session_id=session_id,
            context_window_size=context_window_size,
            now=now,
            window=self._window,
            compact_threshold_ratio=self._compact_threshold_ratio,
        )
