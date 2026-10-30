@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
if "%~1"=="" (
  ".venv\Scripts\python.exe" -m pcb_isolator.convert "local-boards\pi-transducer\Pi Transducer-B_Cu.gbr"
) else (
  ".venv\Scripts\python.exe" -m pcb_isolator.convert "%~1"
)
pause
