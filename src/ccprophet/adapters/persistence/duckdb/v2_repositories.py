"""DuckDB repositories for V2 tables: recommendations, snapshots, outcome_labels,
subset_profiles, pricing_rates.

Kept in a separate module from V1 repositories to avoid one-file bloat.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from ccprophet.adapters.persistence.duckdb._tz import from_utc as _from_utc
from ccprophet.adapters.persistence.duckdb._tz import to_utc_naive as _to_utc_naive
from ccprophet.adapters.persistence.duckdb.repositories import DuckDBSessionRepository
from ccprophet.domain.entities import (
    OutcomeLabel,
    PricingRate,
    Recommendation,
    Session,
    Snapshot,
    SnapshotFileEntry,
    SubsetProfile,
)
from ccprophet.domain.errors import UnknownPricingModel
from ccprophet.domain.values import (
    Confidence,
    Money,
    OutcomeLabelValue,
    RecommendationKind,
    RecommendationStatus,
    SessionId,
    SnapshotId,
    TaskType,
    TokenCount,
)

if TYPE_CHECKING:
    import duckdb


class DuckDBRecommendationRepository:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def save_all(self, recs: Sequence[Recommendation]) -> None:
        rows = [
            [
                r.rec_id,
                r.session_id.value,
                r.kind.value,
                r.target,
                r.est_savings_tokens.value,
                float(r.est_savings_usd.amount),
                r.confidence.value,
                r.rationale,
                r.status.value,
                r.snapshot_id.value if r.snapshot_id else None,
                r.provenance,
                _to_utc_naive(r.created_at),
                _to_utc_naive(r.applied_at),
                _to_utc_naive(r.dismissed_at),
            ]
            for r in recs
        ]
        if not rows:
            return
        self._conn.executemany(
            """
            INSERT OR REPLACE INTO recommendations
                (rec_id, session_id, kind, target, est_savings_tokens,
                 est_savings_usd, confidence, rationale, status, snapshot_id,
                 provenance, created_at, applied_at, dismissed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    def list_for_session(
        self, sid: SessionId, *, status: RecommendationStatus | None = None
    ) -> Iterable[Recommendation]:
        query = "SELECT * FROM recommendations WHERE session_id = ?"
        params: list[object] = [sid.value]
        if status is not None:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY created_at DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [_row_to_recommendation(r) for r in rows]

    def list_pending(self, limit: int = 50) -> Iterable[Recommendation]:
        rows = self._conn.execute(
            "SELECT * FROM recommendations WHERE status = 'pending' "
            "ORDER BY created_at DESC LIMIT ?",
            [limit],
        ).fetchall()
        return [_row_to_recommendation(r) for r in rows]

    def list_applied_in_range(self, start: datetime, end: datetime) -> Iterable[Recommendation]:
        rows = self._conn.execute(
            "SELECT * FROM recommendations WHERE status = 'applied' "
            "AND applied_at >= ? AND applied_at < ? "
            "ORDER BY applied_at ASC",
            [_to_utc_naive(start), _to_utc_naive(end)],
        ).fetchall()
        return [_row_to_recommendation(r) for r in rows]

    def mark_applied(self, rec_ids: Sequence[str], snapshot_id: SnapshotId) -> None:
        if not rec_ids:
            return
        now_utc = _to_utc_naive(datetime.now(timezone.utc))
        placeholders = ",".join(["?"] * len(rec_ids))
        self._conn.execute(
            f"""
            UPDATE recommendations
            SET status = 'applied', snapshot_id = ?, applied_at = ?
            WHERE rec_id IN ({placeholders})
            """,
            [snapshot_id.value, now_utc, *rec_ids],
        )

    def mark_dismissed(self, rec_ids: Sequence[str]) -> None:
        if not rec_ids:
            return
        now_utc = _to_utc_naive(datetime.now(timezone.utc))
        placeholders = ",".join(["?"] * len(rec_ids))
        self._conn.execute(
            f"""
            UPDATE recommendations
            SET status = 'dismissed', dismissed_at = ?
            WHERE rec_id IN ({placeholders})
            """,
            [now_utc, *rec_ids],
        )


def _row_to_recommendation(row: tuple[object, ...]) -> Recommendation:
    snapshot_id_val = row[9]
    return Recommendation(
        rec_id=str(row[0]),
        session_id=SessionId(str(row[1])),
        kind=RecommendationKind(str(row[2])),
        target=str(row[3]) if row[3] is not None else None,
        est_savings_tokens=TokenCount(int(row[4] or 0)),
        est_savings_usd=Money(Decimal(str(row[5] or 0))),
        confidence=Confidence(float(row[6])),
        rationale=str(row[7]),
        status=RecommendationStatus(str(row[8])),
        snapshot_id=SnapshotId(str(snapshot_id_val)) if snapshot_id_val else None,
        provenance=str(row[10]) if row[10] is not None else None,
        created_at=_from_utc(row[11]),  # type: ignore[arg-type]
        applied_at=_from_utc(row[12]),  # type: ignore[arg-type]
        dismissed_at=_from_utc(row[13]),  # type: ignore[arg-type]
    )


class DuckDBSnapshotRepository:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def save(self, snap: Snapshot) -> None:
        manifest = json.dumps(
            [{"path": f.path, "sha256": f.sha256, "bytes": f.byte_size} for f in snap.files]
        )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO snapshots
                (snapshot_id, captured_at, reason, triggered_by, files_manifest,
                 byte_size, restored_at)
            VALUES (?, ?, ?, ?, ?::JSON, ?, ?)
            """,
            [
                snap.snapshot_id.value,
                snap.captured_at,
                snap.reason,
                snap.triggered_by,
                manifest,
                snap.byte_size,
                snap.restored_at,
            ],
        )

    def get(self, sid: SnapshotId) -> Snapshot | None:
        row = self._conn.execute(
            "SELECT * FROM snapshots WHERE snapshot_id = ?", [sid.value]
        ).fetchone()
        if row is None:
            return None
        return _row_to_snapshot(row)

    def list_recent(self, limit: int = 20) -> Sequence[Snapshot]:
        rows = self._conn.execute(
            "SELECT * FROM snapshots ORDER BY captured_at DESC LIMIT ?", [limit]
        ).fetchall()
        return [_row_to_snapshot(r) for r in rows]

    def mark_restored(self, sid: SnapshotId) -> None:
        self._conn.execute(
            "UPDATE snapshots SET restored_at = ? WHERE snapshot_id = ?",
            [_to_utc_naive(datetime.now(timezone.utc)), sid.value],
        )


def _row_to_snapshot(row: tuple[object, ...]) -> Snapshot:
    manifest_raw = row[4]
    manifest = json.loads(manifest_raw) if isinstance(manifest_raw, str) else manifest_raw
    files = tuple(
        SnapshotFileEntry(
            path=str(entry["path"]),
            sha256=str(entry["sha256"]),
            byte_size=int(entry["bytes"]),
        )
        for entry in (manifest or [])
    )
    return Snapshot(
        snapshot_id=SnapshotId(str(row[0])),
        captured_at=row[1],  # type: ignore[arg-type]
        reason=str(row[2]),
        triggered_by=str(row[3]) if row[3] is not None else None,
        files=files,
        byte_size=int(row[5] or 0),
        restored_at=row[6],  # type: ignore[arg-type]
    )


class DuckDBOutcomeRepository:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def set_label(self, label: OutcomeLabel) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO outcome_labels
                (session_id, label, task_type, source, reason, labeled_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                label.session_id.value,
                label.label.value,
                label.task_type.value if label.task_type else None,
                label.source,
                label.reason,
                label.labeled_at,
            ],
        )

    def get_label(self, sid: SessionId) -> OutcomeLabel | None:
        row = self._conn.execute(
            "SELECT * FROM outcome_labels WHERE session_id = ?", [sid.value]
        ).fetchone()
        if row is None:
            return None
        return _row_to_outcome(row)

    def list_sessions_by_label(
        self,
        label: OutcomeLabelValue,
        task_type: TaskType | None = None,
    ) -> Sequence[Session]:
        query = (
            "SELECT s.* FROM sessions s "
            "JOIN outcome_labels ol ON ol.session_id = s.session_id "
            "WHERE ol.label = ?"
        )
        params: list[object] = [label.value]
        if task_type is not None:
            query += " AND ol.task_type = ?"
            params.append(task_type.value)
        rows = self._conn.execute(query, params).fetchall()
        return [DuckDBSessionRepository._row_to_session(r) for r in rows]


def _row_to_outcome(row: tuple[object, ...]) -> OutcomeLabel:
    task_raw = row[2]
    return OutcomeLabel(
        session_id=SessionId(str(row[0])),
        label=OutcomeLabelValue(str(row[1])),
        task_type=TaskType(str(task_raw)) if task_raw else None,
        source=str(row[3]),
        reason=str(row[4]) if row[4] is not None else None,
        labeled_at=row[5],  # type: ignore[arg-type]
    )


class DuckDBSubsetProfileStore:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def save(self, profile: SubsetProfile) -> None:
        self._conn.execute(
            """
            INSERT INTO subset_profiles
                (profile_id, name, task_type, content, derived_from,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?::JSON, ?, ?, ?)
            ON CONFLICT (name) DO UPDATE SET
                task_type = EXCLUDED.task_type,
                content = EXCLUDED.content,
                derived_from = EXCLUDED.derived_from,
                updated_at = EXCLUDED.updated_at
            """,
            [
                profile.profile_id,
                profile.name,
                profile.task_type.value if profile.task_type else None,
                json.dumps(profile.content),
                profile.derived_from,
                _to_utc_naive(profile.created_at),
                _to_utc_naive(profile.updated_at),
            ],
        )

    def load(self, name: str) -> SubsetProfile | None:
        row = self._conn.execute("SELECT * FROM subset_profiles WHERE name = ?", [name]).fetchone()
        if row is None:
            return None
        return _row_to_subset_profile(row)

    def list_all(self) -> Sequence[SubsetProfile]:
        rows = self._conn.execute("SELECT * FROM subset_profiles ORDER BY name").fetchall()
        return [_row_to_subset_profile(r) for r in rows]

    def delete(self, name: str) -> None:
        self._conn.execute("DELETE FROM subset_profiles WHERE name = ?", [name])


def _row_to_subset_profile(row: tuple[object, ...]) -> SubsetProfile:
    raw_content = row[3]
    content = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
    task_raw = row[2]
    return SubsetProfile(
        profile_id=str(row[0]),
        name=str(row[1]),
        task_type=TaskType(str(task_raw)) if task_raw else None,
        content=dict(content or {}),
        derived_from=str(row[4]) if row[4] is not None else None,
        created_at=row[5],  # type: ignore[arg-type]
        updated_at=row[6],  # type: ignore[arg-type]
    )


class DuckDBPricingProvider:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def rate_for(self, model: str, at: datetime | None = None) -> PricingRate:
        if at is None:
            row = self._conn.execute(
                "SELECT * FROM pricing_rates WHERE model = ? ORDER BY effective_at DESC LIMIT 1",
                [model],
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM pricing_rates WHERE model = ? AND effective_at <= ? "
                "ORDER BY effective_at DESC LIMIT 1",
                [model, _to_utc_naive(at)],
            ).fetchone()
        if row is None:
            raise UnknownPricingModel(model)
        return _row_to_rate(row)

    def upsert(self, rate: PricingRate) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO pricing_rates
                (rate_id, model, input_per_mtok, output_per_mtok,
                 cache_write_per_mtok, cache_read_per_mtok, currency,
                 effective_at, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                rate.rate_id,
                rate.model,
                rate.input_per_mtok,
                rate.output_per_mtok,
                rate.cache_write_per_mtok,
                rate.cache_read_per_mtok,
                rate.currency,
                _to_utc_naive(rate.effective_at),
                rate.source,
            ],
        )


def _row_to_rate(row: tuple[object, ...]) -> PricingRate:
    return PricingRate(
        rate_id=str(row[0]),
        model=str(row[1]),
        input_per_mtok=float(row[2]),
        output_per_mtok=float(row[3]),
        cache_write_per_mtok=float(row[4] or 0),
        cache_read_per_mtok=float(row[5] or 0),
        currency=str(row[6] or "USD"),
        effective_at=_from_utc(row[7]),  # type: ignore[arg-type]
        source=str(row[8]),
    )
