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

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating virtual environment in .venv ..."
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } else {
        throw "Python not found on PATH. Install Python from https://www.python.org/downloads/ and tick 'Add python.exe to PATH', or ensure the 'py' launcher is available."
    }
}

if (-not $NoInstall) {
    Write-Host "Installing dependencies ..."
    # Use `python -m pip` so installs work when AppLocker/WDAC blocks pip.exe under .venv\Scripts.
    & $venvPython -m pip install -r (Join-Path $Root "requirements.txt")
}

Write-Host "Starting API on http://127.0.0.1:$Port (docs: http://127.0.0.1:$Port/docs)"
& $venvPython -m uvicorn ntc_score_api:app --host 0.0.0.0 --port $Port
