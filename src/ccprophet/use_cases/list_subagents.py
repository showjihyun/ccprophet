from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ccprophet.domain.entities import Subagent
from ccprophet.domain.values import SessionId
from ccprophet.ports.subagents import SubagentRepository


@dataclass(frozen=True)
class ListSubagentsUseCase:
    """List subagent lifecycles for a given parent session."""

    subagents: SubagentRepository

    def execute_for_parent(self, parent: SessionId) -> Sequence[Subagent]:
        return list(self.subagents.list_for_parent(parent))
