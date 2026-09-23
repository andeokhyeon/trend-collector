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
        f"관심 키워드 <b>{p['track']}개</b>",
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
        out.append(render(ui.tip,
                          f"<b>프로 체험 중</b> · 남은 기간 {left}일"))
    out.append('<div class="pr-grid">'
               + "".join(_card(k, cur, trial)
                         for k in ("free", "basic", "pro", "master"))
               + '</div>')
    out.append(render(
        ui.tip,
        "월결제 오픈 준비 중 — 지금 필요하시면 "
        '<a href="/me">마이페이지</a>의 이메일로 문의해주세요. '
        "조회 1회 = 크레딧 1개 · 같은 키워드는 그날 무료."))
    return "".join(out)
