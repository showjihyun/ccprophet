from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ccprophet.domain.entities import Event, Phase, Session, ToolCall, ToolDef
from ccprophet.domain.values import EventId, PhaseType, RawHash, SessionId, TokenCount


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)

if TYPE_CHECKING:
    import duckdb


class DuckDBSessionRepository:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def upsert(self, session: Session) -> None:
        self._conn.execute(
            """
            INSERT INTO sessions (session_id, project_slug, model, started_at,
                                  ended_at, total_input_tokens, total_output_tokens,
                                  compacted, compacted_at, context_window_size,
                                  total_cache_creation_tokens, total_cache_read_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (session_id) DO UPDATE SET
                model = EXCLUDED.model,
                ended_at = EXCLUDED.ended_at,
                total_input_tokens = EXCLUDED.total_input_tokens,
                total_output_tokens = EXCLUDED.total_output_tokens,
                total_cache_creation_tokens = EXCLUDED.total_cache_creation_tokens,
                total_cache_read_tokens = EXCLUDED.total_cache_read_tokens,
                compacted = EXCLUDED.compacted,
                compacted_at = EXCLUDED.compacted_at
            """,
            [
                session.session_id.value,
                session.project_slug,
                session.model,
                _to_utc_naive(session.started_at),
                _to_utc_naive(session.ended_at),
                session.total_input_tokens.value,
                session.total_output_tokens.value,
                session.compacted,
                _to_utc_naive(session.compacted_at),
                session.context_window_size,
                session.total_cache_creation_tokens.value,
                session.total_cache_read_tokens.value,
            ],
        )

    def get(self, sid: SessionId) -> Session | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", [sid.value]
        ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def latest_active(self) -> Session | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def list_recent(self, limit: int = 10) -> Sequence[Session]:
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", [limit]
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def list_in_range(self, start: datetime, end: datetime) -> Sequence[Session]:
        rows = self._conn.execute(
            "SELECT * FROM sessions WHERE started_at >= ? AND started_at < ? "
            "ORDER BY started_at",
            [_to_utc_naive(start), _to_utc_naive(end)],
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    @staticmethod
    def _row_to_session(row: tuple[object, ...]) -> Session:
        # Schema column order: session_id, project_slug, worktree_path_hash,
        # model, started_at, ended_at, total_input_tokens, total_output_tokens,
        # compacted, compacted_at, context_window_size, created_at,
        # schema_version, total_cache_creation_tokens, total_cache_read_tokens
        cache_creation = int(row[13] or 0) if len(row) > 13 else 0
        cache_read = int(row[14] or 0) if len(row) > 14 else 0
        return Session(
            session_id=SessionId(str(row[0])),
            project_slug=str(row[1]),
            model=str(row[3]),
            started_at=row[4],  # type: ignore[arg-type]
            ended_at=row[5],  # type: ignore[arg-type]
            total_input_tokens=TokenCount(int(row[6] or 0)),
            total_output_tokens=TokenCount(int(row[7] or 0)),
            total_cache_creation_tokens=TokenCount(cache_creation),
            total_cache_read_tokens=TokenCount(cache_read),
            compacted=bool(row[8]),
            compacted_at=row[9],  # type: ignore[arg-type]
            context_window_size=int(row[10] or 200_000),
        )


class DuckDBEventRepository:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def append(self, event: Event) -> None:
        # Two distinct conflicts can occur: (1) `raw_hash` UNIQUE index
        # (same payload re-ingested) and (2) `event_id` PK collision
        # (Claude Code reuses UUIDs when its subagents/ sidecar files
        # duplicate the parent transcript lines with different bytes).
        # Both are legitimate dedup — silently skip.
        if self._event_id_exists(event.event_id.value):
            return
        self._conn.execute(
            """
            INSERT INTO events (event_id, session_id, event_type, ts, payload,
                                raw_hash, ingested_via)
            VALUES (?, ?, ?, ?, ?::JSON, ?, ?)
            ON CONFLICT (raw_hash) DO NOTHING
            """,
            [
                event.event_id.value,
                event.session_id.value,
                event.event_type,
                event.ts,
                json.dumps(event.payload),
                event.raw_hash.value,
                event.ingested_via,
            ],
        )

    def _event_id_exists(self, event_id: str) -> bool:
        result = self._conn.execute(
            "SELECT 1 FROM events WHERE event_id = ? LIMIT 1", [event_id]
        ).fetchone()
        return result is not None

    def dedup_hash_exists(self, raw_hash: RawHash) -> bool:
        result = self._conn.execute(
            "SELECT 1 FROM events WHERE raw_hash = ? LIMIT 1", [raw_hash.value]
        ).fetchone()
        return result is not None

    def list_by_session(self, sid: SessionId) -> Iterable[Event]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY ts", [sid.value]
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row: tuple[object, ...]) -> Event:
        payload_raw = row[4]
        if isinstance(payload_raw, str):
            payload = json.loads(payload_raw)
        else:
            payload = payload_raw or {}
        return Event(
            event_id=EventId(str(row[0])),
            session_id=SessionId(str(row[1])),
            event_type=str(row[2]),
            ts=row[3],  # type: ignore[arg-type]
            payload=payload,
            raw_hash=RawHash(str(row[5])),
            ingested_via=str(row[7] or "hook"),
        )


class DuckDBToolDefRepository:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def bulk_add(self, sid: SessionId, defs: Sequence[ToolDef]) -> None:
        for td in defs:
            self._conn.execute(
                """
                INSERT INTO tool_defs_loaded (session_id, tool_name, tokens, source, loaded_at)
                VALUES (?, ?, ?, ?, now())
                ON CONFLICT (session_id, tool_name) DO NOTHING
                """,
                [sid.value, td.tool_name, td.tokens.value, td.source],
            )

    def list_for_session(self, sid: SessionId) -> Iterable[ToolDef]:
        rows = self._conn.execute(
            "SELECT tool_name, tokens, source FROM tool_defs_loaded WHERE session_id = ?",
            [sid.value],
        ).fetchall()
        return [ToolDef(str(r[0]), TokenCount(int(r[1])), str(r[2])) for r in rows]


class DuckDBToolCallRepository:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def append(self, tc: ToolCall) -> None:
        # Same PK-collision pattern as events.append: Claude's subagent JSONL
        # files duplicate tool_call_ids from the parent transcript. Skip
        # instead of crashing the backfill.
        existing = self._conn.execute(
            "SELECT 1 FROM tool_calls WHERE tool_call_id = ? LIMIT 1",
            [tc.tool_call_id],
        ).fetchone()
        if existing is not None:
            return
        self._conn.execute(
            """
            INSERT INTO tool_calls (tool_call_id, session_id, parent_id, tool_name,
                                    input_hash, input_tokens, output_tokens,
                                    latency_ms, success, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                tc.tool_call_id,
                tc.session_id.value,
                tc.parent_id,
                tc.tool_name,
                tc.input_hash,
                tc.input_tokens.value,
                tc.output_tokens.value,
                tc.latency_ms,
                tc.success,
                tc.ts,
            ],
        )

    def list_for_session(self, sid: SessionId) -> Iterable[ToolCall]:
        rows = self._conn.execute(
            "SELECT * FROM tool_calls WHERE session_id = ? ORDER BY ts", [sid.value]
        ).fetchall()
        return [
            ToolCall(
                tool_call_id=str(r[0]),
                session_id=SessionId(str(r[1])),
                parent_id=r[2] if r[2] else None,  # type: ignore[arg-type]
                tool_name=str(r[3]),
                input_hash=str(r[4]),
                input_tokens=TokenCount(int(r[5] or 0)),
                output_tokens=TokenCount(int(r[6] or 0)),
                latency_ms=int(r[7] or 0),
                success=bool(r[8]),
                ts=r[10],  # type: ignore[arg-type]
            )
            for r in rows
        ]


class DuckDBPhaseRepository:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def replace_for_session(self, sid: SessionId, phases: Sequence[Phase]) -> None:
        self._conn.execute("DELETE FROM phases WHERE session_id = ?", [sid.value])
        for p in phases:
            self._conn.execute(
                """
                INSERT INTO phases (phase_id, session_id, phase_type, start_ts, end_ts,
                                    input_tokens, output_tokens, tool_call_count,
                                    detection_confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    p.phase_id,
                    p.session_id.value,
                    p.phase_type.value,
                    p.start_ts,
                    p.end_ts,
                    p.input_tokens.value,
                    p.output_tokens.value,
                    p.tool_call_count,
                    p.detection_confidence,
                ],
            )

    def list_for_session(self, sid: SessionId) -> Iterable[Phase]:
        rows = self._conn.execute(
            "SELECT * FROM phases WHERE session_id = ? ORDER BY start_ts", [sid.value]
        ).fetchall()
        return [
            Phase(
                phase_id=str(r[0]),
                session_id=SessionId(str(r[1])),
                phase_type=PhaseType(str(r[2])),
                start_ts=r[3],  # type: ignore[arg-type]
                end_ts=r[4],  # type: ignore[arg-type]
                input_tokens=TokenCount(int(r[5] or 0)),
                output_tokens=TokenCount(int(r[6] or 0)),
                tool_call_count=int(r[7] or 0),
                detection_confidence=float(r[8] or 0.0),
            )
            for r in rows
        ]
