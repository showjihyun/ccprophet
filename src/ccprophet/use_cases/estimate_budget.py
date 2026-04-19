from __future__ import annotations

from dataclasses import dataclass

from ccprophet.domain.entities import BudgetEnvelope
from ccprophet.domain.errors import UnknownPricingModel
from ccprophet.domain.services.budget import BudgetAnalyzer
from ccprophet.domain.services.cluster import (
    DEFAULT_MIN_SAMPLES,
    BestConfigExtractor,
    ClusterInputs,
)
from ccprophet.domain.values import OutcomeLabelValue, TaskType
from ccprophet.ports.outcomes import OutcomeRepository
from ccprophet.ports.pricing import PricingProvider
from ccprophet.ports.repositories import ToolCallRepository, ToolDefRepository


@dataclass(frozen=True)
class EstimateBudgetUseCase:
    outcomes: OutcomeRepository
    tool_calls: ToolCallRepository
    tool_defs: ToolDefRepository
    pricing: PricingProvider

    def execute(
        self,
        task_type: TaskType,
        *,
        min_samples: int = DEFAULT_MIN_SAMPLES,
    ) -> BudgetEnvelope:
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

        pricing = _resolve_pricing(self.pricing, cluster)
        return BudgetAnalyzer.analyze(best_config=best_config, sessions=cluster, pricing=pricing)


def _resolve_pricing(provider: PricingProvider, sessions):  # type: ignore[no-untyped-def]
    if not sessions:
        return None
    try:
        return provider.rate_for(sessions[0].model, sessions[0].started_at)
    except UnknownPricingModel:
        return None
