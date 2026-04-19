from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

import pytest

from ccprophet.domain.entities import Forecast
from ccprophet.domain.values import SessionId

NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


def _forecast(
    *,
    forecast_id: str,
    session_id: str = "s-contract",
    predicted_compact_at: datetime | None = None,
    confidence: float = 0.5,
    rate: float = 0.0,
    usage: float = 0.0,
    predicted_at: datetime | None = None,
) -> Forecast:
    return Forecast(
        forecast_id=forecast_id,
        session_id=SessionId(session_id),
        predicted_at=predicted_at or NOW,
        predicted_compact_at=predicted_compact_at,
        confidence=confidence,
        model_used="linear_v1",
        input_token_rate=rate,
        context_usage_at_pred=usage,
    )


class ForecastRepositoryContract(ABC):
    @pytest.fixture
    @abstractmethod
    def repository(self):  # type: ignore[no-untyped-def]
        ...

    def test_save_then_list(self, repository) -> None:  # type: ignore[no-untyped-def]
        f = _forecast(
            forecast_id="f1",
            predicted_compact_at=NOW + timedelta(minutes=10),
            confidence=0.7,
            rate=500.0,
            usage=0.3,
        )
        repository.save(f)
        rows = list(repository.list_for_session(SessionId("s-contract")))
        assert len(rows) == 1
        assert rows[0].forecast_id == "f1"
        assert rows[0].predicted_compact_at == f.predicted_compact_at
        assert rows[0].confidence == pytest.approx(0.7)

    def test_list_returns_empty_for_unknown_session(self, repository) -> None:  # type: ignore[no-untyped-def]
        assert list(repository.list_for_session(SessionId("nope"))) == []

    def test_multiple_forecasts_ordered_chronologically(self, repository) -> None:  # type: ignore[no-untyped-def]
        early = _forecast(
            forecast_id="f-early",
            predicted_at=NOW - timedelta(minutes=5),
        )
        late = _forecast(
            forecast_id="f-late",
            predicted_at=NOW,
        )
        repository.save(late)
        repository.save(early)
        rows = list(repository.list_for_session(SessionId("s-contract")))
        assert [r.forecast_id for r in rows] == ["f-early", "f-late"]

    def test_predicted_compact_at_none_roundtrip(self, repository) -> None:  # type: ignore[no-untyped-def]
        f = _forecast(forecast_id="f-none", predicted_compact_at=None)
        repository.save(f)
        rows = list(repository.list_for_session(SessionId("s-contract")))
        assert len(rows) == 1
        assert rows[0].predicted_compact_at is None


class TestInMemoryForecastRepository(ForecastRepositoryContract):
    @pytest.fixture
    def repository(self):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.inmemory.repositories import (
            InMemoryForecastRepository,
        )

        return InMemoryForecastRepository()
