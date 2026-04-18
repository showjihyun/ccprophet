"""DuckDB repositories for V1-era but newly-wired tables (e.g., `subagents`).

Kept in a separate module from V1 and V2 repositories to stay under the
~300 LOC-per-file ceiling (AP-5).
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ccprophet.adapters.persistence.duckdb._tz import from_utc as _from_utc
from ccprophet.adapters.persistence.duckdb._tz import to_utc_naive as _to_utc_naive
from ccprophet.domain.entities import Forecast, Subagent
from ccprophet.domain.values import SessionId, TokenCount

if TYPE_CHECKING:
    import duckdb


class DuckDBSubagentRepository:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def upsert(self, subagent: Subagent) -> None:
        self._conn.execute(
            """
            INSERT INTO subagents
                (subagent_id, parent_session_id, agent_type, started_at,
                 ended_at, context_tokens, tool_call_count, returned_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (subagent_id) DO UPDATE SET
                parent_session_id = EXCLUDED.parent_session_id,
                agent_type = COALESCE(EXCLUDED.agent_type, subagents.agent_type),
                started_at = EXCLUDED.started_at,
                ended_at = COALESCE(EXCLUDED.ended_at, subagents.ended_at),
                context_tokens = EXCLUDED.context_tokens,
                tool_call_count = EXCLUDED.tool_call_count,
                returned_summary = COALESCE(
                    EXCLUDED.returned_summary, subagents.returned_summary
                )
            """,
            [
                subagent.subagent_id.value,
                subagent.parent_session_id.value,
                subagent.agent_type,
                _to_utc_naive(subagent.started_at),
                _to_utc_naive(subagent.ended_at),
                subagent.context_tokens.value,
                subagent.tool_call_count,
                subagent.returned_summary,
            ],
        )

    def get(self, sid: SessionId) -> Subagent | None:
        row = self._conn.execute(
            "SELECT subagent_id, parent_session_id, agent_type, started_at, "
            "ended_at, context_tokens, tool_call_count, returned_summary "
            "FROM subagents WHERE subagent_id = ?",
            [sid.value],
        ).fetchone()
        if row is None:
            return None
        return _row_to_subagent(row)

    def list_for_parent(self, parent: SessionId) -> Sequence[Subagent]:
        rows = self._conn.execute(
            "SELECT subagent_id, parent_session_id, agent_type, started_at, "
            "ended_at, context_tokens, tool_call_count, returned_summary "
            "FROM subagents WHERE parent_session_id = ? ORDER BY started_at",
            [parent.value],
        ).fetchall()
        return [_row_to_subagent(r) for r in rows]


class DuckDBForecastRepository:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def save(self, forecast: Forecast) -> None:
        self._conn.execute(
            """
            INSERT INTO forecasts
                (forecast_id, session_id, predicted_at, predicted_compact_at,
                 confidence, model_used, input_token_rate, context_usage_at_pred)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (forecast_id) DO UPDATE SET
                predicted_at = EXCLUDED.predicted_at,
                predicted_compact_at = EXCLUDED.predicted_compact_at,
                confidence = EXCLUDED.confidence,
                model_used = EXCLUDED.model_used,
                input_token_rate = EXCLUDED.input_token_rate,
                context_usage_at_pred = EXCLUDED.context_usage_at_pred
            """,
            [
                forecast.forecast_id,
                forecast.session_id.value,
                _to_utc_naive(forecast.predicted_at),
                _to_utc_naive(forecast.predicted_compact_at),
                forecast.confidence,
                forecast.model_used,
                forecast.input_token_rate,
                forecast.context_usage_at_pred,
            ],
        )

    def list_for_session(self, sid: SessionId) -> Sequence[Forecast]:
        rows = self._conn.execute(
            "SELECT forecast_id, session_id, predicted_at, predicted_compact_at, "
            "confidence, model_used, input_token_rate, context_usage_at_pred "
            "FROM forecasts WHERE session_id = ? ORDER BY predicted_at",
            [sid.value],
        ).fetchall()
        return [_row_to_forecast(r) for r in rows]


def _row_to_forecast(row: tuple[object, ...]) -> Forecast:
    return Forecast(
        forecast_id=str(row[0]),
        session_id=SessionId(str(row[1])),
        predicted_at=_from_utc(row[2]),  # type: ignore[arg-type]
        predicted_compact_at=_from_utc(row[3]),  # type: ignore[arg-type]
        confidence=float(row[4] or 0.0),  # type: ignore[call-overload]
        model_used=str(row[5]),
        input_token_rate=float(row[6] or 0.0),  # type: ignore[call-overload]
        context_usage_at_pred=float(row[7] or 0.0),  # type: ignore[call-overload]
    )


def _row_to_subagent(row: tuple[object, ...]) -> Subagent:
    return Subagent(
        subagent_id=SessionId(str(row[0])),
        parent_session_id=SessionId(str(row[1])),
        agent_type=str(row[2]) if row[2] is not None else None,
        started_at=_from_utc(row[3]),  # type: ignore[arg-type]
        ended_at=_from_utc(row[4]),  # type: ignore[arg-type]
        context_tokens=TokenCount(int(row[5] or 0)),  # type: ignore[call-overload]
        tool_call_count=int(row[6] or 0),  # type: ignore[call-overload]
        returned_summary=str(row[7]) if row[7] is not None else None,
    )
