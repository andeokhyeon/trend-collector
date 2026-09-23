# -*- coding: utf-8 -*-
"""키워드 찾기.

⚠️ 2026-09-23: 네이버 회신(9/22)대로 검색 API 값(문서수·경쟁률·최근 30일 글)과
   그걸 쓰던 황금 점수를 전부 뺐다. 뉴스 탭(news.naver.com 랭킹 크롤링)도 내렸다.
   남은 재료: 검색광고 API(검색량·최소노출입찰가) · 구글 트렌드 RSS · 공공데이터 ·
   검색어트렌드. 판정은 naver_api.calc_money_verdict 하나로 통일한다.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd

from uihtml import ui, render
from tables import table_html
import db

# 조회 기간 (app.py 그대로)
PERIOD_HOURS = {"최근": 3, "실시간": 1, "일별": 24, "주간": 24 * 7,
                "월별": 24 * 30, "6시간": 6, "12시간": 12}
PERIOD_SETS = {
    "trend": ("최근", "일별", "주간", "월별"),
    "slow": ("6시간", "일별", "주간", "월별"),
    "daily": ("일별", "주간", "월별"),
}

SEASONAL_CALENDAR = {
    1: ["다이어리", "새해선물", "스키장비", "난방용품", "핫팩"],
    2: ["설날선물세트", "졸업선물", "밸런타인선물", "가습기"],
    3: ["입학선물", "새학기준비", "미세먼지마스크", "공기청정기", "이사철"],
    4: ["벚꽃놀이", "봄나들이용품", "알레르기약", "자외선차단제"],
    5: ["어린이날선물", "가정의달선물", "캠핑용품", "나들이도시락통"],
    6: ["장마철제습기", "여름휴가", "래시가드", "휴대용선풍기"],
    7: ["여름휴가", "물놀이용품", "튜브", "쿨매트", "에어컨"],
    8: ["휴가철캐리어", "휴대용선풍기", "미니에어컨", "대학입시설명회"],
    9: ["추석선물세트", "환절기건강식품", "가을옷"],
    10: ["할로윈의상", "단풍놀이", "가을캠핑", "히트텍"],
    11: ["수능선물", "김장용품", "겨울코트", "블랙프라이데이"],
    12: ["크리스마스선물", "연말모임", "다이어리", "패딩"],
}


def _pills(base, param, options, chosen):
    """기간·갈래 선택 — 스트림릿 라디오 대신 주소 알약."""
    out = ['<div class="kh-filter">']
    for o in options:
        cls = "kh-pill on" if o == chosen else "kh-pill"
        out.append(f'<a class="{cls}" href="{base}&{param}={quote(o)}">{o}</a>')
    out.append('</div>')
    return "".join(out)


def _empty_note(df, source, label=""):
    """왜 비었는지 알려준다 (app.py empty_note)."""
    all_rows = df[df['source'] == source] if not df.empty else df
    if all_rows.empty:
        return render(ui.note,
                      f"아직 {label or '이 항목'} 데이터가 없습니다 — "
                      "다음 수집 회차에 자동으로 채워집니다.")
    last = all_rows['created_at_dt'].max()
    mins = int((datetime.now(timezone.utc) - last).total_seconds() // 60)
    ago = f"{mins}분 전" if mins < 120 else f"{mins // 60}시간 전"
    return render(ui.note,
                  f"이 기간에는 수집된 것이 없습니다 (최근 수집 <b>{ago}</b>) — "
                  "위에서 기간을 넓혀보세요.", True)


def _render_table(df_all, data, sort_col='총 검색량', extra_cols=None, limit=30,
                  show_docs=True, show_volume=True, source=None, label="",
                  empty_msg=None, lead_cols=None):
    """app.py render_table 이식 — HTML을 돌려준다."""
    if data.empty:
        if empty_msg:
            return render(ui.note, empty_msg)
        if source:
            return _empty_note(df_all, source, label)
        return render(ui.note, "아직 수집된 데이터가 없습니다.")
    d = data.sort_values(by=sort_col, ascending=False).head(limit)
    d = d.reset_index(drop=True)
    cols, names = ['keyword'], ['키워드']
    # 키워드 바로 다음에 세울 열 — 화면의 머릿수를 앞으로 당긴다
    for c, lb in (lead_cols or []):
        if c in d.columns:
            cols.append(c); names.append(lb)
    if show_volume:
        cols += ['총 검색량', '검색량 등급']
        names += ['월 검색량', '검색량']
    # show_docs는 예전 호출부 호환용 — 문서수·경쟁률 열은 더 그리지 않는다 (검색 API 값)
    for c, lb in (extra_cols or []):
        if c in d.columns:
            cols.append(c); names.append(lb)
    out = d[cols].copy()
    out.columns = names
    out.index = out.index + 1
    return table_html(out)


def build_money(period="일별", part="전체"):
    """돈 되는 키워드 — 단가 순으로 세운다.

    ⚠️ 골든타임과 다른 질문이다.
       골든타임 = "오늘 뜬 것 중 돈 되는 것" (최근 몇 시간 트렌드만)
       여기     = "수집해둔 전체 중 유입당 값이 비싼 곳" (광고 단가 순)
       검색량 4만에 단가 300원인 키워드보다 3천에 8천원인 쪽이 나을 때가 있다.
       그 판단을 하려면 단가만으로 세운 줄이 따로 있어야 한다.

    ⚠️ 이 화면은 네이버 '검색광고 API'만 쓴다 (검색 API가 아니다).
       검색 API 특약조건(저장·AI·수익화 제한)의 사정권 밖이라,
       유료화까지 가려면 이 방향이 가장 안전하다.
    """
    from naver_api import calc_money_verdict
    df = db.load_data()
    h = PERIOD_HOURS.get(period, 24)
    out = [render(ui.section, "돈 되는 키워드",
                  "광고주가 실제로 거는 금액 순"),
           render(ui.pitch, "검색량이 많다고",
                  "돈이 되지는 않습니다",
                  "광고주가 한 번 클릭에 8천원을 내는 검색어와 300원을 내는 "
                  "검색어는 같은 유입이어도 값이 다릅니다. "
                  "여기는 <b>비싼 쪽부터</b> 보여줍니다."),
           _pills("/discover?v=money&t=" + quote(part), "p",
                  PERIOD_SETS["slow"], period)]

    EMPTY = "아직 볼 수 있는 키워드가 없습니다. 수집기가 한 번 돌면 채워집니다."
    # ⚠️ 수집 데이터가 아예 없을 때 열 이름을 찾으면 터진다 — 먼저 막는다
    if df.empty or '총 검색량' not in df.columns:
        out.append(render(ui.note, EMPTY))
        return "".join(out)

    # 최근 수집분 전체에서 검색량이 있는 것만 — 뉴스는 키워드가 아니라 제외
    pool = df[(df['source'] != 'naver_news') & (df['총 검색량'].fillna(0) > 0)]
    pool = db.latest_snapshot(pool, hours=h)
    if pool.empty:
        out.append(render(ui.note, EMPTY))
        return "".join(out)

    # 단가 조회는 배치로 한 번에 (6시간 캐시). 너무 많이 물으면 느려지니 상위 120개.
    pool = pool.sort_values('총 검색량', ascending=False).head(120)
    kws = pool['keyword'].tolist()
    bids = db.cached_min_bids(tuple(kws))
    if not bids:
        out.append(render(ui.note, "광고 단가를 가져오지 못했습니다 — 잠시 후 다시 시도해주세요."))
        return "".join(out)

    pool = pool.copy()
    pool['광고단가'] = pool['keyword'].map(bids)
    pool = pool[pool['광고단가'].notna() & (pool['광고단가'] > 0)]
    if pool.empty:
        out.append(render(ui.note, EMPTY))
        return "".join(out)
    pool['판정'] = [calc_money_verdict(row['광고단가'], row['총 검색량'])['label']
                  for _, row in pool.iterrows()]
    pool = pool.sort_values('광고단가', ascending=False)

    # 세부/트렌드 갈라보기 — 세부 키워드가 대개 단가가 높고 경쟁이 낮다
    parts = ["전체", "세부 키워드", "트렌드"]
    chosen = part if part in parts else "전체"
    pill = ['<div class="kh-filter">']
    for p in parts:
        cls = "kh-pill on" if p == chosen else "kh-pill"
        pill.append(f'<a class="{cls}" href="/discover?v=money'
                    f'&p={quote(period)}&t={quote(p)}">{p}</a>')
    pill.append('</div>')
    out.append("".join(pill))

    if chosen == "세부 키워드":
        data, lim = pool[pool['keyword_category'] == '세부'], 30
    elif chosen == "트렌드":
        data, lim = pool[pool['keyword_category'] == '트렌드'], 30
    else:
        data, lim = pool, 30

    data = data.copy()
    data['광고단가'] = data['광고단가'].astype(int)
    out.append(_render_table(
        df, data, sort_col='광고단가', limit=lim,
        lead_cols=[('광고단가', '클릭단가(원)')],
        extra_cols=[('판정', '판정')],
        empty_msg=EMPTY))
    out.append(render(ui.tip,
                      "단가 = 네이버 검색광고 <b>최소노출입찰가</b> · "
                      "목록 보기는 크레딧이 들지 않습니다."))
    return "".join(out)


def build_trend(period="최근"):
    df = db.load_data()
    hours = PERIOD_HOURS.get(period, 3)
    out = [render(ui.section, "구글 트렌드", "지금 사람들이 검색하는 것"),
           _pills("/discover?v=trend", "p", PERIOD_SETS["trend"], period)]
    out.append(_render_table(
        df, db.latest_snapshot(df[df['source'] == 'google_trend'], hours=hours),
        show_docs=False, source='google_trend', label="구글 트렌드"))
    return "".join(out)


def build_golden(period="6시간", part="전체"):
    """골든타임 — 오늘 뜬 검색어 중 광고주가 돈을 거는 것.

    ⚠️ 2026-09-23 재정의. 예전 정의는 "뜨는데 아직 블로그 글이 적은 것"이었고,
       '글이 적다'를 블로그 검색(검색 API)으로 셌다 — 이제 못 센다.
       새 정의는 두 재료로만 선다:
         · 오늘 떴다  = 구글 트렌드 RSS에 오른 검색어와 그 연관어(검색광고 API)
         · 돈이 된다  = 최소노출입찰가가 붙어 있다
       기간 기본값을 6시간으로 둔다 — '오늘 뜬 것'이 이 탭의 존재 이유라서.
    """
    from naver_api import calc_money_verdict
    df = db.load_data()
    h = PERIOD_HOURS.get(period, 6)
    out = [render(ui.section, "골든타임", "오늘 뜬 것 중 돈 되는 것"),
           render(ui.pitch, "오늘 뜬 검색어 중",
                  "광고주가 돈을 거는 것만",
                  "구글 트렌드에 오른 검색어와 그 연관어 중 광고 단가가 붙는 것을 "
                  "<b>비싼 순</b>으로 세웁니다. 뜰 때 먼저 쓰는 게 이 탭의 쓰임입니다."),
           _pills(f"/discover?v=golden&t={quote(part)}", "p",
                  PERIOD_SETS["slow"], period)]
    EMPTY = "이 기간에 뜬 검색어 중 단가가 붙은 것이 없습니다 — 기간을 넓혀보세요."
    if df.empty or '총 검색량' not in df.columns:
        out.append(render(ui.note, EMPTY))
        return "".join(out)
    src = df[df['source'].isin(['google_trend', 'golden_time'])
             & (df['총 검색량'].fillna(0) > 0)]
    pool = db.latest_snapshot(src, hours=h)
    if pool.empty:
        out.append(_empty_note(df, 'google_trend', "골든타임"))
        return "".join(out)
    pool = pool.sort_values('총 검색량', ascending=False).head(100)
    bids = db.cached_min_bids(tuple(pool['keyword'].tolist())) or {}
    if not bids:
        out.append(render(ui.note, "광고 단가를 가져오지 못했습니다 — 잠시 후 다시 시도해주세요."))
        return "".join(out)
    pool = pool.copy()
    pool['광고단가'] = pool['keyword'].map(bids)
    pool = pool[pool['광고단가'].notna() & (pool['광고단가'] > 0)]
    if pool.empty:
        out.append(render(ui.note, EMPTY))
        return "".join(out)
    pool['광고단가'] = pool['광고단가'].astype(int)
    pool['판정'] = [calc_money_verdict(row['광고단가'], row['총 검색량'])['label']
                  for _, row in pool.iterrows()]
    # 트렌드 본체(구글에 뜬 그 검색어) / 파생(그 연관어) 갈라보기
    is_trend = (pool['source'] == 'google_trend')
    if 'keyword_category' in pool.columns:
        is_trend = is_trend | (pool['keyword_category'] == '트렌드')
    parts = ["전체", "오늘 트렌드", "파생 키워드"]
    chosen = part if part in parts else "전체"
    pill = ['<div class="kh-filter">']
    for p in parts:
        cls = "kh-pill on" if p == chosen else "kh-pill"
        pill.append(f'<a class="{cls}" href="/discover?v=golden'
                    f'&p={quote(period)}&t={quote(p)}">{p}</a>')
    pill.append('</div>')
    out.append("".join(pill))
    data = (pool[is_trend] if chosen == "오늘 트렌드"
            else pool[~is_trend] if chosen == "파생 키워드" else pool)
    out.append(_render_table(df, data, sort_col='광고단가', limit=30,
                             lead_cols=[('광고단가', '클릭단가(원)')],
                             extra_cols=[('판정', '판정')], empty_msg=EMPTY))
    out.append(render(ui.tip, "단가 = 네이버 검색광고 <b>최소노출입찰가</b> · "
                              "목록 보기는 크레딧이 들지 않습니다."))
    return "".join(out)


def build_weekly():
    df = db.load_data()
    out = [render(ui.section, "주간 캘린더", "미리 써두면 유리한 앞으로 4주")]
    weekly = db.latest_snapshot(df[df['source'] == 'weekly_event'])
    if weekly.empty:
        out.append(render(ui.note, "예정된 이벤트가 없거나 아직 수집되지 않았습니다."))
    else:
        weekly = weekly.copy()
        weekly['d'] = pd.to_datetime(weekly['event_date'], errors='coerce').dt.date
        weekly = weekly.dropna(subset=['d']).sort_values('d')
        today = datetime.now(timezone.utc).date()
        monday = today - timedelta(days=today.weekday())
        weekly['wk'] = weekly['d'].apply(lambda x: (x - monday).days // 7)
        labels = {0: "이번 주", 1: "다음 주", 2: "2주 후", 3: "3주 후"}
        wd = ['월', '화', '수', '목', '금', '토', '일']

        lifts = {}
        for r_ in weekly.itertuples():
            sc = int(getattr(r_, 'rise_score', 0) or 0)
            if sc <= 0:
                continue
            lifts[str(r_.keyword)] = {
                "lift": sc / 10.0,
                "lead": int(float(getattr(r_, 'comp_ratio', 0) or 7)),
                "days_left": (r_.d - today).days,
            }
        # 이모지 대신 색 라벨(표의 색칩)로 — 차분하게 (2026-08-29)
        VERDICT = {"now": "지금", "soon": "곧",
                   "later": "여유", "flat": "안 급함"}

        def lift_cols(name, kind):
            if kind == '청약':
                return "신규", "여유"
            v = lifts.get(str(name))
            if not v:
                return "—", "—"
            lift, lead, left = v["lift"], v["lead"], v["days_left"]
            if lift < 1.6:
                verdict = "flat"
            elif left <= lead:
                verdict = "now"
            elif left <= lead + 7:
                verdict = "soon"
            else:
                verdict = "later"
            mark = VERDICT.get(verdict, "—")
            if verdict != "flat":
                mark += f" · D-{max(left, 0)}"
            return f"{lift:g}배", mark

        for off in sorted(weekly['wk'].unique()):
            off = int(off)
            if off < 0:
                continue
            ws = monday + timedelta(weeks=off)
            out.append(
                f"<div class='kh-weekhead'><b>{labels.get(off, f'{off}주 후')}</b> "
                f"<span class='mono' style='color:{ui.MUTED};font-size:.82rem'>"
                f"{ws.strftime('%m/%d')} – "
                f"{(ws + timedelta(days=6)).strftime('%m/%d')}</span></div>")
            ev = weekly[weekly['wk'] == off].copy()
            ev['요일'] = ev['d'].apply(lambda x: wd[x.weekday()])
            ev = ev.sort_values('d')
            pair = [lift_cols(n, k)
                    for n, k in zip(ev['keyword'], ev['comp_level'])]
            tbl = pd.DataFrame({
                '이벤트': list(ev['keyword']),
                '언제 쓸까': [b for _, b in pair],
                '작년': [a for a, _ in pair],
                '날짜': [d.strftime('%m/%d') for d in ev['d']],
                '요일': list(ev['요일']),
                '종류': list(ev['comp_level']),
            })
            tbl.index = range(1, len(tbl) + 1)
            out.append(table_html(tbl, center_cols=('언제 쓸까', '작년',
                                                    '날짜', '요일', '종류')))

    out.append(render(ui.section, "계절 캘린더", "해마다 같은 시기에 오르는 키워드"))
    kst = datetime.now(timezone(timedelta(hours=9)))
    m = kst.month
    nm = m % 12 + 1
    k1 = render(ui.kpi, f"{m}월 · 지금 쓸 것", "",
                ", ".join(SEASONAL_CALENDAR.get(m, [])))
    k2 = render(ui.kpi, f"{nm}월 · 미리 쓸 것", "",
                ", ".join(SEASONAL_CALENDAR.get(nm, [])))
    out.append(f'<div class="row" style="grid-template-columns:1fr 1fr">'
               f'<div class="cell">{k1}</div><div class="cell">{k2}</div></div>')
    return "".join(out)


# ⚠️ 2026-09-23: 뉴스 탭(build_news)을 지웠다. news.naver.com 랭킹 페이지를
#    크롤링하던 것이라 공식 API가 아니다. "위험 감수하지 않는다"는 원칙대로 내렸다.


def top_money(n=3, hours=24):
    """지금 가장 비싼 키워드 n개 — 첫 화면 잉크 슬랩용. (2026-09-22)

    ⚠️ 여기서 가짜 숫자를 만들지 않는다. 수집 데이터가 없거나 단가를 못
       가져오면 빈 리스트를 돌려주고, 첫 화면은 슬랩 없이 그려진다.
       단가 조회는 db.cached_min_bids가 6시간 기억하므로 첫 화면이
       매번 외부 API를 부르지는 않는다.
    """
    try:
        df = db.load_data()
        if df.empty or '총 검색량' not in df.columns:
            return []
        pool = df[(df['source'] != 'naver_news') & (df['총 검색량'].fillna(0) > 0)]
        pool = db.latest_snapshot(pool, hours=hours)
        if pool.empty:
            return []
        pool = pool.sort_values('총 검색량', ascending=False).head(60)
        bids = db.cached_min_bids(tuple(pool['keyword'].tolist())) or {}
        if not bids:
            return []
        pool = pool.copy()
        pool['광고단가'] = pool['keyword'].map(bids)
        pool = pool[pool['광고단가'].notna() & (pool['광고단가'] > 0)]
        if pool.empty:
            return []
        pool = pool.sort_values('광고단가', ascending=False).head(n)
        return [{"keyword": str(r['keyword']),
                 "bid": int(r['광고단가']),
                 "search": int(r['총 검색량'] or 0)}
                for _, r in pool.iterrows()]
    except Exception:
        return []
