@echo off
chcp 65001 > nul
cd /d "%~dp0"
title GitHub Secrets Helper
python show_secrets.py
echo.
pause
