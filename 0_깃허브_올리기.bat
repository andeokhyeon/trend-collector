@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Push to GitHub

set /p MSG="What changed? (press Enter to skip): "

python push.py %MSG%

echo.
pause
