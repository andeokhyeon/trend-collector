@echo off
chcp 65001 > nul
cd /d "%~dp0"
title 깃허브 맞추고 올리기

echo ============================================================
echo   깃허브와 맞춘 뒤 올립니다
echo ------------------------------------------------------------
echo   폰에서 웹으로 파일을 올리면, PC는 그 사실을 모릅니다.
echo   그 상태에서 PC가 올리려 하면 깃허브가 거절합니다
echo   ("fetch first" / "rejected").
echo   이 파일은 깃허브 상태를 먼저 받아온 뒤,
echo   지금 이 폴더의 파일들을 기준으로 다시 올립니다.
echo   ** 폴더 안의 파일은 하나도 건드리지 않습니다 **
echo ============================================================
echo.

echo [1/3] 깃허브 최신 상태 받아오는 중...
git fetch origin
if errorlevel 1 goto fail

echo [2/3] 기준점 맞추는 중 (파일은 그대로)...
git reset --mixed origin/main
if errorlevel 1 goto fail

echo [3/3] 올리는 중...
echo.
python push.py sync from PC
goto end

:fail
echo.
echo  X 실패했습니다. 위에 나온 메시지를 클로드에게 보여주세요.

:end
echo.
pause
