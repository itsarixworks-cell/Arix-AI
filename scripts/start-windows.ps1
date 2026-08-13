$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not (Test-Path '.venv\Scripts\python.exe')) {
  throw 'Arix is not set up. Run .\scripts\setup-windows.ps1 first.'
}
$env:PATH = "$(Resolve-Path '.venv\Scripts');$env:PATH"
npm run dev
