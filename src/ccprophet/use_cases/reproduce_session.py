"""Reproduce the "best config" from a success-labelled cluster.

- Without `--apply`: returns the Recommendations that *would* be generated.
- With `--apply`: persists them and runs ApplyPruningUseCase using the same
  auto-fix path as `prune --apply` (single code path, single audit trail).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from ccprophet.domain.entities import BestConfig, Recommendation
from ccprophet.domain.services.cluster import (
    DEFAULT_MIN_SAMPLES,
    BestConfigExtractor,
    ClusterInputs,
)
from ccprophet.domain.values import (
    Confidence,
    Money,
    OutcomeLabelValue,
    RecommendationKind,
    TaskType,
    TokenCount,
)
from ccprophet.ports.clock import Clock
from ccprophet.ports.outcomes import OutcomeRepository
from ccprophet.ports.recommendations import RecommendationRepository
from ccprophet.ports.repositories import ToolCallRepository, ToolDefRepository
from ccprophet.use_cases.apply_pruning import ApplyPruningUseCase, PruningOutcome


@dataclass(frozen=True, slots=True)
class ReproduceOutcome:
    best_config: BestConfig
    recommendations: tuple[Recommendation, ...]
    apply_outcome: PruningOutcome | None


@dataclass(frozen=True)
class ReproduceSessionUseCase:
    outcomes: OutcomeRepository
    tool_calls: ToolCallRepository
    tool_defs: ToolDefRepository
    recommendations: RecommendationRepository
    apply: ApplyPruningUseCase
    clock: Clock

    def execute(
        self,
        task_type: TaskType,
        *,
        target_path: Path | None = None,
        apply: bool = False,
        min_samples: int = DEFAULT_MIN_SAMPLES,
    ) -> ReproduceOutcome:
        cluster = list(self.outcomes.list_sessions_by_label(OutcomeLabelValue.SUCCESS, task_type))
        tool_calls_by_session = {
            s.session_id.value: list(self.tool_calls.list_for_session(s.session_id))
            for s in cluster
        }
        tool_defs_by_session = {
            s.session_id.value: list(self.tool_defs.list_for_session(s.session_id)) for s in cluster
        }

        best_config = BestConfigExtractor.extract(
            ClusterInputs(
                task_type=task_type,
                sessions=tuple(cluster),
                tool_calls_by_session=tool_calls_by_session,
                tool_defs_by_session=tool_defs_by_session,
            ),
            min_samples=min_samples,
        )

        recs = _build_recs(best_config, self.clock, cluster)
        if not recs:
            return ReproduceOutcome(best_config=best_config, recommendations=(), apply_outcome=None)

        self.recommendations.save_all(recs)

        apply_outcome: PruningOutcome | None = None
        if apply:
            if target_path is None:
                raise ValueError("target_path required when apply=True")
            apply_outcome = self.apply.execute(
                target_path=target_path,
                reason=f"reproduce:{task_type.value}",
            )

        return ReproduceOutcome(
            best_config=best_config,
            recommendations=tuple(recs),
            apply_outcome=apply_outcome,
        )


def _build_recs(best_config: BestConfig, clock: Clock, cluster) -> list[Recommendation]:
    """Convert BestConfig.dropped_mcps → prune_mcp Recommendations.

    The session_id attached to each rec is the most-recent success session — this
    is just a provenance anchor; ApplyPruning uses them globally via
    `list_pending`.
    """
    if not best_config.dropped_mcps or not cluster:
        return []
    anchor_session = max(cluster, key=lambda s: s.started_at)
    now = clock.now()
    recs: list[Recommendation] = []
    for mcp in best_config.dropped_mcps:
        recs.append(
            Recommendation(
                rec_id=str(uuid.uuid4()),
                session_id=anchor_session.session_id,
                kind=RecommendationKind.PRUNE_MCP,
                target=f"mcp__{mcp}",
                est_savings_tokens=TokenCount(0),
                est_savings_usd=Money.zero(),
                confidence=Confidence(0.7),
                rationale=(
                    f"mcp:{mcp} was loaded but never used across "
                    f"{best_config.cluster_size} success sessions "
                    f"for {best_config.task_type.value}"
                ),
                created_at=now,
                provenance=f"reproduce:{best_config.task_type.value}",
            )
        )
    return recs
