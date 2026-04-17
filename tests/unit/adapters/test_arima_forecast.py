"""Unit tests for the Phase 3 ARIMA forecaster adapter.

These tests treat statsmodels as an optional extra: any test that actually
needs the library goes through ``pytest.importorskip("statsmodels")`` so the
suite stays green when the ``forecast`` extra is not installed. Tests that
exercise the fallback paths (below-min-samples, ImportError, .fit raises)
never touch statsmodels and always run.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import pytest

from ccprophet.adapters.forecast.arima import (
    FALLBACK_MODEL_NAME,
    MODEL_NAME,
    ArimaForecastModel,
)
from ccprophet.domain.services.forecast import TokenSample
from ccprophet.domain.values import SessionId

SID = SessionId("s-arima-test")
NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
CTX = 200_000


def _samples(n: int, *, start_tokens: int = 1000, step_tokens: int = 1500,
             step_seconds: int = 60) -> list[TokenSample]:
    """Build ``n`` linearly-increasing samples spaced ``step_seconds`` apart."""
    base_ts = NOW - timedelta(seconds=step_seconds * (n - 1))
    return [
        TokenSample(
            ts=base_ts + timedelta(seconds=step_seconds * i),
            cumulative_input_tokens=start_tokens + step_tokens * i,
        )
        for i in range(n)
    ]


class TestArimaFallbacks:
    def test_falls_back_when_below_min_samples(self) -> None:
        model = ArimaForecastModel(min_samples=10)
        samples = _samples(5)

        result = model.predict(
            samples,
            session_id=SID,
            context_window_size=CTX,
            now=NOW,
        )

        assert result.model_used == FALLBACK_MODEL_NAME
        assert result.session_id == SID

    def test_falls_back_when_statsmodels_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force ImportError for any `import statsmodels...` inside predict().
        # Setting parent + submodule to None in sys.modules makes the `import`
        # statement raise ImportError without touching the real package.
        monkeypatch.setitem(sys.modules, "statsmodels", None)
        monkeypatch.setitem(sys.modules, "statsmodels.tsa", None)
        monkeypatch.setitem(sys.modules, "statsmodels.tsa.arima", None)
        monkeypatch.setitem(sys.modules, "statsmodels.tsa.arima.model", None)

        model = ArimaForecastModel(min_samples=3)
        samples = _samples(15)

        result = model.predict(
            samples,
            session_id=SID,
            context_window_size=CTX,
            now=NOW,
        )

        assert result.model_used == FALLBACK_MODEL_NAME

    def test_arima_exception_triggers_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Rather than praying that statsmodels raises on a particular input
        # (it sometimes doesn't), install a stub module that always raises.
        pytest.importorskip("statsmodels")
        import statsmodels.tsa.arima.model as arima_mod

        class _ExplodingARIMA:
            def __init__(self, *_: object, **__: object) -> None: ...
            def fit(self, *_: object, **__: object) -> object:
                raise RuntimeError("boom")

        monkeypatch.setattr(arima_mod, "ARIMA", _ExplodingARIMA)

        model = ArimaForecastModel(min_samples=3)
        samples = _samples(12)

        result = model.predict(
            samples,
            session_id=SID,
            context_window_size=CTX,
            now=NOW,
        )

        assert result.model_used == FALLBACK_MODEL_NAME


class TestArimaHappyPath:
    def test_arima_path_on_linear_data(self) -> None:
        pytest.importorskip("statsmodels")
        model = ArimaForecastModel(min_samples=10)
        # 30 points climbing steadily, 1 min apart — clearly trends past
        # the 0.8 * 200k = 160k threshold within the 60-step horizon.
        samples = _samples(30, start_tokens=10_000, step_tokens=5_000,
                           step_seconds=60)

        result = model.predict(
            samples,
            session_id=SID,
            context_window_size=CTX,
            now=NOW,
        )

        assert result.model_used == MODEL_NAME
        assert result.predicted_compact_at is not None
        assert result.predicted_compact_at >= NOW
        assert 0.0 <= result.confidence <= 0.95
        assert 0.0 <= result.context_usage_at_pred <= 1.0
        assert result.session_id == SID


class TestConfidenceScaling:
    def test_confidence_scales_with_sample_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Avoid depending on statsmodels being installed: stub ARIMA with a
        # deterministic fake so the success branch runs everywhere.
        pytest.importorskip("statsmodels")
        import statsmodels.tsa.arima.model as arima_mod

        class _FakeFit:
            def forecast(self, steps: int) -> list[float]:
                return [1.0] * steps  # never crosses threshold -> no compact

        class _FakeARIMA:
            def __init__(self, *_: object, **__: object) -> None: ...
            def fit(self, *_: object, **__: object) -> _FakeFit:
                return _FakeFit()

        monkeypatch.setattr(arima_mod, "ARIMA", _FakeARIMA)

        model = ArimaForecastModel(min_samples=10)
        small = model.predict(
            _samples(12), session_id=SID, context_window_size=CTX, now=NOW
        )
        large = model.predict(
            _samples(200), session_id=SID, context_window_size=CTX, now=NOW
        )

        assert small.model_used == MODEL_NAME
        assert large.model_used == MODEL_NAME
        assert large.confidence >= small.confidence
        assert large.confidence <= 0.95
