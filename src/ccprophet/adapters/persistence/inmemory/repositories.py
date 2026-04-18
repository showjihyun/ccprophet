from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone

from ccprophet.domain.entities import (
    Event,
    Forecast,
    OutcomeLabel,
    Phase,
    PricingRate,
    Recommendation,
    Session,
    SessionSummary,
    Snapshot,
    SnapshotFileEntry,
    Subagent,
    SubsetProfile,
    ToolCall,
    ToolDef,
)
from ccprophet.domain.errors import SnapshotMissing, UnknownPricingModel
from ccprophet.domain.values import (
    OutcomeLabelValue,
    RawHash,
    RecommendationStatus,
    SessionId,
    SnapshotId,
    TaskType,
)
from ccprophet.ports.snapshots import SnapshotMeta


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._store: dict[str, Session] = {}

    def upsert(self, session: Session) -> None:
        self._store[session.session_id.value] = session

    def get(self, sid: SessionId) -> Session | None:
        return self._store.get(sid.value)

    def latest_active(self) -> Session | None:
        active = [s for s in self._store.values() if s.is_active]
        if not active:
            return None
        return max(active, key=lambda s: s.started_at)

    def list_recent(self, limit: int = 10) -> Sequence[Session]:
        ordered = sorted(self._store.values(), key=lambda s: s.started_at, reverse=True)
        return ordered[:limit]

    def list_in_range(self, start: datetime, end: datetime) -> Sequence[Session]:
        return [s for s in self._store.values() if start <= s.started_at < end]


class InMemoryEventRepository:
    def __init__(self) -> None:
        self._events: list[Event] = []
        self._hashes: set[str] = set()

    def append(self, event: Event) -> None:
        if event.raw_hash.value in self._hashes:
            return
        self._hashes.add(event.raw_hash.value)
        self._events.append(event)

    def dedup_hash_exists(self, raw_hash: RawHash) -> bool:
        return raw_hash.value in self._hashes

    def list_by_session(self, sid: SessionId) -> Iterable[Event]:
        return sorted(
            (e for e in self._events if e.session_id == sid),
            key=lambda e: e.ts,
        )


class InMemoryToolDefRepository:
    def __init__(self) -> None:
        self._store: dict[str, list[ToolDef]] = {}

    def bulk_add(self, sid: SessionId, defs: Sequence[ToolDef]) -> None:
        self._store.setdefault(sid.value, []).extend(defs)

    def list_for_session(self, sid: SessionId) -> Iterable[ToolDef]:
        return list(self._store.get(sid.value, []))


class InMemoryToolCallRepository:
    def __init__(self) -> None:
        self._store: list[ToolCall] = []

    def append(self, tc: ToolCall) -> None:
        self._store.append(tc)

    def list_for_session(self, sid: SessionId) -> Iterable[ToolCall]:
        return [tc for tc in self._store if tc.session_id == sid]


class InMemoryPhaseRepository:
    def __init__(self) -> None:
        self._store: dict[str, list[Phase]] = {}

    def replace_for_session(self, sid: SessionId, phases: Sequence[Phase]) -> None:
        self._store[sid.value] = list(phases)

    def list_for_session(self, sid: SessionId) -> Iterable[Phase]:
        return list(self._store.get(sid.value, []))


class InMemoryRecommendationRepository:
    def __init__(self) -> None:
        self._store: dict[str, Recommendation] = {}

    def save_all(self, recs: Sequence[Recommendation]) -> None:
        for r in recs:
            self._store[r.rec_id] = r

    def list_for_session(
        self, sid: SessionId, *, status: RecommendationStatus | None = None
    ) -> Iterable[Recommendation]:
        rows = [r for r in self._store.values() if r.session_id == sid]
        if status is not None:
            rows = [r for r in rows if r.status == status]
        return sorted(rows, key=lambda r: r.created_at, reverse=True)

    def list_pending(self, limit: int = 50) -> Iterable[Recommendation]:
        rows = [
            r for r in self._store.values()
            if r.status == RecommendationStatus.PENDING
        ]
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return rows[:limit]

    def list_applied_in_range(
        self, start: datetime, end: datetime
    ) -> Iterable[Recommendation]:
        rows = [
            r for r in self._store.values()
            if r.status == RecommendationStatus.APPLIED
            and r.applied_at is not None
            and start <= r.applied_at < end
        ]
        # `applied_at` is guaranteed non-None by the filter above; the type
        # checker needs the assertion to narrow `datetime | None` -> `datetime`.
        return sorted(rows, key=lambda r: r.applied_at)  # type: ignore[arg-type,return-value]

    def mark_applied(
        self, rec_ids: Sequence[str], snapshot_id: SnapshotId
    ) -> None:
        now = datetime.now(timezone.utc)
        for rid in rec_ids:
            r = self._store.get(rid)
            if r is None:
                continue
            self._store[rid] = _replace_rec(
                r,
                status=RecommendationStatus.APPLIED,
                snapshot_id=snapshot_id,
                applied_at=now,
            )

    def mark_dismissed(self, rec_ids: Sequence[str]) -> None:
        now = datetime.now(timezone.utc)
        for rid in rec_ids:
            r = self._store.get(rid)
            if r is None:
                continue
            self._store[rid] = _replace_rec(
                r,
                status=RecommendationStatus.DISMISSED,
                dismissed_at=now,
            )


def _replace_rec(rec: Recommendation, **changes: object) -> Recommendation:
    from dataclasses import replace
    return replace(rec, **changes)  # type: ignore[arg-type]


class InMemorySnapshotRepository:
    def __init__(self) -> None:
        self._store: dict[str, Snapshot] = {}

    def save(self, snap: Snapshot) -> None:
        self._store[snap.snapshot_id.value] = snap

    def get(self, sid: SnapshotId) -> Snapshot | None:
        return self._store.get(sid.value)

    def list_recent(self, limit: int = 20) -> Sequence[Snapshot]:
        ordered = sorted(
            self._store.values(), key=lambda s: s.captured_at, reverse=True
        )
        return ordered[:limit]

    def mark_restored(self, sid: SnapshotId) -> None:
        snap = self._store.get(sid.value)
        if snap is None:
            return
        from dataclasses import replace
        self._store[sid.value] = replace(snap, restored_at=datetime.now(timezone.utc))


class InMemorySnapshotStore:
    def __init__(self) -> None:
        self._blobs: dict[str, dict[str, bytes]] = {}
        self._meta: dict[str, Snapshot] = {}

    def capture(
        self, files: Mapping[str, bytes], meta: SnapshotMeta
    ) -> Snapshot:
        import hashlib
        import uuid

        sid = SnapshotId(str(uuid.uuid4()))
        entries = tuple(
            SnapshotFileEntry(
                path=path,
                sha256=hashlib.sha256(data).hexdigest(),
                byte_size=len(data),
            )
            for path, data in files.items()
        )
        snap = Snapshot(
            snapshot_id=sid,
            captured_at=datetime.now(timezone.utc),
            reason=meta.reason,
            triggered_by=meta.triggered_by,
            files=entries,
            byte_size=sum(e.byte_size for e in entries),
        )
        self._blobs[sid.value] = dict(files)
        self._meta[sid.value] = snap
        return snap

    def restore(self, sid: SnapshotId) -> Mapping[str, bytes]:
        if sid.value not in self._blobs:
            raise SnapshotMissing(f"Snapshot not found: {sid}")
        return dict(self._blobs[sid.value])


class InMemoryOutcomeRepository:
    def __init__(self, sessions: InMemorySessionRepository) -> None:
        self._sessions = sessions
        self._labels: dict[str, OutcomeLabel] = {}

    def set_label(self, label: OutcomeLabel) -> None:
        self._labels[label.session_id.value] = label

    def get_label(self, sid: SessionId) -> OutcomeLabel | None:
        return self._labels.get(sid.value)

    def list_sessions_by_label(
        self,
        label: OutcomeLabelValue,
        task_type: TaskType | None = None,
    ) -> Sequence[Session]:
        matching_ids = [
            sid for sid, lbl in self._labels.items()
            if lbl.label == label
            and (task_type is None or lbl.task_type == task_type)
        ]
        result = []
        for sid in matching_ids:
            s = self._sessions.get(SessionId(sid))
            if s is not None:
                result.append(s)
        return result


class InMemorySubsetProfileStore:
    def __init__(self) -> None:
        self._store: dict[str, SubsetProfile] = {}

    def save(self, profile: SubsetProfile) -> None:
        self._store[profile.name] = profile

    def load(self, name: str) -> SubsetProfile | None:
        return self._store.get(name)

    def list_all(self) -> Sequence[SubsetProfile]:
        return sorted(self._store.values(), key=lambda p: p.name)

    def delete(self, name: str) -> None:
        self._store.pop(name, None)


class InMemoryPricingProvider:
    def __init__(self, rates: Iterable[PricingRate] = ()) -> None:
        self._rates: list[PricingRate] = list(rates)

    def add(self, rate: PricingRate) -> None:
        self._rates.append(rate)

    def rate_for(self, model: str, at: datetime | None = None) -> PricingRate:
        candidates = [r for r in self._rates if r.model == model]
        if at is not None:
            candidates = [r for r in candidates if r.effective_at <= at]
        if not candidates:
            raise UnknownPricingModel(model)
        return max(candidates, key=lambda r: r.effective_at)


class InMemoryForecastRepository:
    def __init__(self) -> None:
        self._store: list[Forecast] = []

    def save(self, forecast: Forecast) -> None:
        # Replace any prior row with the same forecast_id (idempotent writes);
        # otherwise append, preserving chronological insertion order.
        for i, existing in enumerate(self._store):
            if existing.forecast_id == forecast.forecast_id:
                self._store[i] = forecast
                return
        self._store.append(forecast)

    def list_for_session(self, sid: SessionId) -> Sequence[Forecast]:
        rows = [f for f in self._store if f.session_id == sid]
        return sorted(rows, key=lambda f: f.predicted_at)


class InMemorySubagentRepository:
    def __init__(self) -> None:
        self._store: dict[str, Subagent] = {}

    def upsert(self, subagent: Subagent) -> None:
        self._store[subagent.subagent_id.value] = subagent

    def get(self, sid: SessionId) -> Subagent | None:
        return self._store.get(sid.value)

    def list_for_parent(self, parent: SessionId) -> Sequence[Subagent]:
        rows = [s for s in self._store.values() if s.parent_session_id == parent]
        return sorted(rows, key=lambda s: s.started_at)


class InMemorySessionSummaryRepository:
    def __init__(self) -> None:
        self._store: dict[str, SessionSummary] = {}

    def upsert(self, summary: SessionSummary) -> None:
        self._store[summary.session_id.value] = summary

    def get(self, sid: SessionId) -> SessionSummary | None:
        return self._store.get(sid.value)

    def list_in_range(
        self, start: datetime, end: datetime
    ) -> Sequence[SessionSummary]:
        rows = [
            s for s in self._store.values()
            if start <= s.started_at < end
        ]
        return sorted(rows, key=lambda s: s.started_at)


class InMemoryRepositorySet:
    def __init__(self) -> None:
        self.sessions = InMemorySessionRepository()
        self.events = InMemoryEventRepository()
        self.tool_defs = InMemoryToolDefRepository()
        self.tool_calls = InMemoryToolCallRepository()
        self.phases = InMemoryPhaseRepository()
        self.recommendations = InMemoryRecommendationRepository()
        self.snapshots = InMemorySnapshotRepository()
        self.snapshot_store = InMemorySnapshotStore()
        self.outcomes = InMemoryOutcomeRepository(self.sessions)
        self.subset_profiles = InMemorySubsetProfileStore()
        self.pricing = InMemoryPricingProvider()
        self.subagents = InMemorySubagentRepository()
        self.forecasts = InMemoryForecastRepository()
        self.session_summaries = InMemorySessionSummaryRepository()
        # Pruner wires the above repos — instantiated lazily via accessor to
        # avoid an import cycle for tests that only use a subset.
        from ccprophet.adapters.persistence.inmemory.hot_table_pruner import (
            InMemoryHotTablePruner,
        )
        self.hot_pruner = InMemoryHotTablePruner(self)
