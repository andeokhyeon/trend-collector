# -*- coding: utf-8 -*-
"""
표와 숫자 표시 — app.py에서 그대로 가져온 부분.
⚠️ 손보지 않는다. 원본과 글자 하나까지 같아야 화면이 같다.
   (원본: app.py의 compact_num / GRADE_TINT / table_html)
"""
import pandas as pd
from html import escape


def compact_num(v):
    """
    3억 같은 큰 수는 카드 폭을 넘쳐 줄바꿈되므로 축약한다.
    (예: 304,890,403 → 3.0억)
    """
    if v is None:
        return "—"
    v = int(v)
    if v >= 100_000_000:
        return f"{v / 100_000_000:.1f}억"
    if v >= 10_000:
        return f"{v / 10_000:,.1f}만"
    return f"{v:,}"


COL_WIDTH = {
    # 이름 : (폭, 표시형식)
    # 키워드는 대개 20자 안쪽이라 large면 남는 공간을 다 먹는다.
    '키워드': ("medium", None),
    '이벤트': ("medium", None),
    '제목': ("large", None),
    '세부 주제': ("medium", None),
    '진단': ("medium", None),
    '판단': ("medium", None),
    '월 검색량': ("small", "%d"),
    '검색량': ("small", None),
    '문서수': ("small", "%d"),
    '누적 문서수': ("small", "%d"),
    '최근 30일': ("small", None),
    '경쟁률': ("small", None),
    '경쟁': ("small", None),
    '기회 점수': ("small", "%d"),
    '내 승산': ("small", None),
    '광고 경쟁도': ("small", "%d"),
    '최근 30일 글': ("small", "%d"),
    '날짜': ("small", None),
    '요일': ("small", None),
    '종류': ("small", None),
    '발행일': ("small", None),
    '경과': ("small", None),
    '직전 글과 간격': ("small", None),
    '출처': ("small", None),
}


# 등급 라벨별 옅은 배경색 (표 안에서 한눈에 구분되게)
GRADE_TINT = {
    '최고': ('#E8F4F0', '#1F6354'), '좋음': ('#E8F4F0', '#1F6354'),
    '매우한산': ('#E8F4F0', '#1F6354'), '한산': ('#E8F4F0', '#1F6354'),
    '비어 있는 자리': ('#DCEFE9', '#175247'), '오래된 글만 많음': ('#E8F4F0', '#1F6354'),
    '해볼 만함': ('#E8F4F0', '#1F6354'), '오래된 글이 1등': ('#DCEFE9', '#175247'),
    '보통': ('#FBF2E1', '#8A6420'),
    '지금 몰리는 중': ('#FBF2E1', '#8A6420'), '누적만 반영': ('#FBF2E1', '#8A6420'),
    '새 글 옛 글 섞임': ('#FBF2E1', '#8A6420'),
    '나쁨': ('#FAEAE5', '#9E3E28'), '최악': ('#FAEAE5', '#9E3E28'),
    '붐빔': ('#FAEAE5', '#9E3E28'), '과열': ('#FAEAE5', '#9E3E28'),
    '이미 꽉 참': ('#F7E1DB', '#8C3520'), '어려움': ('#FAEAE5', '#9E3E28'),
    '최신 글 경쟁': ('#FAEAE5', '#9E3E28'),
    '정보없음': ('#F1F1EC', '#6B7280'), '검색량없음': ('#F1F1EC', '#6B7280'),
    '이슈': ('#ECEFF3', '#4A5560'),
    '매우낮음': ('#F1F1EC', '#6B7280'),
    '높음': ('#EDF1F4', '#2E5468'), '매우높음': ('#E3EAEF', '#1B3A4B'),
    '낮음': ('#FBF2E1', '#8A6420'),
    # 주간 캘린더의 '종류' — 성격이 다른 재료라 색으로 갈라 보이게 한다.
    # 한눈에 '오늘은 세무 글이 있구나'가 읽히는 게 목적이다.
    # (전부 옅은 바탕 + 진한 글자라 대비는 5:1 위로 잡았다)
    '공휴일': ('#FCE7E7', '#9B2C2C'),      # 달력의 빨간 날
    '절기': ('#E3F1E4', '#2C6B36'),        # 계절
    '세무/마감': ('#FBF0DA', '#845413'),    # 돈
    '축제/행사': ('#F1E9F9', '#67399E'),
    '공연/행사': ('#E1F0F2', '#1C5F67'),
    '청약': ('#E5EDFB', '#1F4590'),        # 부동산
}

TINT_COLS = {'검색량', '경쟁률', '진단', '판단', '등급', '종류', '경쟁'}


# 숫자로 다뤄야 하는 컬럼 (오른쪽 정렬 + 등폭 + 천 단위 쉼표)
NUM_COLS = {
    '월 검색량', '검색량', '문서수', '누적 문서수', '최근 30일', '최근 30일 글',
    '기회 점수', '내 승산', '광고 경쟁도', '경쟁률', '순위', '조회수',
    '황금 점수', '광고단가',
}


# 열이 많을 때 키워드 바로 옆으로 당길 '판단' 계열 (왼쪽부터 이 순서로)
PRIORITY_COLS = ('황금 점수', '광고단가', '진단', '판단', '기회 점수',
                 '내 승산', '경쟁률', '검색량', '경쟁')


def _cell_text(v):
    """표에 넣을 문자열. 숫자는 천 단위로 끊고, 빈 값은 —로."""
    if v is None:
        return "—"
    try:
        if pd.isna(v):
            return "—"
    except (TypeError, ValueError):
        pass
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, (int, float)):
        # 12.0 처럼 소수점만 붙은 값은 정수로 보여준다
        return f"{int(v):,}" if float(v).is_integer() else f"{v:,.1f}"
    return str(v)


def table_html(frame, height=None, center_cols=()):
    """
    표를 HTML로 직접 그린다.

    ⚠️ st.dataframe은 첫 열을 고정할 수 없다.
    그래서 모바일에서 옆으로 밀면 '무엇의 숫자인지'가 화면 밖으로 사라진다.
    첫 열(키워드/이벤트/제목)을 붙박이로 두고 나머지만 밀리게 한다.
    """
    cols = list(frame.columns)
    if not cols:
        return ""

    # ⚠️ 열이 많으면 모바일에서 오른쪽이 잘린다.
    # 그때 먼저 보여야 하는 건 원자료(검색량·문서수)가 아니라 '판단'이다.
    # 등급/점수 계열을 키워드 바로 옆으로 당긴다.
    if len(cols) > 4:
        first, rest = cols[0], cols[1:]
        head_up = [c for c in PRIORITY_COLS if c in rest]
        cols = [first] + head_up + [c for c in rest if c not in head_up]

    def cls(i, name):
        if i == 0:
            return "kh-key"
        if name in center_cols:
            return "kh-num kh-center"
        return "kh-num" if name in NUM_COLS else ""

    head = "".join(
        f'<th class="{cls(i, c)}">{escape(str(c))}</th>'
        for i, c in enumerate(cols))

    rows = []
    for n, (idx, row) in enumerate(frame.iterrows(), 1):
        rank = idx if isinstance(idx, (int,)) and not isinstance(idx, bool) else n
        cells = []
        for i, c in enumerate(cols):
            txt = escape(_cell_text(row[c]))
            if i == 0:
                cells.append(f'<td class="kh-key">'
                             f'<span class="kh-rk">{rank}</span>{txt}</td>')
                continue
            # 등급/진단 계열은 의미별 색 칩으로
            tint = GRADE_TINT.get(str(row[c])) if c in TINT_COLS else None
            if tint:
                bg, fg = tint
                cells.append(f'<td><span class="kh-chip" '
                             f'style="background:{bg};color:{fg}">{txt}</span></td>')
            else:
                cells.append(f'<td class="{cls(i, c)}">{txt}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")

    box = ('class="kh-tw kh-scroll" style="max-height:%dpx"' % int(height)
           if height else 'class="kh-tw"')
    return (f'<div {box}><table class="kh-t">'
            f'<thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            f'<div class="kh-hint">← 표를 옆으로 밀면 나머지 항목이 보입니다</div>')


