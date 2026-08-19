@echo off
setlocal
cd /d "%~dp0\.."

echo [Arix] Checking Python 3.11...
py -3.11 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.11 was not found. Install it from https://www.python.org/downloads/
  exit /b 1
)

echo [Arix] Creating Python environment...
if not exist .venv py -3.11 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
python -m playwright install chromium

echo [Arix] Installing desktop dependencies...
call npm install
call npm --prefix frontend install

echo.
echo Setup complete. Run scripts\start-windows.bat to launch Arix.
endlocal
