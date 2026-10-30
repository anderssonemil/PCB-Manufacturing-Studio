@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
if "%~1"=="" (
  echo Drag a saved .kicad_pcb file onto this launcher to export a manufacturing job.
  echo Save your board and refill copper zones in KiCad first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pcb_isolator.kicad_export "%~1"
pause
