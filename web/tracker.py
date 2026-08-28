# -*- coding: utf-8 -*-
"""추적기 — app.py L1903~ 이식. 판정·문구 원본 그대로."""
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd

from uihtml import ui, render
from tables import compact_num
import db

from naver_api import (
    calc_competition, calc_search_change, calc_opportunity,
    calc_since_registered, expected_visits,
)
try:
    import ai_brief
except Exception:
    ai_brief = None


def load_tracking(uid):
    """추적 목록 + 90일 기록. (회원별 — 남의 목록이 섞이면 안 된다)"""
    sb = db.client()
    try:
        q = sb.table("tracked_keywords").select("*")
        try:
            if uid:
                tk = (q.eq("user_id", uid)
                      .order("created_at", desc=True).execute().data or [])
            else:
                tk = (sb.table("tracked_keywords").select("*")
                      .is_("user_id", "null")
                      .order("created_at", desc=True).execute().data or [])
        except Exception:
            tk = (sb.table("tracked_keywords").select("*")
                  .order("created_at", desc=True).execute().data or [])
        since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        hist = (sb.table("tracking_history").select("*")
                .gte("created_at", since).order("created_at").execute().data or [])
        return tk, hist, None
    except Exception as e:
        return [], [], str(e)


def summarize(tracked, history):
    """카드에 넣을 요약 — app.py summary 계산 그대로."""
    hdf = pd.DataFrame(history)
    if not hdf.empty:
        hdf['dt'] = pd.to_datetime(hdf['created_at'], utc=True, errors='coerce')
    summary = []
    for t in tracked:
        kw_ = t["keyword"]
        rows = (hdf[hdf['keyword'] == kw_].sort_values('dt')
                if not hdf.empty else pd.DataFrame())
        if rows.empty:
            summary.append({"keyword": kw_, "rank": None, "change": None,
                            "grade": "기록 없음", "records": 0,
                            "first_rank": None, "last_rank": None,
                            "opportunity": None, "comp_grade": None,
                            "has_post": bool(t.get("has_post")),
                            "search": None, "change_pct": None, "since": None,
                            "id": t.get("id")})
            continue
        last, first = rows.iloc[-1], rows.iloc[0]
        lr = int(last['my_rank']) if pd.notna(last.get('my_rank')) else None
        fr = int(first['my_rank']) if pd.notna(first.get('my_rank')) else None
        ts = int(last.get('total_search') or 0)
        docs = int(last.get('blog_total_docs') or 0)
        _, grade = calc_competition(ts, docs)
        change_pct = calc_search_change(
            [int(v) for v in rows['total_search'].tolist() if pd.notna(v)])
        opp = calc_opportunity(
            float(last.get('comp_ratio') or 0) or None,
            (int(last.get('recent_docs') or 0) / ts) if ts else None,
            total_search=ts, search_change_pct=change_pct)
        summary.append({
            "keyword": kw_, "rank": lr,
            "change": (fr - lr) if (fr and lr) else None,
            "grade": grade, "records": len(rows),
            "first_rank": fr, "last_rank": lr,
            "opportunity": opp["score"], "comp_grade": grade,
            "search": ts,
            "since": (first['dt'].strftime("%m/%d")
                      if pd.notna(first.get('dt')) else None),
            "has_post": bool(t.get("has_post")),
            "since_full": (first['dt'].strftime("%Y-%m-%d")
                           if pd.notna(first.get('dt')) else None),
            "compare": calc_since_registered(
                {"total_search": first.get('total_search'),
                 "blog_total_docs": first.get('blog_total_docs')},
                {"total_search": last.get('total_search'),
                 "blog_total_docs": last.get('blog_total_docs')}),
            "change_pct": change_pct,
            "visits": expected_visits(ts, lr),
            "opp_label": opp["label"],
            "opp_breakdown": opp.get("breakdown"),
            "opp_note": opp.get("note", ""),
            "id": t.get("id"),
        })
    return summary, hdf


def _detail(summary, hdf, pick):
    """선택한 키워드 상세 — app.py _render_detail 이식."""
    info = next((x for x in summary if x["keyword"] == pick), None)
    if not info:
        return ""
    out = ['<div class="box" id="detail">',
           render(ui.section, "키워드별 추이", pick)]
    rows = (hdf[hdf['keyword'] == pick].sort_values('dt')
            if not hdf.empty else pd.DataFrame())
    if rows.empty:
        out.append(render(ui.note,
                          "아직 기록이 없습니다. 다음 수집 때 첫 기록이 만들어집니다."))
        out.append('</div>')
        return "".join(out)
    latest = rows.iloc[-1]
    k1 = render(ui.kpi, "월 검색량",
                compact_num(int(latest.get('total_search') or 0)), "")
    k2 = render(ui.kpi, "이미 쓰인 글",
                compact_num(int(latest.get('blog_total_docs') or 0)), "")
    cp = info.get("change_pct")
    since = info.get("since")
    k3 = render(ui.kpi, "검색량 추세",
                f"{cp:+.0f}%" if cp is not None else "계산 중",
                "기록 3회 이상 필요" if cp is None
                else f"{since} 최초 추적일부터")
    v = info.get("visits")
    if v:
        k4 = render(ui.kpi, "예상 방문자", f"{v:,}명", "한 달에 올 사람 수")
    elif info.get("has_post"):
        k4 = render(ui.kpi, "예상 방문자", "집계 어려움",
                    "내 글이 아직 상위에 없습니다")
    else:
        k4 = render(ui.kpi, "예상 방문자", "—", "아직 이 키워드로 내 글이 없습니다")
    out.append(f'<div class="row" style="grid-template-columns:repeat(4,1fr)">'
               f'<div class="cell">{k1}</div><div class="cell">{k2}</div>'
               f'<div class="cell">{k3}</div><div class="cell">{k4}</div></div>')

    if info.get("compare"):
        since_txt = (f"{info['since_full']} 등록 · 기록 {info['records']}회"
                     if info.get("since_full") else "")
        out.append(render(ui.since_compare, info["compare"], since_txt))

    pts = [(d.strftime("%m/%d"), int(rk) if pd.notna(rk) else None)
           for d, rk in zip(rows['dt'], rows['my_rank'])]
    out.append(render(ui.rank_trend, pts, title=f"{pick} · 순위 추이"))

    if not info.get("visits"):
        if info.get("has_post"):
            out.append(render(ui.note,
                              "이 키워드로 쓴 <b>내 글</b>이 아직 상위에 노출되지 않아 "
                              "<b>예상 방문자를 집계할 수 없습니다.</b> "
                              "순위가 올라오면 자동으로 표시됩니다."))
        else:
            out.append(render(ui.note,
                              "아직 이 키워드로 쓴 <b>내 글</b>이 없어서 "
                              "<b>예상 방문자를 집계할 수 없습니다.</b> "
                              "글을 발행한 뒤 위에서 "
                              "<b>내가 쓴 키워드로 전환</b>해주세요.", True))
    if info.get("opp_breakdown"):
        out.append(render(ui.score_breakdown, info["opp_breakdown"],
                          info["opportunity"]))
    if info.get("opp_note"):
        out.append(render(ui.note,
                          f"<b>{info.get('opp_label', '')}</b> — {info['opp_note']}"))
    out.append('</div>')
    return "".join(out)


def build(uid, my_blog_id="", detail_kw="", flash=""):
    out = [render(ui.section, "키워드 추적기",
                  "저장해두면 순위 변화를 자동으로 기록합니다 · "
                  "최소 하루가 지나야 변화 정보가 제공됩니다")]
    if not my_blog_id:
        out.append(render(ui.note,
                          "블로그를 등록하면 <b>내 글의 순위 변화</b>까지 함께 기록합니다. "
                          "등록하지 않아도 검색량·문서수 변화는 추적됩니다.", True))
    if flash:
        out.append(f'<div class="kh-flash">{flash}</div>')

    # --- 추가 폼 ---
    out.append('''
<form class="search-box kh-track-add" method="post" action="/tracker/add">
  <div class="stTextInput">
    <input name="kw" placeholder="예: 제습기 추천" autocomplete="off">
  </div>
  <div class="stButton kh-primary"><button type="submit">추적 시작</button></div>
  <label class="kh-check"><input type="checkbox" name="wrote" value="1">
    이 키워드로 이미 글을 썼습니다</label>
</form>''')

    tracked, history, err = load_tracking(uid)
    if err:
        out.append(render(ui.note,
                          "추적 데이터를 불러오지 못했습니다. 함께 드린 "
                          "<code>추적기_DB설정.sql</code>을 Supabase SQL Editor에서 "
                          f"실행했는지 확인해주세요.<br><small>{err[:160]}</small>"))
        return "".join(out)
    if not tracked:
        out.append(render(ui.note,
                          "아직 추적 중인 키워드가 없습니다. 위에서 추가해보세요.<br>"
                          "기록은 2시간마다 자동으로 쌓이며, 변화 비교는 "
                          "<b>최소 하루</b>가 지나야 의미 있는 정보가 나옵니다."))
        return "".join(out)

    summary, hdf = summarize(tracked, history)

    # --- 적중률 (제품의 해자 — app.py 그대로) ---
    judged = [x for x in summary
              if x.get("has_post") and x.get("opportunity") is not None]
    ranked_any = any(x.get("rank") is not None for x in judged)
    if len(judged) >= 3 and not ranked_any:
        # ⚠️ 순위가 한 번도 안 재졌는데 0%로 보여주면 '우리 점수가 다 틀렸다'로
        #    읽힌다 (2026-08-28 피드백). 왜 비었는지를 말해준다.
        why = ("블로그를 등록하면" if not my_blog_id
               else "다음 수집부터")
        out.append(render(ui.note,
                          "발행한 글의 <b>실제 순위가 아직 기록되지 않았습니다</b>. "
                          f"{why} 내 글의 순위를 재서 점수 적중률을 보여드립니다. "
                          "(기록은 수집기가 돌 때마다 쌓입니다)", True))
    elif len(judged) >= 3:
        def _hit(x):
            return x.get("rank") is not None and x["rank"] <= 30
        buckets = [("70점 이상", 70, 101), ("40~69점", 40, 70), ("40점 미만", 0, 40)]
        rows_b = []
        for lbl, lo, hi in buckets:
            grp = [x for x in judged if lo <= int(x["opportunity"]) < hi]
            rows_b.append((lbl, len(grp), sum(1 for x in grp if _hit(x))))
        hits = sum(1 for x in judged if _hit(x))
        ranked = [x["rank"] for x in judged if x.get("rank")]
        out.append(render(ui.hit_rate, {
            "n": len(judged), "hit": hits,
            "rate": hits / len(judged) * 100,
            "avg_rank": (sum(ranked) / len(ranked)) if ranked else None,
            "buckets": rows_b}))
    elif judged:
        out.append(render(ui.note,
                          f"발행한 키워드가 <b>{len(judged)}개</b> 모였습니다. "
                          "<b>3개</b>부터 우리 점수의 적중률을 계산해 보여드립니다.",
                          True))

    mine_list = [x for x in summary if x.get("has_post")]
    watch_list = [x for x in summary if not x.get("has_post")]
    ordered = mine_list + watch_list

    out.append(render(ui.section, "추적 중인 키워드",
                      f"{len(ordered)}개 · 내가 쓴 것 {len(mine_list)}개를 앞에 둡니다"))
    out.append(render(ui.note,
                      "글을 발행했다면 카드 밑 <b>변경</b>을 눌러 "
                      "<b>내가 쓴 키워드</b>로 바꿔주세요. 그때부터 순위를 추적합니다."))

    # --- 카드 그리드 — 카드 본체는 ui.py 그대로, 버튼만 폼으로 ---
    cards = []
    for it in ordered:
        body = render(ui._one_track_card, it)
        kq = quote(it["keyword"])
        btns = (f'<div class="tc-btns">'
                f'<a class="kh-btn tc-btn" href="/tracker?detail={kq}#detail">자세히</a>'
                f'<form method="post" action="/tracker/stop">'
                f'<input type="hidden" name="id" value="{it.get("id")}">'
                f'<input type="hidden" name="kw" value="{it["keyword"]}">'
                f'<button class="kh-btn tc-btn" type="submit">중단</button></form>'
                f'<form method="post" action="/tracker/flip">'
                f'<input type="hidden" name="id" value="{it.get("id")}">'
                f'<button class="kh-btn tc-btn" type="submit" '
                f'title="{"지켜보는 중으로 되돌립니다" if it.get("has_post") else "내가 쓴 키워드로 바꿉니다"}'
                f'">변경</button></form></div>')
        cards.append(f'<div class="tc-cell">{body}{btns}</div>')
    out.append(f'<div class="tc-grid">{"".join(cards)}</div>')

    # --- AI 추적 브리핑 ---
    has_record = [x for x in summary if x["records"] > 0]
    if ai_brief is not None and ai_brief.is_enabled():
        if has_record:
            try:
                tb, terr = ai_brief.brief_tracking([
                    {"keyword": x["keyword"], "first_rank": x["first_rank"],
                     "last_rank": x["last_rank"], "records": x["records"],
                     "opportunity": x["opportunity"],
                     "comp_grade": x["comp_grade"]}
                    for x in has_record])
            except Exception as e:
                tb, terr = None, str(e)
            if tb:
                out.append(render(ui.brief_card, tb, "AI 판단 · 지금 어디에 집중할까"))
            elif terr:
                out.append(render(ui.note,
                                  f"추적 브리핑을 만들지 못했습니다. <small>{terr}</small>"))
    else:
        out.append(render(ui.note,
                          "<code>ai_brief.py</code>에 키를 넣으면 순위 변화를 읽고 "
                          "<b>무엇에 집중할지</b> 알려주는 브리핑이 여기 표시됩니다.",
                          True))

    if detail_kw and any(x["keyword"] == detail_kw for x in summary):
        # 상세는 팝업(모달)로 띄운다 (2026-08-28 요청) — 닫으면 /tracker로
        out.append('<div class="kh-modal-back" id="detail">'
                   '<div class="kh-modal">'
                   '<a class="kh-modal-x" href="/tracker" title="닫기">✕</a>'
                   + _detail(summary, hdf, detail_kw)
                   + '</div></div>')
    return "".join(out)
