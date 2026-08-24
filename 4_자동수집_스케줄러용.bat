@echo off
cd /d "%~dp0"
REM Register this file in Windows Task Scheduler.
REM Do not run manually - use 3 instead.
python collector.py >> collector_log.txt 2>&1
