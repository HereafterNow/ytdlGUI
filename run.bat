@echo off
cd /d "%~dp0"
py -3 ytdlp_gui.py
if errorlevel 1 pause
