@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -m pcb_isolator.machining_preview "local-boards\pi-transducer\Pi Transducer-B_Cu.gbr" --drill "local-boards\pi-transducer\Pi Transducer-PTH.drl" --drill "local-boards\pi-transducer\Pi Transducer-NPTH.drl"
if errorlevel 1 pause
