param([string]$Python = 'python', [string]$JdkHome = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
    & .\.venv\Scripts\python.exe -m pip install -r packaging/build-requirements.lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & .\.venv\Scripts\python.exe -m pip install --no-deps -e .
    if ($LASTEXITCODE -ne 0) { throw 'Project installation failed.' }
    if (-not (Test-Path config.toml)) { Copy-Item config.example.toml config.toml }
    & .\helix\setup.ps1 -JdkHome $JdkHome
} finally { Pop-Location }
