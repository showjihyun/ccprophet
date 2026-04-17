from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from ccprophet.adapters.cli.quality import run_quality_command
from ccprophet.adapters.cli.quality_export import export_quality_series
from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import (
    InMemoryRepositorySet,
)
from ccprophet.domain.values import TokenCount
from ccprophet.use_cases.assess_quality import AssessQualityUseCase
from tests.fixtures.builders import SessionBuilder


NOW = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)


def _wire(
    days: int,
    baseline_output: int = 1000,
    recent_output: int = 1000,
) -> AssessQualityUseCase:
    """Replicates the wiring used in test_quality_command._wire."""
    repos = InMemoryRepositorySet()
    for d in range(days):
        day_back = days - d - 1
        output = recent_output if day_back < 2 else baseline_output
        session = replace(
            SessionBuilder().with_id(f"s-{d}").build(),
            model="claude-opus-4-7",
            started_at=NOW - timedelta(days=day_back, hours=1),
            total_output_tokens=TokenCount(output),
            total_input_tokens=TokenCount(output * 4),
        )
        repos.sessions.upsert(session)
    return AssessQualityUseCase(
        sessions=repos.sessions,
        tool_calls=repos.tool_calls,
        outcomes=repos.outcomes,
        clock=FrozenClock(NOW),
    )


def _read_parquet_rows(path: Path) -> list[tuple[object, ...]]:
    conn = duckdb.connect(":memory:")
    try:
        return conn.execute(
            "SELECT * FROM read_parquet(?)", [str(path)]
        ).fetchall()
    finally:
        conn.close()


def _read_parquet_columns(path: Path) -> list[str]:
    conn = duckdb.connect(":memory:")
    try:
        return [
            row[0]
            for row in conn.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
            ).fetchall()
        ]
    finally:
        conn.close()


def test_export_parquet_writes_file_with_expected_rows(tmp_path: Path) -> None:
    uc = _wire(days=10)
    reports = uc.execute(window_days=2, baseline_days=8, threshold_sigma=2.0)

    out = tmp_path / "out.parquet"
    rows_written = export_quality_series(reports, out)

    assert out.exists()
    assert rows_written == 10

    rows = _read_parquet_rows(out)
    assert len(rows) == 10


def test_export_parquet_schema_includes_all_metrics(tmp_path: Path) -> None:
    uc = _wire(days=5)
    reports = uc.execute(window_days=2, baseline_days=3, threshold_sigma=2.0)

    out = tmp_path / "schema.parquet"
    export_quality_series(reports, out)

    columns = set(_read_parquet_columns(out))
    expected = {
        "model",
        "day",
        "sample_size",
        "avg_output_tokens",
        "avg_tool_calls",
        "tool_call_success_rate",
        "autocompact_rate",
        "outcome_fail_rate",
        "repeat_read_rate",
        "avg_input_output_ratio",
    }
    assert expected.issubset(columns), f"missing columns: {expected - columns}"


def test_export_empty_reports_writes_zero_rows(tmp_path: Path) -> None:
    out = tmp_path / "empty.parquet"
    rows_written = export_quality_series([], out)

    assert rows_written == 0
    assert out.exists()
    # Valid parquet file, even if row-empty, must round-trip with zero rows
    # and the expected schema.
    rows = _read_parquet_rows(out)
    assert rows == []
    columns = _read_parquet_columns(out)
    assert "avg_output_tokens" in columns
    assert "outcome_fail_rate" in columns


def test_export_handles_none_outcome_fail_rate(tmp_path: Path) -> None:
    # No OutcomeLabel rows were seeded → every point has outcome_fail_rate=None.
    uc = _wire(days=3)
    reports = uc.execute(window_days=1, baseline_days=2, threshold_sigma=2.0)

    points = [p for r in reports for p in r.series.points]
    assert points, "sanity: expected at least one point"
    assert all(p.outcome_fail_rate is None for p in points)

    out = tmp_path / "nulls.parquet"
    rows_written = export_quality_series(reports, out)
    assert rows_written == len(points)

    columns = _read_parquet_columns(out)
    fail_idx = columns.index("outcome_fail_rate")
    rows = _read_parquet_rows(out)
    assert rows, "expected at least one round-tripped row"
    assert all(row[fail_idx] is None for row in rows)


def test_cli_export_confirmation_printed(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """The CLI wrapper prints a one-line confirmation after the JSON/render path."""
    uc = _wire(days=5)
    out = tmp_path / "cli.parquet"

    code = run_quality_command(
        uc,
        window_days=2,
        baseline_days=3,
        threshold_sigma=2.0,
        as_json=True,
        export_parquet=out,
    )

    captured = capsys.readouterr()
    # JSON goes to stdout, confirmation to stderr when --json is on.
    assert "wrote" in captured.err
    assert str(out) in captured.err
    assert captured.out.strip().startswith("[")  # the JSON payload
    assert out.exists()
    assert code in (0, 1)
