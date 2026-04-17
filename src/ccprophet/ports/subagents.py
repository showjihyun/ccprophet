from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ccprophet.domain.entities import Subagent
from ccprophet.domain.values import SessionId


class SubagentRepository(Protocol):
    def upsert(self, subagent: Subagent) -> None: ...
    def get(self, sid: SessionId) -> Subagent | None: ...
    def list_for_parent(self, parent: SessionId) -> Sequence[Subagent]: ...
