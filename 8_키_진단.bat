@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Key Diagnostic
python diagnose.py
echo.
pause
