param([string]$Python = "", [string]$OutputRoot = "")
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
if (-not $Python) { $Python = Join-Path $projectRoot '.venv\Scripts\python.exe' }
if (-not $OutputRoot) { $OutputRoot = Join-Path $projectRoot 'dist' }
$buildRoot = Join-Path $projectRoot 'build\pyinstaller'
Push-Location $projectRoot
try {
    & $Python -m PyInstaller --noconfirm --distpath $OutputRoot --workpath $buildRoot (Join-Path $PSScriptRoot 'PCB-Isolator.spec')
    if ($LASTEXITCODE -ne 0) { throw 'Portable build failed.' }
    & $Python (Join-Path $PSScriptRoot 'finish_package.py') (Join-Path $OutputRoot 'PCB Isolator')
    if ($LASTEXITCODE -ne 0) { throw 'Archive packaging failed.' }
} finally { Pop-Location }
