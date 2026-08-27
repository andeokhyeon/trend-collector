@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  주간 캘린더만 지금 바로 다시 수집합니다.
echo.
python collector.py weekly
echo.
pause
