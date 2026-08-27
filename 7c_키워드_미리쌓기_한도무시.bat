@echo off
chcp 65001 > nul
cd /d "%~dp0"
title 키워드 미리쌓기 (한도 무시)

echo ============================================
echo   키워드 미리쌓기  -  한도 무시
echo ============================================
echo.
echo  우리가 걸어둔 안전선(하루 60%%)을 끄고
echo  네이버가 실제로 막을 때까지 계속 부릅니다.
echo.
echo  [알아두실 것]
echo   * 네이버 쪽 진짜 한도는 그대로 있습니다.
echo   * 대시보드가 쓸 조회 몫까지 당겨쓰게 됩니다.
echo     낮에 대시보드를 쓰실 거면 7번(보통 모드)을 쓰세요.
echo   * 거절이 이어지면 스스로 쉬었다가 다시 시도합니다.
echo.
echo  멈추려면  Ctrl + C  를 누르거나 이 창을 닫으세요.
echo.
pause

python seed_pool.py nolimit

echo.
echo 종료되었습니다.
pause
