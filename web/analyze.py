# -*- coding: utf-8 -*-
"""
키워드 검사 — 화면 한 장을 HTML 조각들로 만든다.

⚠️ 2026-09-23 전면 재구성. 네이버 회신(9/22)으로 검색 API 기반 값
   (문서수·최근 새 글·경쟁률·기회 점수·상위 글·내 순위)을 전부 뺐다.
   이 화면이 쓰는 재료는 셋뿐이다 —
     · 검색광고 API  : 월 검색량 · PC/모바일 · 광고 경쟁 · 연관 키워드 · 최소노출입찰가
     · 검색어트렌드  : 1년 추이 · 성수기
     · 우리 계산     : 월 수익 추정(검색량 × 우리 가정), 돈 판정(naver_api.calc_money_verdict)
   화면 순서도 그 재료에 맞춰 줄였다:
     판정 슬랩 → 1년 추이 → AI 진단 → 돈 되는 연관 키워드 → 연관 키워드 전체
"""
import re
from concurrent.futures import ThreadPoolExecutor
from html import escape as _esc
from urllib.parse import quote

import pandas as pd

import db
from uihtml import ui, render
from tables import compact_num, table_html

from naver_api import (
    analyze_keyword, get_search_trend, get_min_bids,
    estimate_monthly_income, seasonality_note, calc_money_verdict,
)
try:
    import ai_brief
except Exception:
    ai_brief = None


RELATED_BID_LIMIT = 30      # 단가를 붙여 볼 연관 키워드 수 (검색량 상위부터)


def money_related(related, only_contains=True, limit=RELATED_BID_LIMIT):
    """연관 키워드에 최소노출입찰가를 붙여 '돈 되는 순'으로 세운다.

    ⚠️ 예전 '기회 있는 키워드 보기'는 연관어마다 블로그 검색을 열 번씩
       불러 문서수를 쟀다 — 이제 못 쓴다. 대신 검색광고 입찰가를 한 번에
       묶어 조회한다 (db.cached_min_bids가 6시간 기억한다).
    반환: DataFrame(키워드, 클릭단가(원), 월 검색량, 판정) — 단가 높은 순
    """
    pool = [i for i in (related or [])
            if (i.get("contains", True) or not only_contains)
            and (i["monthly_pc"] + i["monthly_mobile"]) > 0]
    pool = sorted(pool, key=lambda x: -(x["monthly_pc"] + x["monthly_mobile"]))[:limit]
    if not pool:
        return pd.DataFrame()
    kws = tuple(i["keyword"] for i in pool)
    try:
        bids = db.cached_min_bids(kws) or {}
    except Exception:
        bids = {}
    rows = []
    for i in pool:
        vol = i["monthly_pc"] + i["monthly_mobile"]
        bid = bids.get(i["keyword"])
        rows.append({
            "키워드": i["keyword"],
            "클릭단가(원)": int(bid) if bid else None,
            "월 검색량": vol,
            "판정": calc_money_verdict(bid, vol)["label"],
        })
    df = pd.DataFrame(rows)
    df = df.sort_values(["클릭단가(원)", "월 검색량"], ascending=[False, False],
                        na_position="last").reset_index(drop=True)
    df.index = df.index + 1
    return df


def _season(trend):
    """성수기 칸의 (값, 이름표, 설명 한 줄). 없으면 ('—','성수기','')."""
    try:
        se = seasonality_note(trend) if trend else None
    except Exception:
        se = None
    if not se:
        return "—", "성수기", ""
    kind = se[2] if len(se) > 2 else ""
    m = re.search(r"(\d+)일", se[0])
    if kind == "now":
        return "지금", "성수기", se[1]
    if kind == "soon" and m:
        return f"{m.group(1)}일 뒤", "성수기", se[1]
    mm = re.search(r"(\d+월)", se[0])
    return (mm.group(1) if mm else "—"), "성수기 · 지금은 비수기", se[1]


def build(kw, rank=False, only_contains=True, min_vol=0, my_blog_id="", ai=False):
    """키워드 하나를 재서 화면 HTML을 돌려준다.

    rank·my_blog_id는 예전 주소(…&rank=1)와 호출부 호환을 위해 받기만 한다.
    """
    kw = (kw or "").strip()
    out = []
    r = analyze_keyword(kw, with_recent=False)

    # 추이(데이터랩)와 단가(검색광고)는 서로 다른 서버 — 동시에 던진다
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_trend = pool.submit(get_search_trend, kw, days=365,
                              total_search=r.get("total_search"))
        f_bid = pool.submit(get_min_bids, [kw])
        try:
            trend = f_trend.result()
        except Exception:
            trend = None
        try:
            bid = (f_bid.result() or {}).get(kw)
        except Exception:
            bid = None

    total = int(r.get("total_search") or 0)
    chg = trend.get("change_pct") if trend else None
    verdict = calc_money_verdict(bid, total, chg)

    # --- 판정 슬랩 ---------------------------------------------------
    def _cell(val, label, money=False):
        cls = "slab-cell money" if money else "slab-cell"
        return f'<div class="{cls}"><div class="v">{val}</div><div class="l">{label}</div></div>'

    try:
        inc = estimate_monthly_income(total, 3)
    except Exception:
        inc = None
    if not bid:
        money_l = "클릭단가 · 광고주가 거는 돈이 없습니다"
    elif inc and len(inc) > 1 and inc[0] and inc[1]:
        money_l = f"클릭단가 · 3위 시 월 {int(inc[0]):,}~{int(inc[1]):,}원 예상"
    else:
        money_l = "클릭단가 · 광고주가 한 번 클릭에 내는 돈"
    pc, mo = int(r.get("monthly_pc") or 0), int(r.get("monthly_mobile") or 0)
    sv, sl, s_detail = _season(trend)
    cells = [
        _cell(f"{bid:,}원" if bid else "—", money_l, money=True),
        _cell(compact_num(total), f"월 검색량 · PC {pc:,} / 모바일 {mo:,}"),
        _cell(f"{round(mo * 100 / (pc + mo))}%" if (pc + mo) else "—", "모바일 비율"),
        _cell(sv, sl),
    ]
    comp = r.get("comp_level") or "-"
    meta = f"광고 경쟁 {_esc(comp)}" if comp not in ("-", "") else ""
    foot_bits = [f"<b>{_esc(verdict['label'])}</b>", _esc(verdict["note"])]
    if s_detail:
        foot_bits.append(_esc(s_detail))
    out.append(
        '<div class="kh-slab">'
        '<div class="slab-top">'
        f'<div class="slab-kw"><i>키워드 검사{(" · " + meta) if meta else ""}</i>{_esc(kw)}</div>'
        f'<div class="slab-verdict tone-{verdict["tone"]}">{_esc(verdict["label"])}</div>'
        '</div>'
        f'<div class="slab-grid">{"".join(cells)}</div>'
        f'<div class="slab-foot"><p>{" · ".join(foot_bits)}</p></div>'
        '</div>')

    # --- 1년 추이 (언제 쓸지의 근거) ----------------------------------
    if trend and trend.get("points"):
        out.append(render(ui.trend_chart, trend["points"],
                          title="1년 검색 추이",
                          change_pct=chg, abs_points=trend.get("abs")))

    # --- AI 진단 — 버튼을 눌렀을 때만 (느리고 비용이 든다) -------------
    if ai_brief is not None and ai_brief.is_enabled():
        if not ai:
            out.append(
                f'<a class="kh-ai-cta" id="ai" href="/?q={quote(kw)}&ai=1#ai">'
                '<span class="kh-ai-badge">AI</span>'
                '<span class="kh-ai-main">AI 진단 보기</span>'
                '<span class="kh-ai-sub">단가와 검색 수요를 읽고 '
                '&lsquo;써라 / 조건부 / 피해라&rsquo;를 근거와 함께</span></a>')
        else:
            # ⚠️ AI에는 검색광고 값만 넘긴다 — ai_brief.brief_keyword 주석 참고
            payload = {kk: r.get(kk) for kk in
                       ("total_search", "monthly_pc", "monthly_mobile", "pl_avg_depth")}
            payload["min_bid"] = bid
            try:
                brief, berr = ai_brief.brief_keyword(kw, payload, None, None, None)
            except Exception as e:
                brief, berr = None, str(e)
            if brief:
                out.append('<div id="ai"></div>')
                out.append(render(ui.brief_card, brief, "AI 판단 · 이 키워드 써도 될까"))
            else:
                out.append(render(ui.note,
                                  f"판단 브리핑을 만들지 못했습니다. <small>{berr}</small>"))

    rel = r.get("related", [])
    qkw = quote(kw)

    # --- 돈 되는 연관 키워드 -------------------------------------------
    out.append('<div class="box" id="rank">')
    out.append(render(ui.section, "돈 되는 연관 키워드", "광고주가 거는 금액 순"))
    mdf = money_related(rel, only_contains=only_contains)
    if mdf.empty:
        out.append(render(ui.tip, "단가를 붙일 연관 키워드가 없습니다 — 더 일반적인 말로 시도해보세요."))
    else:
        top = mdf.head(10).copy()
        top["클릭단가(원)"] = top["클릭단가(원)"].map(lambda v: f"{int(v):,}" if pd.notna(v) else "—")
        top["월 검색량"] = top["월 검색량"].map(lambda v: f"{int(v):,}")
        out.append(table_html(top))
        out.append(f'<div class="kh-row-split"><div class="kh-cap">'
                   f'검색량 상위 {len(mdf)}개에 단가를 붙여 비싼 순으로 세웠습니다</div>'
                   f'<a class="kh-btn" href="/csv/rank?q={qkw}" download>CSV 내려받기</a></div>')
    out.append('</div>')

    # --- 연관 키워드 전체 (필터 포함) ------------------------------------
    if rel:
        out.append('<div class="box">')
        out.append(render(ui.section, "연관 키워드 전체", f"{len(rel)}개"))
        hints = r.get("hints") or []
        if len(hints) > 1:
            chips = " ".join(f'<span class="hint-chip">{_esc(h)}</span>' for h in hints)
            out.append(f'<div class="hint-row">이렇게 나눠서 찾았습니다 {chips}</div>')

        def _flt(label, href, on):
            cls = "kh-pill on" if on else "kh-pill"
            return f'<a class="{cls}" href="{href}#all">{label}</a>'
        keep = f"/?q={qkw}"
        out.append('<div id="all" class="kh-filter">')
        out.append(_flt(f"'{_esc(r['keyword'])}' 포함한 것만",
                        keep + f"&contains={0 if only_contains else 1}&min={min_vol}",
                        only_contains))
        out.append('<span class="kh-filter-label">최소 검색량</span>')
        for v in (0, 100, 500, 1000, 5000):
            out.append(_flt(f"{v:,}" if v else "전체",
                            keep + f"&contains={1 if only_contains else 0}&min={v}",
                            min_vol == v))
        out.append('</div>')

        rows_all = [{
            "키워드": i["keyword"],
            "월 검색량": i["monthly_pc"] + i["monthly_mobile"],
            "광고 경쟁": i.get("comp_level") or "-",
        } for i in rel
            if (i.get("contains", True) or not only_contains)
            and (i["monthly_pc"] + i["monthly_mobile"]) >= min_vol]

        if not rows_all:
            out.append(render(ui.tip, "조건에 맞는 것이 없습니다 — 최소 검색량을 낮춰보세요."))
        else:
            adf = pd.DataFrame(rows_all).sort_values(
                "월 검색량", ascending=False).reset_index(drop=True)
            adf["월 검색량"] = adf["월 검색량"].map(lambda v: f"{int(v):,}")
            adf.index = adf.index + 1
            out.append(table_html(adf, height=440))
            out.append(f'<div class="kh-row-split"><div class="kh-cap">'
                       f'{len(rows_all)}개 표시 · 전체 {len(rel)}개</div>'
                       f'<a class="kh-btn" href="/csv/rel?q={qkw}'
                       f'&contains={1 if only_contains else 0}&min={min_vol}" '
                       f'download>CSV 내려받기</a></div>')
        out.append('</div>')

    return "".join(out)
