@echo off
chcp 65001 > nul
title Deploy to Gabia
REM 서버 IP를 처음 한 번 적어주세요.
set SERVER=root@서버IP를여기에
echo 가비아 서버에 반영합니다...
ssh %SERVER% "cd /srv/kh/app && git pull && /srv/kh/venv/bin/pip install -q -r web/requirements.txt && systemctl restart kh-web && echo OK"
pause
