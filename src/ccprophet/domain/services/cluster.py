"""Session clustering + BestConfig extraction (Product B core).

Pure domain. Raises `InsufficientSamples` when the success-labelled cluster
has fewer than `min_samples` sessions — callers must decide whether to degrade
to "insufficient data" messaging.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ccprophet.domain.entities import BestConfig, Session, ToolCall, ToolDef
from ccprophet.domain.errors import InsufficientSamples
from ccprophet.domain.values import TaskType, TokenCount

DEFAULT_MIN_SAMPLES = 3
DEFAULT_COMMON_THRESHOLD = 0.6


@dataclass(frozen=True, slots=True)
class ClusterInputs:
    task_type: TaskType
    sessions: tuple[Session, ...]
    tool_calls_by_session: Mapping[str, Sequence[ToolCall]]
    tool_defs_by_session: Mapping[str, Sequence[ToolDef]]


class SessionClusterer:
    @staticmethod
    def find_similar(
        sessions: Sequence[Session],
        *,
        project_slug: str | None = None,
        model: str | None = None,
    ) -> tuple[Session, ...]:
        filtered = list(sessions)
        if project_slug is not None:
            filtered = [s for s in filtered if s.project_slug == project_slug]
        if model is not None:
            filtered = [s for s in filtered if s.model == model]
        return tuple(filtered)


class BestConfigExtractor:
    @staticmethod
    def extract(
        inputs: ClusterInputs,
        *,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        common_threshold: float = DEFAULT_COMMON_THRESHOLD,
    ) -> BestConfig:
        n = len(inputs.sessions)
        if n < min_samples:
            raise InsufficientSamples(
                needed=min_samples,
                got=n,
                context=f"task={inputs.task_type.value}",
            )

        tool_frequency: dict[str, int] = {}
        mcp_frequency: dict[str, int] = {}
        mcp_loaded_in_any: set[str] = set()

        for session in inputs.sessions:
            sid = session.session_id.value
            called_tools = {tc.tool_name for tc in inputs.tool_calls_by_session.get(sid, [])}
            for tool in called_tools:
                tool_frequency[tool] = tool_frequency.get(tool, 0) + 1

            called_mcps = _mcp_servers_called(
                inputs.tool_calls_by_session.get(sid, []),
                inputs.tool_defs_by_session.get(sid, []),
            )
            for mcp in called_mcps:
                mcp_frequency[mcp] = mcp_frequency.get(mcp, 0) + 1

            for td in inputs.tool_defs_by_session.get(sid, []):
                if td.source.startswith("mcp:"):
                    mcp_loaded_in_any.add(td.source[len("mcp:") :])

        threshold_count = max(1, round(n * common_threshold))
        common_tools = tuple(
            sorted(name for name, freq in tool_frequency.items() if freq >= threshold_count)
        )
        # MCPs that were loaded across the cluster but never crossed the threshold
        dropped_mcps = tuple(
            sorted(mcp for mcp in mcp_loaded_in_any if mcp_frequency.get(mcp, 0) < threshold_count)
        )

        total_input = sum(s.total_input_tokens.value for s in inputs.sessions)
        total_output = sum(s.total_output_tokens.value for s in inputs.sessions)
        avg_input = total_input // n
        avg_output = total_output // n
        compacted = sum(1 for s in inputs.sessions if s.compacted)

        return BestConfig(
            task_type=inputs.task_type,
            cluster_size=n,
            sample_session_ids=tuple(s.session_id for s in inputs.sessions),
            common_tools=common_tools,
            dropped_mcps=dropped_mcps,
            avg_input_tokens=TokenCount(avg_input),
            avg_output_tokens=TokenCount(avg_output),
            autocompact_hit_rate=compacted / n,
        )


def _mcp_servers_called(tool_calls: Sequence[ToolCall], tool_defs: Sequence[ToolDef]) -> set[str]:
    """Map a tool_call's tool_name back to its MCP server (via tool_defs.source)."""
    source_lookup: dict[str, str] = {}
    for td in tool_defs:
        if td.source.startswith("mcp:"):
            source_lookup[td.tool_name] = td.source[len("mcp:") :]
    return {server for tc in tool_calls if (server := source_lookup.get(tc.tool_name)) is not None}
