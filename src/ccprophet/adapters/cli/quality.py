from __future__ import annotations

import json as json_module
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import (
        DailyQualityPoint,
        RegressionReport,
    )
    from ccprophet.use_cases.assess_quality import AssessQualityUseCase

SPARK_CHARS = "▁▂▃▄▅▆▇█"
SPARK_CHARS_ASCII = "_.-=+*#@"

KEY_METRICS = (
    "avg_output_tokens",
    "tool_call_success_rate",
    "autocompact_rate",
    "avg_tool_calls",
    "repeat_read_rate",
    "avg_input_output_ratio",
)


def run_quality_command(
    use_case: AssessQualityUseCase,
    *,
    model: str | None = None,
    window_days: int = 7,
    baseline_days: int = 30,
    threshold_sigma: float = 2.0,
    as_json: bool = False,
    ascii_only: bool = False,
    export_parquet: Path | None = None,
) -> int:
    reports = use_case.execute(
        model=model,
        window_days=window_days,
        baseline_days=baseline_days,
        threshold_sigma=threshold_sigma,
    )

    if as_json:
        print(
            json_module.dumps(
                [_report_dict(r) for r in reports], indent=2, default=str
            )
        )
    else:
        _render(reports, ascii_only=ascii_only)

    if export_parquet is not None:
        from ccprophet.adapters.cli.quality_export import export_quality_series

        rows = export_quality_series(reports, export_parquet)
        # When --json is on, stdout is reserved for the JSON payload, so the
        # confirmation goes to stderr to keep pipelines parseable.
        stream = sys.stderr if as_json else sys.stdout
        print(f"wrote {rows} rows to {export_parquet}", file=stream)

    return 1 if any(r.has_regression for r in reports) else 0


def _report_dict(r: RegressionReport) -> dict[str, object]:
    return {
        "model": r.model,
        "window_days": r.window_days,
        "baseline_days": r.baseline_days,
        "window_sample_size": r.window_sample_size,
        "baseline_sample_size": r.baseline_sample_size,
        "has_regression": r.has_regression,
        "flags": [
            {
                "metric": f.metric_name,
                "direction": f.direction,
                "baseline_mean": f.baseline_mean,
                "recent_mean": f.recent_mean,
                "baseline_stddev": f.baseline_stddev,
                "z_score": f.z_score,
                "explanation": f.explanation,
            }
            for f in r.flags
        ],
        "series_points": len(r.series.points),
    }


def _render(
    reports: Sequence[RegressionReport], *, ascii_only: bool
) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    if not reports:
        console.print("[dim]No sessions in the selected window.[/]")
        return

    console.print(
        "[dim]Note: metrics reflect your workload mix as well as model "
        "behavior — a task-type change can drive a flag.[/]"
    )

    chars = SPARK_CHARS_ASCII if ascii_only else SPARK_CHARS

    for report in reports:
        console.print()
        header = (
            f"[bold]{report.model}[/]  "
            f"[dim]window {report.window_days}d "
            f"(n={report.window_sample_size}) vs baseline "
            f"{report.baseline_days}d (n={report.baseline_sample_size})[/]"
        )
        if report.has_regression:
            header += "  [bold red][DEGRADED][/]"
        console.print(header)

        if not report.series.points:
            console.print("  [dim]no data[/]")
            continue

        table = Table(show_header=True, header_style="dim")
        table.add_column("Metric")
        table.add_column("Baseline", justify="right")
        table.add_column("Recent", justify="right")
        table.add_column("Δ σ", justify="right")
        table.add_column("Trend")

        flags_by_metric = {f.metric_name: f for f in report.flags}
        for metric in KEY_METRICS:
            values = [
                _metric_value(p, metric)
                for p in report.series.points
            ]
            sparkline = _sparkline(values, chars)
            flag = flags_by_metric.get(metric)
            if flag is not None:
                color = "red" if flag.direction == "degraded" else "green"
                row = [
                    f"[{color}]{metric}[/{color}]",
                    f"{flag.baseline_mean:.3f}",
                    f"{flag.recent_mean:.3f}",
                    f"[{color}]{flag.z_score:+.2f}[/{color}]",
                    sparkline,
                ]
            else:
                recent_val = (
                    values[-report.window_days:]
                    if report.window_days > 0 else values
                )
                baseline_val = (
                    values[:-report.window_days]
                    if report.window_days > 0 else []
                )
                row = [
                    metric,
                    f"{_mean(baseline_val):.3f}" if baseline_val else "-",
                    f"{_mean(recent_val):.3f}" if recent_val else "-",
                    "[dim]stable[/]",
                    sparkline,
                ]
            table.add_row(*row)

        console.print(table)

        if report.flags:
            console.print()
            for flag in report.flags:
                color = "red" if flag.direction == "degraded" else "green"
                console.print(f"  [{color}]·[/{color}] {flag.explanation}")


def _metric_value(point: DailyQualityPoint, metric: str) -> float:
    v = getattr(point, metric)
    if v is None:
        return 0.0
    return float(v)


def _sparkline(values: Sequence[float], chars: str) -> str:
    if not values:
        return ""
    numeric = [v for v in values if v is not None]
    if not numeric:
        return ""
    lo, hi = min(numeric), max(numeric)
    rng = (hi - lo) or 1.0
    slots = len(chars) - 1
    return "".join(chars[int(((v - lo) / rng) * slots)] for v in numeric)


def _mean(values: Sequence[float]) -> float:
    numeric = [v for v in values if v is not None]
    return sum(numeric) / len(numeric) if numeric else 0.0
