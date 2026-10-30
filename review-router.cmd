@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
set "PYTHONPYCACHEPREFIX=%~dp0generated\launcher-cache-v2"
set "PYTHONDONTWRITEBYTECODE=1"
if "%~1"=="" (
  ".venv\Scripts\python.exe" -m pcb_isolator.router_review --jobs-root "%~dp0jobs"
) else (
  echo Requested folder: "%~1"
  ".venv\Scripts\python.exe" -m pcb_isolator.router_review "%~1"
)
if errorlevel 1 pause
