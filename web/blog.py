# -*- coding: utf-8 -*-
"""내 블로그 — app.py L2243~ 이식. 문구·판정 원본 그대로."""
from datetime import datetime, timedelta, timezone

import pandas as pd

from uihtml import ui, render
from tables import table_html
import db

from naver_api import (
    get_my_blog_feed, estimate_blog_power, extract_blog_id, calc_win_score,
)


def build(user, my_blog_id="", profile=None):
    out = []

    # --- 로그인 헤더 + 로그아웃 ---
    if user:
        name = ((profile or {}).get("nickname")
                or (user.get("email") or "").split("@")[0] or "회원")
        credits = (profile or {}).get("credits")
        mail = user.get("email") or ""
        line = (f"<b>{name}</b>" + (f" ({mail})" if mail else "") + " 로 로그인 중"
                + (f"　·　남은 크레딧 <b>{int(credits):,}</b>"
                   if credits is not None else ""))
        out.append(f'<div class="kh-row-split"><div class="kh-cap">{line}</div>'
                   f'<form method="post" action="/logout">'
                   f'<button class="kh-btn" type="submit">로그아웃</button>'
                   f'</form></div>')

    out.append(render(ui.section, "내 블로그 진단", "지금 내 블로그는 어떤 상태인가"))

    # --- 블로그 주소 입력 (한 곳뿐 — app.py와 동일) ---
    out.append(f'''
<form class="search-box" method="post" action="/blog/set">
  <div class="stTextInput">
    <input name="blog" value="{my_blog_id}"
           placeholder="blog.naver.com/myid  또는  myid" autocomplete="off">
  </div>
  <div class="stButton kh-primary"><button type="submit">저장</button></div>
</form>''')

    if not my_blog_id:
        out.append(render(ui.note,
                          "위 칸에 블로그 주소를 넣어주세요. "
                          "예: <code>blog.naver.com/myid</code> 또는 <code>myid</code>",
                          True))
        return "".join(out)

    try:
        feed = get_my_blog_feed(my_blog_id)
    except Exception:
        feed = {"posts": [], "error": "블로그를 읽지 못했습니다"}

    if feed["error"]:
        out.append(render(ui.note,
                          f"{feed['error']}<br>아이디가 맞는지, 블로그가 공개 상태인지 "
                          "확인해주세요."))
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
            out.append(render(ui.note,
                              "최근 12주 중 절반 이상 글이 없습니다. "
                              "발행 간격이 벌어지면 노출에 불리하게 작용하는 경향이 있습니다."))
        elif empty_weeks == 0:
            out.append(render(ui.note,
                              "12주 내내 빠짐없이 발행했습니다. 꾸준함이 잘 유지되고 있습니다.",
                              True))
        wd_names = ['월', '화', '수', '목', '금', '토', '일']
        wd_count = {i: 0 for i in range(7)}
        for d in dated:
            wd_count[d.weekday()] += 1
        out.append(render(ui.bar_series,
                          [(wd_names[i], wd_count[i]) for i in range(7)],
                          "요일별 발행 분포", height=130, accent=ui.GOOD))

    out.append(render(ui.note,
                      "네이버는 블로그 지수를 공개하지 않습니다. 여기 점수는 "
                      "<b>공개된 RSS로 관측한 발행 빈도와 최근성</b>을 조합한 추정치이며, "
                      "네이버 내부 지수와는 다릅니다. 꾸준한 발행이 노출에 유리하다는 "
                      "일반적 경향을 참고 지표로 만든 것입니다."))

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

    out.append(render(ui.section, "골든타임 대조",
                      "지금 뜨는 키워드 중 내가 노려볼 만한 것"))
    df = db.load_data()
    golden = (db.latest_snapshot(df[df['source'] == 'golden_time'], hours=24)
              if not df.empty else pd.DataFrame())
    if golden.empty:
        out.append(render(ui.note,
                          "골든타임 데이터가 아직 없습니다. collector.py를 실행해주세요."))
    else:
        top = golden.sort_values('rise_score', ascending=False).head(10)
        rows = []
        for _, row in top.iterrows():
            ratio = row.get('comp_ratio') or None
            win = calc_win_score(ratio if ratio else None, power["score"])
            rows.append({"키워드": row['keyword'],
                         "월 검색량": int(row['총 검색량']),
                         "경쟁률": row.get('comp_grade', '정보없음'),
                         "내 승산": (f"{win['score']}점"
                                   if win["score"] is not None else "—"),
                         "판단": win["verdict"]})
        wdf = pd.DataFrame(rows)
        wdf.index = wdf.index + 1
        out.append(table_html(wdf))
    return "".join(out)


__all__ = ["build", "extract_blog_id"]
