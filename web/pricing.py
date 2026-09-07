# -*- coding: utf-8 -*-
"""요금 안내(/pricing) — 플랜 비교와 체험 상태. (2026-09-05 신설)"""
from uihtml import ui, render

import plans as _plans


def _card(key, cur_key, trial):
    p = _plans.PLANS[key]
    price = "0원" if not p["price"] else f"{p['price']:,}원"
    per = "" if not p["price"] else '<span class="pr-per">/월</span>'
    feats = [
        f"키워드 조회 <b>{'가입 시 ' if key == 'free' else '월 '}{p['credits']:,}회</b>",
        f"추적 키워드 <b>{p['track']}개</b>",
        ("CSV 내려받기" if p["csv"] else
         '<span class="pr-no">CSV 내려받기</span>'),
        ("AI 진단" if p["ai"] else
         '<span class="pr-no">AI 진단</span>'),
    ]
    if key == "master":
        feats.append("우선 지원")
    tag = ""
    if key == cur_key:
        tag = ('<span class="pr-tag pr-now">체험 중</span>' if trial
               else '<span class="pr-tag pr-now">내 플랜</span>')
    elif key == "pro":
        tag = '<span class="pr-tag pr-pop">인기</span>'
    lis = "".join(f"<li>{f}</li>" for f in feats)
    cls = "pr-card" + (" pr-cur" if key == cur_key else "")
    return (f'<div class="{cls}">{tag}'
            f'<div class="pr-name">{p["name"]}</div>'
            f'<div class="pr-price">{price}{per}</div>'
            f'<p class="pr-blurb">{p["blurb"]}</p>'
            f'<ul class="pr-feats">{lis}</ul></div>')


def build(prof=None, why=""):
    cur, trial = _plans.effective(prof)
    out = [render(ui.section, "요금 안내", "필요한 만큼만, 월 단위로")]
    if why:
        out.append(_plans.upgrade_box(why))
    left = _plans.trial_left_days(prof)
    if trial and left:
        out.append(render(ui.note,
                          f"지금 <b>프로 체험 중</b>입니다 — 남은 기간 "
                          f"<b>{left}일</b>. 체험이 끝나면 무료 플랜으로 "
                          "돌아갑니다."))
    out.append('<div class="pr-grid">'
               + "".join(_card(k, cur, trial)
                         for k in ("free", "basic", "pro", "master"))
               + '</div>')
    out.append(render(
        ui.note,
        "월결제는 <b>오픈 준비 중</b>입니다. 지금 유료 플랜이 필요하시면 "
        "마이페이지의 이메일로 문의해주세요 — 오픈 전에는 수동으로 "
        "충전해드립니다. 크레딧은 키워드 조회 1회에 1개, <b>같은 키워드는 "
        "그날 다시 봐도 무료</b>입니다."))
    return "".join(out)
