# -*- coding: utf-8 -*-
"""키워드 발굴 — app.py L2412~ 이식. 문구·판정 원본 그대로."""
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
                      f"아직 {label or '이 항목'} 데이터가 수집되지 않았습니다.<br>"
                      "GitHub의 <b>Actions → collector</b>를 실행하거나 "
                      "<b>3_데이터_수집.bat</b>을 돌려주세요.")
    last = all_rows['created_at_dt'].max()
    mins = int((datetime.now(timezone.utc) - last).total_seconds() // 60)
    ago = f"{mins}분 전" if mins < 120 else f"{mins // 60}시간 전"
    return render(ui.note,
                  f"선택한 기간 안에 수집된 것이 없습니다. "
                  f"가장 최근 수집은 <b>{ago}</b>입니다.<br>"
                  "위에서 더 넓은 기간을 눌러보세요.", True)


def _render_table(df_all, data, sort_col='총 검색량', extra_cols=None, limit=30,
                  show_docs=True, show_volume=True, source=None, label="",
                  empty_msg=None):
    """app.py render_table 이식 — HTML을 돌려준다."""
    if data.empty:
        if empty_msg:
            return render(ui.note, empty_msg)
        if source:
            return _empty_note(df_all, source, label)
        return render(ui.note, "아직 이 항목에 수집된 데이터가 없습니다. "
                               "수집기를 실행하면 채워집니다.")
    d = data.sort_values(by=sort_col, ascending=False).head(limit)
    d = d.reset_index(drop=True)
    cols, names = ['keyword'], ['키워드']
    if show_volume:
        cols += ['총 검색량', '검색량 등급']
        names += ['월 검색량', '검색량']
    if show_docs:
        for c, lb in [('blog_total_docs', '문서수'), ('comp_grade', '경쟁률')]:
            if c in d.columns:
                cols.append(c); names.append(lb)
    for c, lb in (extra_cols or []):
        if c in d.columns:
            cols.append(c); names.append(lb)
    out = d[cols].copy()
    out.columns = names
    out.index = out.index + 1
    return table_html(out)


def build_trend(period="최근"):
    df = db.load_data()
    hours = PERIOD_HOURS.get(period, 3)
    out = [render(ui.section, "구글 트렌드", "지금 사람들이 검색하는 것"),
           _pills("/discover?v=trend", "p", PERIOD_SETS["trend"], period)]
    out.append(_render_table(
        df, db.latest_snapshot(df[df['source'] == 'google_trend'], hours=hours),
        show_docs=False, source='google_trend', label="구글 트렌드"))
    return "".join(out)


def build_golden(period="일별", part="파생 키워드"):
    from naver_api import calc_gold_score
    df = db.load_data()
    h = PERIOD_HOURS.get(period, 24)
    out = [render(ui.section, "골든타임", "뜨고 있는데 아직 안 붐비는 선점 구간"),
           render(ui.pitch, "찾는 사람은 있는데", "아직 아무도 안 썼습니다",
                  "먼저 쓰면 선점 효과를 기대할 수 있습니다. "
                  "검색량이 오르는 중이면 위로 올라옵니다."),
           _pills(f"/discover?v=golden&t={quote(part)}", "p",
                  PERIOD_SETS["slow"], period)]
    golden = db.latest_snapshot(df[df['source'] == 'golden_time'], hours=h)

    money_first = True
    if not golden.empty:
        kws = golden['keyword'].head(100).tolist()
        bids = db.cached_min_bids(tuple(kws))
        if bids:
            golden = golden.copy()
            golden['광고단가'] = golden['keyword'].map(bids)
            golden['황금 점수'] = [
                (calc_gold_score(row['총 검색량'], row.get('blog_total_docs'),
                                 bids.get(row['keyword']),
                                 row.get('comp_ratio')) or {}).get('score')
                for _, row in golden.iterrows()]
            golden = golden.sort_values('황금 점수', ascending=False)
        else:
            out.append(render(ui.note,
                              "광고 단가를 가져오지 못했습니다. "
                              "검색광고 API 키를 확인하거나 잠시 후 다시 시도해주세요."))
            money_first = False

    GT_EMPTY = "추천할만한 키워드가 아직은 없습니다."
    if golden.empty:
        out.append(render(ui.note, GT_EMPTY))
    else:
        extra = [('blog_competition', '최근 30일 글')]
        sort = 'rise_score'
        if money_first and '황금 점수' in golden.columns:
            extra = [('황금 점수', '황금 점수'), ('광고단가', '광고단가')] + extra
            sort = '황금 점수'
        parts = ["🔍 파생 키워드", "🔥 오늘 트렌드", "전체"]
        chosen = part if part in ("파생 키워드", "오늘 트렌드", "전체") else "파생 키워드"
        pill = ['<div class="kh-filter">']
        for p in parts:
            plain = p.split(" ", 1)[-1] if p[0] in "🔍🔥" else p
            cls = "kh-pill on" if plain == chosen else "kh-pill"
            pill.append(f'<a class="{cls}" href="/discover?v=golden'
                        f'&p={quote(period)}&t={quote(plain)}">{p}</a>')
        pill.append('</div>')
        out.append("".join(pill))
        if chosen == "파생 키워드":
            data, lim = golden[golden['keyword_category'] == '세부'], 20
        elif chosen == "오늘 트렌드":
            data, lim = golden[golden['keyword_category'] == '트렌드'], 20
        else:
            data, lim = golden, 40
        out.append(_render_table(df, data, sort_col=sort, show_docs=False,
                                 limit=lim, extra_cols=extra,
                                 empty_msg=GT_EMPTY))
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
        VERDICT = {"now": "🔴 지금", "soon": "🟡 곧",
                   "later": "🟢 여유", "flat": "⚪ 안 급함"}

        def lift_cols(name, kind):
            if kind == '청약':
                return "신규", "🟢 여유"
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


def build_news(period="최근"):
    df = db.load_data()
    h = PERIOD_HOURS.get(period, 3)
    out = [render(ui.section, "뉴스", "지금 많이 읽히는 기사"),
           _pills("/discover?v=news", "p", PERIOD_SETS["trend"], period)]
    out.append(_render_table(
        df, db.latest_snapshot(df[df['source'] == 'naver_news'], hours=h),
        show_docs=False, show_volume=False, source='naver_news', label="뉴스"))
    return "".join(out)
