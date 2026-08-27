@echo off
chcp 65001 > nul
cd /d "%~dp0"
title 키워드 미리쌓기 (계속 실행)

echo ============================================
echo   키워드 미리쌓기  -  멈출 때까지 계속
echo ============================================
echo.
echo 검색량을 미리 모아둡니다.
echo 나중에 조회할 때 네이버를 안 불러도 되게 하는 작업입니다.
echo.
echo  * 하루 한도를 다 쓰면 초기화될 때까지 기다렸다가
echo    스스로 다시 시작합니다.
echo  * 펼칠 키워드가 떨어지면 새로 찾아옵니다.
echo.
echo  멈추려면  Ctrl + C  를 누르거나 이 창을 닫으세요.
echo.
pause

python seed_pool.py forever

echo.
echo 종료되었습니다.
pause
