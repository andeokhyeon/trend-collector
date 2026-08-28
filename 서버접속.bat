@echo off
title 키워드헌터 서버 접속
set KEY=C:\Users\dog11\Desktop\안덕현\SSH_KeyPair-260828140336.pem

if not exist "%KEY%" (
  echo.
  echo  [!] 열쇠 파일을 못 찾았습니다.
  echo      찾는 위치: %KEY%
  echo      SSH_KeyPair-....pem 파일 위치를 확인해주세요.
  echo.
  pause
  exit /b
)

echo.
echo  열쇠 파일 권한 정리 중...
icacls "%KEY%" /inheritance:r >nul 2>&1
icacls "%KEY%" /grant:r "%USERNAME%":R >nul 2>&1

echo  서버에 접속합니다.  (처음이면 yes 입력 후 엔터)
echo  ------------------------------------------------------
echo.
ssh -o StrictHostKeyChecking=accept-new -i "%KEY%" ubuntu@1.201.118.198

echo.
echo  ------------------------------------------------------
echo  접속이 끝났습니다.
pause
