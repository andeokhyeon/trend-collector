@echo off
cd /d "%~dp0"
title Keyword Dashboard - Setup

echo ============================================
echo   SETUP  (run this once)
echo ============================================
echo.

python --version
if errorlevel 1 goto NOPYTHON

echo.
echo Installing required packages...
echo This may take a few minutes.
echo.

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo ============================================
echo   DONE. Now run: 2_dashboard.bat
echo ============================================
echo.
pause
exit /b

:NOPYTHON
echo.
echo [ERROR] Python not found.
echo.
echo Install Python from python.org
echo IMPORTANT: check "Add Python to PATH" during install.
echo.
pause
