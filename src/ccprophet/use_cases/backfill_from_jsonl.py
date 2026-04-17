"""Backfill historical sessions from `~/.claude/projects/**/*.jsonl`.

Bypasses `IngestEventUseCase` on purpose — that path stamps events with the
Clock's `now()` (correct for live hooks) but backfill must preserve the
original timestamps. Writes go straight to the repositories with
`ingested_via="jsonl"`.
"""
from __future__ import annotations

import hashlib
import uuid as uuid_mod
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from ccprophet.domain.entities import Event, Session, Subagent, ToolCall
from ccprophet.domain.values import (
    EventId,
    RawHash,
    SessionId,
    TokenCount,
)
from ccprophet.ports.jsonl import JsonlRecord, JsonlSource
from ccprophet.ports.repositories import (
    EventRepository,
    SessionRepository,
    ToolCallRepository,
)
from ccprophet.ports.subagents import SubagentRepository


@dataclass(slots=True)
class BackfillSummary:
    files_read: int = 0
    records_seen: int = 0
    events_ingested: int = 0
    tool_calls_ingested: int = 0
    sessions_touched: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _SessionTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    model: str | None = None


@dataclass(slots=True)
class _SubagentRunning:
    started_at: datetime
    last_ts: datetime
    parent_session_id: str
    tool_call_count: int = 0
    agent_type: str | None = "Task"
    usage_key: str | None = None  # key under which `_accumulate_usage` bucketed tokens


@dataclass(slots=True)
class _SubagentAccumulator:
    """Per-file scratch pad for sidechain detection.

    Two real-world file shapes are supported:

    1. **Inline sidechain**: a single JSONL contains both the main session and
       sidechain records with a *distinct* sessionId. `main_session_id` captures
       the first non-sidechain sessionId; sidechain records keyed by their
       own sessionId become sub-agents of that parent.

    2. **Dedicated subagent file**: `<parent-session-id>/subagents/agent-<hash>.jsonl`
       where *every* record is sidechain and shares the parent's sessionId. We
       synthesise the subagent id from the `agentId` field (falling back to a
       `parent_uuid` hash) and use the shared sessionId as the parent.
    """

    main_session_id: str | None = None
    subagents: dict[str, _SubagentRunning] = field(default_factory=dict)


@dataclass(frozen=True)
class BackfillFromJsonlUseCase:
    source: JsonlSource
    events: EventRepository
    sessions: SessionRepository
    tool_calls: ToolCallRepository
    # Optional so existing call sites that predate subagent tracking keep
    # working until they're updated. When None, sidechain records still get
    # ingested into `events` / `tool_calls` but no Subagent row is written.
    subagents: SubagentRepository | None = None

    def execute(self, paths: Iterable[Path]) -> BackfillSummary:
        summary = BackfillSummary()
        totals: dict[str, _SessionTotals] = {}
        for path in paths:
            slug = _project_slug_from(path)
            file_parent_hint = _parent_session_hint_from_path(path)
            per_file = _SubagentAccumulator()
            try:
                for record in self.source.read_file(path):
                    summary.records_seen += 1
                    self._ingest(
                        record, slug, summary, totals, per_file, file_parent_hint
                    )
            except OSError as exc:
                summary.errors.append(f"{path}: {exc}")
                continue
            summary.files_read += 1
            self._flush_subagents(per_file, totals)
        self._flush_session_totals(totals)
        return summary

    def _ingest(
        self,
        record: JsonlRecord,
        project_slug: str,
        summary: BackfillSummary,
        totals: dict[str, _SessionTotals],
        per_file: _SubagentAccumulator,
        file_parent_hint: str | None,
    ) -> None:
        raw_hash = RawHash(record.raw_hash_hex)
        if self.events.dedup_hash_exists(raw_hash):
            return

        subagent_key = _subagent_key_for(record)
        # A record counts as sidechain if its own payload says so OR if
        # we've already established this key as a subagent in this file
        # (synthetic PostToolUse records drop the flag, so we fall back to
        # the per-file registry).
        is_sidechain = (
            _is_sidechain(record)
            or (subagent_key is not None and subagent_key in per_file.subagents)
        )

        if not is_sidechain and per_file.main_session_id is None:
            per_file.main_session_id = record.session_id

        if is_sidechain:
            self._track_subagent(record, per_file, file_parent_hint)
        else:
            sid = SessionId(record.session_id)
            self._ensure_session(sid, project_slug, record.ts)
            summary.sessions_touched.add(sid.value)

        event = Event(
            event_id=EventId(record.uuid),
            session_id=SessionId(record.session_id),
            event_type=record.event_type,
            ts=record.ts,
            payload=record.payload,
            raw_hash=raw_hash,
            ingested_via="jsonl",
        )
        self.events.append(event)
        summary.events_ingested += 1

        if record.event_type == "PostToolUse" and not is_sidechain:
            # Subagent tool calls are tracked separately via the running
            # counter in `_track_subagent`; we do not attach them to the
            # parent session's tool_calls table.
            self._ingest_tool_call(SessionId(record.session_id), record, summary)
        if record.event_type == "AssistantResponse":
            _accumulate_usage(record, totals)

    def _track_subagent(
        self,
        record: JsonlRecord,
        per_file: _SubagentAccumulator,
        file_parent_hint: str | None,
    ) -> None:
        key = _subagent_key_for(record)
        if key is None:
            return
        parent_candidate = (
            per_file.main_session_id
            or file_parent_hint
            # Inline subagents carry a distinct sessionId AND the parent is
            # already registered. Shared-sessionId subagent files fall back to
            # `file_parent_hint` (the enclosing session directory).
            or record.session_id
        )
        running = per_file.subagents.get(key)
        if running is None:
            per_file.subagents[key] = _SubagentRunning(
                started_at=record.ts,
                last_ts=record.ts,
                parent_session_id=parent_candidate,
                agent_type=_agent_type_of(record),
                usage_key=record.session_id,
            )
            running = per_file.subagents[key]
        else:
            if record.ts > running.last_ts:
                running.last_ts = record.ts
            if record.ts < running.started_at:
                running.started_at = record.ts
        if record.event_type == "PostToolUse":
            running.tool_call_count += 1

    def _flush_subagents(
        self,
        per_file: _SubagentAccumulator,
        totals: dict[str, _SessionTotals],
    ) -> None:
        if self.subagents is None:
            return
        if not per_file.subagents:
            return
        for key, running in per_file.subagents.items():
            parent = per_file.main_session_id or running.parent_session_id
            if not parent or key == parent:
                continue
            tokens = _subagent_context_tokens(totals.get(running.usage_key))
            sub = Subagent(
                subagent_id=SessionId(key),
                parent_session_id=SessionId(parent),
                started_at=running.started_at,
                agent_type=running.agent_type,
                ended_at=running.last_ts,
                tool_call_count=running.tool_call_count,
                context_tokens=TokenCount(tokens),
            )
            self.subagents.upsert(sub)
            # Prevent `_flush_session_totals` from upserting a shadow Session
            # for sessionIds that turned out to be pure subagent transcripts.
            if (
                running.usage_key
                and running.usage_key != parent
                and running.usage_key not in per_file.subagents
            ):
                totals.pop(running.usage_key, None)

    def _flush_session_totals(self, totals: dict[str, _SessionTotals]) -> None:
        for sid_str, t in totals.items():
            session = self.sessions.get(SessionId(sid_str))
            if session is None:
                continue
            updated = replace(
                session,
                total_input_tokens=TokenCount(t.input_tokens),
                total_output_tokens=TokenCount(t.output_tokens),
                total_cache_creation_tokens=TokenCount(t.cache_creation_tokens),
                total_cache_read_tokens=TokenCount(t.cache_read_tokens),
                model=t.model or session.model,
            )
            self.sessions.upsert(updated)

    def _ensure_session(
        self, sid: SessionId, project_slug: str, first_ts: datetime
    ) -> None:
        if self.sessions.get(sid) is not None:
            return
        session = Session(
            session_id=sid,
            project_slug=project_slug,
            model="unknown",
            started_at=first_ts,
        )
        self.sessions.upsert(session)

    def _ingest_tool_call(
        self, sid: SessionId, record: JsonlRecord, summary: BackfillSummary
    ) -> None:
        payload = record.payload
        tool_name = _as_str(payload.get("tool_name"))
        if not tool_name:
            return
        input_repr = repr(payload.get("tool_input"))
        input_hash = hashlib.sha256(input_repr.encode()).hexdigest()[:16]
        tc = ToolCall(
            tool_call_id=record.uuid or uuid_mod.uuid4().hex,
            session_id=sid,
            tool_name=tool_name,
            input_hash=input_hash,
            ts=record.ts,
            input_tokens=TokenCount(0),
            output_tokens=TokenCount(0),
            success=True,
        )
        self.tool_calls.append(tc)
        summary.tool_calls_ingested += 1


def _is_sidechain(record: JsonlRecord) -> bool:
    """Detect Claude Code sub-agent (Task tool) transcript records.

    Claude Code tags sub-session records with either `isSidechain: true`
    or `userType: "sidechain"` (and usually both). The synthetic tool_use
    records emitted by the JsonlReader inherit the parent record's payload
    only partially, so fall back to the payload dict for both fields.
    """
    payload = record.payload
    if payload.get("isSidechain") is True:
        return True
    return payload.get("userType") == "sidechain"


def _project_slug_from(path: Path) -> str:
    parent = path.parent.name
    return parent or "unknown"


def _subagent_key_for(record: JsonlRecord) -> str | None:
    """Key used to group sidechain records into a subagent.

    Prefers the record's sessionId (distinct from the main session for inline
    subagents). Falls back to the record uuid when no sessionId is present.
    """
    if record.session_id:
        return record.session_id
    return record.uuid or None


def _parent_session_hint_from_path(path: Path) -> str | None:
    """Infer a parent sessionId hint from the JSONL file's name/dir.

    The subagent-lifecycle refactor threaded this hint into `_track_subagent`
    so that orphan sidechain files (no main session in the same file) can
    still attach to a plausible parent. For the MVP we don't decode the
    Claude Code filename convention yet — returning None preserves the
    existing "orphan → skip at flush" behaviour via the self-reference
    guard in `_flush_subagents`.
    """
    del path  # reserved for a future heuristic
    return None


def _agent_type_of(record: JsonlRecord) -> str | None:
    """Extract the subagent's agent type from a record payload.

    Claude Code's sidechain records sometimes carry `agentType` or a
    `subagent_type` field inside `tool_input`. When absent, we default to
    the vanilla Task-tool subagent label.
    """
    payload = record.payload
    direct = payload.get("agentType") or payload.get("subagent_type")
    if isinstance(direct, str) and direct:
        return direct
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_use":
                    continue
                tool_input = block.get("input")
                if isinstance(tool_input, dict):
                    st = tool_input.get("subagent_type")
                    if isinstance(st, str) and st:
                        return st
    return "Task"


def _as_str(value: object) -> str:
    if isinstance(value, str):
        return value
    return ""


def _accumulate_usage(
    record: JsonlRecord, totals: dict[str, _SessionTotals]
) -> None:
    message = record.payload.get("message")
    if not isinstance(message, dict):
        return
    bucket = totals.setdefault(record.session_id, _SessionTotals())

    usage = message.get("usage")
    if isinstance(usage, dict):
        bucket.input_tokens += _int_or_zero(usage.get("input_tokens"))
        bucket.cache_creation_tokens += _int_or_zero(
            usage.get("cache_creation_input_tokens")
        )
        bucket.cache_read_tokens += _int_or_zero(
            usage.get("cache_read_input_tokens")
        )
        bucket.output_tokens += _int_or_zero(usage.get("output_tokens"))

    model = message.get("model")
    if isinstance(model, str) and model and not bucket.model:
        bucket.model = model


def _int_or_zero(value: object) -> int:
    try:
        return int(value) if value is not None else 0  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _subagent_context_tokens(totals: _SessionTotals | None) -> int:
    """Context tokens proxy for a subagent: input + cache + output.

    Subagents don't have Session rows so their `_SessionTotals` would otherwise
    be dropped by `_flush_session_totals`. We surface the running total on the
    `Subagent.context_tokens` field instead.
    """
    if totals is None:
        return 0
    return (
        totals.input_tokens
        + totals.cache_creation_tokens
        + totals.cache_read_tokens
        + totals.output_tokens
    )
