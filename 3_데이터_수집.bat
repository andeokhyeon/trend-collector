@echo off
cd /d "%~dp0"
title Keyword Dashboard - Collect Data

echo ============================================
echo   Collecting data...
echo   This takes about 10-20 minutes.
echo ============================================
echo.

python collector.py

echo.
echo ============================================
echo   Finished. Refresh the dashboard (F5).
echo ============================================
echo.
pause
