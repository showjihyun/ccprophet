from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ccprophet.adapters.cli.forecast import run_forecast_command
from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.forecast.linear import LinearForecastModel
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.entities import Event
from ccprophet.domain.values import EventId, RawHash, SessionId
from ccprophet.use_cases.forecast_compact import ForecastCompactUseCase
from tests.fixtures.builders import SessionBuilder

SID = "s-forecast-cli"
NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


def _seed(repos: InMemoryRepositorySet, *, with_curve: bool = True) -> None:
    session = SessionBuilder().with_id(SID).build()
    repos.sessions.upsert(replace(session, context_window_size=200_000))
    if not with_curve:
        return
    for i, offset in enumerate((180, 120, 60, 0)):
        ts = NOW - timedelta(seconds=offset)
        payload = {
            "message": {
                "usage": {
                    "input_tokens": 10_000,
                    "cache_creation_input_tokens": 20_000,
                    "output_tokens": 200,
                }
            }
        }
        repos.events.append(
            Event(
                event_id=EventId(f"evt-{i}"),
                session_id=SessionId(SID),
                event_type="AssistantResponse",
                ts=ts,
                payload=payload,
                raw_hash=RawHash(f"hash-{i}-{offset}"),
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


def test_no_session_returns_2(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    code = run_forecast_command(_use_case(repos), as_json=True)
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert "error" in payload


def test_json_output_schema(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    _seed(repos)
    code = run_forecast_command(_use_case(repos), session=SID, as_json=True)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["session_id"] == SID
    assert payload["model_used"] == "linear_v1"
    assert "predicted_compact_at" in payload
    assert "burn_rate_tokens_per_sec" in payload
    assert 0.0 <= payload["confidence"] <= 1.0
    # With a steady 500 t/s curve, we expect a future prediction.
    assert payload["predicted_compact_at"] is not None


def test_low_sample_session_still_valid_prediction(capsys) -> None:  # type: ignore[no-untyped-def]
    """Zero-event session must not crash — it returns a low-confidence no-prediction."""
    repos = InMemoryRepositorySet()
    _seed(repos, with_curve=False)
    code = run_forecast_command(_use_case(repos), session=SID, as_json=True)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["predicted_compact_at"] is None
    assert payload["confidence"] <= 0.3


def test_rich_rendering_smoke(capsys) -> None:  # type: ignore[no-untyped-def]
    """Non-JSON path should not crash; we just assert exit code + some output."""
    repos = InMemoryRepositorySet()
    _seed(repos)
    code = run_forecast_command(_use_case(repos), session=SID, as_json=False)
    assert code == 0
    out = capsys.readouterr().out
    assert "Autocompact Forecast" in out
    assert "linear_v1" in out


def test_session_not_found_non_json_writes_stderr(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    code = run_forecast_command(_use_case(repos), session="missing", as_json=False)
    assert code == 2
    err = capsys.readouterr().err
    assert "Error" in err or "not found" in err.lower()


def test_forecast_is_persisted_via_cli(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    _seed(repos)
    run_forecast_command(_use_case(repos), session=SID, as_json=True)
    stored = list(repos.forecasts.list_for_session(SessionId(SID)))
    assert len(stored) == 1
