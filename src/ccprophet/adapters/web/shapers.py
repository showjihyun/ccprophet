"""Pure JSON-shape helpers for the Web adapter.

Split out from ``app.py`` to keep the FastAPI module under the AP-5 LOC
guideline. These functions are stateless and framework-free apart from the
dataclasses they read.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from ccprophet.domain.entities import (
    BloatReport,
    CostBreakdown,
    Phase,
    Session,
    ToolCall,
)
from ccprophet.domain.values import PhaseType

PHASE_COLORS: dict[str, str] = {
    PhaseType.PLANNING.value: "#22d3ee",  # cyan
    PhaseType.IMPLEMENTATION.value: "#4ade80",  # green
    PhaseType.DEBUGGING.value: "#f87171",  # red
    PhaseType.REVIEW.value: "#60a5fa",  # blue
    PhaseType.UNKNOWN.value: "#94a3b8",  # slate
}
SESSION_COLOR = "#a78bfa"


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def session_to_dict(s: Session) -> dict[str, Any]:
    return {
        "session_id": s.session_id.value,
        "project_slug": s.project_slug,
        "model": s.model,
        "started_at": iso(s.started_at),
        "ended_at": iso(s.ended_at),
        "total_input_tokens": s.total_input_tokens.value,
        "total_output_tokens": s.total_output_tokens.value,
        "total_cache_creation_tokens": s.total_cache_creation_tokens.value,
        "total_cache_read_tokens": s.total_cache_read_tokens.value,
        "compacted": s.compacted,
        "compacted_at": iso(s.compacted_at),
        "context_window_size": s.context_window_size,
        "is_active": s.is_active,
    }


def bloat_to_dict(b: BloatReport) -> dict[str, Any]:
    return {
        "total_tokens": b.total_tokens.value,
        "bloat_tokens": b.bloat_tokens.value,
        "bloat_ratio": b.bloat_ratio.value,
        "bloat_percent": b.bloat_ratio.as_percent(),
        "used_count": b.used_count,
        "bloat_count": b.bloat_count,
        "used_sources": sorted(b.used_sources),
        "by_source": [
            {
                "source": s.source,
                "total_tokens": s.total_tokens.value,
                "bloat_tokens": s.bloat_tokens.value,
                "bloat_ratio": s.bloat_ratio.value,
                "tool_count": s.tool_count,
                "bloat_count": s.bloat_count,
            }
            for s in b.by_source().values()
        ],
    }


def cost_to_dict(c: CostBreakdown | None) -> dict[str, Any] | None:
    if c is None:
        return None
    return {
        "total_usd": float(c.total_cost.amount),
        "input_usd": float(c.input_cost.amount),
        "output_usd": float(c.output_cost.amount),
        "cache_usd": float(c.cache_cost.amount),
        "currency": c.total_cost.currency,
        "rate_id": c.rate_id,
    }


def phase_for_call(tc: ToolCall, phases: list[Phase]) -> Phase | None:
    """Time-bucket fallback when ToolCall has no explicit phase_id."""
    for p in phases:
        if tc.ts >= p.start_ts and (p.end_ts is None or tc.ts <= p.end_ts):
            return p
    return None


def build_dag(
    session: Session,
    bloat: BloatReport,
    phases: list[Phase],
    tool_calls: Iterable[ToolCall],
) -> dict[str, Any]:
    """Node/edge JSON for the D3 force-directed DAG (PRD F4 §6.4)."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    sid = session.session_id.value
    total_tokens = session.total_input_tokens.value + session.total_output_tokens.value
    nodes.append(
        {
            "id": f"session:{sid}",
            "kind": "session",
            "label": session.project_slug or sid[:8],
            "tokens": total_tokens,
            "color": SESSION_COLOR,
            "phase_type": None,
            "ts": iso(session.started_at),
        }
    )

    for p in phases:
        node_id = f"phase:{p.phase_id}"
        tokens = p.input_tokens.value + p.output_tokens.value
        nodes.append(
            {
                "id": node_id,
                "kind": "phase",
                "label": p.phase_type.value,
                "tokens": tokens,
                "color": PHASE_COLORS.get(p.phase_type.value, "#94a3b8"),
                "phase_type": p.phase_type.value,
                "ts": iso(p.start_ts),
                "tool_call_count": p.tool_call_count,
            }
        )
        edges.append({"source": f"session:{sid}", "target": node_id})

    orphan_id = f"phase:__orphan:{sid}"
    orphan_used = False
    for tc in tool_calls:
        parent = phase_for_call(tc, phases)
        if parent is None:
            if not orphan_used:
                nodes.append(
                    {
                        "id": orphan_id,
                        "kind": "phase",
                        "label": "unphased",
                        "tokens": 0,
                        "color": PHASE_COLORS[PhaseType.UNKNOWN.value],
                        "phase_type": PhaseType.UNKNOWN.value,
                        "ts": iso(session.started_at),
                        "tool_call_count": 0,
                    }
                )
                edges.append({"source": f"session:{sid}", "target": orphan_id})
                orphan_used = True
            parent_id = orphan_id
            color = PHASE_COLORS[PhaseType.UNKNOWN.value]
        else:
            parent_id = f"phase:{parent.phase_id}"
            color = PHASE_COLORS.get(parent.phase_type.value, "#94a3b8")
        call_tokens = tc.input_tokens.value + tc.output_tokens.value
        call_id = f"tool:{tc.tool_call_id}"
        nodes.append(
            {
                "id": call_id,
                "kind": "tool_call",
                "label": tc.tool_name,
                "tokens": call_tokens,
                "color": color,
                "phase_type": None,
                "ts": iso(tc.ts),
                "success": tc.success,
                "latency_ms": tc.latency_ms,
            }
        )
        edges.append({"source": parent_id, "target": call_id})

    return {
        "session": session_to_dict(session),
        "bloat_summary": {
            "total_tokens": bloat.total_tokens.value,
            "bloat_tokens": bloat.bloat_tokens.value,
            "bloat_ratio": bloat.bloat_ratio.value,
        },
        "nodes": nodes,
        "edges": edges,
    }
