from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ccprophet.domain.services.phase import PhaseDetector
from ccprophet.domain.values import PhaseType
from tests.fixtures.builders import EventBuilder

T0 = datetime(2026, 4, 17, 9, 0, 0, tzinfo=timezone.utc)


def _at(minute: int) -> datetime:
    return T0 + timedelta(minutes=minute)


def test_empty_events_produces_no_phases() -> None:
    assert PhaseDetector.detect([]) == []


def test_single_prompt_no_tools_is_planning_low_confidence() -> None:
    events = [
        EventBuilder().of_type("UserPromptSubmit").at(_at(0)).with_hash("h1").build(),
    ]
    phases = PhaseDetector.detect(events)
    assert len(phases) == 1
    assert phases[0].phase_type == PhaseType.PLANNING
    assert phases[0].tool_call_count == 0


def test_implementation_when_edit_ratio_over_30pct() -> None:
    events = [
        EventBuilder().of_type("UserPromptSubmit").at(_at(0)).with_hash("h1").build(),
        EventBuilder().tool_use("Read", "/a.py").at(_at(1)).with_hash("h2").build(),
        EventBuilder().tool_use("Edit", "/a.py").at(_at(2)).with_hash("h3").build(),
        EventBuilder().tool_use("Write", "/b.py").at(_at(3)).with_hash("h4").build(),
    ]
    phases = PhaseDetector.detect(events)
    assert len(phases) == 1
    assert phases[0].phase_type == PhaseType.IMPLEMENTATION
    assert phases[0].tool_call_count == 3


def test_debugging_when_repeat_read_and_bash() -> None:
    events = [
        EventBuilder().of_type("UserPromptSubmit").at(_at(0)).with_hash("h1").build(),
        EventBuilder().tool_use("Read", "/x.py").at(_at(1)).with_hash("h2").build(),
        EventBuilder().tool_use("Bash").at(_at(2)).with_hash("h3").build(),
        EventBuilder().tool_use("Read", "/x.py").at(_at(3)).with_hash("h4").build(),
    ]
    phases = PhaseDetector.detect(events)
    assert phases[0].phase_type == PhaseType.DEBUGGING


def test_review_when_read_only() -> None:
    events = [
        EventBuilder().of_type("UserPromptSubmit").at(_at(0)).with_hash("h1").build(),
        EventBuilder().tool_use("Read", "/a.py").at(_at(1)).with_hash("h2").build(),
        EventBuilder().tool_use("Grep").at(_at(2)).with_hash("h3").build(),
    ]
    phases = PhaseDetector.detect(events)
    assert phases[0].phase_type == PhaseType.REVIEW


def test_planning_when_task_tool_used() -> None:
    events = [
        EventBuilder().of_type("UserPromptSubmit").at(_at(0)).with_hash("h1").build(),
        EventBuilder().tool_use("Task").at(_at(1)).with_hash("h2").build(),
    ]
    phases = PhaseDetector.detect(events)
    assert phases[0].phase_type == PhaseType.PLANNING


def test_multiple_prompts_produce_multiple_phases() -> None:
    events = [
        EventBuilder().of_type("UserPromptSubmit").at(_at(0)).with_hash("h1").build(),
        EventBuilder().tool_use("Edit", "/a.py").at(_at(1)).with_hash("h2").build(),
        EventBuilder().tool_use("Edit", "/b.py").at(_at(2)).with_hash("h3").build(),
        EventBuilder().of_type("UserPromptSubmit").at(_at(5)).with_hash("h4").build(),
        EventBuilder().tool_use("Read", "/a.py").at(_at(6)).with_hash("h5").build(),
    ]
    phases = PhaseDetector.detect(events)
    assert len(phases) == 2
    assert phases[0].phase_type == PhaseType.IMPLEMENTATION
    assert phases[1].phase_type == PhaseType.REVIEW


def test_events_sorted_before_detection() -> None:
    events = [
        EventBuilder().tool_use("Edit", "/a.py").at(_at(2)).with_hash("h3").build(),
        EventBuilder().of_type("UserPromptSubmit").at(_at(0)).with_hash("h1").build(),
        EventBuilder().tool_use("Read", "/a.py").at(_at(1)).with_hash("h2").build(),
    ]
    phases = PhaseDetector.detect(events)
    assert len(phases) == 1
    assert phases[0].start_ts == _at(0)
    assert phases[0].end_ts == _at(2)
