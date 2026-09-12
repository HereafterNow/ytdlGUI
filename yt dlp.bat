@echo off
setlocal

REM --- Config ---------------------------------------------------------
set PYTHON=py
set SCRIPT=%~dp0ytdlp_gui.py
set START_DIR=%USERPROFILE%\Videos
REM --------------------------------------------------------------------

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

where yt-dlp >nul 2>&1
if errorlevel 1 (
    echo [warn] yt-dlp is not on PATH. The GUI will still open, but
    echo        downloads and updates will fail until it's installed
    echo        or a yt-dlp folder is set in the GUI.
    echo.
)

cd /d "%START_DIR%"
%PYTHON% "%SCRIPT%"

if errorlevel 1 (
    echo.
    echo [exit] Python returned error code %errorlevel%.
    pause
)

endlocal