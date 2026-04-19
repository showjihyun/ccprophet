from __future__ import annotations

import json

import duckdb

from ccprophet.adapters.cli.install import (
    HOOK_COMMAND,
    HOOK_CONFIG,
    STATUSLINE_COMMAND,
    run_install_command,
    run_uninstall_command,
)
from ccprophet.adapters.persistence.duckdb.migrations import ensure_schema
from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore


def _read(path) -> dict:  # type: ignore[no-untyped-def, type-arg]
    return json.loads(path.read_text(encoding="utf-8"))


def _settings_store() -> JsonFileSettingsStore:
    return JsonFileSettingsStore()


def _bootstrap_db(db_path) -> int:  # type: ignore[no-untyped-def]
    conn = duckdb.connect(str(db_path))
    try:
        return ensure_schema(conn)
    finally:
        conn.close()


def _install_first(tmp_path, capsys):  # type: ignore[no-untyped-def]
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"theme": "dark"}) + "\n", encoding="utf-8")
    prophet_dir = tmp_path / ".ccprophet"
    run_install_command(
        settings=_settings_store(),
        bootstrap_db=_bootstrap_db,
        as_json=True,
        prophet_dir=prophet_dir,
        settings_path=settings,
    )
    # Drain install's stdout so subsequent capsys.readouterr() sees only
    # the uninstall payload.
    capsys.readouterr()
    return settings, prophet_dir


def test_uninstall_removes_hooks_and_statusline(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    settings, prophet_dir = _install_first(tmp_path, capsys)

    code = run_uninstall_command(
        settings=_settings_store(),
        as_json=True,
        prophet_dir=prophet_dir,
        settings_path=settings,
    )
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert sorted(report["hooks_removed"]) == sorted(HOOK_CONFIG.keys())
    assert report["statusline_removed"] is True
    assert report["applied"] is True

    loaded = _read(settings)
    # Unrelated keys preserved.
    assert loaded["theme"] == "dark"
    # No ccprophet hooks remain for any registered event type.
    for event_type in HOOK_CONFIG:
        commands = [
            h.get("command")
            for h in loaded.get("hooks", {}).get(event_type, [])
            if isinstance(h, dict)
        ]
        assert all(c != HOOK_COMMAND for c in commands)
    # statusLine must not point at ccprophet any more.
    sl = loaded.get("statusLine")
    assert not (
        isinstance(sl, dict)
        and str(sl.get("command", "")).startswith(STATUSLINE_COMMAND.split()[0])
    )
    # DB kept unless --purge.
    assert (prophet_dir / "events.duckdb").exists()


def test_uninstall_preserves_third_party_hooks(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    settings, prophet_dir = _install_first(tmp_path, capsys)
    # Add a foreign hook on PostToolUse — uninstall must leave it intact.
    data = _read(settings)
    data["hooks"]["PostToolUse"].append({"type": "command", "command": "other-tool --logs"})
    settings.write_text(json.dumps(data, indent=2), encoding="utf-8")

    run_uninstall_command(
        settings=_settings_store(),
        as_json=True,
        prophet_dir=prophet_dir,
        settings_path=settings,
    )
    loaded = _read(settings)
    commands = [h.get("command") for h in loaded["hooks"]["PostToolUse"]]
    assert commands == ["other-tool --logs"]


def test_uninstall_dry_run_changes_nothing(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    settings, prophet_dir = _install_first(tmp_path, capsys)
    before = settings.read_bytes()

    code = run_uninstall_command(
        settings=_settings_store(),
        dry_run=True,
        as_json=True,
        prophet_dir=prophet_dir,
        settings_path=settings,
    )
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["applied"] is False
    assert report["dry_run"] is True
    assert settings.read_bytes() == before
    assert (prophet_dir / "events.duckdb").exists()


def test_uninstall_purge_removes_db(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    settings, prophet_dir = _install_first(tmp_path, capsys)
    db = prophet_dir / "events.duckdb"
    assert db.exists()

    code = run_uninstall_command(
        settings=_settings_store(),
        purge=True,
        as_json=True,
        prophet_dir=prophet_dir,
        settings_path=settings,
    )
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["purge"] is True
    assert any(p.endswith("events.duckdb") for p in report["purged"])
    assert not db.exists()


def test_uninstall_idempotent_on_fresh_settings(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    settings = tmp_path / "settings.json"
    settings.write_text("{}\n", encoding="utf-8")
    prophet_dir = tmp_path / ".ccprophet"

    code = run_uninstall_command(
        settings=_settings_store(),
        as_json=True,
        prophet_dir=prophet_dir,
        settings_path=settings,
    )
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["applied"] is False
    assert report["hooks_removed"] == []
    assert report["statusline_removed"] is False
