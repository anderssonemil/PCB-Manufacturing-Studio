@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
if "%~1"=="" (
  ".venv\Scripts\python.exe" -m pcb_isolator.preview "local-boards\pi-transducer\Pi Transducer-B_Cu.gbr"
) else (
  ".venv\Scripts\python.exe" -m pcb_isolator.preview "%~1"
)
if errorlevel 1 pause
