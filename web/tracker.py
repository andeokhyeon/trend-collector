# -*- coding: utf-8 -*-
"""관심 키워드 (예전 '순위 추적').

⚠️ 2026-09-23 재구성. 예전엔 '내 글 순위'가 이 화면의 주인공이었는데,
   순위는 네이버 블로그 검색(검색 API)으로 쟀다 — 회신(9/22)대로 못 쓴다.
   문서수·경쟁률·기회 점수·점수 적중률도 같은 이유로 뺐다.
   남은 질문은 하나다: "내가 찍어둔 키워드, 지금 돈이 되나?"
     · 월 검색량과 그 추세  — 수집기가 매일 남기는 기록 (검색광고 API 값)
     · 지금 단가            — 화면을 열 때 조회 (db.cached_min_bids, 6시간 기억)
     · 판정                  — naver_api.calc_money_verdict (검사 화면과 같은 기준)
"""
from datetime import datetime, timedelta, timezone
from html import escape as _esc
from urllib.parse import quote

import pandas as pd

from uihtml import ui, render
from tables import compact_num
import db

from naver_api import calc_search_change, calc_money_verdict, estimate_monthly_income
try:
    import ai_brief
except Exception:
    ai_brief = None


def load_tracking(uid):
    """관심 목록 + 90일 기록. (회원별 — 남의 목록이 섞이면 안 된다)

    60초 캐시하되, 추가·중단 때 store의 판이 바뀌므로 바뀐 즉시 새로 읽는다."""
    import store
    ver = store.get("trackver", uid) or "0"
    return db._memo(("track", uid, ver), 60, lambda: _load_tracking(uid))


def _load_tracking(uid):
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
        if not tk:
            return [], [], None
        since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        kws = list({x["keyword"] for x in tk})
        # ⚠️ 검색량·날짜만 받는다 — 옛 기록에 남은 순위·문서수 열은 읽지도 않는다
        hist = (sb.table("tracking_history").select("keyword,total_search,created_at")
                .in_("keyword", kws)
                .gte("created_at", since).order("created_at").execute().data or [])
        return tk, hist, None
    except Exception as e:
        return [], [], str(e)


def summarize(tracked, history):
    """카드에 넣을 요약. 단가는 여기서 한 번에 묶어 조회한다."""
    hdf = pd.DataFrame(history)
    if not hdf.empty:
        hdf['dt'] = pd.to_datetime(hdf['created_at'], utc=True, errors='coerce')
    try:
        bids = db.cached_min_bids(tuple(t["keyword"] for t in tracked)) or {}
    except Exception:
        bids = {}
    summary = []
    for t in tracked:
        kw_ = t["keyword"]
        rows = (hdf[hdf['keyword'] == kw_].sort_values('dt')
                if not hdf.empty else pd.DataFrame())
        bid = bids.get(kw_)
        if rows.empty:
            summary.append({"keyword": kw_, "records": 0, "search": None,
                            "change_pct": None, "since": None, "since_full": None,
                            "first_search": None, "bid": bid,
                            "verdict": calc_money_verdict(bid, 0), "id": t.get("id")})
            continue
        vals = [int(v) for v in rows['total_search'].tolist() if pd.notna(v)]
        last, first = rows.iloc[-1], rows.iloc[0]
        ts = int(last.get('total_search') or 0)
        chg = calc_search_change(vals)
        summary.append({
            "keyword": kw_, "records": len(rows), "search": ts,
            "change_pct": chg, "bid": bid,
            "first_search": int(first.get('total_search') or 0),
            "since": (first['dt'].strftime("%m/%d") if pd.notna(first.get('dt')) else None),
            "since_full": (first['dt'].strftime("%Y-%m-%d") if pd.notna(first.get('dt')) else None),
            "verdict": calc_money_verdict(bid, ts, chg),
            "id": t.get("id"),
        })
    return summary, hdf


def _card(it):
    """관심 키워드 카드 — 큰 숫자는 단가, 그 아래 검색량과 추세."""
    v = it["verdict"]
    bid = it.get("bid")
    ts = it.get("search")
    chg = it.get("change_pct")
    if chg is None:
        chg_html = '<div class="tc-chg tc-flat">추세 · 기록 3회부터</div>'
    else:
        cls = "tc-up" if chg >= 10 else ("tc-down" if chg <= -10 else "tc-flat")
        arrow = "↑" if chg >= 10 else ("↓" if chg <= -10 else "·")
        chg_html = f'<div class="tc-chg {cls}">검색 {arrow} {chg:+.0f}%</div>'
    since = f'<div class="tc-sub">{it["since"]} 부터 기록</div>' if it.get("since") else \
            '<div class="tc-sub">다음 수집 때 첫 기록이 쌓입니다</div>'
    return (
        '<div class="track-card">'
        f'<div class="tc-head"><span class="tc-tag">관심 키워드</span></div>'
        f'<div class="tc-kw">{_esc(it["keyword"])}</div>'
        f'<div class="tc-rank tc-money">{f"{int(bid):,}원" if bid else "—"}</div>'
        f'<div class="tc-sub">클릭단가 · 월 검색량 {compact_num(ts) if ts else "—"}</div>'
        f'{chg_html}{since}'
        f'<div class="tc-meta"><span class="tc-verdict tone-{v["tone"]}">{_esc(v["label"])}</span>'
        f'<span class="tc-rec">기록 {it["records"]}회</span></div>'
        '</div>')


def _detail(summary, hdf, pick):
    """선택한 키워드 상세 — 검색량 추이와 돈 판정."""
    info = next((x for x in summary if x["keyword"] == pick), None)
    if not info:
        return ""
    out = ['<div class="box" id="detail">',
           render(ui.section, "관심 키워드", pick)]
    bid, ts, cp = info.get("bid"), info.get("search"), info.get("change_pct")
    k1 = render(ui.kpi, "지금 클릭단가", f"{int(bid):,}원" if bid else "—",
                "최소노출입찰가 · 오늘 조회")
    k2 = render(ui.kpi, "월 검색량", compact_num(ts) if ts else "—",
                f"등록 때 {compact_num(info['first_search'])}" if info.get("first_search") else "")
    k3 = render(ui.kpi, "검색량 추세", f"{cp:+.0f}%" if cp is not None else "계산 중",
                "기록 3회 이상 필요" if cp is None else f"{info.get('since')} 부터")
    try:
        inc = estimate_monthly_income(ts, 3) if ts else None
    except Exception:
        inc = None
    k4 = render(ui.kpi, "3위 시 월 수익",
                f"{int(inc[0]):,}~{int(inc[1]):,}원" if inc and inc[0] else "—",
                "애드포스트 기준 추정")
    out.append(f'<div class="row" style="grid-template-columns:repeat(4,1fr)">'
               f'<div class="cell">{k1}</div><div class="cell">{k2}</div>'
               f'<div class="cell">{k3}</div><div class="cell">{k4}</div></div>')
    rows = (hdf[hdf['keyword'] == pick].sort_values('dt')
            if not hdf.empty else pd.DataFrame())
    pts = [(d.strftime("%Y-%m-%d"), int(v)) for d, v in zip(rows['dt'], rows['total_search'])
           if pd.notna(d) and pd.notna(v)] if not rows.empty else []
    if len(pts) >= 4:
        out.append(render(ui.trend_chart, pts, title=f"{pick} · 기록된 월 검색량",
                          change_pct=cp))
    else:
        out.append(render(ui.tip, "기록이 4회 이상 쌓이면 검색량 추이 그래프가 나옵니다."))
    v = info["verdict"]
    out.append(render(ui.tip, f"<b>{_esc(v['label'])}</b> — {_esc(v['note'])}"))
    out.append('</div>')
    return "".join(out)


def build(uid, my_blog_id="", detail_kw="", flash="", ai=False):
    out = [render(ui.section, "관심 키워드",
                  "찍어둔 키워드의 검색량을 매일 기록하고, 지금 단가와 함께 보여줍니다")]
    if flash:
        out.append(f'<div class="kh-flash">{_esc(flash)}</div>')

    out.append('''
<form class="search-box kh-track-add" method="post" action="/tracker/add">
  <div class="stTextInput">
    <input name="kw" placeholder="예: 제습기 추천" autocomplete="off">
  </div>
  <div class="stButton kh-primary"><button type="submit">담아두기</button></div>
</form>''')

    tracked, history, err = load_tracking(uid)
    if err:
        out.append(render(ui.note, "관심 키워드를 불러오지 못했습니다. "
                                   f"<small>{_esc(err[:160])}</small>"))
        return "".join(out)
    if not tracked:
        out.append(render(ui.note, "아직 담아둔 키워드가 없습니다 — 위에서 추가해보세요."))
        out.append(render(ui.tip, "검색량은 매일 자동으로 기록되고, 추세는 기록 3회부터 나옵니다."))
        return "".join(out)

    summary, hdf = summarize(tracked, history)
    # 단가 높은 순 — 이 제품의 질문이 '돈이 되나'라서
    ordered = sorted(summary, key=lambda x: -(x.get("bid") or 0))
    out.append(render(ui.tip, f"<b>{len(ordered)}개</b> · 지금 단가 높은 순"))

    cards = []
    for it in ordered:
        kq = quote(it["keyword"])
        btns = (f'<div class="tc-btns">'
                f'<a class="kh-btn tc-btn" href="/tracker?detail={kq}#detail">자세히</a>'
                f'<a class="kh-btn tc-btn" href="/?q={kq}">검사</a>'
                f'<form method="post" action="/tracker/stop">'
                f'<input type="hidden" name="id" value="{it.get("id")}">'
                f'<input type="hidden" name="kw" value="{_esc(it["keyword"])}">'
                f'<button class="kh-btn tc-btn" type="submit">빼기</button></form></div>')
        cards.append(f'<div class="tc-cell">{_card(it)}{btns}</div>')
    out.append(f'<div class="tc-grid">{"".join(cards)}</div>')

    # --- AI 브리핑 — 버튼을 눌렀을 때만 ---
    has_record = [x for x in summary if x["records"] > 0]
    if ai_brief is not None and ai_brief.is_enabled() and has_record:
        if not ai:
            out.append(
                '<a class="kh-ai-cta" id="ai" href="/tracker?ai=1#ai">'
                '<span class="kh-ai-badge">AI</span>'
                '<span class="kh-ai-main">AI 진단 보기</span>'
                '<span class="kh-ai-sub">검색 수요와 단가를 읽고 '
                '<b>지금 어디에 집중할지</b></span></a>')
        else:
            # AI에는 검색광고 값(검색량·단가)만 넘긴다 — ai_brief 주석 참고
            try:
                tb, terr = ai_brief.brief_tracking([
                    {"keyword": x["keyword"], "records": x["records"],
                     "total_search": x.get("search"), "min_bid": x.get("bid")}
                    for x in has_record])
            except Exception as e:
                tb, terr = None, str(e)
            if tb:
                out.append('<div id="ai"></div>')
                out.append(render(ui.brief_card, tb, "AI 판단 · 지금 어디에 집중할까"))
            elif terr:
                out.append(render(ui.note,
                                  f"브리핑을 만들지 못했습니다. <small>{_esc(str(terr))}</small>"))

    if detail_kw and any(x["keyword"] == detail_kw for x in summary):
        out.append(
            '<div class="kh-modal-back" id="detail" '
            'onclick="if(event.target===this){this.remove();'
            'history.replaceState(null,\'\',\'/tracker\');}">'
            '<div class="kh-modal">'
            '<a class="kh-modal-x" href="/tracker" title="닫기" '
            'onclick="this.closest(\'.kh-modal-back\').remove();'
            'history.replaceState(null,\'\',\'/tracker\');return false;">✕</a>'
            + _detail(summary, hdf, detail_kw)
            + '</div></div>')
    return "".join(out)
