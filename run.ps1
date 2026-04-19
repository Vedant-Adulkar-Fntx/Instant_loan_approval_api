# NTC score API — create/activate venv, install deps, start uvicorn.
# Usage: .\run.ps1 [-Port 8000] [-NoInstall]

param(
    [int]$Port = 8000,
    [switch]$NoInstall
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location -LiteralPath $Root

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
$venvPip = Join-Path $Root ".venv\Scripts\pip.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating virtual environment in .venv ..."
    python -m venv .venv
}

if (-not $NoInstall) {
    Write-Host "Installing dependencies ..."
    & $venvPip install -r (Join-Path $Root "requirements.txt")
}

Write-Host "Starting API on http://127.0.0.1:$Port (docs: http://127.0.0.1:$Port/docs)"
& (Join-Path $Root ".venv\Scripts\python.exe") -m uvicorn ntc_score_api:app --host 0.0.0.0 --port $Port
