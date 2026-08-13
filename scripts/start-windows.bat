@echo off
setlocal
cd /d "%~dp0\.."
if not exist .venv\Scripts\python.exe (
  echo Arix is not set up. Run scripts\setup-windows.bat first.
  exit /b 1
)
call .venv\Scripts\activate.bat
call npm run dev
endlocal
