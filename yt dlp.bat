@echo off
setlocal

REM --- Config ---------------------------------------------------------
set PYTHON=py
set SCRIPT=%~dp0ytdlp_gui.py
set SIDECAR=%APPDATA%\ytdlp_gui.cfg
set PRIMARY_DIR=Z:\Downloads
set FALLBACK_DIR=I:\Trung\Download
REM --------------------------------------------------------------------

REM --- 1) Try to read save_folder from the GUI's sidecar config ------
set START_DIR=
if exist "%SIDECAR%" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%SIDECAR%") do (
        if /i "%%A"=="save_folder" set "START_DIR=%%B"
    )
)

REM --- 2) Nothing saved? Prefer Z:\New Downloads if Z: is mounted ----
if not defined START_DIR (
    if exist "Z:\" (
        set "START_DIR=%PRIMARY_DIR%"
    ) else (
        set "START_DIR=%FALLBACK_DIR%"
    )
)

REM --- 3) Saved folder unreachable? Prefer Z:\New Downloads ----------
if not exist "%START_DIR%\" (
    echo [warn] Download folder not available: %START_DIR%
    if exist "Z:\" (
        echo        Using: %PRIMARY_DIR%
        set "START_DIR=%PRIMARY_DIR%"
    ) else (
        echo        Z: not mounted. Using: %FALLBACK_DIR%
        set "START_DIR=%FALLBACK_DIR%"
    )
)

REM --- 4) Still unreachable? Try the I: fallback ---------------------
if not exist "%START_DIR%\" (
    echo [warn] Still unavailable. Falling back to: %FALLBACK_DIR%
    set "START_DIR=%FALLBACK_DIR%"
)

REM --- 5) Give up gracefully and use the user profile ----------------
if not exist "%START_DIR%\" (
    echo [warn] No configured download folder is reachable.
    echo        Continuing from: %USERPROFILE%
    set "START_DIR=%USERPROFILE%"
)

echo [info] Working directory: %START_DIR%
echo.
REM --------------------------------------------------------------------

REM --- Python sanity check -------------------------------------------
where %PYTHON% >nul 2>&1
if errorlevel 1 (
    echo [error] Could not find Python ^(%PYTHON%^) on PATH.
    echo Install Python from https://www.python.org/downloads/ and try again.
    pause
    exit /b 1
)

if not exist "%SCRIPT%" (
    echo [error] GUI script not found at:
    echo         %SCRIPT%
    pause
    exit /b 1
)

REM --- Launch --------------------------------------------------------
cd /d "%START_DIR%"
%PYTHON% "%SCRIPT%"

if errorlevel 1 (
    echo.
    echo [exit] Python returned error code %errorlevel%.
    pause
)

endlocal