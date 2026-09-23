# -*- coding: utf-8 -*-
"""발행 진단 — 내 블로그의 공개 RSS만 본다.

⚠️ 2026-09-23: 아래에 있던 '골든타임 대조(내 승산)'를 뺐다. 경쟁률(블로그 검색
   문서수, 검색 API 값)로 승산을 매기던 것이라 네이버 회신(9/22)대로 못 쓴다.
   이 화면은 본인 블로그의 공개 RSS(발행 리듬·요일·최근 글)만 쓴다.
"""
from datetime import datetime, timedelta, timezone

import pandas as pd

from uihtml import ui, render
from tables import table_html
import db

from naver_api import (
    get_my_blog_feed, estimate_blog_power, extract_blog_id,
)


def build(user, my_blog_id="", profile=None):
    out = []

    # ⚠️ 2026-09-22: 계정·크레딧·로그아웃 줄을 여기서 지웠다.
    #    상단바의 내 이름 알약과 마이페이지가 이미 같은 말을 하고 있어서,
    #    이 페이지에만 계정 띠가 하나 더 붙어 화면이 정리가 안 돼 보였다.

    out.append(render(ui.section, "내 블로그 진단", "지금 내 블로그는 어떤 상태인가"))

    # 주소 입력은 마이페이지로 옮겼다 (2026-08-28) — 매번 치지 않게 계정에 저장
    if not my_blog_id:
        out.append(render(ui.note,
                          "아직 블로그 주소가 등록되지 않았습니다. "
                          '<a href="/me">마이페이지</a>에서 한 번만 등록하면 '
                          "여기서 바로 진단해드립니다.", True))
        return "".join(out)
    out.append(render(ui.tip,
                      f"진단 대상 <code>{my_blog_id}</code> · "
                      '<a href="/me">주소 변경</a>'))

    try:
        feed = get_my_blog_feed(my_blog_id)
    except Exception:
        feed = {"posts": [], "error": "블로그를 읽지 못했습니다"}

    if feed["error"]:
        out.append(render(ui.note,
                          f"{feed['error']} — 아이디와 공개 상태를 확인해주세요."))
        return "".join(out)

    power = estimate_blog_power(feed["posts"])
    posts = feed["posts"]

    k1 = render(ui.kpi, "주당 발행", f"{power['posts_per_week']}편", "최근 90일 평균")
    gap = power.get('avg_gap_days')
    k2 = render(ui.kpi, "평균 발행 간격",
                f"{gap}일" if gap is not None else "—", "글과 글 사이")
    last_txt = (f"{power['days_since_last']}일 전"
                if power['days_since_last'] is not None else "—")
    k3 = render(ui.kpi, "마지막 글", last_txt, "최근 발행일")
    k4 = render(ui.kpi, "활동 등급", power['level'], f"수집된 글 {len(posts)}편")
    out.append(f'<div class="row" style="grid-template-columns:repeat(4,1fr)">'
               f'<div class="cell">{k1}</div><div class="cell">{k2}</div>'
               f'<div class="cell">{k3}</div><div class="cell">{k4}</div></div>')

    out.append(render(ui.gauge, "발행 활동성", power["score"],
                      ("휴면", "보통", "매우활발")))

    dated = [p["date"] for p in posts if p.get("date")]
    if dated:
        today = datetime.now(timezone.utc).date()
        this_mon = today - timedelta(days=today.weekday())
        buckets = {}
        for d in dated:
            off = (this_mon - (d.date() - timedelta(days=d.weekday()))).days // 7
            if 0 <= off <= 11:
                buckets[off] = buckets.get(off, 0) + 1
        series = []
        for off in range(11, -1, -1):
            ws = this_mon - timedelta(weeks=off)
            label = "이번주" if off == 0 else ws.strftime("%m/%d")
            series.append((label, buckets.get(off, 0)))
        out.append(render(ui.bar_series, series, "최근 12주 발행 리듬",
                          accent=ui.DEEP))
        empty_weeks = sum(1 for _, v in series if v == 0)
        if empty_weeks >= 6:
            out.append(render(ui.tip,
                              "최근 12주 중 절반 이상 글이 없습니다 — 간격이 벌어지면 "
                              "노출에 불리한 경향이 있습니다."))
        elif empty_weeks == 0:
            out.append(render(ui.tip, "12주 내내 빠짐없이 발행했습니다."))
        wd_names = ['월', '화', '수', '목', '금', '토', '일']
        wd_count = {i: 0 for i in range(7)}
        for d in dated:
            wd_count[d.weekday()] += 1
        out.append(render(ui.bar_series,
                          [(wd_names[i], wd_count[i]) for i in range(7)],
                          "요일별 발행 분포", height=130, accent=ui.GOOD))

    out.append(
        '<details class="kh-more"><summary>이 점수는 어떻게 나온 건가요</summary>'
        '<p>네이버는 블로그 지수를 공개하지 않습니다. 여기 점수는 공개된 RSS로 '
        '관측한 <b>발행 빈도와 최근성</b>을 조합한 추정치이며, 네이버 내부 지수와는 '
        '다릅니다. 꾸준한 발행이 노출에 유리하다는 일반적 경향을 참고 지표로 '
        '만든 것입니다.</p></details>')

    if posts:
        out.append(render(ui.section, "최근 발행", "내가 최근에 쓴 글"))
        now_ = datetime.now(timezone.utc)
        rows = []
        for i, p in enumerate(posts[:20]):
            d = p["date"]
            gap2 = ""
            if d and i + 1 < len(posts) and posts[i + 1]["date"]:
                gap2 = f"{(d - posts[i + 1]['date']).days}일"
            rows.append({"제목": p["title"],
                         "발행일": d.strftime("%Y-%m-%d") if d else "—",
                         "경과": f"{(now_ - d).days}일 전" if d else "—",
                         "직전 글과 간격": gap2 or "—"})
        pdf = pd.DataFrame(rows)
        pdf.index = pdf.index + 1
        out.append(table_html(pdf))

    return "".join(out)


__all__ = ["build", "extract_blog_id"]
