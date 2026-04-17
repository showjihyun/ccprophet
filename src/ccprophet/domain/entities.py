from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from ccprophet.domain.values import (
    BloatRatio,
    Confidence,
    EventId,
    FilePathHash,
    Money,
    OutcomeLabelValue,
    PhaseType,
    RawHash,
    RecommendationKind,
    RecommendationStatus,
    SessionId,
    SnapshotId,
    TaskType,
    TokenCount,
    ToolSource,
)


@dataclass(frozen=True, slots=True)
class Session:
    session_id: SessionId
    project_slug: str
    model: str
    started_at: datetime
    ended_at: datetime | None = None
    total_input_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    total_output_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    total_cache_creation_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    total_cache_read_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    compacted: bool = False
    compacted_at: datetime | None = None
    context_window_size: int = 200_000

    @property
    def is_active(self) -> bool:
        return self.ended_at is None


@dataclass(frozen=True, slots=True)
class Event:
    event_id: EventId
    session_id: SessionId
    event_type: str
    ts: datetime
    payload: dict[str, object]
    raw_hash: RawHash
    ingested_via: str = "hook"


@dataclass(frozen=True, slots=True)
class ToolCall:
    tool_call_id: str
    session_id: SessionId
    tool_name: str
    input_hash: str
    ts: datetime
    input_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    output_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    latency_ms: int = 0
    success: bool = True
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolDef:
    tool_name: str
    tokens: TokenCount
    source: str

    @property
    def source_type(self) -> ToolSource:
        return ToolSource.from_string(self.source)

    @property
    def source_group(self) -> str:
        if self.source.startswith("mcp:"):
            return self.source
        return self.source


@dataclass(frozen=True, slots=True)
class FileAccess:
    file_read_id: str
    session_id: SessionId
    file_path_hash: FilePathHash
    tokens: TokenCount
    ts: datetime
    referenced_in_output: bool = False


@dataclass(frozen=True, slots=True)
class Phase:
    phase_id: str
    session_id: SessionId
    phase_type: PhaseType
    start_ts: datetime
    end_ts: datetime | None = None
    input_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    output_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    tool_call_count: int = 0
    detection_confidence: float = 0.5


@dataclass(frozen=True, slots=True)
class Forecast:
    """Projected autocompact event for a session.

    `predicted_compact_at is None` means "no compact expected in the usable
    window" — either the session is flat/decreasing or we don't yet have
    enough samples to regress. See DATAMODELING.md §4.7.
    """

    forecast_id: str
    session_id: SessionId
    predicted_at: datetime
    predicted_compact_at: datetime | None
    confidence: float  # 0.0-1.0
    model_used: str  # 'linear_v1' | 'arima_v2' | ...
    input_token_rate: float  # tokens/sec at predicted_at
    context_usage_at_pred: float  # 0.0-1.0


@dataclass(frozen=True, slots=True)
class Subagent:
    """A Claude Code Task-tool-spawned sub-session.

    The `subagent_id` is the Claude-generated session id that the Task tool
    runs under — distinct from the parent session's id. `parent_session_id`
    points at the user-facing session that spawned it.
    """

    subagent_id: SessionId
    parent_session_id: SessionId
    started_at: datetime
    agent_type: str | None = None
    ended_at: datetime | None = None
    context_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    tool_call_count: int = 0
    returned_summary: str | None = None


@dataclass(frozen=True, slots=True)
class BloatItem:
    tool_name: str
    source: str
    tokens: TokenCount
    used: bool


@dataclass(frozen=True, slots=True)
class BloatReport:
    items: tuple[BloatItem, ...]
    total_tokens: TokenCount
    bloat_tokens: TokenCount
    bloat_ratio: BloatRatio
    used_sources: frozenset[str]

    @property
    def used_count(self) -> int:
        return sum(1 for i in self.items if i.used)

    @property
    def bloat_count(self) -> int:
        return sum(1 for i in self.items if not i.used)

    def by_source(self) -> dict[str, SourceBloatSummary]:
        groups: dict[str, list[BloatItem]] = {}
        for item in self.items:
            groups.setdefault(item.source, []).append(item)
        return {
            source: SourceBloatSummary.from_items(source, items)
            for source, items in groups.items()
        }


@dataclass(frozen=True, slots=True)
class SourceBloatSummary:
    source: str
    total_tokens: TokenCount
    bloat_tokens: TokenCount
    bloat_ratio: BloatRatio
    tool_count: int
    bloat_count: int

    @classmethod
    def from_items(cls, source: str, items: list[BloatItem]) -> SourceBloatSummary:
        total = sum(i.tokens.value for i in items)
        bloat = sum(i.tokens.value for i in items if not i.used)
        ratio = bloat / total if total > 0 else 0.0
        return cls(
            source=source,
            total_tokens=TokenCount(total),
            bloat_tokens=TokenCount(bloat),
            bloat_ratio=BloatRatio(ratio),
            tool_count=len(items),
            bloat_count=sum(1 for i in items if not i.used),
        )


@dataclass(frozen=True, slots=True)
class Recommendation:
    rec_id: str
    session_id: SessionId
    kind: RecommendationKind
    rationale: str
    confidence: Confidence
    created_at: datetime
    target: str | None = None
    est_savings_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    est_savings_usd: Money = field(default_factory=Money.zero)
    status: RecommendationStatus = RecommendationStatus.PENDING
    snapshot_id: SnapshotId | None = None
    provenance: str | None = None
    applied_at: datetime | None = None
    dismissed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SnapshotFileEntry:
    path: str
    sha256: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class Snapshot:
    snapshot_id: SnapshotId
    captured_at: datetime
    reason: str
    files: tuple[SnapshotFileEntry, ...]
    triggered_by: str | None = None
    byte_size: int = 0
    restored_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OutcomeLabel:
    session_id: SessionId
    label: OutcomeLabelValue
    source: str
    labeled_at: datetime
    task_type: TaskType | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class SubsetProfile:
    profile_id: str
    name: str
    content: dict[str, object]
    created_at: datetime
    task_type: TaskType | None = None
    derived_from: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PricingRate:
    rate_id: str
    model: str
    input_per_mtok: float
    output_per_mtok: float
    effective_at: datetime
    source: str
    cache_write_per_mtok: float = 0.0
    cache_read_per_mtok: float = 0.0
    currency: str = "USD"


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    session_id: SessionId
    model: str
    input_cost: Money
    output_cost: Money
    cache_cost: Money
    total_cost: Money
    rate_id: str


@dataclass(frozen=True, slots=True)
class ModelCostSummary:
    model: str
    session_count: int
    total_input_tokens: TokenCount
    total_output_tokens: TokenCount
    total_cost: Money


@dataclass(frozen=True, slots=True)
class MonthlyCostSummary:
    month_start: datetime
    month_end: datetime
    session_count: int
    total_cost: Money
    realized_savings: Money
    by_model: tuple[ModelCostSummary, ...]

    @property
    def avg_session_cost(self) -> Money:
        if self.session_count == 0:
            return Money.zero(self.total_cost.currency)
        amount = self.total_cost.amount / self.session_count
        return Money(amount, self.total_cost.currency)


@dataclass(frozen=True, slots=True)
class DailyQualityPoint:
    """Per-day aggregate of quality signals for a single model."""

    day: date
    model: str
    sample_size: int
    avg_output_tokens: float
    avg_tool_calls: float
    tool_call_success_rate: float
    autocompact_rate: float
    outcome_fail_rate: float | None
    repeat_read_rate: float
    avg_input_output_ratio: float


@dataclass(frozen=True, slots=True)
class QualitySeries:
    model: str
    points: tuple[DailyQualityPoint, ...]


@dataclass(frozen=True, slots=True)
class RegressionFlag:
    metric_name: str
    baseline_mean: float
    recent_mean: float
    baseline_stddev: float
    z_score: float
    direction: str  # 'degraded' | 'improved' | 'stable'
    explanation: str


@dataclass(frozen=True, slots=True)
class RegressionReport:
    model: str
    window_days: int
    baseline_days: int
    window_sample_size: int
    baseline_sample_size: int
    flags: tuple[RegressionFlag, ...]
    series: QualitySeries

    @property
    def has_regression(self) -> bool:
        return any(f.direction == "degraded" for f in self.flags)


@dataclass(frozen=True, slots=True)
class SessionDiff:
    session_a_id: SessionId
    session_b_id: SessionId
    input_tokens_delta: int
    output_tokens_delta: int
    tool_call_count_delta: int
    bloat_ratio_delta: float
    compacted_delta: int
    tools_added: tuple[str, ...]
    tools_removed: tuple[str, ...]
    mcps_added: tuple[str, ...]
    mcps_removed: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PostmortemFinding:
    kind: str
    detail: str


@dataclass(frozen=True, slots=True)
class PostmortemReport:
    failed_session_id: SessionId
    task_type: TaskType | None
    sample_size: int
    findings: tuple[PostmortemFinding, ...]
    suggestions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BestConfig:
    """Distilled "what worked" configuration from a success-labelled cluster."""

    task_type: TaskType
    cluster_size: int
    sample_session_ids: tuple[SessionId, ...]
    common_tools: tuple[str, ...]
    dropped_mcps: tuple[str, ...]
    avg_input_tokens: TokenCount
    avg_output_tokens: TokenCount
    autocompact_hit_rate: float


@dataclass(frozen=True, slots=True)
class BudgetEnvelope:
    """Pre-flight token/cost envelope for a given task type."""

    task_type: TaskType
    sample_size: int
    estimated_input_tokens_mean: TokenCount
    estimated_input_tokens_stddev: int
    estimated_output_tokens_mean: TokenCount
    estimated_cost: Money
    best_config: BestConfig
    risk_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SettingsDoc:
    """Parsed settings.json / .mcp.json along with the SHA256 of its source bytes.

    `content` is the parsed JSON mapping; `sha256` anchors concurrent-edit detection
    — if the file hash at write time differs, Auto-Fix aborts (see AP-7).
    """

    path: str
    content: dict[str, object]
    sha256: str


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """Aggregate-only snapshot of a session for long-term retention.

    Produced by the rollup use case before hot-table rows are pruned; contains
    everything needed to answer "was this session bloated?" without the
    per-event detail. See DATAMODELING.md §6.2.
    """

    session_id: SessionId
    project_slug: str
    model: str
    started_at: datetime
    summarized_at: datetime
    ended_at: datetime | None = None
    total_input_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    total_output_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    total_cache_creation_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    total_cache_read_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    compacted: bool = False
    tool_call_count: int = 0
    unique_tools_used: int = 0
    loaded_tool_def_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    bloat_tokens: TokenCount = field(default_factory=lambda: TokenCount(0))
    bloat_ratio: BloatRatio = field(default_factory=lambda: BloatRatio(0.0))
    file_read_count: int = 0
    phase_count: int = 0
    source_rows_deleted: bool = False
