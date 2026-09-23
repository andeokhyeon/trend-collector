# -*- coding: utf-8 -*-
"""
키워드 분석 — 화면 한 장을 HTML 조각들로 만든다.

⚠️ 판정 로직과 문구는 app.py의 '단일 키워드 진단'(L1204~)을 그대로 옮겼다.
   부품(ui.kpi, ui.donut …)도 ui.py 것을 그대로 부른다(uihtml.render).
   여기서 새로 정하는 건 '어느 부품을 어느 칸에 놓는가' 하나뿐이다.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import escape as _esc
from urllib.parse import quote

import pandas as pd

from uihtml import ui, render
from tables import compact_num, table_html

from naver_api import (
    analyze_keyword, get_search_trend, get_min_bids, get_volumes,
    calc_opportunity, ad_density_pct,
    calc_gold_score, estimate_monthly_income, seasonality_note,
    get_my_blog_feed, check_my_rank, estimate_blog_power, calc_win_score,
)
try:
    import ai_brief
except Exception:
    ai_brief = None


def measure_batch(keywords, known):
    """
    연관 키워드를 한꺼번에 측정한다 (app.py measure_batch 이식).

    ⚠️ 검색량을 모르는 키워드(자동완성)를 analyze_keyword에 그냥 넘기면
    내부에서 힌트로 쪼개져 0이 나온다. 모르는 것은 get_volumes로
    5개씩 묶어 먼저 채운 뒤 넘긴다.
    """
    smap = dict(known)
    unknown = [k for k in keywords if k not in smap]
    chunks = [unknown[i:i + 5] for i in range(0, len(unknown), 5)]

    def _vols(chunk):
        try:
            return chunk, get_volumes(chunk)
        except Exception:
            return chunk, {}

    if chunks:
        with ThreadPoolExecutor(max_workers=min(6, len(chunks))) as vp:
            for chunk, vols in vp.map(_vols, chunks):
                for k in chunk:
                    v = vols.get(k.replace(" ", "").upper())
                    if v:
                        smap[k] = {"monthly_pc": int(v * 0.3),
                                   "monthly_mobile": v - int(v * 0.3),
                                   "comp_level": "-", "pl_avg_depth": 0}

    out, failed = {}, []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(analyze_keyword, k, True, False, False,
                               smap.get(k), True): k
                   for k in keywords if k in smap}
        for fut in as_completed(futures):
            k = futures[fut]
            try:
                res = fut.result()
                if res and res.get("total_search", 0) > 0:
                    out[k] = res
                else:
                    failed.append(k)
            except Exception:
                failed.append(k)
    no_demand = [k for k in keywords if k not in smap]
    return ([out[k] for k in keywords if k in out], failed, no_demand)


def _row(cells, ratio=None):
    """가로 칸 나누기 — 스트림릿의 st.columns 대신."""
    if ratio:
        style = f'grid-template-columns:{" ".join(f"{r}fr" for r in ratio)}'
    else:
        style = f'grid-template-columns:repeat({len(cells)},1fr)'
    inner = "".join(f'<div class="cell">{c}</div>' for c in cells)
    return f'<div class="row" style="{style}">{inner}</div>'


def build(kw, rank=False, only_contains=True, min_vol=0, my_blog_id="", ai=False):
    """키워드 하나를 재서 화면 HTML을 돌려준다."""
    kw = (kw or "").strip()
    out = []
    r = analyze_keyword(kw)

    # 추이와 광고 단가는 서로 다른 서버 — 동시에 던진다 (app.py와 같은 이유)
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_trend = pool.submit(get_search_trend, kw, days=365,
                              total_search=r.get("total_search"))
        f_bid = pool.submit(get_min_bids, [kw])
        try:
            trend = f_trend.result()
        except Exception:
            trend = None
        try:
            bids = f_bid.result() or {}
            bid = bids.get(kw)
        except Exception:
            bid = None

    chg = trend.get("change_pct") if trend else None
    if chg is not None:
        try:
            r["opportunity"] = calc_opportunity(
                r.get("comp_ratio"), r.get("recent_ratio"),
                total_search=r.get("total_search"), search_change_pct=chg)
        except Exception:
            pass

    recent_docs = r.get("recent_docs")
    recent_grade = r.get("recent_grade", "정보없음")
    opp = r.get("opportunity") or {"score": 0, "label": "정보없음", "note": ""}

    # --- 판정 슬랩 ---
    # ⚠️ 2026-09-22 3차. 예전엔 흰 카드 네 장(단가·검색량·문서수·새글)이었다.
    #    네 장이 같은 무게로 나란히 서 있으니 무엇이 결론인지 알 수 없었고,
    #    화면이 '어느 SaaS에나 있는 관리자 페이지'처럼 보였다.
    #    이제는 어두운 판 하나에 다 담고, 그 안에서 단가만 크게 키운다.
    #    이 제품이 파는 게 단가라서 머릿수도 단가여야 말이 맞는다.
    #    ⚠️ 어두운 판은 한 화면에 하나만. 둘이 되면 다시 다크 테마가 된다.
    def _cell(val, label, money=False):
        cls = "slab-cell money" if money else "slab-cell"
        return f'<div class="{cls}"><div class="v">{val}</div><div class="l">{label}</div></div>'

    try:
        _inc = estimate_monthly_income(r.get("total_search"), 3)
    except Exception:
        _inc = None
    _money_l = "클릭단가 · 광고주가 한 번 클릭에 내는 돈"
    if bid and _inc:
        _lo = _inc[0] if isinstance(_inc, (list, tuple)) and len(_inc) > 1 else None
        _hi = _inc[1] if isinstance(_inc, (list, tuple)) and len(_inc) > 1 else None
        if _lo and _hi:
            _money_l = f"클릭단가 · 3위 시 월 {int(_lo):,}~{int(_hi):,}원 예상"
    elif not bid:
        _money_l = "클릭단가 · 가져오지 못했습니다"
    cells = [_cell(f"{bid:,}원" if bid else "—", _money_l, money=True),
             _cell(compact_num(r["total_search"]),
                   f"월 검색량 · PC {r['monthly_pc']:,} / 모바일 {r['monthly_mobile']:,}"),
    ]
    # ⚠️ 2026-09-23 (31번 Peach Fuzz 시안): 셋째·넷째 칸을 문서수·최근 새 글에서
    #    모바일 비율·성수기로 바꿨다. 문서수·새 글은 네이버 검색 API 값이라
    #    회신(9/22)대로 더 앞세울 수 없다. 모바일 비율은 검색광고 API,
    #    성수기는 검색어트렌드 값이다.
    _pc, _mo = int(r.get("monthly_pc") or 0), int(r.get("monthly_mobile") or 0)
    _mob = f"{round(_mo * 100 / (_pc + _mo))}%" if (_pc + _mo) else "—"
    cells.append(_cell(_mob, "모바일 비율"))
    try:
        _se = seasonality_note(trend) if trend else None
    except Exception:
        _se = None
    import re as _re
    if _se:
        _kind = _se[2] if len(_se) > 2 else ""
        _m = _re.search(r"(\d+)일", _se[0])
        if _kind == "now":
            sv, sl = "지금", "성수기"
        elif _kind == "soon" and _m:
            sv, sl = f"{_m.group(1)}일 뒤", "성수기"
        else:
            _mm = _re.search(r"(\d+월)", _se[0])
            sv, sl = (_mm.group(1) if _mm else "—"), "성수기 · 지금은 비수기"
    else:
        sv, sl = "—", "성수기"
    cells.append(_cell(sv, sl))

    # 판정 한 줄 — 문구 H 결: "해볼 만함 · 작년 고점 10월 · 지금 써두면 선점됩니다"
    verdict = _esc(opp.get("label") or "")
    bits = []
    if verdict:
        bits.append(f"<b>{verdict}</b>")
    if _se and len(_se) > 1:
        bits.append(_esc(_se[1]))
    foot = f'<div class="slab-foot"><p>{" · ".join(bits)}</p></div>' if bits else ""
    out.append(
        '<div class="kh-slab">'
        f'<div class="slab-top">'
        f'<div class="slab-kw"><i>단일 키워드 진단</i>{_esc(kw)}</div>'
        f'<div class="slab-score"><b>{int(opp.get("score") or 0)}</b><i>기회 점수</i></div>'
        f'</div>'
        f'<div class="slab-grid">{"".join(cells)}</div>'
        f'{foot}</div>')

    # --- 도넛 + 점수 구성 ---
    donut = render(ui.donut,
                   [("모바일", r["monthly_mobile"], ui.DEEP),
                    ("PC", r["monthly_pc"], ui.WARN)],
                   compact_num(r["total_search"]), "월 검색량")
    breakdown = (render(ui.score_breakdown, opp["breakdown"], opp["score"])
                 if opp.get("breakdown") else "")
    out.append(_row([donut, breakdown], ratio=(1, 2)))

    # --- 1년 추이 + 황금 키워드 ---
    if trend and trend.get("points"):
        out.append(render(ui.trend_chart, trend["points"],
                          title="1년 검색 추이",
                          change_pct=trend.get("change_pct"),
                          abs_points=trend.get("abs")))
    # ⚠️ '황금 키워드 점수' 카드를 뺐다 (2026-09-22 3차).
    #    입찰가와 월 수익 추정이 슬랩과 글자까지 똑같았고, 한 화면에 점수가
    #    둘(기회 78 / 황금 80)이라 무엇을 보고 판단하라는 건지 알 수 없었다.
    #    낱개 키워드 화면의 점수는 '기회 점수' 하나다.
    #    황금 점수는 여러 개를 줄 세우는 자리(/discover?v=money)에 남아 있다.
    #    이 카드가 혼자 들고 있던 성수기 한 줄은 슬랩 바닥으로 옮겼다.

    # --- 경쟁률 눈금 + 기회 점수 ---
    if r.get("comp_ratio") is not None:
        out.append(render(
            ui.scale_gauge, r["comp_ratio"],
            [(0.1, "아주 좋음", ui.GOOD), (0.5, "좋음", ui.GOOD),
             (2, "보통", ui.WARN), (10, "나쁨", ui.BAD), (None, "최악", ui.BAD)],
            title="경쟁률 — 쓰인 글 ÷ 찾는 사람",
            note="낮을수록 유리합니다. 1이면 찾는 사람 수만큼 글이 있다는 뜻"))
    # ⚠️ '기회 점수' 게이지를 뺐다 (2026-09-22 3차).
    #    같은 숫자가 슬랩 오른쪽 · 점수 구성 · 게이지까지 세 번 나왔다.
    #    진단 매트릭스의 판정 문장도 슬랩 바닥과 같은 말이라 비웠다.
    out.append(render(ui.diagnosis_matrix, r["comp_grade"], recent_grade, "", ""))

    # --- 내 승산 (app.py L1327~ 이식) ---
    if my_blog_id:
        try:
            with ThreadPoolExecutor(max_workers=2) as wp:
                f_feed = wp.submit(get_my_blog_feed, my_blog_id)
                f_rank = wp.submit(check_my_rank, kw, my_blog_id)
                feed = f_feed.result()
                my_rank = f_rank.result()
            power = estimate_blog_power(feed["posts"])
            win = calc_win_score(r["comp_ratio"], power["score"],
                                 opportunity_score=opp["score"])
        except Exception:
            win, my_rank = {"score": None}, None
        if win["score"] is not None:
            out.append(render(ui.gauge, f"내 승산 · {win['verdict']}",
                              win["score"], ("어려움", "보통", "유리")))
            rank_txt = (f"이 키워드 상위 30위 안에 내 글이 <b>{my_rank}위</b>로 있습니다."
                        if my_rank else "아직 상위 30위 안에 내 글이 없습니다.")
            out.append(f'<div class="note" style="margin-top:6px">{rank_txt}</div>')
    else:
        out.append(render(
            ui.tip,
            '<a href="/me">블로그 주소를 등록</a>하면 내 블로그로 이 키워드를 '
            "뚫을 수 있는지까지 판정합니다."))

    # --- AI 판단 브리핑 — 버튼을 눌렀을 때만 만든다 (2026-08-29)
    #     매 조회마다 클로드를 부르면 느리고 비용도 든다. 원하는 사람만.
    if ai_brief is not None and ai_brief.is_enabled():
        if not ai:
            _aq = quote(kw)
            out.append(
                f'<a class="kh-ai-cta" id="ai" href="/?q={_aq}&ai=1#ai">'
                '<span class="kh-ai-badge">AI</span>'
                '<span class="kh-ai-main">AI 진단 보기</span>'
                '<span class="kh-ai-sub">단가와 검색 수요를 읽고 '
                '&lsquo;써라 / 조건부 / 피해라&rsquo;를 근거와 함께</span></a>')
        else:
            # ⚠️ 검색 API에서 온 값(문서수·경쟁률·기회점수)은 AI에 넘기지
            #    않는다 — 약관 2.3. ai_brief.brief_keyword 주석 참고.
            payload = {kk: r.get(kk) for kk in
                       ("total_search", "monthly_pc", "monthly_mobile",
                        "pl_avg_depth")}
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

    # --- 노려볼 만한 연관 키워드 (app.py L1384~ 이식) ---
    out.append('<div class="box">')
    out.append(render(ui.section, "노려볼 만한 연관 키워드", ""))
    if not rel:
        out.append(render(ui.tip, "연관 키워드를 찾지 못했습니다 — 더 일반적인 말로 시도해보세요."))
    else:
        pool_rel = [i for i in rel if i.get("contains", True) or not only_contains]
        pool_rel = sorted(pool_rel,
                          key=lambda x: (-(x["monthly_pc"] + x["monthly_mobile"]),
                                         x.get("source") == "자동완성"))
        avail = [i["keyword"] for i in pool_rel]
        known = {i["keyword"]: {"monthly_pc": i["monthly_pc"],
                                "monthly_mobile": i["monthly_mobile"],
                                "comp_level": i.get("comp_level", "-"),
                                "pl_avg_depth": 0}
                 for i in pool_rel if (i["monthly_pc"] + i["monthly_mobile"]) > 0}

        if not rank:
            out.append(render(
                ui.tip,
                "연관 키워드의 문서수까지 재서 노려볼 순서대로 세웁니다."))
            out.append(f'<a class="kh-btn kh-btn-primary" '
                       f'href="/?q={qkw}&rank=1#rank">기회 있는 키워드 보기</a>')
        else:
            targets = avail[:10]
            subs, failed, no_demand = measure_batch(tuple(targets), known)
            if no_demand:
                out.append(f'<div class="kh-cap">{len(no_demand)}개는 검색량이 '
                           f'확인되지 않아 순위에서 제외했습니다.</div>')
            rows = []
            for sub in subs:
                rd = sub.get("recent_docs")
                sopp = sub.get("opportunity") or {"score": 0, "label": "정보없음"}
                rows.append({
                    "키워드": sub["keyword"],
                    "월 검색량": sub["total_search"],
                    "누적 문서수": sub["doc_count"] if sub["doc_count"] is not None else 0,
                    "최근 30일": ((f"{rd:,}+" if sub.get("recent_capped") else f"{rd:,}")
                                if rd is not None else "—"),
                    "기회 점수": sopp["score"],
                    "진단": sopp["label"],
                })
            if not rows:
                out.append(render(ui.tip,
                                  "순위를 매길 만한 연관 키워드가 없습니다 — "
                                  "더 일반적인 말로 시도해보세요."))
            else:
                rel_df = pd.DataFrame(rows).sort_values(
                    "기회 점수", ascending=False).reset_index(drop=True)
                rel_df.index = rel_df.index + 1
                out.append('<div id="rank"></div>')
                out.append(render(
                    ui.tip,
                    "기회 점수 높은 순 — <b>찾는 사람은 있는데 쓰인 글이 적을수록</b> "
                    "위로 옵니다."))
                out.append(render(
                    ui.hunt_rank,
                    [{"keyword": row["키워드"], "search": int(row["월 검색량"]),
                      "docs": int(row["누적 문서수"]), "score": int(row["기회 점수"]),
                      "label": row["진단"]} for _, row in rel_df.iterrows()],
                    main={"keyword": r["keyword"], "search": r["total_search"],
                          "docs": r.get("doc_count")},
                    limit=10))
                out.append(table_html(rel_df))
                out.append(f'<a class="kh-btn" href="/csv/rank?q={qkw}" '
                           f'download>CSV 내려받기</a>')
    out.append('</div>')

    # --- 연관 키워드 전체 (app.py L1604~ 이식 — 필터 포함) ---
    if rel:
        out.append('<div class="box">')
        out.append(render(ui.section, "연관 키워드 전체", f"{len(rel)}개"))
        hints = r.get("hints") or []
        if len(hints) > 1:
            chips = " ".join(f'<span class="hint-chip">{h}</span>' for h in hints)
            out.append(f'<div class="hint-row">이렇게 나눠서 찾았습니다 {chips}</div>')

        # 필터 — 스트림릿 체크박스·슬라이더 대신 주소로 골라 다시 그린다
        def _flt(label, href, on):
            cls = "kh-pill on" if on else "kh-pill"
            return f'<a class="{cls}" href="{href}#all">{label}</a>'
        keep = f"/?q={qkw}" + ("&rank=1" if rank else "")
        out.append('<div id="all" class="kh-filter">')
        out.append(_flt(f"'{r['keyword']}' 포함한 것만",
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
            "월 검색량": (i["monthly_pc"] + i["monthly_mobile"]
                       if i.get("source") != "자동완성" else None),
            "경쟁": i.get("comp_level") or "-",
            "출처": i.get("source", "검색광고"),
        } for i in rel
            if (i.get("contains", True) or not only_contains)
            and (i.get("source") == "자동완성"
                 or (i["monthly_pc"] + i["monthly_mobile"]) >= min_vol)]

        if not rows_all:
            out.append(render(ui.tip, "조건에 맞는 것이 없습니다 — 최소 검색량을 낮춰보세요."))
        else:
            adf = pd.DataFrame(rows_all).sort_values(
                "월 검색량", ascending=False, na_position="last").reset_index(drop=True)
            adf["월 검색량"] = adf["월 검색량"].map(
                lambda v: f"{int(v):,}" if pd.notna(v) else "—")
            adf.index = adf.index + 1
            out.append(table_html(adf, height=440))
            out.append(f'<div class="kh-row-split"><div class="kh-cap">'
                       f'{len(rows_all)}개 표시 · 전체 {len(rel)}개</div>'
                       f'<a class="kh-btn" href="/csv/rel?q={qkw}'
                       f'&contains={1 if only_contains else 0}&min={min_vol}" '
                       f'download>CSV 내려받기</a></div>')
        out.append('</div>')

    return "".join(out)
