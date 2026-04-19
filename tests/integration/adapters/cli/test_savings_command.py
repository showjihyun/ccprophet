"""Integration tests for `ccprophet savings` CLI adapter."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ccprophet.adapters.cli.savings import run_savings_command
from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore
from ccprophet.use_cases.compute_savings import ComputeSavingsUseCase

FROZEN = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)


def _wire(tmp_path) -> tuple[InMemoryRepositorySet, ComputeSavingsUseCase]:  # type: ignore[no-untyped-def]
    settings = tmp_path / "settings.json"
    settings.write_text('{"env": {}}\n', encoding="utf-8")
    repos = InMemoryRepositorySet()
    uc = ComputeSavingsUseCase(
        recommendations=repos.recommendations,
        settings=JsonFileSettingsStore(),
        clock=FrozenClock(FROZEN),
        settings_path=settings,
    )
    return repos, uc


def test_savings_empty_json_shape(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    _, uc = _wire(tmp_path)
    code = run_savings_command(uc, as_json=True)
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["applied"]["count"] == 0
    assert payload["applied"]["total_usd"] == 0
    assert payload["pending"]["count"] == 0
    assert "window_start" in payload
    assert "window_end" in payload


def test_savings_rich_path(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    _, uc = _wire(tmp_path)
    code = run_savings_command(uc, as_json=False)
    assert code == 0


def test_savings_custom_window_reflected(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    _, uc = _wire(tmp_path)
    code = run_savings_command(uc, window_days=7, as_json=True)
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    # window_start should be 7 days before window_end
    start = datetime.fromisoformat(payload["window_start"])
    end = datetime.fromisoformat(payload["window_end"])
    delta = end - start
    assert delta.days == 7
