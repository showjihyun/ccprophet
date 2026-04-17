from __future__ import annotations

import pytest

from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase


@pytest.fixture
def inmemory_repos() -> InMemoryRepositorySet:
    return InMemoryRepositorySet()


@pytest.fixture
def analyze_bloat(inmemory_repos: InMemoryRepositorySet) -> AnalyzeBloatUseCase:
    return AnalyzeBloatUseCase(
        sessions=inmemory_repos.sessions,
        tool_defs=inmemory_repos.tool_defs,
        tool_calls=inmemory_repos.tool_calls,
    )
