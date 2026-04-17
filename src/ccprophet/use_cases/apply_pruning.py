"""Apply step for Auto Tool Pruning (F7).

AP-7 invariants enforced here:
1. Snapshot the target file(s) BEFORE writing.
2. Record Snapshot metadata in DB.
3. `SettingsStore.write_atomic` with expected_hash — rejects concurrent edits.
4. Only after write succeeds do we mark the recommendations as applied.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ccprophet.domain.entities import Snapshot
from ccprophet.domain.values import SessionId
from ccprophet.ports.clock import Clock
from ccprophet.ports.recommendations import RecommendationRepository
from ccprophet.ports.settings import SettingsStore
from ccprophet.ports.snapshots import SnapshotMeta, SnapshotRepository, SnapshotStore
from ccprophet.use_cases.prune_tools import PruneToolsUseCase


@dataclass(frozen=True, slots=True)
class PruningOutcome:
    snapshot: Snapshot | None
    applied_rec_ids: tuple[str, ...]
    written: bool
    reason: str


@dataclass(frozen=True)
class ApplyPruningUseCase:
    prune: PruneToolsUseCase
    settings: SettingsStore
    snapshot_store: SnapshotStore
    snapshots: SnapshotRepository
    recommendations: RecommendationRepository
    clock: Clock

    def execute(
        self,
        *,
        target_path: Path,
        session_id: SessionId | None = None,
        reason: str | None = None,
    ) -> PruningOutcome:
        preview = self.prune.execute(
            target_path=target_path, session_id=session_id
        )
        if not preview.has_changes:
            return PruningOutcome(
                snapshot=None,
                applied_rec_ids=(),
                written=False,
                reason="no changes to apply",
            )

        original_bytes = target_path.read_bytes()
        snapshot = self.snapshot_store.capture(
            files={str(target_path): original_bytes},
            meta=SnapshotMeta(
                reason=reason or self._default_reason(self.clock.now()),
                triggered_by="apply_pruning",
            ),
        )
        self.snapshots.save(snapshot)

        self.settings.write_atomic(
            target_path,
            preview.plan.new_content,
            expected_hash=preview.plan.original.sha256,
        )

        rec_ids = list(preview.plan.applied_rec_ids)
        self.recommendations.mark_applied(rec_ids, snapshot.snapshot_id)

        return PruningOutcome(
            snapshot=snapshot,
            applied_rec_ids=tuple(rec_ids),
            written=True,
            reason=snapshot.reason,
        )

    @staticmethod
    def _default_reason(now: datetime) -> str:
        return f"prune-{now.strftime('%Y%m%dT%H%M%S')}"
