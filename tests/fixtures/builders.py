from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from decimal import Decimal

from ccprophet.domain.entities import (
    Event,
    OutcomeLabel,
    Phase,
    PricingRate,
    Recommendation,
    Session,
    Subagent,
    SubsetProfile,
    ToolCall,
    ToolDef,
)
from ccprophet.domain.values import (
    Confidence,
    EventId,
    Money,
    OutcomeLabelValue,
    PhaseType,
    RawHash,
    RecommendationKind,
    SessionId,
    TaskType,
    TokenCount,
)


class SessionBuilder:
    def __init__(self) -> None:
        self._id = SessionId("test-session-001")
        self._project = "test-project"
        self._model = "claude-opus-4-6"
        self._started_at = datetime(2026, 4, 16, 9, 0, 0, tzinfo=timezone.utc)
        self._ended_at: datetime | None = None

    def with_id(self, sid: str) -> SessionBuilder:
        self._id = SessionId(sid)
        return self

    def ended(self, dt: datetime | None = None) -> SessionBuilder:
        self._ended_at = dt or datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc)
        return self

    def build(self) -> Session:
        return Session(
            session_id=self._id,
            project_slug=self._project,
            model=self._model,
            started_at=self._started_at,
            ended_at=self._ended_at,
        )


class ToolDefBuilder:
    def __init__(self) -> None:
        self._name = "Read"
        self._tokens = 1000
        self._source = "system"

    def named(self, name: str) -> ToolDefBuilder:
        self._name = name
        return self

    def with_tokens(self, t: int) -> ToolDefBuilder:
        self._tokens = t
        return self

    def from_source(self, s: str) -> ToolDefBuilder:
        self._source = s
        return self

    def build(self) -> ToolDef:
        return ToolDef(self._name, TokenCount(self._tokens), self._source)


class ToolCallBuilder:
    _counter = 0

    def __init__(self) -> None:
        ToolCallBuilder._counter += 1
        self._id = f"tc-{ToolCallBuilder._counter}"
        self._session = SessionId("test-session-001")
        self._tool = "Read"
        self._ts = datetime(2026, 4, 16, 9, 1, 0, tzinfo=timezone.utc)

    def in_session(self, sid: SessionId | str) -> ToolCallBuilder:
        self._session = SessionId(sid) if isinstance(sid, str) else sid
        return self

    def for_tool(self, name: str) -> ToolCallBuilder:
        self._tool = name
        return self

    def at(self, ts: datetime) -> ToolCallBuilder:
        self._ts = ts
        return self

    def build(self) -> ToolCall:
        return ToolCall(
            tool_call_id=self._id,
            session_id=self._session,
            tool_name=self._tool,
            input_hash="abc123",
            ts=self._ts,
        )


class EventBuilder:
    _counter = 0

    def __init__(self) -> None:
        EventBuilder._counter += 1
        self._id = EventId(f"evt-{EventBuilder._counter}")
        self._session = SessionId("test-session-001")
        self._type = "PostToolUse"
        self._ts = datetime(2026, 4, 16, 9, 1, 0, tzinfo=timezone.utc)
        self._payload: dict[str, object] = {}
        self._hash = RawHash(f"hash-{EventBuilder._counter}")

    def for_session(self, sid: str) -> EventBuilder:
        self._session = SessionId(sid)
        return self

    def of_type(self, t: str) -> EventBuilder:
        self._type = t
        return self

    def at(self, ts: datetime) -> EventBuilder:
        self._ts = ts
        return self

    def with_hash(self, h: str) -> EventBuilder:
        self._hash = RawHash(h)
        return self

    def with_payload(self, payload: dict[str, object]) -> EventBuilder:
        self._payload = payload
        return self

    def tool_use(self, tool_name: str, file_path: str | None = None) -> EventBuilder:
        self._type = "PostToolUse"
        payload: dict[str, object] = {"tool_name": tool_name}
        if file_path is not None:
            payload["tool_input"] = {"file_path": file_path}
        self._payload = payload
        return self

    def build(self) -> Event:
        return Event(
            event_id=self._id,
            session_id=self._session,
            event_type=self._type,
            ts=self._ts,
            payload=self._payload,
            raw_hash=self._hash,
        )


class PhaseBuilder:
    _counter = 0

    def __init__(self) -> None:
        PhaseBuilder._counter += 1
        self._id = f"phase-{PhaseBuilder._counter}"
        self._session = SessionId("test-session-001")
        self._type = PhaseType.PLANNING
        self._start = datetime(2026, 4, 16, 9, 0, 0, tzinfo=timezone.utc)
        self._end: datetime | None = datetime(2026, 4, 16, 9, 5, 0, tzinfo=timezone.utc)

    def of_type(self, t: PhaseType) -> PhaseBuilder:
        self._type = t
        return self

    def in_session(self, sid: str) -> PhaseBuilder:
        self._session = SessionId(sid)
        return self

    def build(self) -> Phase:
        return Phase(
            phase_id=self._id,
            session_id=self._session,
            phase_type=self._type,
            start_ts=self._start,
            end_ts=self._end,
        )


class RecommendationBuilder:
    _counter = 0

    def __init__(self) -> None:
        RecommendationBuilder._counter += 1
        self._id = f"rec-{RecommendationBuilder._counter}"
        self._session = SessionId("test-session-001")
        self._kind = RecommendationKind.PRUNE_MCP
        self._target: str | None = "mcp__github"
        self._tokens = 1400
        self._usd = Decimal("0.021")
        self._confidence = 0.85
        self._rationale = "최근 30일 0회 사용, 1.4k 토큰 절감"
        self._created = datetime(2026, 4, 17, 9, 0, 0, tzinfo=timezone.utc)

    def in_session(self, sid: str) -> RecommendationBuilder:
        self._session = SessionId(sid)
        return self

    def kind(self, k: RecommendationKind) -> RecommendationBuilder:
        self._kind = k
        return self

    def target(self, t: str) -> RecommendationBuilder:
        self._target = t
        return self

    def build(self) -> Recommendation:
        return Recommendation(
            rec_id=self._id,
            session_id=self._session,
            kind=self._kind,
            target=self._target,
            est_savings_tokens=TokenCount(self._tokens),
            est_savings_usd=Money(self._usd),
            confidence=Confidence(self._confidence),
            rationale=self._rationale,
            created_at=self._created,
        )


class OutcomeLabelBuilder:
    def __init__(self) -> None:
        self._session = SessionId("test-session-001")
        self._label = OutcomeLabelValue.SUCCESS
        self._task: TaskType | None = TaskType("refactor")
        self._source = "manual"
        self._reason: str | None = None
        self._labeled_at = datetime(2026, 4, 17, 9, 0, 0, tzinfo=timezone.utc)

    def for_session(self, sid: str) -> OutcomeLabelBuilder:
        self._session = SessionId(sid)
        return self

    def with_label(self, label: OutcomeLabelValue) -> OutcomeLabelBuilder:
        self._label = label
        return self

    def with_task(self, task: str) -> OutcomeLabelBuilder:
        self._task = TaskType(task)
        return self

    def build(self) -> OutcomeLabel:
        return OutcomeLabel(
            session_id=self._session,
            label=self._label,
            task_type=self._task,
            source=self._source,
            reason=self._reason,
            labeled_at=self._labeled_at,
        )


class PricingRateBuilder:
    _counter = 0

    def __init__(self) -> None:
        PricingRateBuilder._counter += 1
        self._id = f"rate-{PricingRateBuilder._counter}"
        self._model = "claude-opus-4-7"
        self._in_rate = 15.0
        self._out_rate = 75.0
        self._effective = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def for_model(self, model: str) -> PricingRateBuilder:
        self._model = model
        return self

    def effective_at(self, dt: datetime) -> PricingRateBuilder:
        self._effective = dt
        return self

    def build(self) -> PricingRate:
        return PricingRate(
            rate_id=self._id,
            model=self._model,
            input_per_mtok=self._in_rate,
            output_per_mtok=self._out_rate,
            effective_at=self._effective,
            source="test",
        )


class SubagentBuilder:
    _counter = 0

    def __init__(self) -> None:
        SubagentBuilder._counter += 1
        n = SubagentBuilder._counter
        self._subagent_id = SessionId(f"sub-{n}")
        self._parent = SessionId("test-session-001")
        self._started_at = datetime(2026, 4, 17, 9, 0, 0, tzinfo=timezone.utc)
        self._agent_type: str | None = "Task"
        self._ended_at: datetime | None = None
        self._context_tokens = 0
        self._tool_call_count = 0

    def with_id(self, sid: str) -> SubagentBuilder:
        self._subagent_id = SessionId(sid)
        return self

    def with_parent(self, parent: str) -> SubagentBuilder:
        self._parent = SessionId(parent)
        return self

    def started(self, ts: datetime) -> SubagentBuilder:
        self._started_at = ts
        return self

    def ended(self, ts: datetime) -> SubagentBuilder:
        self._ended_at = ts
        return self

    def with_tool_calls(self, n: int) -> SubagentBuilder:
        self._tool_call_count = n
        return self

    def build(self) -> Subagent:
        return Subagent(
            subagent_id=self._subagent_id,
            parent_session_id=self._parent,
            started_at=self._started_at,
            agent_type=self._agent_type,
            ended_at=self._ended_at,
            context_tokens=TokenCount(self._context_tokens),
            tool_call_count=self._tool_call_count,
        )


class SubsetProfileBuilder:
    _counter = 0

    def __init__(self) -> None:
        SubsetProfileBuilder._counter += 1
        self._id = f"prof-{SubsetProfileBuilder._counter}"
        self._name = f"profile-{SubsetProfileBuilder._counter}"
        self._task: TaskType | None = TaskType("refactor")
        self._created = datetime(2026, 4, 17, tzinfo=timezone.utc)
        self._content: dict[str, object] = {"enabled_tools": ["Read", "Edit"]}

    def named(self, name: str) -> SubsetProfileBuilder:
        self._name = name
        return self

    def with_content(self, content: dict[str, object]) -> SubsetProfileBuilder:
        self._content = content
        return self

    def build(self) -> SubsetProfile:
        return SubsetProfile(
            profile_id=self._id,
            name=self._name,
            task_type=self._task,
            content=self._content,
            created_at=self._created,
            derived_from="manual",
        )
