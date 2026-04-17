"""Parquet export for Quality Watch daily time-series (PRD FR-12.7).

Adapter-layer utility: flattens ``QualitySeries.points`` from a sequence of
``RegressionReport`` instances into rows and writes them to a Parquet file via
a *fresh in-memory DuckDB connection* — never the main application DB.

Kept here (not in ``use_cases/`` or ``domain/``) because parquet I/O is a
framework concern and DuckDB is an adapter dependency (LAYERING LP-5).
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import DailyQualityPoint, RegressionReport


# Column order matches the task spec so external pipelines can rely on it.
_COLUMNS: tuple[str, ...] = (
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
)

_CREATE_SQL = """
CREATE TABLE quality_series (
    model              VARCHAR,
    day                DATE,
    sample_size        INTEGER,
    avg_output_tokens  DOUBLE,
    avg_tool_calls     DOUBLE,
    tool_call_success_rate DOUBLE,
    autocompact_rate   DOUBLE,
    outcome_fail_rate  DOUBLE,
    repeat_read_rate   DOUBLE,
    avg_input_output_ratio DOUBLE
)
"""

_INSERT_SQL = (
    "INSERT INTO quality_series VALUES "
    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def export_quality_series(
    reports: Sequence[RegressionReport], path: Path
) -> int:
    """Write flattened daily quality points to a Parquet file.

    Parameters
    ----------
    reports:
        Sequence of regression reports from ``AssessQualityUseCase.execute``.
    path:
        Destination Parquet file. Parent directories must already exist.

    Returns
    -------
    int
        Number of rows written. Zero for empty input (still produces a valid
        empty Parquet file with the expected schema).
    """
    import duckdb  # adapter-local import (LP-5)

    path = Path(path)
    rows = list(_flatten(reports))

    conn = duckdb.connect(":memory:")
    try:
        conn.execute(_CREATE_SQL)
        if rows:
            conn.executemany(_INSERT_SQL, rows)
        # OVERWRITE keeps the command idempotent across re-runs.
        conn.execute(
            "COPY quality_series TO ? (FORMAT PARQUET, OVERWRITE)",
            [str(path)],
        )
    finally:
        conn.close()

    return len(rows)


def _flatten(
    reports: Sequence[RegressionReport],
) -> "list[tuple[object, ...]]":
    out: list[tuple[object, ...]] = []
    for report in reports:
        for point in report.series.points:
            out.append(_row(point))
    return out


def _row(p: DailyQualityPoint) -> tuple[object, ...]:
    return (
        p.model,
        p.day,
        p.sample_size,
        float(p.avg_output_tokens),
        float(p.avg_tool_calls),
        float(p.tool_call_success_rate),
        float(p.autocompact_rate),
        None if p.outcome_fail_rate is None else float(p.outcome_fail_rate),
        float(p.repeat_read_rate),
        float(p.avg_input_output_ratio),
    )


__all__ = ["export_quality_series"]
