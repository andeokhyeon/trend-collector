@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"
REM 윈도우 작업 스케줄러에 이 파일을 등록하세요.
REM 직접 실행하지 마세요 - 그럴 때는 3번을 쓰세요.
python collector.py >> collector_log.txt 2>&1
