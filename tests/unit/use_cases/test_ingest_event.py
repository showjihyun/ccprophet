from __future__ import annotations

from datetime import datetime, timezone

from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.values import SessionId
from ccprophet.use_cases.ingest_event import IngestEventUseCase

FROZEN = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)


def _uc(repos: InMemoryRepositorySet) -> IngestEventUseCase:
    return IngestEventUseCase(
        events=repos.events,
        sessions=repos.sessions,
        tool_calls=repos.tool_calls,
        clock=FrozenClock(FROZEN),
    )


def _session(repos: InMemoryRepositorySet, sid: str) -> object:
    return repos.sessions.get(SessionId(sid))


def test_top_level_usage_accumulates_on_existing_session() -> None:
    repos = InMemoryRepositorySet()
    uc = _uc(repos)

    uc.execute(
        "PostToolUse",
        {
            "session_id": "s-top",
            "tool_name": "Read",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 50,
                "cache_creation_input_tokens": 1000,
                "cache_read_input_tokens": 200,
            },
            "model": "claude-opus-4-7",
        },
    )

    session = _session(repos, "s-top")
    assert session is not None
    assert session.total_input_tokens.value == 10
    assert session.total_output_tokens.value == 50
    assert session.total_cache_creation_tokens.value == 1000
    assert session.total_cache_read_tokens.value == 200
    assert session.model == "claude-opus-4-7"


def test_nested_message_usage_accumulates_on_existing_session() -> None:
    repos = InMemoryRepositorySet()
    uc = _uc(repos)

    uc.execute(
        "AssistantResponse",
        {
            "session_id": "s-nested",
            "message": {
                "model": "claude-opus-4-7",
                "usage": {
                    "input_tokens": 7,
                    "output_tokens": 11,
                    "cache_creation_input_tokens": 13,
                    "cache_read_input_tokens": 17,
                },
            },
        },
    )

    session = _session(repos, "s-nested")
    assert session is not None
    assert session.total_input_tokens.value == 7
    assert session.total_output_tokens.value == 11
    assert session.total_cache_creation_tokens.value == 13
    assert session.total_cache_read_tokens.value == 17
    assert session.model == "claude-opus-4-7"


def test_successive_events_add_up_instead_of_overwriting() -> None:
    repos = InMemoryRepositorySet()
    uc = _uc(repos)

    uc.execute(
        "AssistantResponse",
        {
            "session_id": "s-sum",
            "message": {
                "model": "claude-opus-4-7",
                "usage": {
                    "input_tokens": 5,
                    "output_tokens": 9,
                    "cache_creation_input_tokens": 100,
                    "cache_read_input_tokens": 0,
                },
            },
        },
    )
    uc.execute(
        "AssistantResponse",
        {
            "session_id": "s-sum",
            "message": {
                "model": "claude-opus-4-7",
                "usage": {
                    "input_tokens": 3,
                    "output_tokens": 4,
                    "cache_creation_input_tokens": 50,
                    "cache_read_input_tokens": 25,
                },
            },
        },
    )

    session = _session(repos, "s-sum")
    assert session is not None
    assert session.total_input_tokens.value == 8
    assert session.total_output_tokens.value == 13
    assert session.total_cache_creation_tokens.value == 150
    assert session.total_cache_read_tokens.value == 25


def test_payload_without_usage_is_noop_for_token_counts() -> None:
    repos = InMemoryRepositorySet()
    uc = _uc(repos)

    uc.execute(
        "PostToolUse",
        {"session_id": "s-noop", "tool_name": "Read"},
    )

    session = _session(repos, "s-noop")
    assert session is not None
    assert session.total_input_tokens.value == 0
    assert session.total_output_tokens.value == 0
    assert session.total_cache_creation_tokens.value == 0
    assert session.total_cache_read_tokens.value == 0
    # Ensure this default initial event still created the session.
    assert session.model == "unknown"


def test_model_upgrades_from_unknown_on_first_assistant_message() -> None:
    repos = InMemoryRepositorySet()
    uc = _uc(repos)

    # First event: no model, session is created with model="unknown".
    uc.execute(
        "UserPromptSubmit",
        {"session_id": "s-upgrade"},
    )
    first = _session(repos, "s-upgrade")
    assert first is not None
    assert first.model == "unknown"

    # Second event carries a nested message.model — should upgrade.
    uc.execute(
        "AssistantResponse",
        {
            "session_id": "s-upgrade",
            "message": {
                "model": "claude-opus-4-7",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        },
    )
    upgraded = _session(repos, "s-upgrade")
    assert upgraded is not None
    assert upgraded.model == "claude-opus-4-7"


def test_existing_non_unknown_model_is_preserved() -> None:
    repos = InMemoryRepositorySet()
    uc = _uc(repos)

    # Seed session with a known model via top-level payload.
    uc.execute(
        "SessionStart",
        {"session_id": "s-keep", "model": "claude-sonnet-4-5"},
    )
    seeded = _session(repos, "s-keep")
    assert seeded is not None
    assert seeded.model == "claude-sonnet-4-5"

    # Subsequent event with a *different* model should NOT overwrite.
    uc.execute(
        "AssistantResponse",
        {
            "session_id": "s-keep",
            "message": {
                "model": "claude-opus-4-7",
                "usage": {
                    "input_tokens": 2,
                    "output_tokens": 3,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        },
    )
    kept = _session(repos, "s-keep")
    assert kept is not None
    assert kept.model == "claude-sonnet-4-5"
    # Tokens still accumulate.
    assert kept.total_input_tokens.value == 2
    assert kept.total_output_tokens.value == 3

    # Subsequent event with empty/missing model should leave it alone too.
    uc.execute(
        "AssistantResponse",
        {
            "session_id": "s-keep",
            "message": {
                "usage": {
                    "input_tokens": 4,
                    "output_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        },
    )
    still = _session(repos, "s-keep")
    assert still is not None
    assert still.model == "claude-sonnet-4-5"
    assert still.total_input_tokens.value == 6


def test_non_integer_usage_values_coerce_to_zero() -> None:
    repos = InMemoryRepositorySet()
    uc = _uc(repos)

    uc.execute(
        "AssistantResponse",
        {
            "session_id": "s-bad",
            "message": {
                "model": "claude-opus-4-7",
                "usage": {
                    "input_tokens": "not-a-number",
                    "output_tokens": None,
                    "cache_creation_input_tokens": 7,
                    "cache_read_input_tokens": "also-bad",
                },
            },
        },
    )

    session = _session(repos, "s-bad")
    assert session is not None
    assert session.total_input_tokens.value == 0
    assert session.total_output_tokens.value == 0
    assert session.total_cache_creation_tokens.value == 7
    assert session.total_cache_read_tokens.value == 0
