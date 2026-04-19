@echo off
REM ccprophet installer for Windows (cmd)
REM   install.bat              -> installs with extras: web,mcp,forecast
REM   install.bat minimal      -> installs with no extras
REM   install.bat web          -> installs with a custom extras spec
REM
REM Exit codes: 0 ok, 1 uv bootstrap failed, 2 ccprophet install failed.

setlocal enabledelayedexpansion

set "SOURCE=git+https://github.com/showjihyun/ccprophet.git"
set "EXTRAS=web,mcp,forecast"
if not "%~1"=="" (
    if /I "%~1"=="minimal" (set "EXTRAS=") else (set "EXTRAS=%~1")
)

echo ====================================
echo  ccprophet installer
echo  source : %SOURCE%
if defined EXTRAS (echo  extras : %EXTRAS%) else (echo  extras : ^<none^>)
echo ====================================
echo.

REM --- 1. Ensure uv is installed -------------------------------------------
where uv >nul 2>nul
if %errorlevel%==0 (
    echo [1/3] uv detected.
) else (
    echo [1/3] uv not found. Bootstrapping...
    where winget >nul 2>nul
    if !errorlevel!==0 (
        winget install --id astral-sh.uv -e --silent ^
            --accept-source-agreements --accept-package-agreements
    )
    where uv >nul 2>nul
    if !errorlevel! neq 0 (
        echo       winget unavailable or failed, trying astral install script...
        powershell -NoProfile -ExecutionPolicy Bypass ^
            -Command "irm https://astral.sh/uv/install.ps1 | iex"
    )
    REM Refresh PATH so uv is visible in this session.
    set "PATH=%USERPROFILE%\.local\bin;%LOCALAPPDATA%\Programs\uv;%PATH%"
    where uv >nul 2>nul
    if !errorlevel! neq 0 (
        echo ERROR: uv installation failed. See https://docs.astral.sh/uv/
        exit /b 1
    )
)

REM --- 2. Install ccprophet -------------------------------------------------
echo [2/3] Installing ccprophet...
if defined EXTRAS (
    uv tool install --force "ccprophet[%EXTRAS%] @ %SOURCE%"
) else (
    uv tool install --force "ccprophet @ %SOURCE%"
)
if errorlevel 1 (
    echo ERROR: uv tool install failed.
    exit /b 2
)

REM --- 3. Wire PATH + verify ----------------------------------------------
echo [3/3] Updating shell PATH...
uv tool update-shell >nul 2>nul

where ccprophet >nul 2>nul
if errorlevel 1 (
    echo.
    echo Installed. Open a NEW terminal, then run:
    echo     ccprophet --version
    echo     ccprophet install
) else (
    echo.
    ccprophet --version
    echo.
    echo Next steps:
    echo     ccprophet install  ^# wire hooks + create DB + migrate schema
    echo     ccprophet ingest   ^# backfill past sessions
)

endlocal
exit /b 0
