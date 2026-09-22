@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem ============================================================
rem  불필요 파일 보관  (2026-09-22 전면 개편)
rem
rem  ⚠️ 지우지 않고 _보관\ 폴더로 "옮긴다".
rem     혹시 필요해지면 다시 꺼내면 된다. 확인 후 _보관 폴더를
rem     통째로 지우면 진짜 삭제다.
rem ============================================================

set BK=_보관
if not exist "%BK%" mkdir "%BK%"
if not exist "%BK%\web_static" mkdir "%BK%\web_static"
if not exist "%BK%\web_shots" mkdir "%BK%\web_shots"

echo.
echo === 1. 스트림릿 시절 유물 =========================
rem 웹(FastAPI)으로 완전히 옮겼다. app.py는 148KB짜리 옛 대시보드다.
call :mv "app.py"
call :mv "2_대시보드_실행.bat"
if exist ".streamlit" move /y ".streamlit" "%BK%\" >nul 2>&1 && echo   .streamlit\

echo.
echo === 2. 옛 스타일시트 ==============================
rem kh.css 하나로 합쳤다. 이 셋이 서로 덮어써서 사고가 났었다.
call :mvs "web\static\app.css"
call :mvs "web\static\bridge.css"
call :mvs "web\static\parity.css"
call :mv  "web\build_css.py"

echo.
echo === 3. 위험한 배치파일 ============================
rem 7c는 2026-08-29 사이트를 6시간 멈추게 한 그 파일이다.
call :mv "7_키워드_미리쌓기.bat"
call :mv "7b_키워드_미리쌓기_한번만.bat"
call :mv "7c_키워드_미리쌓기_한도무시.bat"
call :mv "4_자동수집_스케줄러용.bat"

echo.
echo === 4. 중복·일회성 배치파일 =======================
rem 깃허브 올리기는 0b 하나만 쓴다.
call :mv "0_깃허브_올리기.bat"
call :mv "5_깃허브키_보기.bat"
call :mv "6_깃허브_자동실행_만들기.bat"
call :mv "9_깃허브_준비.bat"
call :mv "8_키_진단.bat"
call :mv "GitHub_자동실행_설정.md"

echo.
echo === 5. 일회성 점검 스크립트 =======================
call :mv "diagnose.py"
call :mv "show_secrets.py"
call :mv "make_workflows.py"
call :mv "push.py"
call :mv "claude_usage.py"
call :mv "key_template.txt"
call :mv "collector_log.txt"
call :mv "ui.py.bak"

echo.
echo === 6. 작업용 스크린샷 ============================
for %%F in ("web\*.png") do (
  move /y "%%F" "%BK%\web_shots\" >nul 2>&1 && echo   %%~nxF
)

echo.
echo ============================================================
echo  끝났습니다. 옮긴 파일은 _보관\ 폴더에 있습니다.
echo  사이트를 한 번 돌려보고 문제가 없으면 _보관 폴더를 지우세요.
echo.
echo  남겨둔 것: accounts.py naver_api.py cache.py collector.py
echo             config.py ui.py ai_brief.py seed_pool.py
echo             web\ 전부, SQL 2개, 서버접속.bat, 0b 올리기,
echo             1_최초설치 3_데이터수집 8_공공데이터점검 9_주간캘린더
echo ============================================================
echo.
pause
exit /b

:mv
if exist "%~1" (move /y "%~1" "%BK%\" >nul 2>&1 && echo   %~1)
exit /b

:mvs
if exist "%~1" (move /y "%~1" "%BK%\web_static\" >nul 2>&1 && echo   %~1)
exit /b
