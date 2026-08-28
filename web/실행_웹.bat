@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Keyword Hunter Web (dev)
REM 가짜 데이터로 화면만 볼 때는 아래 줄을 그대로 둡니다.
REM 진짜 API(.env의 키)로 돌릴 때는 아래 한 줄을 지우세요.
set KH_FAKE=1
python -m pip install -q fastapi uvicorn jinja2 python-multipart
echo.
echo   브라우저에서  http://localhost:8000  을 여세요.
echo   (끝내려면 이 창에서 Ctrl+C)
echo.
python -m uvicorn main:app --host 127.0.0.1 --port 8000
pause
