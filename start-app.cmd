@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
set "PYTHONPYCACHEPREFIX=%~dp0generated\launcher-cache-v2"
set "PYTHONDONTWRITEBYTECODE=1"
".venv\Scripts\python.exe" -m pcb_isolator.desktop %*
if errorlevel 1 pause
