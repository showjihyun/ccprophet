@echo off
REM ccprophet uninstaller for Windows (cmd).
REM Removes the `ccprophet` uv tool. Leaves uv itself and the DuckDB
REM (~/.claude-prophet/events.duckdb) untouched — delete those manually.

setlocal

where uv >nul 2>nul
if errorlevel 1 (
    echo uv not found on PATH; nothing to do.
    exit /b 0
)

echo Uninstalling ccprophet...
uv tool uninstall ccprophet
if errorlevel 1 (
    echo ccprophet was not installed as a uv tool.
    exit /b 0
)

echo.
echo Done. Residual data not removed:
echo     %USERPROFILE%\.claude-prophet\    ^# DuckDB + snapshots
echo     Claude Code settings.json hooks   ^# run `ccprophet uninstall` BEFORE this script to clean hooks
echo.

endlocal
exit /b 0
