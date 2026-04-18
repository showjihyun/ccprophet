"""Pure `BudgetEnvelope` computation on top of a `BestConfig`.

Input: the success-labelled cluster (already found by the use case) +
optional PricingRate for cost estimation. Output: envelope with stats and
risk flags the CLI can render verbatim.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal

from ccprophet.domain.entities import (
    BestConfig,
    BudgetEnvelope,
    PricingRate,
    Session,
)
from ccprophet.domain.values import Money, TokenCount

HIGH_AUTOCOMPACT_RATE = 0.25


class BudgetAnalyzer:
    @staticmethod
    def analyze(
        *,
        best_config: BestConfig,
        sessions: Sequence[Session],
        pricing: PricingRate | None = None,
    ) -> BudgetEnvelope:
        n = len(sessions)
        input_values = [s.total_input_tokens.value for s in sessions]
        output_values = [s.total_output_tokens.value for s in sessions]

        input_mean = sum(input_values) // n if n else 0
        output_mean = sum(output_values) // n if n else 0
        input_stddev = _stddev(input_values, input_mean)

        cost = _estimate_cost(input_mean, output_mean, pricing)

        flags: list[str] = []
        if best_config.autocompact_hit_rate >= HIGH_AUTOCOMPACT_RATE:
            rate_pct = round(best_config.autocompact_hit_rate * 100)
            flags.append(
                f"high autocompact rate: {rate_pct}% of similar sessions"
            )
        if best_config.dropped_mcps:
            flags.append(
                f"{len(best_config.dropped_mcps)} unused MCP(s) detected — "
                "consider subset profile"
            )

        return BudgetEnvelope(
            task_type=best_config.task_type,
            sample_size=best_config.cluster_size,
            estimated_input_tokens_mean=TokenCount(input_mean),
            estimated_input_tokens_stddev=input_stddev,
            estimated_output_tokens_mean=TokenCount(output_mean),
            estimated_cost=cost,
            best_config=best_config,
            risk_flags=tuple(flags),
        )


def _stddev(values: Sequence[int], mean: int) -> int:
    if len(values) < 2:
        return 0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return round(math.sqrt(variance))


def _estimate_cost(
    input_mean: int, output_mean: int, pricing: PricingRate | None
) -> Money:
    if pricing is None:
        return Money.zero()
    input_usd = Decimal(str(pricing.input_per_mtok)) * Decimal(input_mean) / Decimal(1_000_000)
    output_usd = Decimal(str(pricing.output_per_mtok)) * Decimal(output_mean) / Decimal(1_000_000)
    return Money(input_usd + output_usd, pricing.currency)
