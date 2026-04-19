"""Driven port for autocompact forecasting.

A `ForecastModel` takes a chronological sequence of cumulative-input-token
samples and returns a `Forecast` entity. Phase 1 has a single adapter
(`LinearForecastModel`); Phase 3 adds `ArimaForecastModel` behind the same
interface. Use cases depend only on this Protocol.

Kept in its own module (rather than co-located in `repositories.py`) to keep
each port file narrowly focused and the import graph shallow.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from ccprophet.domain.entities import Forecast
from ccprophet.domain.services.forecast import TokenSample
from ccprophet.domain.values import SessionId


class ForecastModel(Protocol):
    def predict(
        self,
        samples: Sequence[TokenSample],
        *,
        session_id: SessionId,
        context_window_size: int,
        now: datetime,
    ) -> Forecast: ...
