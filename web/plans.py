# -*- coding: utf-8 -*-
"""
플랜(요금제)과 권한 — 서버가 문을 지킨다. (2026-09-05 신설)

⚠️ 설계 원칙
   · accounts.py(공용 두뇌, 크레딧 원장)는 건드리지 않는다.
     플랜 표만 accounts.PLANS에 얹고(관리 콘솔 드롭다운용),
     기능 권한(추적 한도·CSV·AI)은 전부 이 파일이 판정한다.
   · 체험(트라이얼)은 plan 컬럼을 바꾸지 않는다.
     profiles.trial_ends_at 만 보고 "지금은 프로 대우"를 계산한다.
     그래서 체험이 끝나도 크레딧 원장은 아무 일도 없다.
   · DB에 trial 컬럼이 아직 없어도 사이트는 그대로 돈다 (전부 best-effort).

체험: 가입 시 자동 부여는 하지 않는다 (2026-09-07 결정 — 없앴다).
   다만 profiles.trial_ends_at에 날짜를 넣으면 그때까지 프로 대우가 되므로,
   관리자가 이벤트로 특정 회원에게 수동으로 줄 수는 있다.
"""
import os
from datetime import datetime, timezone

# ── 플랜 표 ─────────────────────────────────────────────
#  name/credits/price 는 관리 콘솔(admin.py)이 그대로 읽는 키라 이름을 지킨다.
#  credits = 월 제공 크레딧(키워드 조회 횟수), track = 추적 키워드 한도.
PLANS = {
    "free":   {"name": "무료",   "credits": 3,    "price": 0,
               "track": 3,   "csv": False, "ai": False,
               "blurb": "가입하면 조회 3회 — 맛보기"},
    "basic":  {"name": "베이직", "credits": 300,  "price": 9900,
               "track": 10,  "csv": True,  "ai": False,
               "blurb": "취미 블로거 — 조회와 CSV까지"},
    "pro":    {"name": "프로",   "credits": 1000, "price": 19900,
               "track": 30,  "csv": True,  "ai": True,
               "blurb": "수익 블로거 — AI 진단까지 전부"},
    "master": {"name": "마스터", "credits": 3000, "price": 48300,
               "track": 100, "csv": True,  "ai": True,
               "blurb": "대량 운영 — 한도 걱정 없이"},
}

def install():
    """accounts.PLANS에 4단계 표를 얹는다 — 관리 콘솔 플랜 변경 드롭다운용."""
    try:
        import accounts
        accounts.PLANS.update(PLANS)
    except Exception:
        pass


# ── 체험 판정 ───────────────────────────────────────────
def _parse(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except Exception:
        return None


def trial_left_days(prof):
    """체험이 살아 있으면 남은 일수(1 이상), 아니면 0."""
    end = _parse((prof or {}).get("trial_ends_at"))
    if not end:
        return 0
    left = (end - datetime.now(timezone.utc)).total_seconds() / 86400
    return max(0, int(left) + 1) if left > 0 else 0


def effective(prof):
    """(플랜키, 체험중여부) — 무료 회원이라도 체험 중이면 프로 대우."""
    plan = str((prof or {}).get("plan") or "free")
    if plan not in PLANS:
        plan = "free"
    if plan == "free" and trial_left_days(prof) > 0:
        return "pro", True
    return plan, False


def _feat(prof, key):
    plan, _ = effective(prof)
    return PLANS[plan].get(key)


def allow_ai(prof):
    return bool(_feat(prof, "ai"))


def allow_csv(prof):
    return bool(_feat(prof, "csv"))


def track_limit(prof):
    return int(_feat(prof, "track") or 3)


# ── 업그레이드 안내 상자 ────────────────────────────────
_WHY = {
    "ai":    ("AI 진단은 프로 플랜부터",
              "검색량·경쟁·추세를 AI가 읽고 <b>글 쓸지 말지</b>까지 "
              "판정해주는 기능입니다."),
    "csv":   ("CSV 내려받기는 베이직 플랜부터",
              "연관 키워드 전체를 파일로 받아 엑셀에서 정리할 수 있습니다."),
    "track": ("추적 키워드가 한도에 닿았습니다",
              "플랜을 올리면 더 많은 키워드를 매일 자동으로 지켜봅니다."),
    "credit": ("크레딧을 다 쓰셨습니다",
               "플랜을 올리면 매달 크레딧이 새로 채워집니다."),
}


def upgrade_box(why="credit"):
    from uihtml import ui, render
    title, body = _WHY.get(why, _WHY["credit"])
    return render(
        ui.pitch, title, "요금 안내에서 플랜을 비교해보세요",
        body + ' <a href="/pricing">요금 안내 보기 →</a>')
