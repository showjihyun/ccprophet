"""NFR-1: hook-path p99 latency must stay under 50ms.

Measures the end-to-end ingest path (IngestEventUseCase.execute on a real
DuckDB connection) after schema warmup — the one-shot fixed cost of
`ensure_schema` is excluded because it only runs on first invocation per
process, not per hook call.
"""
from __future__ import annotations

import statistics
import time
from datetime import datetime, timezone

import duckdb
import pytest

from ccprophet.adapters.clock.system import SystemClock
from ccprophet.adapters.persistence.duckdb.migrations import ensure_schema
from ccprophet.adapters.persistence.duckdb.repositories import (
    DuckDBEventRepository,
    DuckDBSessionRepository,
    DuckDBToolCallRepository,
)
from ccprophet.use_cases.ingest_event import IngestEventUseCase

ITERATIONS = 1000
P99_BUDGET_MS = 50.0


@pytest.mark.perf
def test_hook_ingest_p99_under_50ms(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "perf.duckdb"
    conn = duckdb.connect(str(db))
    try:
        ensure_schema(conn)
        uc = IngestEventUseCase(
            events=DuckDBEventRepository(conn),
            sessions=DuckDBSessionRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
            clock=SystemClock(),
        )

        # Warm up JIT / dedup caches so we measure steady-state, not cold start.
        now = datetime.now(timezone.utc).isoformat()
        for i in range(10):
            uc.execute(
                "UserPromptSubmit",
                {
                    "session_id": f"warm-{i}",
                    "ts": now,
                    "content": "warmup",
                },
            )

        samples_ms: list[float] = []
        for i in range(ITERATIONS):
            payload = {
                "session_id": f"perf-{i}",
                "ts": datetime.now(timezone.utc).isoformat(),
                "content": "x" * 40,
            }
            t0 = time.perf_counter()
            uc.execute("UserPromptSubmit", payload)
            samples_ms.append((time.perf_counter() - t0) * 1000.0)

    finally:
        conn.close()

    samples_ms.sort()
    p50 = statistics.median(samples_ms)
    p99 = samples_ms[int(len(samples_ms) * 0.99)]
    p_max = samples_ms[-1]

    assert p99 < P99_BUDGET_MS, (
        f"Hook p99 {p99:.2f}ms exceeds {P99_BUDGET_MS}ms budget "
        f"(p50={p50:.2f}ms, max={p_max:.2f}ms, n={len(samples_ms)})"
    )
