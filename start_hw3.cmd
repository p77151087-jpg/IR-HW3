@echo off
setlocal
cd /d "%~dp0"
set "HW3_PYTHON=%~dp0.venv\Scripts\python.exe"
set "PYTHONDONTWRITEBYTECODE=1"
if not exist "%HW3_PYTHON%" goto failed
"%HW3_PYTHON%" -B -X utf8 -c "import streamlit, nltk, regex"
if errorlevel 1 goto failed
echo Open http://127.0.0.1:8503 in your browser. Keep this window open.
"%HW3_PYTHON%" -B -X utf8 -m streamlit run app.py --server.address 127.0.0.1 --server.port 8503
if errorlevel 1 goto failed
exit /b 0
:failed
echo HW3 could not start. Check the error above.
echo Run powershell -ExecutionPolicy Bypass -File scripts\setup_hw3.ps1 to install packages.
echo If port 8503 is in use, stop the existing HW3 window first.
pause
exit /b 1
