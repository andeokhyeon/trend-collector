# -*- coding: utf-8 -*-
"""
로그인 — 서버가 세션을 쥔다.

⚠️ 스트림릿 시절의 교훈을 그대로 가져왔다:
   · 확인코드(code_verifier)는 브라우저를 믿지 않고 서버가 보관한다
   · 세션은 도장(HMAC) 찍힌 쿠키 하나 — accounts.make_token 재사용
   · 실패하면 원문을 화면에 남긴다 (감추면 이틀을 잃는다)
"""
import os
import secrets
import time

import accounts
import db
from config import SUPABASE_URL, SUPABASE_KEY, SITE_URL

COOKIE = accounts.COOKIE          # "kh_s"
_verifiers = {}                   # vid -> (verifier, 시각)


def init():
    accounts.attach(db.client(), SUPABASE_KEY, SUPABASE_URL)


def current_user(request):
    """쿠키에서 로그인 상태를 되살린다. 없으면 None."""
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None
    return accounts.user_from_token(tok)


def start_oauth(provider, next_path="/"):
    """소셜 로그인 시작 — 이동할 주소를 돌려준다."""
    verifier, challenge = accounts.new_verifier()
    vid = secrets.token_urlsafe(9)
    now = time.time()
    for k in [k for k, (_, t) in _verifiers.items() if now - t > 1200]:
        _verifiers.pop(k, None)
    _verifiers[vid] = (verifier, now)
    site = (os.environ.get("KH_SITE") or SITE_URL or "").rstrip("/")
    back = f"{site}/auth/cb?vid={vid}&next={next_path}"
    url, _v, msg = accounts.oauth_url(provider, back, (verifier, challenge))
    return url, msg


def finish_oauth(code, vid):
    """돌아온 code를 세션으로. 반환 (토큰|None, 오류문구)."""
    got = _verifiers.pop(vid, None)
    verifier = got[0] if got else None
    ok, msg, user = accounts.exchange(code, verifier,
                                      note="표=%s" % ("있음" if verifier else "없음"))
    if not ok:
        return None, msg
    return accounts.make_token(user["id"]), ""
