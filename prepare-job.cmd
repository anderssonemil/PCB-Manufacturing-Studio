@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
set "PYTHONPYCACHEPREFIX=%~dp0generated\launcher-cache-v2"
set "PYTHONDONTWRITEBYTECODE=1"
if "%~1"=="" (
  echo Drag a job folder with a saved alignment selection onto this launcher.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pcb_isolator.job_outputs "%~1"
pause
