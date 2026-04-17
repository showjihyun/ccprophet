from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ccprophet.domain.services.forecast import (
    LinearForecaster,
    TokenSample,
)
from ccprophet.domain.values import SessionId

SID = SessionId("s-forecast")
NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


def _samples(*offsets_and_tokens: tuple[int, int]) -> list[TokenSample]:
    """Build samples from (seconds_before_now, cumulative_tokens) pairs."""
    return [
        TokenSample(ts=NOW - timedelta(seconds=off), cumulative_input_tokens=tok)
        for off, tok in offsets_and_tokens
    ]


class TestLinearForecaster:
    def test_empty_samples_returns_no_prediction_low_confidence(self) -> None:
        forecast = LinearForecaster.predict(
            [], session_id=SID, context_window_size=200_000, now=NOW
        )
        assert forecast.predicted_compact_at is None
        assert forecast.confidence <= 0.3
        assert forecast.input_token_rate == 0.0
        assert forecast.model_used == "linear_v1"

    def test_single_sample_returns_no_prediction_low_confidence(self) -> None:
        samples = _samples((0, 50_000))
        forecast = LinearForecaster.predict(
            samples, session_id=SID, context_window_size=200_000, now=NOW
        )
        assert forecast.predicted_compact_at is None
        assert forecast.confidence <= 0.3
        assert forecast.context_usage_at_pred == 0.25

    def test_flat_slope_returns_no_compact_steady_confidence(self) -> None:
        # Same cumulative tokens at every time point → slope 0.
        samples = _samples((240, 50_000), (180, 50_000), (120, 50_000), (0, 50_000))
        forecast = LinearForecaster.predict(
            samples, session_id=SID, context_window_size=200_000, now=NOW
        )
        assert forecast.predicted_compact_at is None
        assert forecast.input_token_rate == 0.0
        assert forecast.confidence <= 0.5

    def test_steep_upward_curve_projects_near_future(self) -> None:
        # 1000 tokens/sec burn rate, currently at 150k / 200k*0.8 = 160k threshold.
        # Remaining = 10k, ETA ≈ 10 seconds.
        samples = _samples(
            (240, 150_000 - 240_000),  # negative but we only care about slope
            (180, 150_000 - 180_000),
            (120, 150_000 - 120_000),
            (60, 150_000 - 60_000),
            (0, 150_000),
        )
        # Re-build with sensible cumulative values that only increase:
        samples = _samples(
            (240, 30_000),
            (180, 60_000),
            (120, 90_000),
            (60, 120_000),
            (0, 150_000),
        )
        forecast = LinearForecaster.predict(
            samples, session_id=SID, context_window_size=200_000, now=NOW
        )
        assert forecast.predicted_compact_at is not None
        # Slope ≈ 500 tokens/sec, threshold 160k, remaining 10k → ~20s
        delta = (forecast.predicted_compact_at - NOW).total_seconds()
        assert 15 <= delta <= 25
        assert forecast.input_token_rate > 0

    def test_threshold_already_exceeded_projects_now(self) -> None:
        samples = _samples(
            (180, 170_000),
            (120, 180_000),
            (60, 190_000),
            (0, 200_000),  # way past 80% of 200k (= 160k)
        )
        forecast = LinearForecaster.predict(
            samples, session_id=SID, context_window_size=200_000, now=NOW
        )
        assert forecast.predicted_compact_at is not None
        # "Already past" → predicted at `now`
        assert forecast.predicted_compact_at == NOW

    def test_small_context_window_projects_faster(self) -> None:
        # Same slope, smaller window → earlier ETA.
        samples = _samples(
            (120, 10_000),
            (60, 20_000),
            (0, 30_000),
        )
        big = LinearForecaster.predict(
            samples, session_id=SID, context_window_size=200_000, now=NOW
        )
        small = LinearForecaster.predict(
            samples, session_id=SID, context_window_size=50_000, now=NOW
        )
        assert big.predicted_compact_at is not None
        assert small.predicted_compact_at is not None
        assert small.predicted_compact_at < big.predicted_compact_at

    def test_samples_outside_window_are_ignored(self) -> None:
        # Only the (-30s, -0s) pair falls inside the default 5-minute window,
        # but 600s ago sample must NOT influence slope.
        samples = _samples(
            (600, 1_000_000),   # far outside window — huge cumulative
            (30, 10_000),
            (0, 20_000),
        )
        forecast = LinearForecaster.predict(
            samples, session_id=SID, context_window_size=200_000, now=NOW
        )
        # With only the last two points, slope = (20k-10k)/30s ≈ 333 t/s.
        assert forecast.predicted_compact_at is not None
        assert 250 < forecast.input_token_rate < 400

    def test_sample_count_drives_confidence_up_to_cap(self) -> None:
        many = [
            TokenSample(
                ts=NOW - timedelta(seconds=60 - i),
                cumulative_input_tokens=i * 100,
            )
            for i in range(60)
        ]
        forecast = LinearForecaster.predict(
            many, session_id=SID, context_window_size=200_000, now=NOW
        )
        # 50 samples in the window → confidence capped at 0.95
        assert 0.9 <= forecast.confidence <= 0.95

    def test_horizon_clamped_to_seven_days(self) -> None:
        # Very slow burn rate → naive ETA would be years.
        samples = _samples(
            (120, 10_000),
            (60, 10_001),
            (0, 10_002),
        )
        forecast = LinearForecaster.predict(
            samples, session_id=SID, context_window_size=200_000, now=NOW
        )
        assert forecast.predicted_compact_at is not None
        delta = forecast.predicted_compact_at - NOW
        assert delta <= timedelta(days=7) + timedelta(seconds=1)

    def test_custom_threshold_ratio(self) -> None:
        samples = _samples(
            (120, 50_000),
            (60, 100_000),
            (0, 150_000),
        )
        strict = LinearForecaster.predict(
            samples,
            session_id=SID,
            context_window_size=200_000,
            now=NOW,
            compact_threshold_ratio=0.5,  # threshold 100k — already passed
        )
        lenient = LinearForecaster.predict(
            samples,
            session_id=SID,
            context_window_size=200_000,
            now=NOW,
            compact_threshold_ratio=0.9,
        )
        # Strict: last_cum (150k) > threshold (100k) → predicted at now
        assert strict.predicted_compact_at == NOW
        # Lenient: last_cum (150k) < threshold (180k) → future
        assert lenient.predicted_compact_at is not None
        assert lenient.predicted_compact_at > NOW

    def test_forecast_id_is_unique_across_calls(self) -> None:
        samples = _samples((0, 50_000))
        a = LinearForecaster.predict(
            samples, session_id=SID, context_window_size=200_000, now=NOW
        )
        b = LinearForecaster.predict(
            samples, session_id=SID, context_window_size=200_000, now=NOW
        )
        assert a.forecast_id != b.forecast_id

    def test_context_usage_reports_ratio_against_window(self) -> None:
        samples = _samples((0, 40_000))
        forecast = LinearForecaster.predict(
            samples, session_id=SID, context_window_size=200_000, now=NOW
        )
        assert abs(forecast.context_usage_at_pred - 0.2) < 1e-6

    def test_context_usage_is_capped_at_one(self) -> None:
        samples = _samples((0, 999_999_999))
        forecast = LinearForecaster.predict(
            samples, session_id=SID, context_window_size=200_000, now=NOW
        )
        assert forecast.context_usage_at_pred == 1.0
