from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, replace
from datetime import datetime

from ccprophet.domain.entities import Event, Session, ToolCall
from ccprophet.domain.values import EventId, RawHash, SessionId, TokenCount, int_or_zero
from ccprophet.ports.clock import Clock
from ccprophet.ports.repositories import (
    EventRepository,
    SessionRepository,
    ToolCallRepository,
)


@dataclass(frozen=True)
class IngestEventUseCase:
    events: EventRepository
    sessions: SessionRepository
    tool_calls: ToolCallRepository
    clock: Clock

    def execute(self, event_type: str, payload: dict[str, object]) -> None:
        raw_json = str(sorted(payload.items()))
        raw_hash = RawHash(hashlib.sha256(raw_json.encode()).hexdigest())

        if self.events.dedup_hash_exists(raw_hash):
            return

        session_id_str = str(payload.get("session_id", ""))
        if not session_id_str:
            return

        sid = SessionId(session_id_str)
        now = self.clock.now()

        self._ensure_session(sid, payload, now)

        event = Event(
            event_id=EventId(uuid.uuid4().hex),
            session_id=sid,
            event_type=event_type,
            ts=now,
            payload=payload,
            raw_hash=raw_hash,
            ingested_via="hook",
        )
        self.events.append(event)

        if event_type == "PostToolUse":
            self._ingest_tool_call(sid, payload, now)

        self._accumulate_usage(sid, payload)

    def _ensure_session(self, sid: SessionId, payload: dict[str, object], now: datetime) -> None:
        existing = self.sessions.get(sid)
        if existing is None:
            session = Session(
                session_id=sid,
                project_slug=str(payload.get("project_slug", "unknown")),
                model=str(payload.get("model", "unknown")),
                started_at=now,
            )
            self.sessions.upsert(session)

    def _ingest_tool_call(self, sid: SessionId, payload: dict[str, object], now: datetime) -> None:
        tool_name = str(payload.get("tool_name", "unknown"))
        input_hash_raw = str(payload.get("tool_input", ""))
        input_hash = hashlib.sha256(input_hash_raw.encode()).hexdigest()[:16]

        tc = ToolCall(
            tool_call_id=uuid.uuid4().hex,
            session_id=sid,
            tool_name=tool_name,
            input_hash=input_hash,
            ts=now,
            input_tokens=TokenCount(int_or_zero(payload.get("input_tokens"))),
            output_tokens=TokenCount(int_or_zero(payload.get("output_tokens"))),
            latency_ms=int_or_zero(payload.get("latency_ms")),
            success=bool(payload.get("success", True)),
        )
        self.tool_calls.append(tc)

    def _accumulate_usage(self, sid: SessionId, payload: dict[str, object]) -> None:
        usage, model = _extract_usage_and_model(payload)
        if usage is None and not model:
            return

        session = self.sessions.get(sid)
        if session is None:
            return

        added_input = 0
        added_output = 0
        added_cache_creation = 0
        added_cache_read = 0
        if usage is not None:
            added_input = int_or_zero(usage.get("input_tokens"))
            added_output = int_or_zero(usage.get("output_tokens"))
            added_cache_creation = int_or_zero(usage.get("cache_creation_input_tokens"))
            added_cache_read = int_or_zero(usage.get("cache_read_input_tokens"))

        new_model = session.model
        if session.model == "unknown" and model:
            new_model = model

        if (
            added_input == 0
            and added_output == 0
            and added_cache_creation == 0
            and added_cache_read == 0
            and new_model == session.model
        ):
            return

        updated = replace(
            session,
            total_input_tokens=TokenCount(session.total_input_tokens.value + added_input),
            total_output_tokens=TokenCount(session.total_output_tokens.value + added_output),
            total_cache_creation_tokens=TokenCount(
                session.total_cache_creation_tokens.value + added_cache_creation
            ),
            total_cache_read_tokens=TokenCount(
                session.total_cache_read_tokens.value + added_cache_read
            ),
            model=new_model,
        )
        self.sessions.upsert(updated)


def _extract_usage_and_model(
    payload: dict[str, object],
) -> tuple[dict[str, object] | None, str]:
    """Pull usage+model from either top-level keys or nested `message` dict."""
    usage: dict[str, object] | None = None
    top_usage = payload.get("usage")
    if isinstance(top_usage, dict):
        usage = top_usage

    model = ""
    top_model = payload.get("model")
    if isinstance(top_model, str) and top_model:
        model = top_model

    message = payload.get("message")
    if isinstance(message, dict):
        if usage is None:
            nested_usage = message.get("usage")
            if isinstance(nested_usage, dict):
                usage = nested_usage
        if not model:
            nested_model = message.get("model")
            if isinstance(nested_model, str) and nested_model:
                model = nested_model

    return usage, model
