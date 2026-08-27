@echo off
chcp 65001 > nul
cd /d "%~dp0"
title 키워드 미리쌓기 (한 번만)

echo ============================================
echo   키워드 미리쌓기  -  한도까지만
echo ============================================
echo.
echo 하루 한도의 60%%까지만 쓰고 스스로 멈춥니다.
echo 계속 돌리려면 7번 파일을 쓰세요.
echo.
pause

python seed_pool.py

echo.
pause
