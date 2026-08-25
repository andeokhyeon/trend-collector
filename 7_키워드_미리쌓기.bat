@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Seed Keyword Pool

echo ============================================
echo   Seed Keyword Pool
echo ============================================
echo.
echo This collects search volumes in advance
echo so users don't trigger API calls later.
echo.
echo It stops automatically at 60%% of the daily limit.
echo You can close this window anytime.
echo.
pause

python seed_pool.py
echo.
pause
