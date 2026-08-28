# -*- coding: utf-8 -*-
"""상위노출 해부 — app.py L1662~ 이식. 로직·문구 원본 그대로."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from uihtml import ui, render
from naver_api import get_serp, analyze_serp, weak_spots


def build(kw, sort="sim", my_blog_id=""):
    kw = (kw or "").strip()
    out = []
    out.append(render(ui.section, "상위노출 해부",
                      "이 키워드로 1등 한 글들은 어떻게 생겼나"))
    out.append(render(ui.pitch, "상위권이 전부 옛날 글이면",
                      "지금 밀어낼 수 있습니다",
                      "경쟁률 숫자만으로는 안 보이는 것입니다."))
    if not kw:
        out.append(render(ui.note, "위쪽 입력칸에 키워드를 넣어주세요.", True))
        return "".join(out)

    sort_key = "date" if sort == "date" else "sim"
    # 판정은 항상 '노출 순위순' 기준 (최신순으로 판정하면 의미가 없다)
    if sort_key == "sim":
        serp = get_serp(kw, display=30, sort="sim")
        base = serp
    else:
        with ThreadPoolExecutor(max_workers=2) as sp:
            f_d = sp.submit(get_serp, kw, 30, "date")
            f_b = sp.submit(get_serp, kw, 30, "sim")
            serp, base = f_d.result(), f_b.result()
    meta = analyze_serp(base, top_n=10)

    if not serp:
        out.append(render(ui.note,
                          "검색 결과를 가져오지 못했습니다. API 키 설정을 확인해주세요."))
        return "".join(out)

    out.append(render(ui.weak_strip, weak_spots(base, kw), kw))

    head = "최신 발행순 10개" if sort_key == "date" else "노출 순위 상위 10개"
    qkw = quote(kw)

    def _sopt(label, val):
        cls = "kh-pill on" if (sort_key == val) else "kh-pill"
        return f'<a class="{cls}" href="/serp?q={qkw}&sort={val}">{label}</a>'
    # ⚠️ ui.section은 div 두 개(eyebrow+제목)를 뱉는다. 한 덩어리로 감싸야
    #    옆의 정렬 알약과 좌우로 나뉜다 (안 감싸면 제목이 가운데로 밀린다).
    out.append(
        '<div class="kh-row-split"><div>'
        + render(ui.section, head, "제목과 발행 시점")
        + f'</div><div class="kh-filter">{_sopt("노출 순위순", "sim")}'
          f'{_sopt("최신 발행순", "date")}</div></div>')
    if my_blog_id:
        out.append(render(
            ui.note,
            f"내 블로그(<code>{my_blog_id}</code>)의 글이 있으면 금색으로 표시됩니다. "
            "다른 사람의 블로그 이름은 표시하지 않습니다."))
    out.append(render(ui.serp_list, serp, my_blog_id=my_blog_id, limit=10))

    # 11~30위 — 스트림릿 expander 대신 접이식 details
    more = render(ui.serp_list, serp[10:], my_blog_id=my_blog_id, limit=20)
    out.append(f'<details class="kh-fold"><summary>11위 ~ 30위도 보기</summary>'
               f'{more}</details>')

    # --- KPI 4칸 (문구 원본 그대로) ---
    n_top = meta["count"]
    short = {"최신 글 경쟁": "최신 글 경쟁", "오래된 글이 1등": "오래된 글이 1등",
             "새 글 옛 글 섞임": "섞여 있음"}.get(meta["verdict"], meta["verdict"])
    k1 = render(ui.kpi, "판정", short, f"상위 {n_top}개를 보고 내린 결론")
    ma = meta["median_age"]
    if ma is None:
        age_txt, age_sub = "—", "발행일을 읽지 못함"
    elif ma >= 365:
        age_txt, age_sub = f"{ma // 365}년 전", "상위 글이 대체로 오래됨"
    elif ma >= 30:
        age_txt, age_sub = f"{ma // 30}개월 전", "상위 글이 비교적 최근"
    else:
        age_txt, age_sub = f"{ma}일 전", "상위 글이 갓 올라옴"
    k2 = render(ui.kpi, "언제 쓰인 글인가", age_txt, age_sub)
    dated = meta.get("dated_count") or n_top
    unknown = meta.get("unknown_date") or 0
    sub = f"1년 넘은 글은 {meta['old_365']}개"
    if unknown:
        sub += f" · 발행일 불명 {unknown}개 제외"
    k3 = render(ui.kpi, "상위 10개 중 최근 3개월 글",
                f"{meta['fresh_90']}개 / {dated}개", sub)
    tb = meta["top_blogger"]
    uniq = int(meta["unique_ratio"] * 100)
    if tb and tb[1] > 1:
        k4 = render(ui.kpi, "한 블로그 독점", f"최대 {tb[1]}칸",
                    f"서로 다른 블로그 {uniq}%")
    else:
        k4 = render(ui.kpi, "한 블로그 독점", "없음", "전부 다른 블로그가 한 칸씩")
    out.append(f'<div class="row" style="grid-template-columns:repeat(4,1fr)">'
               f'<div class="cell">{k1}</div><div class="cell">{k2}</div>'
               f'<div class="cell">{k3}</div><div class="cell">{k4}</div></div>')

    out.append(render(ui.note, f"<b>{meta['verdict']}</b> — {meta['advice']}",
                      meta["verdict"] == "오래된 글이 1등"))

    g1 = render(ui.bar_series, meta["age_buckets"],
                "상위 10개 글이 언제 쓰였나 (몇 개월 전)",
                height=170, accent=ui.DEEP, show_pct=True)
    fresh_pct = meta["fresh_90"] / max(1, meta["count"]) * 100
    g2 = (render(ui.gauge, "신규 유입 압력", int(fresh_pct), ("낮음", "보통", "높음"),
                 color=ui.BAD if fresh_pct >= 70 else (
                     ui.WARN if fresh_pct >= 40 else ui.GOOD))
          + render(ui.note,
                   "최근 3개월 글이 많을수록 계속 새 글이 들어오는 자리라 "
                   "한 번 올라가도 유지가 어렵습니다."))
    out.append(f'<div class="row" style="grid-template-columns:3fr 2fr">'
               f'<div class="cell">{g1}</div><div class="cell">{g2}</div></div>')
    return "".join(out)
