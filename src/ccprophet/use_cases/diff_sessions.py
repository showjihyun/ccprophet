from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ccprophet.domain.entities import SessionDiff
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.services.bloat import BloatCalculator
from ccprophet.domain.values import SessionId
from ccprophet.ports.repositories import (
    SessionRepository,
    ToolCallRepository,
    ToolDefRepository,
)


@dataclass(frozen=True)
class DiffSessionsUseCase:
    sessions: SessionRepository
    tool_defs: ToolDefRepository
    tool_calls: ToolCallRepository

    def execute(self, sid_a: SessionId, sid_b: SessionId) -> SessionDiff:
        a = self.sessions.get(sid_a)
        b = self.sessions.get(sid_b)
        if a is None:
            raise SessionNotFound(sid_a)
        if b is None:
            raise SessionNotFound(sid_b)

        calls_a = list(self.tool_calls.list_for_session(sid_a))
        calls_b = list(self.tool_calls.list_for_session(sid_b))
        defs_a = list(self.tool_defs.list_for_session(sid_a))
        defs_b = list(self.tool_defs.list_for_session(sid_b))

        tools_a = {tc.tool_name for tc in calls_a}
        tools_b = {tc.tool_name for tc in calls_b}
        mcps_a = _mcps_called(calls_a, defs_a)
        mcps_b = _mcps_called(calls_b, defs_b)

        bloat_a = BloatCalculator.calculate(defs_a, calls_a).bloat_ratio.value
        bloat_b = BloatCalculator.calculate(defs_b, calls_b).bloat_ratio.value

        return SessionDiff(
            session_a_id=sid_a,
            session_b_id=sid_b,
            input_tokens_delta=b.total_input_tokens.value - a.total_input_tokens.value,
            output_tokens_delta=b.total_output_tokens.value - a.total_output_tokens.value,
            tool_call_count_delta=len(calls_b) - len(calls_a),
            bloat_ratio_delta=bloat_b - bloat_a,
            compacted_delta=int(b.compacted) - int(a.compacted),
            tools_added=tuple(sorted(tools_b - tools_a)),
            tools_removed=tuple(sorted(tools_a - tools_b)),
            mcps_added=tuple(sorted(mcps_b - mcps_a)),
            mcps_removed=tuple(sorted(mcps_a - mcps_b)),
        )


def _mcps_called(calls: Sequence, defs: Sequence) -> set[str]:  # type: ignore[no-untyped-def]
    source_lookup = {
        td.tool_name: td.source[len("mcp:"):]
        for td in defs
        if td.source.startswith("mcp:")
    }
    return {
        server
        for tc in calls
        if (server := source_lookup.get(tc.tool_name)) is not None
    }
