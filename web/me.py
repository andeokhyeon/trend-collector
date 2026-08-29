# -*- coding: utf-8 -*-
"""마이페이지 — 내 계정·크레딧·사용 내역. (2026-08-28 신설)"""
from datetime import datetime, timedelta, timezone

from uihtml import ui, render

_PLAN = {"free": "무료", "basic": "베이직", "pro": "프로"}


def _kst(iso):
    """UTC ISO 문자열 → 'MM/DD HH:MM' (한국시간)."""
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        d = d.astimezone(timezone(timedelta(hours=9)))
        return d.strftime("%m/%d %H:%M")
    except Exception:
        return "—"


def build(user, prof, blog_id=""):
    prof = prof or {}
    out = [render(ui.section, "마이페이지", "내 계정과 크레딧")]

    name = (prof.get("nickname")
            or (user.get("email") or "").split("@")[0] or "회원")
    email = prof.get("email") or user.get("email") or "—"
    plan = _PLAN.get(str(prof.get("plan") or "free"), str(prof.get("plan") or "무료"))
    credits = prof.get("credits")
    joined = _kst(prof.get("created_at")) if prof.get("created_at") else "—"

    k1 = render(ui.kpi, "남은 크레딧",
                f"{int(credits):,}" if credits is not None else "—",
                "키워드 조회 1회에 1개 · 같은 키워드는 그날 무료")
    k2 = render(ui.kpi, "플랜", plan, "충전·업그레이드는 준비 중입니다")
    k3 = render(ui.kpi, "가입", joined, "")
    out.append(f'<div class="row" style="grid-template-columns:repeat(3,1fr)">'
               f'<div class="cell">{k1}</div><div class="cell">{k2}</div>'
               f'<div class="cell">{k3}</div></div>')

    # 계정 정보
    out.append('<div class="box">')
    out.append(render(ui.section, "계정", ""))
    rows = [("닉네임", name), ("이메일", email),
            ("내 블로그", blog_id or "미설정 — 아래에서 등록해주세요")]
    out.append('<div class="me-rows">' + "".join(
        f'<div class="me-row"><span class="me-k">{k}</span>'
        f'<span class="me-v">{v}</span></div>' for k, v in rows) + '</div>')
    out.append('</div>')

    # 블로그 주소 — 여기서 한 번 등록하면 계정에 저장된다 (2026-08-28)
    out.append('<div class="box">')
    out.append(render(ui.section, "내 블로그 주소",
                      "한 번 등록하면 모든 화면에서 내 글을 금색으로 표시합니다"))
    out.append(f"""
<form class="search-box" method="post" action="/me/blog">
  <div class="stTextInput">
    <input name="blog" value="{blog_id}"
           placeholder="blog.naver.com/myid  또는  myid" autocomplete="off">
  </div>
  <div class="stButton kh-primary"><button type="submit">저장</button></div>
</form>""")
    out.append('</div>')

    out.append('<p class="kh-guide-link" style="text-align:left">'
               '<a href="/guide">이용 가이드 보기 →</a></p>')

    # 로그아웃 — POST 폼 (링크로 하면 미리보기 봇이 눌러버린다)
    out.append(
        '<form method="post" action="/logout" style="margin-top:18px">'
        '<button class="kh-btn me-logout" type="submit">로그아웃</button></form>')
    return "".join(out)
