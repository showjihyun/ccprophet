from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ccprophet.domain.entities import Recommendation
from ccprophet.ports.recommendations import RecommendationRepository


@dataclass(frozen=True)
class ListRecommendationsUseCase:
    """Return globally pending recommendations (newest first)."""

    recommendations: RecommendationRepository

    def execute(self, limit: int = 50) -> Sequence[Recommendation]:
        return list(self.recommendations.list_pending(limit=limit))
