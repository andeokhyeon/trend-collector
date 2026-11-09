# -*- coding: utf-8 -*-
"""
관제탑(ops)용 운영 요약 — GET /api/ops/summary

인증: Authorization: Bearer <비밀키>
  비밀키 = 서버 .env 의 OPS_SECRET, 없으면 SUPABASE_KEY 로부터 만든 파생값
           HMAC-SHA256(key=SUPABASE_KEY, msg="kh-ops-summary") 의 hex.
  ⚠️ 서버 .env 를 따로 고치지 않아도 되게 하려는 장치. SUPABASE_KEY 자체는 밖으로 나가지 않는다.
개인정보(이메일·닉네임)는 내보내지 않는다.
"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone


def expected_secret():
    s = os.environ.get("OPS_SECRET", "").strip()
    if s:
        return s
    try:
        from config import SUPABASE_KEY
    except Exception:
        SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
    if not SUPABASE_KEY:
        return ""
    return hmac.new(str(SUPABASE_KEY).encode(), b"kh-ops-summary", hashlib.sha256).hexdigest()


def authorized(header):
    exp = expected_secret()
    if not exp or not header or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[7:].strip(), exp)


def build():
    import accounts
    now = datetime.now(timezone.utc)
    kst = timezone(timedelta(hours=9))
    today_kst = datetime.now(kst).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    d7 = now - timedelta(days=7)

    members = accounts.all_members(limit=5000) or []

    def ts(v):
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except Exception:
            return None

    total = len(members)
    today = sum(1 for m in members if (ts(m.get("created_at")) or now) >= today_kst)
    week = sum(1 for m in members if (ts(m.get("created_at")) or now) >= d7)
    paid = [m for m in members if (m.get("plan") or "free") != "free" and (not m.get("plan_expires") or (ts(m.get("plan_expires")) or now) > now)]
    active7 = sum(1 for m in members if m.get("last_seen") and (ts(m.get("last_seen")) or d7) >= d7)
    mrr = sum(accounts.PLANS.get(m.get("plan") or "free", {}).get("price", 0) for m in paid)

    usage = accounts.usage_by_user(days=7) or {}
    calls7 = sum(sum(v.values()) for v in usage.values())
    analyze7 = sum(v.get("analyze", 0) for v in usage.values())

    logs = accounts.recent_credit_log(limit=20) or []
    recent = []
    for m in members[:5]:
        recent.append({"type": "signup", "at": m.get("created_at"), "text": "회원 가입 (" + str(m.get("plan") or "free") + ")"})
    for l in logs[:6]:
        kw = (l.get("keyword") or "").strip()
        recent.append({"type": "job", "at": l.get("created_at"), "text": ("크레딧 " + str(l.get("delta")) + " · " + str(l.get("reason") or "")) + (" · " + kw if kw else "")})
    recent = sorted([r for r in recent if r.get("at")], key=lambda r: str(r["at"]), reverse=True)[:8]

    alerts = []
    if not accounts.table_ready():
        alerts.append({"level": "error", "text": "회원 테이블에 연결되지 않음"})

    return {
        "site": "keywordhunter",
        "generated_at": now.isoformat(),
        "kpis": [
            {"key": "members", "label": "회원", "value": total, "sub": "7일 +" + str(week)},
            {"key": "today", "label": "오늘 가입", "value": today},
            {"key": "paid", "label": "유료 회원", "value": len(paid)},
            {"key": "mrr", "label": "월 구독액", "value": mrr, "unit": "KRW", "sub": "플랜 정가 기준"},
            {"key": "active", "label": "7일 활성", "value": active7},
            {"key": "calls", "label": "7일 조회", "value": calls7, "sub": "분석 " + str(analyze7)},
        ],
        "recent": recent,
        "alerts": alerts,
        "links": [],
    }
