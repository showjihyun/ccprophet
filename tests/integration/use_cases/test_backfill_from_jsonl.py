from __future__ import annotations

import json

from ccprophet.adapters.filewatch.jsonl_reader import JsonlReader
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.values import SessionId
from ccprophet.use_cases.backfill_from_jsonl import BackfillFromJsonlUseCase


def _use_case(
    repos: InMemoryRepositorySet, *, with_subagents: bool = True
) -> BackfillFromJsonlUseCase:
    return BackfillFromJsonlUseCase(
        source=JsonlReader(),
        events=repos.events,
        sessions=repos.sessions,
        tool_calls=repos.tool_calls,
        subagents=repos.subagents if with_subagents else None,
    )


def _sample_jsonl(tmp_path, slug: str = "proj-a") -> list:  # type: ignore[no-untyped-def]
    project = tmp_path / slug
    project.mkdir()
    path = project / "session.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": "s-1",
                        "uuid": "u1",
                        "timestamp": "2026-04-17T09:00:00Z",
                        "message": {"role": "user", "content": "start"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "s-1",
                        "uuid": "u2",
                        "timestamp": "2026-04-17T09:01:00Z",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "tc-1",
                                    "name": "Read",
                                    "input": {"file_path": "/x.py"},
                                }
                            ]
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return [path]


def test_ingests_events_and_tool_calls(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    paths = _sample_jsonl(tmp_path)
    summary = _use_case(repos).execute(paths)

    assert summary.files_read == 1
    assert summary.events_ingested == 3  # user + assistant + synthetic PostToolUse
    assert summary.tool_calls_ingested == 1
    assert "s-1" in summary.sessions_touched

    session = repos.sessions.get(SessionId("s-1"))
    assert session is not None
    assert session.project_slug == "proj-a"

    calls = list(repos.tool_calls.list_for_session(SessionId("s-1")))
    assert [c.tool_name for c in calls] == ["Read"]


def test_dedup_prevents_double_ingest(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    paths = _sample_jsonl(tmp_path)
    first = _use_case(repos).execute(paths)
    second = _use_case(repos).execute(paths)
    assert first.events_ingested > 0
    assert second.events_ingested == 0
    calls = list(repos.tool_calls.list_for_session(SessionId("s-1")))
    assert len(calls) == 1


def test_skips_empty_and_invalid(tmp_path) -> None:  # type: ignore[no-untyped-def]
    project = tmp_path / "proj"
    project.mkdir()
    path = project / "bad.jsonl"
    path.write_text("\n\nnot json\n", encoding="utf-8")
    repos = InMemoryRepositorySet()
    summary = _use_case(repos).execute([path])
    assert summary.events_ingested == 0
    assert summary.files_read == 1


def test_accumulates_token_usage_on_sessions(tmp_path) -> None:  # type: ignore[no-untyped-def]
    project = tmp_path / "proj-usage"
    project.mkdir()
    path = project / "s.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": "s-u",
                        "uuid": "u1",
                        "timestamp": "2026-04-17T09:00:00Z",
                        "message": {"role": "user", "content": "hi"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "s-u",
                        "uuid": "a1",
                        "timestamp": "2026-04-17T09:00:01Z",
                        "message": {
                            "model": "claude-opus-4-7",
                            "content": [],
                            "usage": {
                                "input_tokens": 10,
                                "cache_creation_input_tokens": 1000,
                                "cache_read_input_tokens": 0,
                                "output_tokens": 50,
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "s-u",
                        "uuid": "a2",
                        "timestamp": "2026-04-17T09:01:00Z",
                        "message": {
                            "model": "claude-opus-4-7",
                            "content": [],
                            "usage": {
                                "input_tokens": 0,
                                "cache_read_input_tokens": 1000,
                                "output_tokens": 70,
                            },
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    repos = InMemoryRepositorySet()
    _use_case(repos).execute([path])

    session = repos.sessions.get(SessionId("s-u"))
    assert session is not None
    assert session.total_input_tokens.value == 10
    assert session.total_cache_creation_tokens.value == 1000
    assert session.total_cache_read_tokens.value == 1000
    assert session.total_output_tokens.value == 120
    assert session.model == "claude-opus-4-7"


def _sidechain_jsonl(tmp_path) -> list:  # type: ignore[no-untyped-def]
    """Simulates a parent session with one Task-spawned subagent.

    parent session `main-1` kicks off a subagent at session `sub-99`. The
    subagent records carry both `isSidechain: true` and `userType: sidechain`
    (Claude Code writes both in practice). The subagent makes one tool call.
    """
    project = tmp_path / "proj-sub"
    project.mkdir()
    path = project / "mixed.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": "main-1",
                        "uuid": "um1",
                        "timestamp": "2026-04-17T09:00:00Z",
                        "message": {"role": "user", "content": "do it"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "main-1",
                        "uuid": "am1",
                        "timestamp": "2026-04-17T09:00:05Z",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "task-1",
                                    "name": "Task",
                                    "input": {"subagent_type": "general", "prompt": "investigate"},
                                }
                            ]
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": "sub-99",
                        "uuid": "us1",
                        "timestamp": "2026-04-17T09:00:10Z",
                        "isSidechain": True,
                        "userType": "sidechain",
                        "message": {"role": "user", "content": "investigate"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "sub-99",
                        "uuid": "as1",
                        "timestamp": "2026-04-17T09:00:12Z",
                        "isSidechain": True,
                        "userType": "sidechain",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "tc-sub-1",
                                    "name": "Read",
                                    "input": {"file_path": "/x.py"},
                                }
                            ]
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "sub-99",
                        "uuid": "as2",
                        "timestamp": "2026-04-17T09:00:20Z",
                        "isSidechain": True,
                        "userType": "sidechain",
                        "message": {"content": [{"type": "text", "text": "done"}]},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return [path]


def test_records_subagent_from_sidechain_events(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    _use_case(repos).execute(_sidechain_jsonl(tmp_path))

    sub = repos.subagents.get(SessionId("sub-99"))
    assert sub is not None
    assert sub.parent_session_id == SessionId("main-1")
    assert sub.agent_type == "Task"
    assert sub.tool_call_count >= 1
    # started_at / ended_at bracket all sidechain records.
    assert sub.started_at is not None and sub.ended_at is not None
    assert sub.started_at <= sub.ended_at

    # Listing via the repository returns the subagent under its parent.
    listed = list(repos.subagents.list_for_parent(SessionId("main-1")))
    assert [s.subagent_id.value for s in listed] == ["sub-99"]

    # The parent session still exists; the sidechain sessionId is NOT
    # registered as a session.
    assert repos.sessions.get(SessionId("main-1")) is not None
    assert repos.sessions.get(SessionId("sub-99")) is None


def test_subagent_context_tokens_are_accumulated(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Subagent sessions accumulate their own input/output/cache tokens via
    the sidechain AssistantResponse `message.usage`; these land on the
    Subagent entity rather than being silently dropped."""
    project = tmp_path / "proj-tokens"
    project.mkdir()
    path = project / "mixed.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": "main-1",
                        "uuid": "um1",
                        "timestamp": "2026-04-17T09:00:00Z",
                        "message": {"role": "user", "content": "do it"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "sub-42",
                        "uuid": "as1",
                        "timestamp": "2026-04-17T09:00:10Z",
                        "isSidechain": True,
                        "userType": "sidechain",
                        "message": {
                            "model": "claude-opus-4-7",
                            "content": [{"type": "text", "text": "ok"}],
                            "usage": {
                                "input_tokens": 10,
                                "cache_creation_input_tokens": 500,
                                "cache_read_input_tokens": 100,
                                "output_tokens": 25,
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "sub-42",
                        "uuid": "as2",
                        "timestamp": "2026-04-17T09:00:20Z",
                        "isSidechain": True,
                        "userType": "sidechain",
                        "message": {
                            "model": "claude-opus-4-7",
                            "content": [{"type": "text", "text": "done"}],
                            "usage": {
                                "input_tokens": 5,
                                "cache_read_input_tokens": 1000,
                                "output_tokens": 40,
                            },
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    repos = InMemoryRepositorySet()
    _use_case(repos).execute([path])

    sub = repos.subagents.get(SessionId("sub-42"))
    assert sub is not None
    # 10 + 500 + 100 + 25 + 5 + 1000 + 40 = 1680
    assert sub.context_tokens.value == 1680


def test_no_subagents_without_port_wired(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    _use_case(repos, with_subagents=False).execute(_sidechain_jsonl(tmp_path))
    # Without the port wired, no Subagent row is written. Events/tool_calls
    # from the sidechain session still flow through unchanged.
    assert list(repos.subagents.list_for_parent(SessionId("main-1"))) == []


def test_subagent_without_detectable_parent_is_skipped(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """If a file contains ONLY sidechain records (orphan), no parent can be
    inferred so we skip — better than inventing a bogus parent link."""
    project = tmp_path / "proj-orphan"
    project.mkdir()
    path = project / "orphan.jsonl"
    path.write_text(
        json.dumps(
            {
                "type": "user",
                "sessionId": "orphan-1",
                "uuid": "uo1",
                "timestamp": "2026-04-17T09:00:00Z",
                "isSidechain": True,
                "userType": "sidechain",
                "message": {"role": "user", "content": "orphan"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    repos = InMemoryRepositorySet()
    _use_case(repos).execute([path])

    assert repos.subagents.get(SessionId("orphan-1")) is None
