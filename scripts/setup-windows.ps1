$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

py -3.11 --version
if (-not (Test-Path '.venv')) { py -3.11 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm install
npm --prefix frontend install
Write-Host 'Setup complete. Run .\scripts\start-windows.ps1' -ForegroundColor Cyan
