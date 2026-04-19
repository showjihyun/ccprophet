"""Consolidated view of token-reduction settings and their dollar impact.

Three buckets:
- `applied`: recommendations already accepted (`status=applied`) + env vars currently
  set in the user's `.claude/settings.json` env block or process environment.
- `pending`: recommendations the user hasn't applied yet (`status=pending`).
- `opportunities`: known-good knobs that are not yet set AND not yet recommended,
  surfaced as suggestions with community-validated typical savings ranges.

This is a pure read-only dashboard — no state is mutated.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from ccprophet.domain.entities import Recommendation
from ccprophet.domain.values import Money, RecommendationKind
from ccprophet.ports.clock import Clock
from ccprophet.ports.recommendations import RecommendationRepository
from ccprophet.ports.settings import SettingsStore

# Known env-var knobs with community-reported typical savings.
KNOWN_ENV_VARS: tuple[tuple[str, str, str], ...] = (
    ("MAX_THINKING_TOKENS", "10000", "caps extended thinking; ~30-40% per session"),
    ("CLAUDE_CODE_SUBAGENT_MODEL", "haiku", "Haiku for subagents; ~80% cheaper"),
    ("MAX_MCP_OUTPUT_TOKENS", "15000", "caps per-call MCP output"),
)


@dataclass(frozen=True, slots=True)
class ActiveEnvVar:
    name: str
    value: str
    source: str  # "process" | "settings.json"


@dataclass(frozen=True, slots=True)
class OpportunityEnvVar:
    name: str
    suggested_value: str
    note: str


@dataclass(frozen=True, slots=True)
class SavingsSummary:
    window_start: datetime
    window_end: datetime
    applied_count: int
    applied_total: Money
    pending_count: int
    pending_total: Money
    active_env_vars: tuple[ActiveEnvVar, ...]
    opportunity_env_vars: tuple[OpportunityEnvVar, ...]
    applied_items: tuple[Recommendation, ...] = field(default_factory=tuple)
    pending_items: tuple[Recommendation, ...] = field(default_factory=tuple)

    @property
    def total_potential(self) -> Money:
        return self.applied_total + self.pending_total


@dataclass(frozen=True)
class ComputeSavingsUseCase:
    recommendations: RecommendationRepository
    settings: SettingsStore
    clock: Clock
    settings_path: Path

    def execute(self, *, window_days: int = 30, currency: str = "USD") -> SavingsSummary:
        now = self.clock.now()
        start = now - timedelta(days=window_days)
        # +1s buffer so a rec marked applied in the same clock tick as
        # `execute()` still lands inside the range (range is half-open).
        applied = list(
            self.recommendations.list_applied_in_range(start, now + timedelta(seconds=1))
        )
        pending = list(self.recommendations.list_pending(limit=100))

        applied_total = _sum_usd(applied, currency)
        pending_total = _sum_usd(pending, currency)

        active = _collect_active_env_vars(self.settings, self.settings_path)
        opportunities = _compute_opportunities(active, pending)

        return SavingsSummary(
            window_start=start,
            window_end=now,
            applied_count=len(applied),
            applied_total=applied_total,
            pending_count=len(pending),
            pending_total=pending_total,
            active_env_vars=active,
            opportunity_env_vars=opportunities,
            applied_items=tuple(applied),
            pending_items=tuple(pending),
        )


def _sum_usd(recs: Sequence[Recommendation], currency: str) -> Money:
    total = Money.zero(currency)
    for r in recs:
        if r.est_savings_usd.currency == currency:
            total = total + r.est_savings_usd
    return total


def _collect_active_env_vars(
    settings: SettingsStore, settings_path: Path
) -> tuple[ActiveEnvVar, ...]:
    rows: list[ActiveEnvVar] = []
    known_names = [name for name, _, _ in KNOWN_ENV_VARS]

    # settings.json env block takes precedence since it's project-scoped.
    try:
        if settings_path.exists():
            doc = settings.read(settings_path)
            env_block = doc.content.get("env")
            if isinstance(env_block, dict):
                for name in known_names:
                    value = env_block.get(name)
                    if isinstance(value, str) and value:
                        rows.append(ActiveEnvVar(name=name, value=value, source="settings.json"))
    except (OSError, ValueError):
        pass

    seen = {r.name for r in rows}
    for name in known_names:
        if name in seen:
            continue
        value = os.environ.get(name)
        if value:
            rows.append(ActiveEnvVar(name=name, value=value, source="process"))

    return tuple(rows)


def _compute_opportunities(
    active: Sequence[ActiveEnvVar],
    pending: Sequence[Recommendation],
) -> tuple[OpportunityEnvVar, ...]:
    active_names = {a.name for a in active}
    pending_env_targets = {
        r.target.split("=", 1)[0]
        for r in pending
        if r.kind == RecommendationKind.SET_ENV_VAR and r.target and "=" in r.target
    }
    rows = []
    for name, suggested, note in KNOWN_ENV_VARS:
        if name in active_names:
            continue
        if name in pending_env_targets:
            continue  # already recommended, shown in pending section
        rows.append(OpportunityEnvVar(name=name, suggested_value=suggested, note=note))
    return tuple(rows)
