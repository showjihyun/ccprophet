from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ccprophet.domain.entities import (
    BloatReport,
    Session,
    SessionSummary,
    ToolCall,
    ToolDef,
)
from ccprophet.domain.values import TokenCount


class SessionAggregator:
    """Pure aggregator: Session + child collections + BloatReport -> SessionSummary.

    No IO, no clock. The caller supplies `summarized_at` (via a Clock port in
    the use case layer). Reuses `BloatReport` so we stay consistent with the
    live `ccprophet bloat` numbers.
    """

    @staticmethod
    def summarize(
        session: Session,
        tool_calls: Sequence[ToolCall],
        tool_defs: Sequence[ToolDef],
        phases_count: int,
        file_reads_count: int,
        bloat_report: BloatReport,
        *,
        summarized_at: datetime,
    ) -> SessionSummary:
        unique_tools = {tc.tool_name for tc in tool_calls}
        loaded_tokens = sum(td.tokens.value for td in tool_defs)

        return SessionSummary(
            session_id=session.session_id,
            project_slug=session.project_slug,
            model=session.model,
            started_at=session.started_at,
            ended_at=session.ended_at,
            summarized_at=summarized_at,
            total_input_tokens=session.total_input_tokens,
            total_output_tokens=session.total_output_tokens,
            total_cache_creation_tokens=session.total_cache_creation_tokens,
            total_cache_read_tokens=session.total_cache_read_tokens,
            compacted=session.compacted,
            tool_call_count=len(tool_calls),
            unique_tools_used=len(unique_tools),
            loaded_tool_def_tokens=TokenCount(loaded_tokens),
            bloat_tokens=bloat_report.bloat_tokens,
            bloat_ratio=bloat_report.bloat_ratio,
            file_read_count=file_reads_count,
            phase_count=phases_count,
            source_rows_deleted=False,
        )
