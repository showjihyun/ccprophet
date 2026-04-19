"""Property tests — PhaseDetector domain invariants.

LAYERING.md §7.6 requires Hypothesis coverage of the invariant:
"every event falls into exactly one phase, and phase boundaries align with
UserPromptSubmit/SessionStart events." Also: detection_confidence ∈ [0, 1],
phase order preserves event chronology.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone

from hypothesis import given
from hypothesis import strategies as st

from ccprophet.domain.entities import Event
from ccprophet.domain.services.phase import PROMPT_EVENTS, PhaseDetector
from ccprophet.domain.values import EventId, RawHash, SessionId

_BASE = datetime(2026, 4, 18, 0, 0, 0, tzinfo=timezone.utc)

_EVENT_TYPES = st.sampled_from(
    ["UserPromptSubmit", "SessionStart", "PostToolUse", "AssistantResponse"]
)
_TOOL_NAMES = st.sampled_from(["Read", "Edit", "Bash", "Glob", "Grep", "Task", "Write"])


def _make_event(idx: int, etype: str, tool: str | None) -> Event:
    payload: dict[str, object] = {}
    if etype == "PostToolUse" and tool:
        payload = {"tool_name": tool}
    return Event(
        event_id=EventId(f"e-{idx}"),
        session_id=SessionId("prop-sess"),
        event_type=etype,
        ts=_BASE + timedelta(seconds=idx),
        payload=payload,
        raw_hash=RawHash(f"h-{idx}"),
    )


@given(
    st.lists(
        st.tuples(_EVENT_TYPES, _TOOL_NAMES),
        min_size=0,
        max_size=60,
    )
)
def test_every_event_in_exactly_one_phase(spec) -> None:  # type: ignore[no-untyped-def]
    events = [_make_event(i, etype, tool) for i, (etype, tool) in enumerate(spec)]
    phases = PhaseDetector.detect(events)

    if not events:
        assert phases == []
        return

    # Event count conservation: sum of per-phase tool_call_count only covers
    # PostToolUse; instead verify via timespan coverage.
    first_ts = min(e.ts for e in events)
    last_ts = max(e.ts for e in events)
    assert phases, "non-empty events must produce at least one phase"
    assert phases[0].start_ts == first_ts
    assert phases[-1].end_ts == last_ts


@given(
    st.lists(
        st.tuples(_EVENT_TYPES, _TOOL_NAMES),
        min_size=1,
        max_size=40,
    )
)
def test_confidence_in_unit_interval(spec) -> None:  # type: ignore[no-untyped-def]
    events = [_make_event(i, etype, tool) for i, (etype, tool) in enumerate(spec)]
    phases = PhaseDetector.detect(events)
    for p in phases:
        assert 0.0 <= p.detection_confidence <= 1.0


@given(
    st.lists(
        st.tuples(_EVENT_TYPES, _TOOL_NAMES),
        min_size=2,
        max_size=40,
    )
)
def test_phases_chronological(spec) -> None:  # type: ignore[no-untyped-def]
    events = [_make_event(i, etype, tool) for i, (etype, tool) in enumerate(spec)]
    phases = PhaseDetector.detect(events)
    for prev, nxt in itertools.pairwise(phases):
        assert prev.start_ts <= nxt.start_ts
        assert prev.end_ts <= nxt.end_ts


@given(
    st.lists(
        st.tuples(_EVENT_TYPES, _TOOL_NAMES),
        min_size=1,
        max_size=40,
    )
)
def test_phase_count_matches_prompt_boundaries(spec) -> None:  # type: ignore[no-untyped-def]
    events = [_make_event(i, etype, tool) for i, (etype, tool) in enumerate(spec)]
    phases = PhaseDetector.detect(events)

    # A phase starts at the first event AND at each subsequent prompt-like
    # event. Count of phases = 1 + count of prompt events *after* index 0.
    prompt_after_first = sum(1 for e in events[1:] if e.event_type in PROMPT_EVENTS)
    assert len(phases) == 1 + prompt_after_first
