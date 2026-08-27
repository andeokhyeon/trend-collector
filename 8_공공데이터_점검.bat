@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
python check_publicdata.py
echo.
pause
