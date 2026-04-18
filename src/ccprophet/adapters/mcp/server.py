"""Read-only MCP server exposing ccprophet analyses to Claude Code.

Wires already-constructed use cases behind MCP tools. Every tool is a pure
read/analyze operation — no adapter here writes to the DB or filesystem
(AP-7, PRD §6.6). Writes (e.g. persisting recommendations) are avoided by
passing ``persist=False`` to the underlying use case where applicable.
"""
from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Any

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from ccprophet.domain.entities import (
    BloatReport,
    BudgetEnvelope,
    Phase,
    Recommendation,
    RegressionReport,
)
from ccprophet.domain.errors import (
    InsufficientSamples,
    SessionNotFound,
    UnknownPricingModel,
)
from ccprophet.domain.values import SessionId, TaskType
from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
from ccprophet.use_cases.assess_quality import AssessQualityUseCase
from ccprophet.use_cases.detect_phases import DetectPhasesUseCase
from ccprophet.use_cases.estimate_budget import EstimateBudgetUseCase
from ccprophet.use_cases.list_recommendations import ListRecommendationsUseCase

SERVER_NAME = "ccprophet"
SERVER_VERSION = "0.1.0"


def _to_jsonable(obj: Any) -> Any:
    """Best-effort JSON-serialize ccprophet dataclasses / Money / datetimes."""
    return _json.loads(_json.dumps(obj, default=str))


# --- response shapers --------------------------------------------------------


def shape_bloat(report: BloatReport) -> dict[str, Any]:
    return {
        "total_tokens": report.total_tokens.value,
        "bloat_tokens": report.bloat_tokens.value,
        "bloat_ratio": report.bloat_ratio.value,
        "used_count": report.used_count,
        "bloat_count": report.bloat_count,
        "used_sources": sorted(report.used_sources),
        "by_source": [
            {
                "source": s.source,
                "total_tokens": s.total_tokens.value,
                "bloat_tokens": s.bloat_tokens.value,
                "bloat_ratio": s.bloat_ratio.value,
                "tool_count": s.tool_count,
                "bloat_count": s.bloat_count,
            }
            for s in report.by_source().values()
        ],
    }


def shape_phase(p: Phase) -> dict[str, Any]:
    return {
        "phase_id": p.phase_id,
        "session_id": p.session_id.value,
        "phase_type": p.phase_type.value,
        "start_ts": p.start_ts.isoformat(),
        "end_ts": p.end_ts.isoformat() if p.end_ts else None,
        "input_tokens": p.input_tokens.value,
        "output_tokens": p.output_tokens.value,
        "tool_call_count": p.tool_call_count,
        "detection_confidence": p.detection_confidence,
    }


def shape_recommendation(r: Recommendation) -> dict[str, Any]:
    return {
        "rec_id": r.rec_id,
        "session_id": r.session_id.value,
        "kind": r.kind.value,
        "target": r.target,
        "rationale": r.rationale,
        "confidence": r.confidence.value,
        "est_savings_tokens": r.est_savings_tokens.value,
        "est_savings_usd": float(r.est_savings_usd.amount),
        "currency": r.est_savings_usd.currency,
        "status": r.status.value,
        "created_at": r.created_at.isoformat(),
    }


def shape_budget(env: BudgetEnvelope) -> dict[str, Any]:
    bc = env.best_config
    return {
        "task_type": env.task_type.value,
        "sample_size": env.sample_size,
        "estimated_input_tokens_mean": env.estimated_input_tokens_mean.value,
        "estimated_input_tokens_stddev": env.estimated_input_tokens_stddev,
        "estimated_output_tokens_mean": env.estimated_output_tokens_mean.value,
        "estimated_cost_usd": float(env.estimated_cost.amount),
        "currency": env.estimated_cost.currency,
        "risk_flags": list(env.risk_flags),
        "best_config": {
            "cluster_size": bc.cluster_size,
            "common_tools": list(bc.common_tools),
            "dropped_mcps": list(bc.dropped_mcps),
            "avg_input_tokens": bc.avg_input_tokens.value,
            "avg_output_tokens": bc.avg_output_tokens.value,
            "autocompact_hit_rate": bc.autocompact_hit_rate,
        },
    }


def shape_regression(r: RegressionReport) -> dict[str, Any]:
    return {
        "model": r.model,
        "window_days": r.window_days,
        "baseline_days": r.baseline_days,
        "window_sample_size": r.window_sample_size,
        "baseline_sample_size": r.baseline_sample_size,
        "has_regression": r.has_regression,
        "flags": [
            {
                "metric": f.metric_name,
                "baseline_mean": f.baseline_mean,
                "recent_mean": f.recent_mean,
                "baseline_stddev": f.baseline_stddev,
                "z_score": f.z_score,
                "direction": f.direction,
                "explanation": f.explanation,
            }
            for f in r.flags
        ],
    }


# --- tool definitions --------------------------------------------------------


def _tool_definitions() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_current_bloat",
            description="Bloat summary for the latest active Claude Code session.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        types.Tool(
            name="get_phase_breakdown",
            description="Detected phases for a session (default: latest active).",
            inputSchema={
                "type": "object",
                "properties": {
                    "sid": {"type": ["string", "null"], "description": "Session ID"},
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="recommend_action",
            description="Pending recommendations across sessions (newest first).",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="estimate_budget",
            description="Token/cost envelope for a task type (needs >=3 successes).",
            inputSchema={
                "type": "object",
                "properties": {"task_type": {"type": "string", "minLength": 1}},
                "required": ["task_type"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="quality_report",
            description="Per-model regression reports for the recent window.",
            inputSchema={
                "type": "object",
                "properties": {
                    "model": {"type": ["string", "null"]},
                    "window_days": {"type": "integer", "minimum": 1, "maximum": 90},
                    "baseline_days": {"type": "integer", "minimum": 1, "maximum": 365},
                },
                "additionalProperties": False,
            },
        ),
    ]


# --- server ------------------------------------------------------------------


@dataclass
class CcprophetMcpServer:
    """Composition-root-friendly MCP server.

    All use cases are injected. The server never instantiates adapters itself,
    preserving the harness-only composition rule (LAYERING LP-6).
    """

    analyze_bloat: AnalyzeBloatUseCase
    detect_phases: DetectPhasesUseCase
    list_recommendations: ListRecommendationsUseCase
    estimate_budget: EstimateBudgetUseCase
    assess_quality: AssessQualityUseCase

    def __post_init__(self) -> None:
        self._server: Server = Server(SERVER_NAME, version=SERVER_VERSION)
        self._register()

    # -- tool handlers (public for unit testing) -----------------------------

    def tool_get_current_bloat(self) -> dict[str, Any]:
        try:
            report = self.analyze_bloat.execute_current()
        except SessionNotFound as e:
            return _error("session_not_found", str(e))
        return shape_bloat(report)

    def tool_get_phase_breakdown(self, sid: str | None = None) -> dict[str, Any]:
        try:
            phases = (
                self.detect_phases.execute(SessionId(sid), persist=False)
                if sid
                else self.detect_phases.execute_current(persist=False)
            )
        except SessionNotFound as e:
            return _error("session_not_found", str(e))
        return {"phases": [shape_phase(p) for p in phases]}

    def tool_recommend_action(self, limit: int = 50) -> dict[str, Any]:
        recs = list(self.list_recommendations.execute(limit=limit))
        return {"recommendations": [shape_recommendation(r) for r in recs]}

    def tool_estimate_budget(self, task_type: str) -> dict[str, Any]:
        try:
            env = self.estimate_budget.execute(TaskType(task_type))
        except InsufficientSamples as e:
            return _error("insufficient_samples", str(e))
        except UnknownPricingModel as e:
            return _error("unknown_pricing_model", str(e))
        return shape_budget(env)

    def tool_quality_report(
        self,
        model: str | None = None,
        window_days: int = 7,
        baseline_days: int = 30,
    ) -> dict[str, Any]:
        reports = self.assess_quality.execute(
            model=model, window_days=window_days, baseline_days=baseline_days
        )
        return {"reports": [shape_regression(r) for r in reports]}

    # -- dispatch ------------------------------------------------------------

    def dispatch(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args = arguments or {}
        if name == "get_current_bloat":
            return self.tool_get_current_bloat()
        if name == "get_phase_breakdown":
            return self.tool_get_phase_breakdown(sid=args.get("sid"))
        if name == "recommend_action":
            return self.tool_recommend_action(limit=int(args.get("limit", 50)))
        if name == "estimate_budget":
            return self.tool_estimate_budget(task_type=args["task_type"])
        if name == "quality_report":
            return self.tool_quality_report(
                model=args.get("model"),
                window_days=int(args.get("window_days", 7)),
                baseline_days=int(args.get("baseline_days", 30)),
            )
        return _error("unknown_tool", f"Unknown tool: {name}")

    # -- MCP wiring ----------------------------------------------------------

    def _register(self) -> None:
        server = self._server

        @server.list_tools()
        async def _list() -> list[types.Tool]:
            return _tool_definitions()

        @server.call_tool()
        async def _call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            # dispatch is sync; we intentionally don't off-thread since all
            # tools are read-only DuckDB queries (< 500ms target, NFR-1).
            try:
                return _to_jsonable(self.dispatch(name, arguments))
            except Exception as exc:  # AP-3 silent fail — never crash the session
                return _error("internal_error", f"{type(exc).__name__}: {exc}")

    async def run_stdio(self) -> None:
        async with stdio_server() as (read, write):
            await self._server.run(
                read, write, self._server.create_initialization_options()
            )


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": message, "code": code}
