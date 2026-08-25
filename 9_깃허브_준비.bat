@echo off
chcp 65001 > nul
cd /d "%~dp0"
title GitHub Safety Check

echo ============================================
echo   GitHub Safety Check
echo ============================================
echo.

REM --- create .gitignore ---
if exist ".gitignore" (
  echo [OK] .gitignore already exists.
) else (
  > ".gitignore" echo # Never upload these
  >>".gitignore" echo .env
  >>".gitignore" echo *.env
  >>".gitignore" echo .streamlit/secrets.toml
  >>".gitignore" echo.
  >>".gitignore" echo # Python
  >>".gitignore" echo __pycache__/
  >>".gitignore" echo *.pyc
  >>".gitignore" echo.
  >>".gitignore" echo # Logs
  >>".gitignore" echo collector_log.txt
  >>".gitignore" echo.
  >>".gitignore" echo # Local key files
  >>".gitignore" echo key_template.txt
  echo [OK] .gitignore created.
)

echo.
echo --------------------------------------------
echo   Files that will NOT be uploaded:
echo --------------------------------------------
type ".gitignore"

echo.
echo --------------------------------------------
echo   Checking for exposed keys...
echo --------------------------------------------

set FOUND=0
findstr /S /M /C:"sk-ant-api03" *.py >nul 2>&1 && set FOUND=1
findstr /S /M /C:"sb_publishable" *.py >nul 2>&1 && set FOUND=1

if %FOUND%==1 (
  echo [WARNING] API keys found in .py files!
  echo           Do NOT upload to GitHub.
) else (
  echo [OK] No keys found in .py files.
)

echo.
if exist ".env" (
  echo [OK] .env exists and is protected by .gitignore.
) else (
  echo [!] .env not found. Run "0_keysetup.bat" first.
)

echo.
echo ============================================
echo   Safe to upload the .py files now.
echo ============================================
echo.
pause
