@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
set "PYTHONPYCACHEPREFIX=%~dp0generated\launcher-cache-v2"
set "PYTHONDONTWRITEBYTECODE=1"
echo PCB Isolator launcher v2 - empty drill files supported
if "%~1"=="" (
  echo Drag a manufacturing job folder onto this launcher.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pcb_isolator.machining_preview --job "%~1"
if errorlevel 1 pause
