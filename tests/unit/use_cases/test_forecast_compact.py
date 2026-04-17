from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.forecast.linear import LinearForecastModel
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.entities import Event
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.values import EventId, RawHash, SessionId
from ccprophet.use_cases.forecast_compact import ForecastCompactUseCase
from tests.fixtures.builders import SessionBuilder

SID = "s-forecast"
NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


def _seed_session(repos: InMemoryRepositorySet, *, context_window: int = 200_000) -> None:
    # SessionBuilder doesn't expose context_window_size — patch via replace.
    from dataclasses import replace
    session = SessionBuilder().with_id(SID).build()
    repos.sessions.upsert(replace(session, context_window_size=context_window))


def _assistant_event(
    repos: InMemoryRepositorySet,
    *,
    seconds_before_now: int,
    input_tokens: int,
    cache_creation: int = 0,
    cache_read: int = 0,
    event_idx: int = 0,
) -> None:
    ts = NOW - timedelta(seconds=seconds_before_now)
    payload = {
        "message": {
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
                "output_tokens": 100,
            }
        }
    }
    repos.events.append(
        Event(
            event_id=EventId(f"evt-fc-{event_idx}"),
            session_id=SessionId(SID),
            event_type="AssistantResponse",
            ts=ts,
            payload=payload,
            raw_hash=RawHash(f"hash-fc-{event_idx}-{seconds_before_now}"),
        )
    )


def _use_case(repos: InMemoryRepositorySet) -> ForecastCompactUseCase:
    return ForecastCompactUseCase(
        sessions=repos.sessions,
        events=repos.events,
        forecasts=repos.forecasts,
        model=LinearForecastModel(),
        clock=FrozenClock(NOW),
    )


class TestForecastCompactUseCase:
    def test_raises_when_session_missing(self) -> None:
        repos = InMemoryRepositorySet()
        uc = _use_case(repos)
        with pytest.raises(SessionNotFound):
            uc.execute(SessionId("nope"))

    def test_execute_current_raises_when_no_active_session(self) -> None:
        repos = InMemoryRepositorySet()
        uc = _use_case(repos)
        with pytest.raises(SessionNotFound):
            uc.execute_current()

    def test_happy_path_extracts_cumulative_curve_from_events(self) -> None:
        repos = InMemoryRepositorySet()
        _seed_session(repos)
        # 4 assistant responses, each +30k tokens over 120 seconds → 1000 t/s
        for i, offset in enumerate((180, 120, 60, 0)):
            _assistant_event(
                repos,
                seconds_before_now=offset,
                input_tokens=10_000,
                cache_creation=20_000,
                event_idx=i,
            )
        forecast = _use_case(repos).execute(SessionId(SID))
        assert forecast.predicted_compact_at is not None
        assert forecast.input_token_rate > 0
        assert forecast.model_used == "linear_v1"

    def test_forecast_is_persisted(self) -> None:
        repos = InMemoryRepositorySet()
        _seed_session(repos)
        for i, offset in enumerate((180, 120, 60, 0)):
            _assistant_event(
                repos,
                seconds_before_now=offset,
                input_tokens=10_000,
                event_idx=i,
            )
        uc = _use_case(repos)
        forecast = uc.execute(SessionId(SID))
        stored = list(repos.forecasts.list_for_session(SessionId(SID)))
        assert len(stored) == 1
        assert stored[0].forecast_id == forecast.forecast_id

    def test_session_with_no_events_returns_low_confidence(self) -> None:
        repos = InMemoryRepositorySet()
        _seed_session(repos)
        forecast = _use_case(repos).execute(SessionId(SID))
        assert forecast.predicted_compact_at is None
        assert forecast.confidence <= 0.3

    def test_events_without_usage_are_skipped(self) -> None:
        repos = InMemoryRepositorySet()
        _seed_session(repos)
        # PreToolUse event has no message.usage — must be ignored.
        repos.events.append(
            Event(
                event_id=EventId("evt-skip-1"),
                session_id=SessionId(SID),
                event_type="PreToolUse",
                ts=NOW - timedelta(seconds=60),
                payload={"tool_name": "Read"},
                raw_hash=RawHash("hash-skip-1"),
            )
        )
        forecast = _use_case(repos).execute(SessionId(SID))
        # No usage samples means < 2 points → low confidence no-prediction.
        assert forecast.predicted_compact_at is None

    def test_execute_current_uses_latest_active(self) -> None:
        repos = InMemoryRepositorySet()
        _seed_session(repos)
        for i, offset in enumerate((120, 60, 0)):
            _assistant_event(
                repos, seconds_before_now=offset, input_tokens=20_000, event_idx=i
            )
        forecast = _use_case(repos).execute_current()
        assert forecast.session_id == SessionId(SID)

    def test_context_window_size_influences_eta(self) -> None:
        # Build two repos with different window sizes but identical token curves
        curve = [(180, 10_000), (120, 20_000), (60, 30_000), (0, 40_000)]

        def _build(window: int) -> ForecastCompactUseCase:
            repos = InMemoryRepositorySet()
            _seed_session(repos, context_window=window)
            for i, (off, tokens) in enumerate(curve):
                _assistant_event(
                    repos,
                    seconds_before_now=off,
                    input_tokens=tokens if i == 0 else tokens - curve[i - 1][1],
                    event_idx=i,
                )
            return _use_case(repos)

        big = _build(400_000).execute(SessionId(SID))
        small = _build(60_000).execute(SessionId(SID))
        assert big.predicted_compact_at is not None
        assert small.predicted_compact_at is not None
        assert small.predicted_compact_at <= big.predicted_compact_at
