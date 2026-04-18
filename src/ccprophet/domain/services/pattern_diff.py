"""Rule-based, LLM-free pattern diff between two sessions (PRD F9 / FR-9.3).

Produces a ``PatternDiffReport`` from two already-ingested sessions. Pure
domain — no IO, no third-party deps, no ``datetime.now()``. All thresholds
are constants at module level so they are easy to audit in code review.

Design notes:

* Headline selection is deterministic: highest severity first, ties broken by
  the largest numeric delta carried on the finding (via ``_magnitude``).
* ``detail`` strings are intentionally terse — the Web UI renders them verbatim
  next to a severity dot, and the CLI ``diff`` command can reuse them without
  re-formatting.
"""
from __future__ import annotations

import contextlib
from collections.abc import Sequence
from dataclasses import dataclass

from ccprophet.domain.entities import Phase, Session, ToolCall, ToolDef
from ccprophet.domain.services.bloat import BloatCalculator
from ccprophet.domain.values import SessionId

# Rule thresholds (FR-9.3). Change here, not in callers.
TOKEN_DELTA_WARN = 0.25            # ±25% relative change → 'info'
TOKEN_DELTA_WARN_SEVERE = 0.50     # ±50% → 'warn'
TOKEN_DELTA_CRITICAL = 1.00        # ±100% → 'critical'
TOOL_MIX_JACCARD_THRESHOLD = 0.5   # Jaccard distance ≥ 0.5 → fire
BLOAT_DELTA_PP = 0.10              # ≥ 10 percentage points in bloat ratio
READ_LOOP_MIN_REPEAT = 5           # same input_hash seen ≥ N times
PHASE_SHIFT_PP = 0.20              # any phase fraction differs by ≥ 20pp

SEVERITY_RANK = {"info": 0, "warn": 1, "critical": 2}


@dataclass(frozen=True, slots=True)
class PatternFinding:
    kind: str
    severity: str
    detail: str


@dataclass(frozen=True, slots=True)
class PatternDiffReport:
    session_a_id: SessionId
    session_b_id: SessionId
    findings: tuple[PatternFinding, ...]
    headline: str


# --- helpers (module-private) -------------------------------------------------


def _mcps_called(calls: Sequence[ToolCall], defs: Sequence[ToolDef]) -> set[str]:
    lookup = {
        td.tool_name: td.source[len("mcp:"):]
        for td in defs
        if td.source.startswith("mcp:")
    }
    return {s for tc in calls if (s := lookup.get(tc.tool_name)) is not None}


def _has_read_loop(calls: Sequence[ToolCall]) -> tuple[bool, str | None, int]:
    """True when any ``input_hash`` appears ≥ READ_LOOP_MIN_REPEAT in ``Read`` calls."""
    counts: dict[str, int] = {}
    for tc in calls:
        if tc.tool_name != "Read":
            continue
        counts[tc.input_hash] = counts.get(tc.input_hash, 0) + 1
    if not counts:
        return False, None, 0
    worst_hash, worst_count = max(counts.items(), key=lambda kv: kv[1])
    return worst_count >= READ_LOOP_MIN_REPEAT, worst_hash, worst_count


def _phase_fractions(phases: Sequence[Phase]) -> dict[str, float]:
    """Fraction of phases falling into each ``phase_type`` (count-based)."""
    if not phases:
        return {}
    total = len(phases)
    freq: dict[str, int] = {}
    for p in phases:
        name = p.phase_type.value
        freq[name] = freq.get(name, 0) + 1
    return {k: v / total for k, v in freq.items()}


def _jaccard_distance(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return 1.0 - (len(a & b) / len(union))


def _relative_delta(a: int, b: int) -> float:
    """Signed relative change from ``a`` to ``b``. Falls back to abs when a==0."""
    if a == 0 and b == 0:
        return 0.0
    if a == 0:
        return 1.0 if b > 0 else -1.0
    return (b - a) / a


def _magnitude(finding: PatternFinding) -> float:
    """Sort key for headline tie-breaking. Scans detail for largest magnitude."""
    best = 0.0
    buf: list[str] = []
    for ch in finding.detail + " ":
        if ch.isdigit() or ch in ".-":
            buf.append(ch)
            continue
        if buf:
            with contextlib.suppress(ValueError):
                best = max(best, abs(float("".join(buf))))
            buf = []
    return best


def _token_severity(delta: float) -> str:
    adelta = abs(delta)
    if adelta >= TOKEN_DELTA_CRITICAL:
        return "critical"
    if adelta >= TOKEN_DELTA_WARN_SEVERE:
        return "warn"
    return "info"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


# --- analyzer -----------------------------------------------------------------


class PatternDiffAnalyzer:
    """Pure rule engine producing a ``PatternDiffReport`` for two sessions."""

    @staticmethod
    def analyze(
        *,
        a: Session,
        b: Session,
        calls_a: Sequence[ToolCall],
        calls_b: Sequence[ToolCall],
        defs_a: Sequence[ToolDef],
        defs_b: Sequence[ToolDef],
        phases_a: Sequence[Phase],
        phases_b: Sequence[Phase],
    ) -> PatternDiffReport:
        findings: list[PatternFinding] = []

        # Rule 1 — token delta on total_input_tokens.
        tok_a = a.total_input_tokens.value
        tok_b = b.total_input_tokens.value
        rel = _relative_delta(tok_a, tok_b)
        if abs(rel) >= TOKEN_DELTA_WARN:
            findings.append(
                PatternFinding(
                    kind="token_delta",
                    severity=_token_severity(rel),
                    detail=(
                        f"input tokens {tok_a} -> {tok_b} "
                        f"({'+' if rel >= 0 else ''}{_pct(rel)})"
                    ),
                )
            )

        # Rule 2 — autocompact state flipped.
        if a.compacted != b.compacted:
            who_a = "A" if a.compacted else "B"
            who_b = "A" if not a.compacted else "B"
            findings.append(
                PatternFinding(
                    kind="autocompact_changed",
                    severity="critical",
                    detail=(
                        f"{who_a} compacted, {who_b} did not — "
                        "context-window pressure differs"
                    ),
                )
            )

        # Rule 3 — tool-mix Jaccard.
        tools_a = {tc.tool_name for tc in calls_a}
        tools_b = {tc.tool_name for tc in calls_b}
        jdist = _jaccard_distance(tools_a, tools_b)
        if jdist >= TOOL_MIX_JACCARD_THRESHOLD:
            only_a = sorted(tools_a - tools_b)
            only_b = sorted(tools_b - tools_a)
            detail = (
                f"tool-mix shift (Jaccard distance {jdist:.2f}); "
                f"only A: {only_a or '[]'}; only B: {only_b or '[]'}"
            )
            findings.append(
                PatternFinding(kind="tool_mix_shift", severity="warn", detail=detail)
            )

        # Rule 4 — bloat ratio delta.
        bloat_a = BloatCalculator.calculate(defs_a, calls_a).bloat_ratio.value
        bloat_b = BloatCalculator.calculate(defs_b, calls_b).bloat_ratio.value
        bloat_delta = bloat_b - bloat_a
        if abs(bloat_delta) >= BLOAT_DELTA_PP:
            worse = bloat_delta > 0  # B has more bloat than A
            findings.append(
                PatternFinding(
                    kind="bloat_delta",
                    severity="warn" if worse else "info",
                    detail=(
                        f"bloat ratio {_pct(bloat_a)} -> {_pct(bloat_b)} "
                        f"(Δ {'+' if bloat_delta >= 0 else ''}"
                        f"{bloat_delta * 100:.1f}pp)"
                    ),
                )
            )

        # Rule 5 — MCP subset changed.
        mcps_a = _mcps_called(calls_a, defs_a)
        mcps_b = _mcps_called(calls_b, defs_b)
        only_mcp_a = sorted(mcps_a - mcps_b)
        only_mcp_b = sorted(mcps_b - mcps_a)
        if only_mcp_a or only_mcp_b:
            findings.append(
                PatternFinding(
                    kind="mcp_subset_changed",
                    severity="info",
                    detail=(
                        f"MCP servers only A: {only_mcp_a or '[]'}; "
                        f"only B: {only_mcp_b or '[]'}"
                    ),
                )
            )

        # Rule 6 — read-loop XOR.
        loop_a, hash_a, count_a = _has_read_loop(calls_a)
        loop_b, hash_b, count_b = _has_read_loop(calls_b)
        if loop_a != loop_b:
            if loop_a:
                who, h, n = "A", hash_a, count_a
            else:
                who, h, n = "B", hash_b, count_b
            findings.append(
                PatternFinding(
                    kind="read_loop_delta",
                    severity="warn",
                    detail=(
                        f"{who} has a Read loop "
                        f"(same input_hash {str(h)[:12]}… x{n}); "
                        "the other side does not"
                    ),
                )
            )

        # Rule 7 — phase composition shift.
        frac_a = _phase_fractions(phases_a)
        frac_b = _phase_fractions(phases_b)
        keys = set(frac_a) | set(frac_b)
        biggest_name: str | None = None
        biggest_delta = 0.0
        for name in keys:
            delta = frac_b.get(name, 0.0) - frac_a.get(name, 0.0)
            if abs(delta) > abs(biggest_delta):
                biggest_delta = delta
                biggest_name = name
        if biggest_name is not None and abs(biggest_delta) >= PHASE_SHIFT_PP:
            findings.append(
                PatternFinding(
                    kind="phase_shift",
                    severity="info",
                    detail=(
                        f"phase '{biggest_name}' fraction "
                        f"{_pct(frac_a.get(biggest_name, 0.0))} -> "
                        f"{_pct(frac_b.get(biggest_name, 0.0))} "
                        f"(Δ {'+' if biggest_delta >= 0 else ''}"
                        f"{biggest_delta * 100:.1f}pp)"
                    ),
                )
            )

        # Headline — highest severity, ties broken by magnitude.
        if not findings:
            headline = "No structural deltas detected."
        else:
            top = max(
                findings,
                key=lambda f: (SEVERITY_RANK[f.severity], _magnitude(f)),
            )
            headline = top.detail

        return PatternDiffReport(
            session_a_id=a.session_id,
            session_b_id=b.session_id,
            findings=tuple(findings),
            headline=headline,
        )
