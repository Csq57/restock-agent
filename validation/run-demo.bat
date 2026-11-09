@echo off
REM One-click demo for someone who is not going to read a README.
REM Runs entirely offline in mock mode: no PayPal credentials, no API keys, no internet needed
REM after the first install.
setlocal
REM Hard offline switch: mock PayPal + deterministic planner, whatever .env says.
set RESTOCK_OFFLINE=1
cd /d "%~dp0.."

echo.
echo  Restock Agent - local demo
echo  --------------------------
echo  Setting up a private Python environment (first run only, about a minute)...
echo.

if not exist ".venv-demo" (
  py -3 -m venv .venv-demo 2>nul || python -m venv .venv-demo
)
call ".venv-demo\Scripts\activate.bat" >nul 2>&1

python -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo  Could not install the dependencies. Is Python 3.10+ installed?
  echo  https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

echo.
echo  Opening http://127.0.0.1:8756/ in your browser.
echo  Nothing is charged: this runs in mock mode with the sample stock CSV.
echo  Close this window when you are done.
echo.

start "" http://127.0.0.1:8756/
python -m uvicorn app.main:app --host 127.0.0.1 --port 8756

endlocal
