from __future__ import annotations

import json

from ccprophet.adapters.cli.install import (
    HOOK_COMMAND,
    HOOK_CONFIG,
    STATUSLINE_COMMAND,
    run_install_command,
)


def _read(path) -> dict:  # type: ignore[no-untyped-def, type-arg]
    return json.loads(path.read_text(encoding="utf-8"))


def test_dry_run_does_not_write(capsys, tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"existing": True}) + "\n", encoding="utf-8")
    prophet_dir = tmp_path / ".ccprophet"
    before = settings.read_bytes()

    code = run_install_command(
        dry_run=True,
        as_json=True,
        prophet_dir=prophet_dir,
        settings_path=settings,
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applied"] is False
    assert sorted(payload["hooks_added"]) == sorted(HOOK_CONFIG.keys())
    assert settings.read_bytes() == before
    assert not prophet_dir.exists()


def test_install_adds_hooks_atomically(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"theme": "dark"}) + "\n", encoding="utf-8")
    prophet_dir = tmp_path / ".ccprophet"

    code = run_install_command(
        as_json=True,
        prophet_dir=prophet_dir,
        settings_path=settings,
    )
    assert code == 0
    loaded = _read(settings)
    assert loaded["theme"] == "dark"
    for event_type in HOOK_CONFIG:
        commands = [
            entry.get("command")
            for entry in loaded["hooks"][event_type]
            if isinstance(entry, dict)
        ]
        assert any(c == HOOK_COMMAND for c in commands)
    assert loaded["statusLine"]["command"] == STATUSLINE_COMMAND
    assert (prophet_dir / "events.duckdb").exists()


def test_existing_statusline_preserved(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"statusLine": {"type": "command", "command": STATUSLINE_COMMAND}})
        + "\n",
        encoding="utf-8",
    )
    prophet_dir = tmp_path / ".ccprophet"
    run_install_command(
        as_json=True, prophet_dir=prophet_dir, settings_path=settings
    )
    loaded = _read(settings)
    assert loaded["statusLine"]["command"] == STATUSLINE_COMMAND


def test_install_is_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = tmp_path / "settings.json"
    settings.write_text("{}\n", encoding="utf-8")
    prophet_dir = tmp_path / ".ccprophet"

    run_install_command(
        as_json=True, prophet_dir=prophet_dir, settings_path=settings
    )
    first = settings.read_bytes()
    run_install_command(
        as_json=True, prophet_dir=prophet_dir, settings_path=settings
    )
    assert settings.read_bytes() == first


def test_install_on_missing_settings_creates_it(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = tmp_path / "nested" / "settings.json"
    prophet_dir = tmp_path / ".ccprophet"
    run_install_command(
        as_json=True, prophet_dir=prophet_dir, settings_path=settings
    )
    assert settings.exists()
    loaded = _read(settings)
    assert "hooks" in loaded
