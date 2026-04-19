"""One-line status for Claude Code's `statusLine` integration.

Called frequently → keep work minimal and never fail. If the DB doesn't exist
or no session has been recorded yet, print a placeholder and exit 0 (AP-3).
"""

from __future__ import annotations

import json as json_module
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import Session, ToolCall, ToolDef
    from ccprophet.domain.values import SessionId
    from ccprophet.ports.pricing import PricingProvider
    from ccprophet.ports.repositories import SessionRepository

from ccprophet.domain.errors import UnknownPricingModel
from ccprophet.domain.services.bloat import BloatCalculator
from ccprophet.domain.services.cost import CostCalculator

# Bloat thresholds for the passive statusline indicator. Kept deliberately
# conservative — the point is to nudge users toward `ccprophet prune`, not
# to cry wolf on every session.
BLOAT_WARN_PCT = 40.0  # yellow / ⚠ prompt
BLOAT_ALERT_PCT = 70.0  # red / ❗ prompt


def run_statusline_command(
    sessions: SessionRepository,
    pricing: PricingProvider | None = None,
    *,
    tool_defs_for: Callable[[SessionId], Iterable[ToolDef]] | None = None,
    tool_calls_for: Callable[[SessionId], Iterable[ToolCall]] | None = None,
    as_json: bool = False,
    with_cost: bool = False,
) -> int:
    session = _pick_latest_session(sessions)
    if session is None:
        _emit({"status": "no-session"}, "(ccprophet: no session yet)", as_json=as_json)
        return 0

    parts = {
        "session_id": session.session_id.value[:8],
        "model": session.model,
        "input_tokens": session.total_input_tokens.value,
        "output_tokens": session.total_output_tokens.value,
    }

    # FR-10.3: cost column only when the user opts in via --cost.
    if with_cost and pricing is not None:
        try:
            rate = pricing.rate_for(session.model, session.started_at)
            breakdown = CostCalculator.session_cost(session, rate)
            parts["cost_usd"] = float(breakdown.total_cost.amount)
        except UnknownPricingModel:
            parts["cost_usd"] = None

    if tool_defs_for is not None and tool_calls_for is not None:
        loaded = list(tool_defs_for(session.session_id))
        called = list(tool_calls_for(session.session_id))
        if loaded:
            report = BloatCalculator.calculate(loaded, called)
            pct = report.bloat_ratio.as_percent()
            parts["bloat_pct"] = pct
            parts["bloat_level"] = _bloat_level(pct)
        else:
            parts["bloat_pct"] = None
            parts["bloat_level"] = "ok"

    _emit(parts, _format_line(parts), as_json=as_json)
    return 0


def _bloat_level(pct: float) -> str:
    if pct >= BLOAT_ALERT_PCT:
        return "alert"
    if pct >= BLOAT_WARN_PCT:
        return "warn"
    return "ok"


def _pick_latest_session(sessions: SessionRepository) -> Session | None:
    active = sessions.latest_active()
    if active is not None:
        return active
    recent = list(sessions.list_recent(limit=1))
    return recent[0] if recent else None


def _format_line(parts: dict) -> str:  # type: ignore[type-arg]
    sid = parts["session_id"]
    model = parts["model"]
    segs = [f"[{sid}] {model}"]
    in_tok = _fmt_tok(parts["input_tokens"])
    out_tok = _fmt_tok(parts["output_tokens"])
    segs.append(f"{in_tok}/{out_tok}")
    cost = parts.get("cost_usd")
    if cost is not None:
        segs.append(f"${cost:.2f}")
    bloat = parts.get("bloat_pct")
    if bloat is not None:
        badge = _bloat_badge(parts.get("bloat_level", "ok"))
        segs.append(f"{badge}bloat {bloat:.0f}%")
    return " | ".join(segs)


def _bloat_badge(level: str) -> str:
    # Plain ASCII glyphs keep the statusline readable under every terminal
    # encoding ccprophet supports (macOS, Linux, Windows cp949 / cp1252). A
    # trailing space separates the badge from the numeric percentage.
    if level == "alert":
        return "!! "
    if level == "warn":
        return "! "
    return ""


def _fmt_tok(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def _emit(parts: dict, line: str, *, as_json: bool) -> None:  # type: ignore[type-arg]
    if as_json:
        print(json_module.dumps(parts, default=str))
    else:
        print(line)
