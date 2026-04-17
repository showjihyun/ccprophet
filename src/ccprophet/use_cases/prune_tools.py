"""Dry-run planner for auto-fix.

Loads pending `prune_*` recommendations and computes the settings.json patch
that would be applied. Writes nothing; callers (CLI, ApplyPruningUseCase)
consume the returned `PrunePreview`.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ccprophet.domain.entities import Recommendation
from ccprophet.domain.services.settings_patch import (
    SettingsPatchPlan,
    SettingsPatchPlanner,
)
from ccprophet.domain.values import RecommendationKind, SessionId
from ccprophet.ports.recommendations import RecommendationRepository
from ccprophet.ports.settings import SettingsStore

PRUNE_KINDS = frozenset(
    {RecommendationKind.PRUNE_MCP, RecommendationKind.PRUNE_TOOL}
)


@dataclass(frozen=True, slots=True)
class PrunePreview:
    target_path: Path
    recommendations: tuple[Recommendation, ...]
    plan: SettingsPatchPlan

    @property
    def has_changes(self) -> bool:
        return self.plan.has_changes


@dataclass(frozen=True)
class PruneToolsUseCase:
    recommendations: RecommendationRepository
    settings: SettingsStore

    def execute(
        self,
        *,
        target_path: Path,
        session_id: SessionId | None = None,
    ) -> PrunePreview:
        pending = _load_pending(self.recommendations, session_id)
        doc = self.settings.read(target_path)
        plan = SettingsPatchPlanner.plan(doc, pending)
        return PrunePreview(
            target_path=target_path,
            recommendations=tuple(pending),
            plan=plan,
        )


def _load_pending(
    repo: RecommendationRepository, session_id: SessionId | None
) -> Sequence[Recommendation]:
    raw = (
        list(repo.list_for_session(session_id))
        if session_id is not None
        else list(repo.list_pending(limit=100))
    )
    return [r for r in raw if r.kind in PRUNE_KINDS and r.status.value == "pending"]
