@echo off
cd /d "%~dp0"
title Keyword Hunter

REM --- create theme config if missing ---
if not exist ".streamlit" mkdir ".streamlit"
if not exist ".streamlit\config.toml" (
  > ".streamlit\config.toml" echo [theme]
  >>".streamlit\config.toml" echo primaryColor = "#C8963E"
  >>".streamlit\config.toml" echo backgroundColor = "#FAFAF7"
  >>".streamlit\config.toml" echo secondaryBackgroundColor = "#FFFFFF"
  >>".streamlit\config.toml" echo textColor = "#14161A"
  >>".streamlit\config.toml" echo font = "sans serif"
  >>".streamlit\config.toml" echo.
  >>".streamlit\config.toml" echo [browser]
  >>".streamlit\config.toml" echo gatherUsageStats = false
  >>".streamlit\config.toml" echo.
  >>".streamlit\config.toml" echo [client]
  >>".streamlit\config.toml" echo toolbarMode = "viewer"
  echo Theme config created.
)
REM add toolbarMode if missing in an existing config
findstr /C:"toolbarMode" ".streamlit\config.toml" >nul 2>&1
if errorlevel 1 (
  >>".streamlit\config.toml" echo.
  >>".streamlit\config.toml" echo [client]
  >>".streamlit\config.toml" echo toolbarMode = "viewer"
)

REM --- warn if .env is missing ---
if not exist ".env" (
  echo.
  echo [!] .env file not found.
  echo     Copy ".env.example" to ".env" and put your API keys in it.
  echo.
)

echo ============================================
echo   Starting Keyword Hunter...
echo ============================================
echo.
echo Your browser will open automatically.
echo Close this window to stop.
echo.

python -m streamlit run app.py

echo.
echo [ERROR] Failed to start.
echo Did you run 1_setup.bat first?
echo.
pause
