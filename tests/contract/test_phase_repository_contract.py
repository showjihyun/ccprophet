from __future__ import annotations

from abc import ABC, abstractmethod

import pytest

from ccprophet.domain.values import PhaseType, SessionId
from tests.fixtures.builders import PhaseBuilder


class PhaseRepositoryContract(ABC):
    @pytest.fixture
    @abstractmethod
    def repository(self):  # type: ignore[no-untyped-def]
        ...

    def test_replace_then_list(self, repository) -> None:  # type: ignore[no-untyped-def]
        p1 = PhaseBuilder().in_session("s1").of_type(PhaseType.PLANNING).build()
        p2 = PhaseBuilder().in_session("s1").of_type(PhaseType.IMPLEMENTATION).build()
        repository.replace_for_session(SessionId("s1"), [p1, p2])
        got = list(repository.list_for_session(SessionId("s1")))
        assert len(got) == 2
        assert {p.phase_type for p in got} == {PhaseType.PLANNING, PhaseType.IMPLEMENTATION}

    def test_replace_clears_existing(self, repository) -> None:  # type: ignore[no-untyped-def]
        first = PhaseBuilder().in_session("s1").of_type(PhaseType.PLANNING).build()
        repository.replace_for_session(SessionId("s1"), [first])
        second = PhaseBuilder().in_session("s1").of_type(PhaseType.REVIEW).build()
        repository.replace_for_session(SessionId("s1"), [second])
        got = list(repository.list_for_session(SessionId("s1")))
        assert len(got) == 1
        assert got[0].phase_type == PhaseType.REVIEW

    def test_empty_list_when_unknown(self, repository) -> None:  # type: ignore[no-untyped-def]
        assert list(repository.list_for_session(SessionId("none"))) == []


class TestInMemoryPhaseRepository(PhaseRepositoryContract):
    @pytest.fixture
    def repository(self):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.inmemory.repositories import (
            InMemoryPhaseRepository,
        )

        return InMemoryPhaseRepository()
