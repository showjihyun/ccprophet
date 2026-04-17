from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.errors import SessionNotFound, UnknownPricingModel
from ccprophet.domain.values import Money, SessionId, TokenCount
from ccprophet.use_cases.compute_session_cost import ComputeSessionCostUseCase
from tests.fixtures.builders import PricingRateBuilder, SessionBuilder


def _uc(repos: InMemoryRepositorySet) -> ComputeSessionCostUseCase:
    return ComputeSessionCostUseCase(
        sessions=repos.sessions, pricing=repos.pricing
    )


def test_returns_breakdown_for_known_session() -> None:
    repos = InMemoryRepositorySet()
    session = replace(
        SessionBuilder().with_id("s").build(),
        total_input_tokens=TokenCount(1_000_000),
        total_output_tokens=TokenCount(0),
        model="claude-opus-4-6",
    )
    repos.sessions.upsert(session)
    repos.pricing.add(PricingRateBuilder().for_model("claude-opus-4-6").build())

    cost = _uc(repos).execute(SessionId("s"))
    assert cost.total_cost == Money(Decimal("15.0"))


def test_unknown_session_raises() -> None:
    repos = InMemoryRepositorySet()
    with pytest.raises(SessionNotFound):
        _uc(repos).execute(SessionId("nope"))


def test_unknown_model_propagates() -> None:
    repos = InMemoryRepositorySet()
    session = SessionBuilder().with_id("s").build()
    repos.sessions.upsert(session)
    with pytest.raises(UnknownPricingModel):
        _uc(repos).execute(SessionId("s"))
