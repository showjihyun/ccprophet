"""Forecast when a session will hit the autocompact threshold (F5 Phase 1).

Derives a chronological sequence of cumulative-input-token samples from the
session's `AssistantResponse` events (usage deltas), feeds them into the
`ForecastModel` port, persists the result, and returns the Forecast.

Same extraction shape as `backfill_from_jsonl._accumulate_usage` — but kept
per-event here because the forecaster needs the *curve*, not the final total.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from ccprophet.domain.entities import Event, Forecast
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.services.forecast import TokenSample
from ccprophet.domain.values import SessionId
from ccprophet.ports.clock import Clock
from ccprophet.ports.forecast_model import ForecastModel
from ccprophet.ports.repositories import (
    EventRepository,
    ForecastRepository,
    SessionRepository,
)


@dataclass(frozen=True)
class ForecastCompactUseCase:
    sessions: SessionRepository
    events: EventRepository
    forecasts: ForecastRepository
    model: ForecastModel
    clock: Clock

    def execute(self, session_id: SessionId) -> Forecast:
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)

        samples = _samples_from_events(self.events.list_by_session(session_id))
        forecast = self.model.predict(
            samples,
            session_id=session_id,
            context_window_size=session.context_window_size,
            now=self.clock.now(),
        )
        self.forecasts.save(forecast)
        return forecast

    def execute_current(self) -> Forecast:
        session = self.sessions.latest_active()
        if session is None:
            raise SessionNotFound(SessionId("(no active session)"))
        return self.execute(session.session_id)


def _samples_from_events(events: Iterable[Event]) -> list[TokenSample]:
    """Build the cumulative-input-token curve from AssistantResponse events.

    Only AssistantResponse rows carry `message.usage` in Claude Code JSONL,
    so other event types are skipped silently. Events without usage are also
    skipped (don't advance the curve). Timestamps are normalized to UTC-aware
    to avoid mixing naive (DuckDB default) and aware (SystemClock) values in
    the forecaster's window filter.
    """
    samples: list[TokenSample] = []
    cumulative = 0
    materialized = [(_normalize_ts(e.ts), e.payload) for e in events]
    materialized.sort(key=lambda pair: pair[0])
    for ts, payload in materialized:
        delta = _extract_input_delta(payload)
        if delta is None:
            continue
        cumulative += delta
        samples.append(TokenSample(ts=ts, cumulative_input_tokens=cumulative))
    return samples


def _normalize_ts(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _extract_input_delta(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    total = (
        _int_or_zero(usage.get("input_tokens"))
        + _int_or_zero(usage.get("cache_creation_input_tokens"))
        + _int_or_zero(usage.get("cache_read_input_tokens"))
    )
    # A usage block with all zeros still counts as a data point so the curve
    # isn't broken by idle steps — otherwise we'd miss "no movement" signal.
    return total


def _int_or_zero(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
