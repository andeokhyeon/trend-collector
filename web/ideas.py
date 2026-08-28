# -*- coding: utf-8 -*-
"""글감 만들기 — app.py L1793~ 이식. 로직·문구 원본 그대로."""
import pandas as pd

from uihtml import ui, render
from tables import table_html
from naver_api import analyze_keyword, get_serp, analyze_titles, build_outline


def build(kw):
    kw = (kw or "").strip()
    out = []
    out.append(render(ui.section, "글감 만들기", "상위권은 실제로 어떻게 쓰는가"))
    out.append(render(
        ui.note,
        "제목을 지어내지도, 남의 제목을 그대로 보여주지도 않습니다. "
        "베껴 쓰게 되면 결국 손해이기 때문입니다. 대신 상위권 제목에서 "
        "<b>어떤 형식이 통하는지</b>와 <b>실제로 검색되는 세부 주제</b>만 뽑아냅니다. "
        "이걸 재료로 직접 쓰시는 게 훨씬 낫습니다."))
    if not kw:
        out.append(render(ui.note, "위쪽 입력칸에 키워드를 넣어주세요.", True))
        return "".join(out)

    a = analyze_keyword(kw, with_recent=False)
    sp = get_serp(kw, display=30)
    an = analyze_titles(kw, sp, a.get("related", []))
    outline = build_outline(kw, an)

    if not an:
        out.append(render(ui.note,
                          "상위 글을 가져오지 못했습니다. 다른 키워드로 시도해보세요."))
        return "".join(out)

    k1 = render(ui.kpi, "제목 길이", f"{an['median_len']}자",
                f"짧게 {an['min_len']} · 길게 {an['max_len']}")
    k2 = render(ui.kpi, "가장 흔한 형식",
                max([("숫자형", an["num_ratio"]), ("후기형", an["experience_ratio"]),
                     ("정리형", an["summary_ratio"])], key=lambda x: x[1])[0],
                "상위권이 많이 쓰는 틀")
    k3 = render(ui.kpi, "후기·경험형", f"{an['experience_ratio'] * 100:.0f}%",
                "직접 써본 이야기")
    k4 = render(ui.kpi, "분석한 제목", f"{an['count']}개", "상위 노출 글 기준")
    out.append(f'<div class="row" style="grid-template-columns:repeat(4,1fr)">'
               f'<div class="cell">{k1}</div><div class="cell">{k2}</div>'
               f'<div class="cell">{k3}</div><div class="cell">{k4}</div></div>')

    out.append(render(ui.section, "상위권 제목의 공통 형식",
                      "어떤 틀이 먹히는지만 봅니다"))
    out.append(render(
        ui.bar_series,
        [("숫자 넣기", int(an["num_ratio"] * 100)),
         ("후기·경험형", int(an["experience_ratio"] * 100)),
         ("정리·비교형", int(an["summary_ratio"] * 100)),
         ("괄호 붙이기", int(an["bracket_ratio"] * 100)),
         ("질문형", int(an["question_ratio"] * 100))],
        "상위권 제목이 쓰는 형식 (100개 중 몇 %)", height=175, accent=ui.DEEP))

    hints = []
    if an["num_ratio"] >= 0.4:
        hints.append("제목에 <b>숫자</b>를 넣는 형식이 통하고 있습니다")
    if an["experience_ratio"] >= 0.3:
        hints.append("<b>직접 써본 경험</b>을 앞세운 제목이 강세입니다")
    if an["summary_ratio"] >= 0.3:
        hints.append("<b>정리·비교형</b>으로 묶는 제목이 많습니다")
    if an["bracket_ratio"] >= 0.3:
        hints.append("<b>괄호</b>로 글의 성격을 앞에 붙이는 형식이 흔합니다")
    if an["question_ratio"] >= 0.2:
        hints.append("<b>질문형</b> 제목이 눈에 띕니다")
    hints.append(f"길이는 <b>{an['median_len']}자</b> 안팎이 평균입니다")
    out.append(render(ui.note, " · ".join(hints)))

    if an["common_words"]:
        out.append(render(ui.section, "제목에 자주 나오는 단어",
                          "상위권이 공통으로 짚는 지점"))
        mx = an["common_words"][0][1]
        chips = " ".join(
            f'<span class="wchip" style="background:rgba(27,58,75,'
            f'{0.12 + 0.55 * (c / mx):.2f})">{w}<b>{c}</b></span>'
            for w, c in an["common_words"])
        out.append(f'<div class="chart-box">{chips}</div>')

    if an["subtopics"]:
        out.append(render(ui.section, "실제로 검색되는 세부 주제",
                          "검색량이 확인된 것만"))
        sub_df = pd.DataFrame([{"세부 주제": x["keyword"], "월 검색량": x["volume"]}
                               for x in an["subtopics"]])
        sub_df.index = sub_df.index + 1
        out.append(table_html(sub_df, center_cols=("월 검색량",)))

    if outline:
        out.append(render(ui.section, "글 뼈대 후보", "근거가 있는 항목만 모았습니다"))
        rows = "".join(
            f'<div class="outline-card"><div class="outline-top">'
            f'<span class="outline-num" style="background:'
            f'{ui.DEEP if s_["kind"] == "필수" else ui.GOLD}">'
            f'{"핵심" if s_["kind"] == "필수" else "검색"}</span>'
            f'<span class="outline-h">{s_["heading"]}</span></div>'
            f'<div class="outline-w">{s_["why"]}</div></div>'
            for s_ in outline)
        out.append(f'<div class="outline-grid">{rows}</div>')
    return "".join(out)
