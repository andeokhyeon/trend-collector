@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Create GitHub Actions Workflows

echo ============================================
echo   Create GitHub Actions Workflows
echo ============================================
echo.

python make_workflows.py

echo.
echo ============================================
echo   Next steps
echo ============================================
echo.
echo  1) git add .
echo  2) git commit -m "add github actions"
echo  3) git push
echo.
echo  4) On GitHub:
echo     Settings ^> Secrets and variables ^> Actions
echo     Register 9 secrets from your .env file
echo.
echo  5) Actions tab ^> collector ^> Run workflow
echo.
pause
