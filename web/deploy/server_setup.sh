#!/bin/bash
# ============================================================
# 키워드 헌터 — 가비아 g클라우드(우분투) 첫 설정. 딱 한 번 실행.
#
# 사용법 (서버에 접속한 뒤):
#   sudo bash server_setup.sh <깃허브주소> <도메인>
#   예) sudo bash server_setup.sh https://github.com/andeokhyeon/trend-collector.git keywordhunter.co.kr
#
# 하는 일:
#   ① 파이썬·nginx 설치  ② 코드 받기  ③ 항상 켜져 있게 등록(systemd)
#   ④ 도메인 연결(nginx)  ⑤ HTTPS 자물쇠(certbot, 자동갱신)
# ============================================================
set -e
REPO="${1:?깃허브 주소를 첫 인자로 주세요}"
DOMAIN="${2:?도메인을 둘째 인자로 주세요}"
APP=/srv/kh/app
VENV=/srv/kh/venv

echo "== [1/6] 프로그램 설치 =="
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx

echo "== [2/6] 코드 받기 =="
mkdir -p /srv/kh
if [ ! -d "$APP/.git" ]; then
  git clone "$REPO" "$APP"
else
  git -C "$APP" pull
fi

echo "== [3/6] 파이썬 준비 =="
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$APP/web/requirements.txt"

echo "== [4/6] 항상 켜져 있게 등록 =="
cat > /etc/systemd/system/kh-web.service <<UNIT
[Unit]
Description=Keyword Hunter Web
After=network.target

[Service]
WorkingDirectory=$APP/web
# ⚠️ 키는 코드가 아니라 이 파일이 읽는 $APP/.env 에 둔다 (깃허브에 안 올라감)
ExecStart=$VENV/bin/uvicorn main:app --host 127.0.0.1 --port 8600 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now kh-web

echo "== [5/6] 도메인 연결(nginx) =="
cat > /etc/nginx/sites-available/kh <<NGINX
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    location / {
        proxy_pass http://127.0.0.1:8600;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/kh /etc/nginx/sites-enabled/kh
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "== [6/6] HTTPS 자물쇠 =="
echo "   (도메인의 DNS가 이 서버 IP를 가리키고 있어야 성공합니다)"
certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos \
  -m dog1128@nate.com --redirect || \
  echo "⚠️ 자물쇠 발급 실패 — DNS가 아직 안 퍼졌을 수 있습니다. 몇 시간 뒤: certbot --nginx -d $DOMAIN -d www.$DOMAIN"

echo ""
echo "============================================"
echo "  끝. 확인:  https://$DOMAIN"
echo "  ⚠️ 남은 일: $APP/.env 파일에 API 키 넣기 (PC의 .env 내용 복사)"
echo "     넣은 뒤:  systemctl restart kh-web"
echo "============================================"
