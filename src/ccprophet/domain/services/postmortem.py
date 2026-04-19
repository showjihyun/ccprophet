"""Diff a failed session against the success-labelled cluster for the same task.

Pure. The use case is responsible for loading the inputs (OutcomeRepo,
ToolCallRepo, ToolDefRepo) and converting label metadata.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import mean

from ccprophet.domain.entities import (
    PostmortemFinding,
    PostmortemReport,
    Session,
    ToolCall,
    ToolDef,
)
from ccprophet.domain.values import TaskType

TASK_TOOL = "Task"
READ_TOOLS = frozenset({"Read", "Glob", "Grep"})
REPEAT_READ_THRESHOLD = 5
TASK_OVERRUN_DELTA = 2.0


@dataclass(frozen=True, slots=True)
class PostmortemInputs:
    failed_session: Session
    task_type: TaskType | None
    failed_tool_calls: Sequence[ToolCall]
    failed_tool_defs: Sequence[ToolDef]
    success_sessions: Sequence[Session]
    success_tool_calls: Mapping[str, Sequence[ToolCall]]
    success_tool_defs: Mapping[str, Sequence[ToolDef]]


class PostmortemAnalyzer:
    @staticmethod
    def analyze(inputs: PostmortemInputs) -> PostmortemReport:
        findings: list[PostmortemFinding] = []
        suggestions: list[str] = []
        n = len(inputs.success_sessions)

        findings.extend(_task_overrun_findings(inputs))
        findings.extend(_repeat_read_findings(inputs))
        findings.extend(_unused_mcp_findings(inputs))

        if any(f.kind == "unused_mcp" for f in findings):
            suggestions.append("Apply `ccprophet prune` to drop unused MCPs before next attempt")
        if any(f.kind == "repeat_reads" for f in findings):
            suggestions.append("Consider summarising frequently-read files into CLAUDE.md")
        if inputs.failed_session.compacted:
            suggestions.append("Autocompact hit — consider `/clear` around 80% context usage")

        return PostmortemReport(
            failed_session_id=inputs.failed_session.session_id,
            task_type=inputs.task_type,
            sample_size=n,
            findings=tuple(findings),
            suggestions=tuple(suggestions),
            rationale=_rationale(findings, inputs.failed_session.compacted, n),
        )


def _rationale(findings: Sequence[PostmortemFinding], compacted: bool, sample_size: int) -> str:
    """Compress the worst finding into a 1-line "why it failed" (AP-8)."""
    if sample_size < 3:
        return (
            f"Only {sample_size} labelled success sample(s) — conclusions are "
            f"low-confidence; mark more sessions to strengthen the baseline."
        )
    # Rank by expected user impact: task overrun > repeat reads > unused MCPs
    # (tool bloat is the cheapest to fix; task fan-out is the most disruptive).
    priority = {"task_overrun": 0, "repeat_reads": 1, "unused_mcp": 2}
    ranked = sorted(findings, key=lambda f: priority.get(f.kind, 99))
    if ranked:
        top = ranked[0]
        label = {
            "task_overrun": "Task tool fan-out",
            "repeat_reads": "File re-reading loop",
            "unused_mcp": "Unused MCP bloat",
        }.get(top.kind, top.kind)
        compact_note = " after autocompact" if compacted else ""
        return f"{label}{compact_note} — {top.detail}."
    if compacted:
        return "Session hit autocompact but matched success patterns otherwise."
    return "No dominant failure signal; session matches success patterns on the tracked axes."


def _task_overrun_findings(inputs: PostmortemInputs) -> list[PostmortemFinding]:
    failed_tasks = sum(1 for tc in inputs.failed_tool_calls if tc.tool_name == TASK_TOOL)
    if not inputs.success_sessions:
        return []
    success_task_counts = [
        sum(
            1
            for tc in inputs.success_tool_calls.get(s.session_id.value, [])
            if tc.tool_name == TASK_TOOL
        )
        for s in inputs.success_sessions
    ]
    avg = mean(success_task_counts) if success_task_counts else 0
    if failed_tasks > avg + TASK_OVERRUN_DELTA:
        return [
            PostmortemFinding(
                kind="task_overrun",
                detail=(f"Task tool called {failed_tasks}x (success avg {avg:.1f}x)"),
            )
        ]
    return []


def _repeat_read_findings(inputs: PostmortemInputs) -> list[PostmortemFinding]:
    path_counts: dict[str, int] = {}
    for tc in inputs.failed_tool_calls:
        if tc.tool_name not in READ_TOOLS:
            continue
        path_counts[tc.input_hash] = path_counts.get(tc.input_hash, 0) + 1

    repeated = [
        (hash_, count) for hash_, count in path_counts.items() if count >= REPEAT_READ_THRESHOLD
    ]
    if not repeated:
        return []
    worst = max(repeated, key=lambda pair: pair[1])
    return [
        PostmortemFinding(
            kind="repeat_reads",
            detail=(f"{len(repeated)} file(s) re-read ≥{REPEAT_READ_THRESHOLD}x (max {worst[1]}x)"),
        )
    ]


def _unused_mcp_findings(inputs: PostmortemInputs) -> list[PostmortemFinding]:
    loaded = {
        td.source[len("mcp:") :] for td in inputs.failed_tool_defs if td.source.startswith("mcp:")
    }
    called_sources: set[str] = set()
    source_lookup = {
        td.tool_name: td.source[len("mcp:") :]
        for td in inputs.failed_tool_defs
        if td.source.startswith("mcp:")
    }
    for tc in inputs.failed_tool_calls:
        server = source_lookup.get(tc.tool_name)
        if server:
            called_sources.add(server)
    unused = loaded - called_sources
    if not unused:
        return []
    return [
        PostmortemFinding(
            kind="unused_mcp",
            detail=f"{len(unused)} MCP(s) loaded but unused: " + ", ".join(sorted(unused)),
        )
    ]
