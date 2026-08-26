import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta, timezone

# naver_api.py가 옛 버전이면 여기서 ImportError가 난다.
# 그냥 죽지 않고 무엇을 해야 하는지 화면에 알려준다.
try:
    from naver_api import (
        analyze_keyword, get_my_blog_feed, estimate_blog_power,
        check_my_rank, calc_win_score, extract_blog_id,
        get_serp, analyze_serp, analyze_titles, build_outline, calc_competition,
    get_volumes,
    calc_opportunity, calc_search_change, expected_visits, ad_density_pct,
    calc_since_registered,
    )
except ImportError as _e:
    import streamlit as _st
    _st.error(
        f"**naver_api.py가 예전 버전입니다.**\n\n"
        f"새로 받은 `naver_api.py`를 app.py와 **같은 폴더**에 덮어쓴 뒤, "
        f"검은 실행창을 완전히 닫고 `2_대시보드_실행.bat`을 다시 실행해주세요.\n\n"
        f"(F5 새로고침만으로는 모듈이 갱신되지 않습니다)\n\n"
        f"---\n원본 메시지: `{_e}`"
    )
    _st.stop()
import ui
import ai_brief

# cache.py가 없어도 앱은 돌아가야 한다.
# (공용 캐시가 없으면 사용자끼리 결과를 나눠 쓰지 못할 뿐이다)
try:
    import cache
except ImportError:
    cache = None
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 설정 ---------------------------------------------------
# 키는 config.py에서 읽는다. 코드에는 키를 두지 않는다.
import config
SUPABASE_URL = config.SUPABASE_URL
SUPABASE_KEY = config.SUPABASE_KEY

# initial_sidebar_state를 지정하지 않으면 화면 폭에 따라 사이드바가 접힌 채로 뜬다.
# 접힌 상태에서 여는 버튼까지 안 보이면 사용자가 손쓸 방법이 없다.
st.set_page_config(page_title="키워드 헌터", page_icon="🎯",
                   layout="wide", initial_sidebar_state="expanded")
ui.inject_css()


@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# 키가 없으면 무엇을 해야 하는지 알려주고 멈춘다.
_missing, _optional_missing = config.check()
if _missing:
    st.error(
        "**API 키가 설정되지 않았습니다.**\n\n"
        "폴더 안의 `.env.예시` 파일을 복사해서 이름을 **`.env`** 로 바꾸고, "
        "그 안에 키를 넣어주세요.\n\n"
        "빠진 항목: " + ", ".join(f"`{k}`" for k in _missing)
    )
    st.stop()

supabase = init_connection()
# 사용자끼리 조회 결과를 나눠 쓰도록 공용 캐시에 연결한다.
if cache is not None:
    cache.attach(supabase)
else:
    st.warning("`cache.py` 파일이 폴더에 없습니다. 같은 폴더에 넣고 다시 실행하면 "
               "같은 키워드를 여러 번 조회해도 네이버를 다시 부르지 않습니다.")


@st.cache_data(ttl=60)
def load_data():
    """
    최근 30일치 원본 데이터를 그대로 반환한다.
    탭마다 필요한 기간이 다르므로, 기간 필터링과 '키워드별 최신값 추리기'는
    각 탭에서 latest_snapshot()으로 따로 처리한다.
    """
    try:
        # 수집이 매일 쌓이면 30일치가 3천 건을 훌쩍 넘는다.
        # 상한이 낮으면 오래된 기록이 잘려 '월별' 조회가 반쪽이 된다.
        wide_start = datetime.now(timezone.utc) - timedelta(days=30)
        res = (supabase.table("trends_master").select("*")
               .gte("created_at", wide_start.isoformat())
               .order("created_at", desc=True).limit(20000).execute())

        df = pd.DataFrame(res.data)
        if df.empty:
            return pd.DataFrame()

        df['created_at_dt'] = pd.to_datetime(df['created_at'], utc=True, errors='coerce')
        df['총 검색량'] = df['monthly_pc'] + df['monthly_mobile']

        defaults = {
            'rise_score': 0, 'pl_avg_depth': 0, 'blog_competition': 0,
            'blog_total_docs': 0, 'comp_ratio': 0, 'comp_grade': '정보없음',
            'event_date': None, 'keyword_category': None,
        }
        for col, default in defaults.items():
            if col not in df.columns:
                df[col] = default
            if default is not None:
                df[col] = df[col].fillna(default)

        # 검색량 등급 (경쟁률과는 다른 지표 — 이건 '얼마나 많이 찾는가')
        def volume_grade(total):
            if total < 500:
                return "매우낮음"
            if total < 5000:
                return "낮음"
            if total < 20000:
                return "보통"
            if total < 100000:
                return "높음"
            return "매우높음"

        df['검색량 등급'] = df['총 검색량'].apply(volume_grade)
        if 'comp_level' in df.columns:
            no_data = (df['source'] == 'google_trend') & (df['comp_level'] == '-')
            df.loc[no_data, '검색량 등급'] = "정보없음"
        df.loc[df['source'] == 'naver_news', '검색량 등급'] = "이슈"
        return df
    except Exception as e:
        st.error(f"데이터를 불러오지 못했습니다: {e}")
        return pd.DataFrame()


# 조회 기간 선택지.
#
# ⚠️ 수집 주기보다 짧은 기간을 고르면 아무것도 안 나온다.
# 수집기는 2시간마다 돌고, 항목마다 그보다 긴 주기를 따로 갖는다.
#   구글 트렌드 : 수집기가 돌 때마다   → 실제 2시간 간격
#   골든타임    : 6시간마다
#   주간 캘린더 : 하루 1번
# 그래서 항목별로 '있을 법한 기간'만 보여준다.
PERIOD_HOURS = {
    "최근": 3, "실시간": 1, "일별": 24, "주간": 24 * 7, "월별": 24 * 30,
    "6시간": 6, "12시간": 12,
}

# 항목별 선택지 (수집 주기에 맞춤)
PERIOD_SETS = {
    "trend": ("최근", "일별", "주간", "월별"),        # 2시간마다 수집
    "slow": ("6시간", "일별", "주간", "월별"),        # 6시간마다 수집
    "daily": ("일별", "주간", "월별"),                # 하루 1번 수집
}


def empty_note(source, hours, label=""):
    """
    선택한 기간에 데이터가 없을 때, 왜 없는지 알려준다.

    '데이터가 없습니다'만 뜨면 고장 난 것처럼 보인다.
    실제로는 기간을 좁게 잡아서 안 걸리는 경우가 대부분이다.
    """
    all_rows = df[df['source'] == source] if not df.empty else df
    if all_rows.empty:
        ui.note(f"아직 {label or '이 항목'} 데이터가 수집되지 않았습니다.<br>"
                "GitHub의 <b>Actions → collector</b>를 실행하거나 "
                "<b>3_데이터_수집.bat</b>을 돌려주세요.")
        return

    last = all_rows['created_at_dt'].max()
    mins = int((datetime.now(timezone.utc) - last).total_seconds() // 60)
    ago = f"{mins}분 전" if mins < 120 else f"{mins // 60}시간 전"
    ui.note(f"선택한 기간 안에 수집된 것이 없습니다. "
            f"가장 최근 수집은 <b>{ago}</b>입니다.<br>"
            "위에서 더 넓은 기간을 눌러보세요.", gold=True)


def period_picker(key, kind="trend", default=None):
    """
    조회 기간 선택.
    kind로 항목의 수집 주기에 맞는 선택지를 고른다.
    """
    options = PERIOD_SETS.get(kind, PERIOD_SETS["trend"])
    if default not in options:
        default = options[0]
    choice = st.radio("조회 기간", list(options), horizontal=True,
                      key=key, index=list(options).index(default))
    return choice, PERIOD_HOURS[choice]


def latest_snapshot(df_source, hours=None):
    """(선택적으로 기간 제한 후) 키워드별 가장 최근 값만 남긴다."""
    d = df_source
    if hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        d = d[d['created_at_dt'] >= cutoff]
    if d.empty:
        return d
    return d.sort_values('created_at_dt', ascending=False).drop_duplicates(subset='keyword', keep='first')


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
    '키워드': ("large", None),
    '이벤트': ("large", None),
    '제목': ("large", None),
    '세부 주제': ("large", None),
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


def col_config(columns):
    """
    표의 컬럼 폭을 내용에 맞게 지정한다.
    기본값은 남는 공간을 컬럼끼리 균등 분배해서
    숫자 한 칸짜리 컬럼도 불필요하게 넓어진다.
    """
    cfg = {}
    try:
        for name in columns:
            width, fmt = COL_WIDTH.get(name, ("small", None))
            if fmt:
                cfg[name] = st.column_config.NumberColumn(name, width=width, format=fmt)
            else:
                cfg[name] = st.column_config.Column(name, width=width)
    except AttributeError:
        return None
    return cfg


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
}

TINT_COLS = {'검색량', '경쟁률', '진단', '판단', '등급', '종류', '경쟁'}


def style_table(frame):
    """
    표에 옅은 색을 입힌다.
    등급 계열은 의미별 색, 수치는 값이 클수록 진해지는 옅은 네이비.
    """
    def tint_cell(val):
        bg, fg = GRADE_TINT.get(str(val), (None, None))
        if bg:
            return f'background-color:{bg};color:{fg};font-weight:600'
        return ''

    sty = frame.style
    tint_targets = [c for c in frame.columns if c in TINT_COLS]
    if tint_targets:
        sty = sty.map(tint_cell, subset=tint_targets)

    num_cols = [c for c in ('월 검색량', '기회 점수', '내 승산', '광고 경쟁도',
                            '문서수', '누적 문서수', '최근 30일 글')
                if c in frame.columns and pd.api.types.is_numeric_dtype(frame[c])]
    for c in num_cols:
        col = frame[c]
        lo, hi = col.min(), col.max()
        if pd.isna(lo) or pd.isna(hi) or hi == lo:
            continue

        def shade(v, lo=lo, hi=hi):
            if pd.isna(v):
                return ''
            t = (v - lo) / (hi - lo)
            return f'background-color:rgba(27,58,75,{0.06 + t * 0.26:.3f})'

        sty = sty.map(shade, subset=[c])
    return sty


def show_table(frame, height=None):
    """
    모든 표를 같은 규칙으로 그린다.
    스타일이나 컬럼 설정이 버전 문제로 실패해도 표는 반드시 보이게 물러난다.
    """
    kwargs = {"use_container_width": True}
    if height is not None:
        kwargs["height"] = height
    cfg = col_config(frame.columns)
    if cfg is not None:
        kwargs["column_config"] = cfg
    try:
        st.dataframe(style_table(frame), **kwargs)
        return
    except Exception:
        pass
    try:
        st.dataframe(frame, **kwargs)
        return
    except Exception:
        pass
    st.dataframe(frame, use_container_width=True)


def render_table(data, sort_col='총 검색량', extra_cols=None, limit=30,
                 show_docs=True, show_volume=True, source=None, label=""):
    """
    show_docs   : 문서수/경쟁률 컬럼 표시 여부
    show_volume : 월 검색량/검색량 등급 컬럼 표시 여부
    source      : 비어 있을 때 왜 없는지 안내하기 위한 소스 이름
    """
    if data.empty:
        if source:
            empty_note(source, None, label)
        else:
            ui.note("아직 이 항목에 수집된 데이터가 없습니다. "
                    "수집기를 실행하면 채워집니다.")
        return

    d = data.sort_values(by=sort_col, ascending=False).head(limit).reset_index(drop=True)

    cols = ['keyword']
    names = ['키워드']
    if show_volume:
        cols += ['총 검색량', '검색량 등급']
        names += ['월 검색량', '검색량']
    if show_docs:
        for c, label in [('blog_total_docs', '문서수'), ('comp_grade', '경쟁률')]:
            if c in d.columns:
                cols.append(c)
                names.append(label)
    for c, label in (extra_cols or []):
        if c in d.columns:
            cols.append(c)
            names.append(label)

    out = d[cols].copy()
    out.columns = names
    out.index = out.index + 1
    show_table(out)


df = load_data()

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


# ============================================================
# 사이드바 — 내 블로그 등록 (향후 회원가입/결제가 들어갈 자리)
# ============================================================
# 사이드바를 없앴다.
# 모바일에서 기본으로 접히는 데다 여는 버튼을 찾기 어려워
# 실제로는 쓰이지 않는 공간이 된다. 필요한 것만 본문 위로 옮겼다.

my_blog_id = st.session_state.get("blog_id", "")

ui.masthead(
    "키워드 헌터",
    "검색량만 보면 경쟁을 알 수 없습니다. 이미 쓰인 글까지 재서 "
    "지금 이길 수 있는 키워드를 찾습니다."
)

# --- 상단 정보 줄 (사이드바에 있던 것들) ---
_fresh = ""
if not df.empty:
    _last = df['created_at_dt'].max()
    _mins = int((datetime.now(timezone.utc) - _last).total_seconds() // 60)
    _fresh = f"{_mins}분 전" if _mins < 120 else f"{_mins // 60}시간 전"

try:
    import naver_api as _na
    _ver = _na.MODULE_VERSION
except Exception:
    _ver = ""

ui.topbar(st.session_state.get("blog_id", ""), _fresh, _ver)

# --- 검색창 (항상 최상단) ---
# 어느 탭에 있든 바로 검색할 수 있게 탭 위에 둔다.
# 도구의 핵심 동작이 화면에 들어오자마자 보여야 한다.
with st.container(border=True):
    kc1, kc2 = st.columns([5, 1])
    with kc1:
        kw_input = st.text_input(
            "조사할 키워드",
            placeholder="분석할 키워드를 입력하세요",
            key="research_kw",
            label_visibility="collapsed")
    with kc2:
        searched = st.button("🔍 분석", use_container_width=True,
                             key="research_go", type="primary")

if searched and kw_input.strip():
    st.session_state["active_kw"] = kw_input.strip()
elif kw_input.strip():
    st.session_state["active_kw"] = kw_input.strip()
elif not kw_input:
    st.session_state.pop("active_kw", None)

research_kw = st.session_state.get("active_kw", "")

# --- 내 블로그 등록 ---
# 한 번 등록하면 다시 열 일이 없어서 접어둔다.
_registered = bool(st.session_state.get("blog_id"))
with st.expander(
        f"🏠 내 블로그  ·  {st.session_state['blog_id']}" if _registered
        else "🏠 내 블로그 주소 입력하기",
        expanded=False):
    bc1, bc2 = st.columns([4, 1])
    with bc1:
        blog_input = st.text_input(
            "블로그 주소",
            value=st.session_state.get("blog_id", ""),
            placeholder="blog.naver.com/myid   또는   myid",
            key="blog_input_main",
            label_visibility="collapsed")
    with bc2:
        if st.button("등록", use_container_width=True, key="blog_save_main"):
            if blog_input.strip():
                st.session_state["blog_id"] = extract_blog_id(blog_input)
            else:
                st.session_state.pop("blog_id", None)
            st.rerun()
    if not _registered:
        st.caption("등록하면 키워드마다 '내 블로그로 뚫을 수 있는지'까지 계산합니다.")

# 관리 탭은 주소 뒤에 열쇠말을 붙였을 때만 나타난다.
#
#   https://내주소.streamlit.app/?dog11286575=1
#
# 평소에는 탭 자체가 없어서 남이 볼 수 없고,
# 열쇠말로 들어가도 비밀번호를 한 번 더 물어본다.
def _get_query_params():
    """Streamlit 버전에 따라 주소 파라미터를 가져온다."""
    try:
        return dict(st.query_params)
    except Exception:
        pass
    try:
        return st.experimental_get_query_params()
    except Exception:
        return {}


def _admin_requested():
    qp = _get_query_params()
    if not config.ADMIN_KEY or config.ADMIN_KEY not in qp:
        return False
    # 열쇠말은 맞는데 비밀번호가 서버에 없으면 이유를 알려준다.
    if not config.ADMIN_PASSWORD:
        st.warning(
            "관리 탭을 열려면 **ADMIN_PASSWORD** 가 필요합니다.\n\n"
            "Streamlit Cloud라면 **Manage app → Settings → Secrets** 에 "
            "아래 두 줄을 넣고 저장해주세요.\n\n"
            "```\nADMIN_PASSWORD = \"원하는비밀번호\"\n"
            "ADMIN_KEY = \"dog11286575\"\n```"
        )
        return False
    return True


# 주소에 ?debug=1 을 붙이면 무엇 때문에 관리 탭이 안 뜨는지 알려준다.
if "debug" in _get_query_params():
    _qp = _get_query_params()
    st.info(
        f"**진단**\n\n"
        f"- 주소 파라미터: `{list(_qp.keys()) or '없음'}`\n"
        f"- 찾는 열쇠말: `{config.ADMIN_KEY or '(설정 안 됨)'}`\n"
        f"- 열쇠말 일치: `{config.ADMIN_KEY in _qp if config.ADMIN_KEY else False}`\n"
        f"- 비밀번호 설정됨: `{bool(config.ADMIN_PASSWORD)}`\n"
        f"- 모듈 버전: `{__import__('naver_api').MODULE_VERSION}`"
    )

_tab_names = ["🔎 키워드 조사", "📈 추적기", "🏠 내 블로그", "📡 키워드 발굴"]
# 한 번 들어오면 조작하는 동안 유지된다 (주소가 지워져도 탭이 사라지지 않게)
if _admin_requested():
    st.session_state["admin_visible"] = True
_has_admin = bool(st.session_state.get("admin_visible"))
if _has_admin:
    _tab_names.append("🔧 관리")

_all_tabs = st.tabs(_tab_names)
tabs = _all_tabs[:4]
admin_tab = _all_tabs[4] if _has_admin else None

with tabs[0]:
    sub_research = st.tabs(["키워드 분석", "상위노출 해부", "글감 만들기"])
with tabs[3]:
    sub_discover = st.tabs(["구글 트렌드", "골든타임", "주간 캘린더", "뉴스"])

# ------------------------------------------------------------
# 1. 키워드 분석
# ------------------------------------------------------------
with sub_research[0]:
    ui.section("단일 키워드 진단", "이 키워드, 지금 뛰어들어도 될까")
    ui.note(
        "두 가지를 따로 봅니다.<br>"
        "<b>누적 문서수</b> — 지금까지 쌓인 글. 시장이 얼마나 포화됐는지<br>"
        "<b>최근 30일 발행</b> — 요즘 쓰이는 글. 지금 사람들이 몰리고 있는지<br>"
        "둘 다 월 검색량과 비교합니다. 특히 <b>누적은 많은데 최근이 한산한</b> 키워드는, "
        "오래된 글만 남아 있다는 뜻이라 새 글로 밀어낼 여지가 있습니다.")
    st.write("")

    kw = research_kw
    if not kw:
        ui.note("위쪽 입력칸에 키워드를 넣으면 이 탭과 "
                "<b>상위노출 해부</b>, <b>글감 만들기</b>가 한꺼번에 채워집니다.", gold=True)

    if kw:
        with st.spinner(f"'{kw}' 측정 중"):
            r = analyze_keyword(kw.strip())

        recent_docs = r.get('recent_docs')
        recent_grade = r.get('recent_grade', '정보없음')
        opp = r.get('opportunity') or {'score': 0, 'label': '정보없음', 'note': ''}

        if 'opportunity' not in r:
            ui.note("최근 30일 지표가 로드되지 않았습니다. 검은 실행창을 닫고 "
                    "<b>2_대시보드_실행.bat</b>을 다시 실행해주세요.", gold=True)

        # --- 한 줄 요약 지표 -----------------------------------
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            ui.kpi("월 검색량", compact_num(r['total_search']),
                   f"PC {r['monthly_pc']:,} · 모바일 {r['monthly_mobile']:,}")
        with c2:
            ui.kpi("이미 쓰인 글", compact_num(r['doc_count']),
                   f"{r['doc_count']:,}편" if r['doc_count'] is not None else "조회 실패")
        with c3:
            if recent_docs is not None:
                # 1000건이 한계라 그 이상은 발행 속도로 추정한다.
                # 추정도 어려우면 정직하게 '1000+'로 둔다.
                if r.get('recent_estimated'):
                    val = f"약 {compact_num(recent_docs)}"
                    sub = f"발행 속도로 추정 · {recent_grade}"
                elif r.get('recent_capped'):
                    val = f"{recent_docs:,}+"
                    sub = f"너무 많아 정확히 못 셈 · {recent_grade}"
                else:
                    val = f"{recent_docs:,}"
                    sub = f"요즘 분위기 · {recent_grade}"
                ui.kpi("최근 30일 새 글", val, sub)
            else:
                ui.kpi("최근 30일 새 글", "—", "조회 실패")
        with c4:
            ad_pct, ad_label = ad_density_pct(r['pl_avg_depth'])
            ui.kpi("광고 경쟁", f"{ad_pct}%", f"{ad_label} · 높을수록 단가가 비쌈")

        st.write("")

        # --- 검색량 구성 + 경쟁률 눈금 --------------------------
        d1, d2 = st.columns([1, 2])
        with d1:
            ui.donut(
                [("모바일", r['monthly_mobile'], ui.DEEP),
                 ("PC", r['monthly_pc'], ui.GOLD)],
                compact_num(r['total_search']), "월 검색량")
        with d2:
            if r.get('comp_ratio') is not None:
                ui.scale_gauge(
                    r['comp_ratio'],
                    [(0.1, "아주 좋음", ui.GOOD), (0.5, "좋음", ui.GOOD),
                     (2, "보통", ui.WARN), (10, "나쁨", ui.BAD), (None, "최악", ui.BAD)],
                    title="경쟁률 — 쓰인 글 ÷ 찾는 사람",
                    note="낮을수록 유리합니다. 1이면 찾는 사람 수만큼 글이 있다는 뜻")
            ui.gauge("기회 점수", opp['score'], ("불리", "보통", "유리"))
            if opp.get("breakdown"):
                ui.score_breakdown(opp["breakdown"], opp["score"])

        st.write("")

        # --- 진단: 어느 칸에 속하는지 색으로 -------------------
        ui.diagnosis_matrix(r['comp_grade'], recent_grade,
                            opp['label'], opp.get('note', ''))

        # --- 내 승산 -------------------------------------------
        power, my_rank, win = None, None, None
        if my_blog_id:
            with st.spinner("내 블로그와 대조 중"):
                feed = get_my_blog_feed(my_blog_id)
                power = estimate_blog_power(feed["posts"])
                win = calc_win_score(r['comp_ratio'], power["score"],
                                     opportunity_score=opp['score'])
                my_rank = check_my_rank(kw.strip(), my_blog_id)

            if win["score"] is not None:
                ui.gauge(f"내 승산 · {win['verdict']}", win["score"],
                         ("어려움", "보통", "유리"))
                rank_txt = (f"이 키워드 상위 30위 안에 내 글이 <b>{my_rank}위</b>로 있습니다."
                            if my_rank else "아직 상위 30위 안에 내 글이 없습니다.")
                st.markdown(f'<div class="note" style="margin-top:6px">{rank_txt}</div>',
                            unsafe_allow_html=True)
        else:
            ui.note("사이드바나 <b>내 블로그</b> 탭에서 블로그를 등록하면 "
                    "<b>내 블로그로 이 키워드를 뚫을 수 있는지</b>까지 계산합니다.", gold=True)

        # --- AI 판단 브리핑 ---------------------------------
        st.write("")
        if ai_brief.is_enabled():
            @st.cache_data(ttl=1800, show_spinner=False)
            def get_brief(k, payload):
                return ai_brief.brief_keyword(k, payload["a"], payload.get("serp"),
                                              payload.get("power"), payload.get("rank"))

            # recent_capped를 빠뜨리면 AI가 '1000+'를 '정확히 1000건'으로 읽는다
            payload = {"a": {kk: r.get(kk) for kk in
                             ("total_search", "monthly_pc", "monthly_mobile",
                              "doc_count", "recent_docs", "recent_capped",
                              "recent_estimated",
                              "comp_ratio", "comp_grade",
                              "recent_grade", "opportunity", "pl_avg_depth")}}
            if my_blog_id and power:
                payload["power"] = {"posts_per_week": power.get("posts_per_week"),
                                    "level": power.get("level"),
                                    "days_since_last": power.get("days_since_last")}
                payload["rank"] = my_rank
            with st.spinner("측정값을 읽고 판단하는 중..."):
                brief, berr = get_brief(kw.strip(), payload)
            if brief:
                ui.brief_card(brief, "AI 판단 · 이 키워드 써도 될까")
            else:
                ui.note(f"판단 브리핑을 만들지 못했습니다. <small>{berr}</small>")
        else:
            ui.note("<b>AI 판단 브리핑</b>을 켜려면 <code>ai_brief.py</code>의 "
                    "<code>ANTHROPIC_API_KEY</code>에 키를 넣어주세요. "
                    "측정된 숫자를 읽고 '써라 / 조건부 / 피해라'를 근거와 함께 알려줍니다.",
                    gold=True)

        if r.get("related"):
            ui.note("↓ 아래에 <b>🏹 사냥 지도</b>가 있습니다. "
                    "연관 키워드를 검색량·문서수 좌표에 흩뿌려서, "
                    "어느 키워드가 노려볼 만한 구역에 있는지 색으로 구분해 보여줍니다.")

        st.divider()
        ui.section("사냥 순위", "노려볼 만한 연관 키워드 10개")

        rel = r.get("related", [])
        if not rel:
            ui.note("연관 키워드를 찾지 못했습니다. 더 일반적인 키워드로 시도해보세요.")
        else:
            # 측정 개수를 고를 수 있게 한다.
            # Streamlit은 스크립트가 도는 동안 다른 조작을 받지 못하므로,
            # 급할 때는 개수를 줄여 대기 시간을 짧게 가져갈 수 있어야 한다.
            # 네이버는 '같은 업종의 다른 키워드'도 연관어로 준다.
            # (삼성 → LG전자 같은 경우) 기본은 키워드를 품은 것만 본다.
            only_contains = st.checkbox(
                "이 키워드를 포함한 것만 보기", value=True, key="rel_filter",
                help="끄면 네이버가 같은 업종으로 묶은 다른 키워드까지 함께 봅니다.")
            # ⚠️ 검색량 0인 것을 빼면 안 된다.
            # 자동완성으로 온 키워드는 검색량을 아직 모를 뿐(0)이지
            # 사람들이 안 찾는다는 뜻이 아니다.
            # '국민은행'처럼 광고 데이터가 없는 키워드는 연관어가 전부
            # 자동완성이라, 이 조건 하나로 후보가 통째로 사라졌다.
            pool_rel = [i for i in rel
                        if i.get("contains", True) or not only_contains]

            # 검색량을 아는 것을 먼저, 그 안에서 큰 순으로.
            # 모르는 것(자동완성)은 뒤에 붙여 남는 자리를 채운다.
            pool_rel = sorted(
                pool_rel,
                key=lambda x: (-(x["monthly_pc"] + x["monthly_mobile"]),
                               x.get("source") == "자동완성"))
            avail = [i["keyword"] for i in pool_rel]
            if not avail:
                ui.note("이 키워드를 포함한 연관어가 없습니다. "
                        "위 체크를 끄면 같은 업종의 다른 키워드까지 볼 수 있습니다.")
            else:
                _no_vol = sum(1 for i in pool_rel
                              if (i["monthly_pc"] + i["monthly_mobile"]) == 0)
                if _no_vol:
                    st.caption(f"후보 {len(avail)}개 중 {_no_vol}개는 검색량을 "
                               "아직 모릅니다. 순위를 매길 때 함께 조회합니다.")
            # 버튼을 눌렀을 때만 잰다.
            # 키워드를 칠 때마다 자동으로 API를 쓰면 호출 한도가 금방 닳는다.
            with st.container(border=True):
                mc1, mc2 = st.columns([2, 1])
                with mc1:
                    pick_n = st.radio("몇 개를 잴까요", [5, 10, 15],
                                      index=1, horizontal=True, key="map_count",
                                      help="많이 잴수록 시간이 더 걸립니다. "
                                           "상위 10개만 순위에 표시됩니다.")
                with mc2:
                    st.markdown('<div class="search-btn-pad"></div>',
                                unsafe_allow_html=True)
                    draw_map = st.button("🏹 순위 매기기",
                                         use_container_width=True, key="map_go")

            if draw_map:
                st.session_state["map_kw"] = r["keyword"]

            # 다른 키워드를 새로 검색하면 지도를 닫는다
            if st.session_state.get("map_kw") not in (None, r["keyword"]):
                st.session_state.pop("map_kw", None)

            show_map = st.session_state.get("map_kw") == r["keyword"]
            targets = avail[:pick_n] if show_map else []

            # 이미 아는 검색량을 함께 넘긴다.
            # 다시 물으면 호출만 낭비되고, 힌트로 쪼개지면서
            # 엉뚱한 값이 돌아와 '측정 실패'로 처리되는 일이 생긴다.
            # 검색량을 아는 것만 넘긴다.
            # 자동완성으로 온 것(0)은 넘기지 않아야 측정 단계에서
            # 네이버에 직접 물어보고 실제 값을 채운다.
            known = {i["keyword"]: {
                "monthly_pc": i["monthly_pc"],
                "monthly_mobile": i["monthly_mobile"],
                "comp_level": i.get("comp_level", "-"),
                "pl_avg_depth": 0,
            } for i in pool_rel
                if (i["monthly_pc"] + i["monthly_mobile"]) > 0}

            @st.cache_data(ttl=1800, show_spinner=False)
            def measure_batch(keywords, stats):
                """
                연관 키워드를 한꺼번에 측정한다.

                ⚠️ 검색량을 모르는 키워드(자동완성으로 온 것)를
                analyze_keyword에 그냥 넘기면, 내부에서 힌트로 쪼개지면서
                응답 첫 항목이 원래 키워드가 아니게 되어 0이 나온다.
                그래서 모르는 것들은 get_volumes로 5개씩 묶어 먼저 채운 뒤
                측정에 넘긴다. (get_volumes는 쪼개지 않는다)
                """
                smap = dict(stats)

                # ① 검색량을 모르는 것부터 채운다 (5개씩, 호출 1회로 5개)
                unknown = [k for k in keywords if k not in smap]
                for i in range(0, len(unknown), 5):
                    try:
                        vols = get_volumes(unknown[i:i + 5])
                    except Exception:
                        continue
                    for k in unknown[i:i + 5]:
                        v = vols.get(k.replace(" ", "").upper())
                        if v:
                            smap[k] = {"monthly_pc": int(v * 0.3),
                                       "monthly_mobile": v - int(v * 0.3),
                                       "comp_level": "-", "pl_avg_depth": 0}

                # ② 문서수를 잰다 (검색량은 이미 알고 있다)
                out, failed = {}, []
                with ThreadPoolExecutor(max_workers=4) as pool:
                    futures = {
                        pool.submit(analyze_keyword, k, True, False, False,
                                    smap.get(k), True): k
                        for k in keywords if k in smap
                    }
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

                # 검색량이 정말 0인 것은 '실패'가 아니라 '수요 없음'이다
                no_demand = [k for k in keywords if k not in smap]
                return ([out[k] for k in keywords if k in out],
                        failed, no_demand)

            subs, failed, no_demand = [], [], []
            if targets:
                _stats = tuple(sorted(
                    (k, tuple(sorted(known[k].items())))
                    for k in targets if k in known))
                try:
                    with st.status(f"연관 키워드 {len(targets)}개 측정 중...",
                                   expanded=True) as status:
                        st.markdown('<div class="prog-label">검색량과 문서수를 '
                                    '조회하고 있습니다. 잠시만 기다려주세요.</div>',
                                    unsafe_allow_html=True)
                        subs, failed, no_demand = measure_batch(
                            tuple(targets), _stats)
                        status.update(label=f"측정 완료 · {len(subs)}개",
                                      state="complete", expanded=False)
                except AttributeError:
                    with st.spinner(f"연관 키워드 {len(targets)}개 측정 중..."):
                        subs, failed, no_demand = measure_batch(
                            tuple(targets), _stats)

            if no_demand:
                st.caption(f"{len(no_demand)}개는 검색량이 확인되지 않아 "
                           "순위에서 제외했습니다.")

            if failed:
                ui.note(f"{len(failed)}개는 조회하지 못했습니다. "
                        "네이버 API 호출이 몰리면 일부가 거절될 수 있습니다. "
                        "잠시 후 다시 시도하거나 측정 개수를 줄여보세요.")

            rows = []
            for sub in subs:
                rd = sub.get('recent_docs')
                sopp = sub.get('opportunity') or {'score': 0, 'label': '정보없음'}
                rows.append({
                    "키워드": sub["keyword"],
                    "월 검색량": sub["total_search"],
                    "누적 문서수": sub["doc_count"] if sub["doc_count"] is not None else 0,
                    "최근 30일": ((f"{rd:,}+" if sub.get('recent_capped') else f"{rd:,}")
                                if rd is not None else "—"),
                    "기회 점수": sopp["score"],
                    "진단": sopp["label"],
                })

            if not rows:
                if not targets:
                    ui.note("<b>순위 매기기</b>를 누르면 연관 키워드의 문서수를 재서 "
                            "노려볼 만한 순서대로 세웁니다.")
                elif failed:
                    ui.note(f"측정에 실패했습니다({len(failed)}개). "
                            "네이버 호출이 몰리면 거절될 수 있습니다. "
                            "잠시 후 다시 눌러보세요.")
                else:
                    ui.note("순위를 매길 만한 연관 키워드를 찾지 못했습니다. "
                            "더 일반적인 키워드로 시도해보세요.")
            else:
                rel_df = pd.DataFrame(rows).sort_values(
                    "기회 점수", ascending=False).reset_index(drop=True)
                rel_df.index = rel_df.index + 1

                ui.note("기회 점수가 높은 순입니다. "
                        "<b>찾는 사람은 있는데 쓰인 글이 적을수록</b> 위로 옵니다. "
                        "1~3위는 특히 노려볼 만한 자리입니다.")

                ui.hunt_rank(
                    [{"keyword": row["키워드"],
                      "search": int(row["월 검색량"]),
                      "docs": int(row["누적 문서수"]),
                      "score": int(row["기회 점수"]),
                      "label": row["진단"]}
                     for _, row in rel_df.iterrows()],
                    main={"keyword": r["keyword"], "search": r["total_search"],
                          "docs": r.get("doc_count")},
                    limit=10)

                with st.expander("표로 보기"):
                    show_table(rel_df)

        # --- 연관 키워드 전체 ---
        # 네이버가 주는 걸 다 보여준다. 사냥 지도는 문서수까지 재느라
        # 몇 개만 다루지만, 검색량만 보는 목록은 수백 개도 부담이 없다.
        all_rel = r.get("related") or []
        if all_rel:
            st.write("")
            ui.section("연관 키워드 전체", f"{len(all_rel)}개")

            # 어떤 조각으로 물어봤는지 보여준다.
            # 네이버는 띄어쓰기에 민감해서 '반딧불축제'와 '반딧불 축제'가
            # 다른 결과를 준다. 그래서 여러 형태로 나눠 묻는다.
            _hints = r.get("hints") or []
            _ac_count = sum(1 for i in all_rel if i.get("source") == "자동완성")
            if _ac_count:
                ui.note(f"이 중 <b>{_ac_count}개</b>는 네이버 검색창 자동완성에서 "
                        "가져왔습니다. 검색광고 데이터에 없는 이슈·뉴스 키워드까지 "
                        "찾기 위해서입니다. 검색량은 그 키워드를 직접 조회해야 나옵니다.")

            if len(_hints) > 1:
                chips = " ".join(
                    f'<span class="hint-chip">{h}</span>' for h in _hints)
                st.markdown(
                    f'<div class="hint-row">이렇게 나눠서 찾았습니다 {chips}</div>',
                    unsafe_allow_html=True)

            fc1, fc2 = st.columns([1, 1])
            with fc1:
                only_has = st.checkbox(f"'{r['keyword']}' 포함한 것만",
                                       value=False, key="rel_all_filter")
            with fc2:
                min_vol = st.select_slider(
                    "최소 검색량", options=[0, 100, 500, 1000, 5000],
                    value=0, key="rel_all_min")

            rows_all = [{
                "키워드": i["keyword"],
                # 자동완성으로 온 것은 검색량을 아직 모른다.
                # 0으로 표시하면 '아무도 안 찾는다'로 오해하므로 구분한다.
                "월 검색량": (i["monthly_pc"] + i["monthly_mobile"]
                            if i.get("source") != "자동완성" else None),
                "경쟁": i.get("comp_level") or "-",
                "출처": i.get("source", "검색광고"),
            } for i in all_rel
                if (i.get("contains", True) or not only_has)
                and (i.get("source") == "자동완성"
                     or (i["monthly_pc"] + i["monthly_mobile"]) >= min_vol)]

            if not rows_all:
                ui.note("조건에 맞는 연관 키워드가 없습니다. 최소 검색량을 낮춰보세요.")
            else:
                # 자동완성으로 온 것은 검색량을 모른다.
                # 한 번에 채워주면 어느 게 쓸 만한지 바로 판단할 수 있다.
                _unknown = [x["키워드"] for x in rows_all
                            if x["월 검색량"] is None]
                if _unknown:
                    uc1, uc2 = st.columns([1, 3])
                    with uc1:
                        fill = st.button(f"검색량 채우기 ({len(_unknown)}개)",
                                         key="fill_vol",
                                         use_container_width=True)
                    with uc2:
                        st.caption("자동완성으로 찾은 키워드의 검색량을 한 번에 조회합니다. "
                                   f"약 {max(1, (len(_unknown) + 4) // 5)}회 조회가 필요합니다.")

                    if fill:
                        @st.cache_data(ttl=1800, show_spinner=False)
                        def fill_volumes(words):
                            """5개씩 묶어 조회한다 (한 번에 5개까지 가능)."""
                            out = {}
                            for i in range(0, len(words), 5):
                                try:
                                    out.update(get_volumes(words[i:i + 5]))
                                except Exception:
                                    pass
                            return out

                        with st.spinner("검색량을 조회하는 중..."):
                            found = fill_volumes(tuple(_unknown))
                        for x in rows_all:
                            if x["월 검색량"] is None:
                                v = found.get(x["키워드"].replace(" ", "").upper())
                                if v is not None:
                                    x["월 검색량"] = v
                        st.success(f"{sum(1 for v in found.values() if v)}개의 "
                                   "검색량을 찾았습니다.")

                adf = pd.DataFrame(rows_all).sort_values(
                    "월 검색량", ascending=False,
                    na_position="last").reset_index(drop=True)
                # None이 그대로 보이지 않게 빈칸으로 바꾼다
                adf["월 검색량"] = adf["월 검색량"].map(
                    lambda v: f"{int(v):,}" if pd.notna(v) else "—")
                adf.index = adf.index + 1
                st.dataframe(adf, use_container_width=True, height=440,
                             column_config=col_config(adf.columns) or None)
                st.caption(f"{len(rows_all)}개 표시 · 전체 {len(all_rel)}개")

# ------------------------------------------------------------
# 2. 상위노출 해부
# ------------------------------------------------------------
with sub_research[1]:
    ui.section("상위노출 해부", "이 키워드로 1등 한 글들은 어떻게 생겼나")
    ui.note("경쟁률 숫자만으로는 안 보이는 것이 있습니다. "
            "상위권이 전부 몇 년 전 글이라면 낡은 정보만 남았다는 뜻이고, "
            "새로 제대로 쓴 글로 밀어낼 여지가 큽니다.")
    st.write("")

    serp_kw = research_kw
    if not serp_kw:
        ui.note("위쪽 입력칸에 키워드를 넣어주세요.", gold=True)

    if serp_kw:
        serp_sort = st.radio("정렬", ["노출 순위순", "최신 발행순"],
                             horizontal=True, key="serp_sort")
        sort_key = "date" if serp_sort == "최신 발행순" else "sim"

        @st.cache_data(ttl=1800, show_spinner=False)
        def load_serp(k, sort_key):
            data = get_serp(k, display=30, sort=sort_key)
            # 판정은 항상 '노출 순위순' 기준으로 낸다.
            # 최신순 목록으로 판정하면 당연히 최신 글만 나와 의미가 없다.
            base = data if sort_key == "sim" else get_serp(k, display=30, sort="sim")
            return data, analyze_serp(base, top_n=10)

        with st.spinner(f"'{serp_kw}' 상위 글을 분석하는 중..."):
            serp, meta = load_serp(serp_kw.strip(), sort_key)

        if not serp:
            ui.note("검색 결과를 가져오지 못했습니다. API 키 설정을 확인해주세요.")
        else:
            head = "최신 발행순 10개" if sort_key == "date" else "노출 순위 상위 10개"
            ui.section(head, "제목과 발행 시점")
            if my_blog_id:
                ui.note(f"내 블로그(<code>{my_blog_id}</code>)의 글이 있으면 금색으로 표시됩니다. "
                        "다른 사람의 블로그 이름은 표시하지 않습니다.")
            ui.serp_list(serp, my_blog_id=my_blog_id, limit=10)

            with st.expander("11위 ~ 30위도 보기"):
                ui.serp_list(serp[10:], my_blog_id=my_blog_id, limit=20)


            st.divider()
            n_top = meta["count"]
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                short = {"최신 글 경쟁": "최신 글 경쟁", "오래된 글이 1등": "오래된 글이 1등",
                         "새 글 옛 글 섞임": "섞여 있음"}.get(meta["verdict"], meta["verdict"])
                ui.kpi("판정", short, f"상위 {n_top}개를 보고 내린 결론")
            with c2:
                ma = meta["median_age"]
                if ma is None:
                    age_txt, age_sub = "—", "발행일을 읽지 못함"
                elif ma >= 365:
                    age_txt = f"{ma // 365}년 전"
                    age_sub = "상위 글이 대체로 오래됨"
                elif ma >= 30:
                    age_txt = f"{ma // 30}개월 전"
                    age_sub = "상위 글이 비교적 최근"
                else:
                    age_txt = f"{ma}일 전"
                    age_sub = "상위 글이 갓 올라옴"
                ui.kpi("언제 쓰인 글인가", age_txt, age_sub)
            with c3:
                dated = meta.get("dated_count") or n_top
                unknown = meta.get("unknown_date") or 0
                sub = f"1년 넘은 글은 {meta['old_365']}개"
                if unknown:
                    sub += f" · 발행일 불명 {unknown}개 제외"
                ui.kpi("상위 10개 중 최근 3개월 글",
                       f"{meta['fresh_90']}개 / {dated}개", sub)
            with c4:
                tb = meta["top_blogger"]
                uniq = int(meta["unique_ratio"] * 100)
                if tb and tb[1] > 1:
                    ui.kpi("한 블로그 독점", f"최대 {tb[1]}칸",
                           f"서로 다른 블로그 {uniq}%")
                else:
                    ui.kpi("한 블로그 독점", "없음",
                           "전부 다른 블로그가 한 칸씩")

            st.write("")
            ui.note(f"<b>{meta['verdict']}</b> — {meta['advice']}",
                    gold=meta["verdict"] == "오래된 글이 1등")

            st.write("")
            g1, g2 = st.columns([3, 2])
            with g1:
                ui.bar_series(meta["age_buckets"],
                              "상위 10개 글이 언제 쓰였나 (몇 개월 전)",
                              height=170, accent=ui.DEEP, show_pct=True)
            with g2:
                fresh_pct = meta["fresh_90"] / max(1, meta["count"]) * 100
                ui.gauge("신규 유입 압력", int(fresh_pct),
                         ("낮음", "보통", "높음"),
                         color=ui.BAD if fresh_pct >= 70 else (
                             ui.WARN if fresh_pct >= 40 else ui.GOOD))
                ui.note("최근 3개월 글이 많을수록 계속 새 글이 들어오는 자리라 "
                        "한 번 올라가도 유지가 어렵습니다.")

            st.write("")
# ------------------------------------------------------------
# 3. 글감 만들기
# ------------------------------------------------------------
with sub_research[2]:
    ui.section("글감 만들기", "상위권은 실제로 어떻게 쓰는가")
    ui.note("제목을 지어내지도, 남의 제목을 그대로 보여주지도 않습니다. "
            "베껴 쓰게 되면 결국 손해이기 때문입니다. 대신 상위권 제목에서 "
            "<b>어떤 형식이 통하는지</b>와 <b>실제로 검색되는 세부 주제</b>만 뽑아냅니다. "
            "이걸 재료로 직접 쓰시는 게 훨씬 낫습니다.")
    st.write("")

    idea_kw = research_kw
    if not idea_kw:
        ui.note("위쪽 입력칸에 키워드를 넣어주세요.", gold=True)

    if idea_kw:
        @st.cache_data(ttl=1800, show_spinner=False)
        def load_ideas(k):
            a = analyze_keyword(k, with_recent=False)
            sp = get_serp(k, display=30)
            an = analyze_titles(k, sp, a.get("related", []))
            return a, sp, an, build_outline(k, an)

        with st.spinner(f"'{idea_kw}' 상위 글을 뜯어보는 중..."):
            a, sp, an, outline = load_ideas(idea_kw.strip())

        if not an:
            ui.note("상위 글을 가져오지 못했습니다. 다른 키워드로 시도해보세요.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                ui.kpi("제목 길이", f"{an['median_len']}자",
                       f"짧게 {an['min_len']} · 길게 {an['max_len']}")
            with c2:
                ui.kpi("가장 흔한 형식",
                       max([("숫자형", an["num_ratio"]), ("후기형", an["experience_ratio"]),
                            ("정리형", an["summary_ratio"])], key=lambda x: x[1])[0],
                       "상위권이 많이 쓰는 틀")
            with c3:
                ui.kpi("후기·경험형", f"{an['experience_ratio'] * 100:.0f}%",
                       "직접 써본 이야기")
            with c4:
                ui.kpi("분석한 제목", f"{an['count']}개", "상위 노출 글 기준")

            st.write("")
            ui.section("상위권 제목의 공통 형식", "어떤 틀이 먹히는지만 봅니다")

            # 형식별 사용 비율을 막대로 — 원문 대신 패턴만 보여준다
            ui.bar_series(
                [("숫자 넣기", int(an["num_ratio"] * 100)),
                 ("후기·경험형", int(an["experience_ratio"] * 100)),
                 ("정리·비교형", int(an["summary_ratio"] * 100)),
                 ("괄호 붙이기", int(an["bracket_ratio"] * 100)),
                 ("질문형", int(an["question_ratio"] * 100))],
                "상위권 제목이 쓰는 형식 (100개 중 몇 %)",
                height=175, accent=ui.DEEP)

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
            ui.note(" · ".join(hints))

            if an["common_words"]:
                st.write("")
                ui.section("제목에 자주 나오는 단어", "상위권이 공통으로 짚는 지점")
                mx = an["common_words"][0][1]
                chips = " ".join(
                    f'<span class="wchip" style="background:rgba(27,58,75,'
                    f'{0.12 + 0.55 * (c / mx):.2f})">{w}'
                    f'<b>{c}</b></span>' for w, c in an["common_words"])
                st.markdown(f'<div class="chart-box">{chips}</div>',
                            unsafe_allow_html=True)

            if an["subtopics"]:
                st.write("")
                ui.section("실제로 검색되는 세부 주제", "검색량이 확인된 것만")
                sub_df = pd.DataFrame([
                    {"세부 주제": x["keyword"], "월 검색량": x["volume"]}
                    for x in an["subtopics"]])
                sub_df.index = sub_df.index + 1
                show_table(sub_df)

            if outline:
                st.write("")
                ui.section("글 뼈대 후보", "근거가 있는 항목만 모았습니다")
                rows = "".join(
                    f'<div class="outline-item">'
                    f'<div class="outline-num" style="background:'
                    f'{ui.DEEP if s_["kind"] == "필수" else ui.GOLD}">'
                    f'{"핵심" if s_["kind"] == "필수" else "검색"}</div>'
                    f'<div><div class="outline-h">{s_["heading"]}</div>'
                    f'<div class="outline-w">{s_["why"]}</div></div></div>'
                    for s_ in outline)
                st.markdown(f'<div class="chart-box">{rows}</div>',
                            unsafe_allow_html=True)

# ------------------------------------------------------------
# 4. 추적기
# ------------------------------------------------------------
with tabs[1]:
    ui.section("키워드 추적기", "저장해두면 순위 변화를 매일 기록합니다")

    if not my_blog_id:
        ui.note("블로그를 등록하면 <b>내 글의 순위 변화</b>까지 함께 기록합니다. "
                "등록하지 않아도 검색량·문서수 변화는 추적됩니다.", gold=True)

    with st.container(border=True):
        add_c1, add_c2 = st.columns([3, 1])
        with add_c1:
            new_kw = st.text_input("추적할 키워드 추가", placeholder="예: 제습기 추천",
                                   key="track_add", label_visibility="collapsed")
        with add_c2:
            add_clicked = st.button("추적 시작", use_container_width=True)
        wrote = st.checkbox("이 키워드로 이미 글을 썼습니다",
                            key="track_has_post",
                            help="체크하면 내 글의 검색 순위를 추적합니다. "
                                 "체크하지 않으면 검색량 변화만 지켜봅니다.")

    if add_clicked and new_kw.strip():
        try:
            supabase.table("tracked_keywords").insert({
                "keyword": new_kw.strip(), "blog_id": my_blog_id or "",
                "has_post": bool(wrote),
            }).execute()
            st.success(f"'{new_kw.strip()}' 추적을 시작합니다. "
                       + ("글을 쓰셨으니 순위를 추적합니다. "
                          if wrote else "검색량 변화를 지켜봅니다. ")
                       + "다음 수집부터 기록이 쌓입니다.")
            st.cache_data.clear()
        except Exception as e:
            msg = str(e)
            if "duplicate" in msg.lower() or "unique" in msg.lower():
                st.info("이미 추적 중인 키워드입니다.")
            elif "has_post" in msg:
                st.error("`추적기_DB추가.sql`을 Supabase에서 실행해주세요. "
                         "글 작성 여부를 구분하는 컬럼이 필요합니다.")
            elif "does not exist" in msg or "relation" in msg:
                st.error("추적용 테이블이 없습니다. 함께 드린 "
                         "`추적기_DB설정.sql`을 Supabase에서 실행해주세요.")
            else:
                st.error(f"추가 실패: {e}")

    st.divider()

    @st.cache_data(ttl=60)
    def load_tracking():
        try:
            tk = supabase.table("tracked_keywords").select("*") \
                .order("created_at", desc=True).execute().data or []
            since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
            hist = supabase.table("tracking_history").select("*") \
                .gte("created_at", since).order("created_at").execute().data or []
            return tk, hist, None
        except Exception as e:
            return [], [], str(e)

    tracked, history, err = load_tracking()

    if err:
        ui.note("추적 데이터를 불러오지 못했습니다. 함께 드린 "
                "<code>추적기_DB설정.sql</code>을 Supabase SQL Editor에서 "
                f"실행했는지 확인해주세요.<br><small>{err[:160]}</small>")
    elif not tracked:
        ui.note("아직 추적 중인 키워드가 없습니다. 위에서 추가해보세요.<br>"
                "추가한 뒤 <b>3_데이터_수집.bat</b>을 실행하면 첫 기록이 쌓입니다.")
    else:
        hdf = pd.DataFrame(history)
        if not hdf.empty:
            hdf['dt'] = pd.to_datetime(hdf['created_at'], utc=True, errors='coerce')

        # --- 한눈에 보기: 저장한 키워드를 카드로 ------------------
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
                                "search": None, "change_pct": None, "since": None})
                continue
            last, first = rows.iloc[-1], rows.iloc[0]
            lr = int(last['my_rank']) if pd.notna(last.get('my_rank')) else None
            fr = int(first['my_rank']) if pd.notna(first.get('my_rank')) else None
            ts = int(last.get('total_search') or 0)
            docs = int(last.get('blog_total_docs') or 0)
            _, grade = calc_competition(ts, docs)

            # 💡 추적 기록이 쌓였으므로 '검색량 추세'를 계산할 수 있다.
            # 이 축이 있어야 '한물 간 시장'과 '아직 발견 안 된 기회'가 구분된다.
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
                "opportunity": opp["score"],
                "comp_grade": grade,
                "search": ts,
                "since": first['dt'].strftime("%m/%d") if pd.notna(first.get('dt')) else None,
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
            })

        mine_list = [x for x in summary if x.get("has_post")]
        watch_list = [x for x in summary if not x.get("has_post")]

        stopped = detail_kw = None

        if mine_list:
            ui.section("내가 쓴 키워드", f"{len(mine_list)}개 · 순위가 오르는지 봅니다")
            s1, d1 = ui.tracked_cards(mine_list, key_prefix="mine")
            stopped = stopped or s1
            detail_kw = detail_kw or d1
            st.write("")

        if watch_list:
            ui.section("지켜보는 키워드",
                       f"{len(watch_list)}개 · 아직 글은 없고 검색량 변화만 봅니다")
            ui.note("글을 쓴 뒤에는 아래에서 <b>내가 쓴 키워드로 전환</b>해주세요. "
                    "그때부터 순위를 추적합니다.")
            s2, d2 = ui.tracked_cards(watch_list, key_prefix="watch")
            stopped = stopped or s2
            detail_kw = detail_kw or d2

            with st.expander("글을 쓴 키워드로 전환하기"):
                to_flip = st.multiselect("글을 발행한 키워드를 고르세요",
                                         [x["keyword"] for x in watch_list],
                                         key="flip_kws")
                if st.button("선택한 키워드를 '내가 쓴 키워드'로 전환") and to_flip:
                    try:
                        for kwn in to_flip:
                            tgt = next((t for t in tracked if t["keyword"] == kwn), None)
                            if tgt:
                                supabase.table("tracked_keywords") \
                                    .update({"has_post": True}) \
                                    .eq("id", tgt["id"]).execute()
                        st.cache_data.clear()
                        st.success(f"{len(to_flip)}개를 전환했습니다. 다음 수집부터 "
                                   "순위가 기록됩니다.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"전환 실패: {e}")
        if detail_kw:
            st.session_state["track_detail"] = detail_kw
        if stopped:
            target = next((t for t in tracked if t["keyword"] == stopped), None)
            if target:
                try:
                    supabase.table("tracked_keywords").delete() \
                        .eq("id", target["id"]).execute()
                    st.cache_data.clear()
                    st.success(f"'{stopped}' 추적을 중단했습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(f"삭제 실패: {e}")

        # --- 추적 브리핑 -----------------------------------------
        st.write("")
        has_record = [x for x in summary if x["records"] > 0]
        if ai_brief.is_enabled():
            if has_record:
                @st.cache_data(ttl=1800, show_spinner=False)
                def get_track_brief(payload):
                    return ai_brief.brief_tracking(payload)

                with st.spinner("추적 기록을 읽는 중..."):
                    tb, terr = get_track_brief([
                        {"keyword": x["keyword"], "first_rank": x["first_rank"],
                         "last_rank": x["last_rank"], "records": x["records"],
                         "opportunity": x["opportunity"], "comp_grade": x["comp_grade"]}
                        for x in has_record])
                if tb:
                    ui.brief_card(tb, "AI 판단 · 지금 어디에 집중할까")
        else:
            ui.note("<code>ai_brief.py</code>에 키를 넣으면 순위 변화를 읽고 "
                    "<b>무엇에 집중할지</b> 알려주는 브리핑이 여기 표시됩니다.", gold=True)

        st.divider()
        def _render_detail(pick):
            """선택한 키워드의 상세 추이. 팝업과 인라인에서 함께 쓴다."""
            info = next((x for x in summary if x["keyword"] == pick), None)
            if not info:
                return
            rows = (hdf[hdf['keyword'] == pick].sort_values('dt')
                    if not hdf.empty else pd.DataFrame())
            if rows.empty:
                ui.note("아직 기록이 없습니다. <b>3_데이터_수집.bat</b>을 실행하면 "
                        "첫 기록이 만들어집니다.")
                return
            latest = rows.iloc[-1]
            k1, k2 = st.columns(2)
            with k1:
                ui.kpi("월 검색량",
                       compact_num(int(latest.get('total_search') or 0)), "")
            with k2:
                ui.kpi("이미 쓰인 글",
                       compact_num(int(latest.get('blog_total_docs') or 0)), "")
            k3, k4 = st.columns(2)
            with k3:
                cp = info.get("change_pct")
                since = info.get("since")
                ui.kpi("검색량 추세",
                       f"{cp:+.0f}%" if cp is not None else "계산 중",
                       "기록 3회 이상 필요" if cp is None
                       else f"{since} 최초 추적일부터")
            with k4:
                v = info.get("visits")
                if v:
                    ui.kpi("예상 방문자", f"{v:,}명", "한 달에 올 사람 수")
                elif info.get("has_post"):
                    ui.kpi("예상 방문자", "집계 어려움",
                           "내 글이 아직 상위에 없습니다")
                else:
                    ui.kpi("예상 방문자", "—",
                           "아직 이 키워드로 내 글이 없습니다")

            # 등록 당시와 지금을 비교 — 검색량만으로는 남들이 몰려든 걸 알 수 없다
            if info.get("compare"):
                since_txt = (f"{info['since_full']} 등록 · 기록 {info['records']}회"
                             if info.get("since_full") else "")
                ui.since_compare(info["compare"], since_txt)

            pts = [(d.strftime("%m/%d"), int(rk) if pd.notna(rk) else None)
                   for d, rk in zip(rows['dt'], rows['my_rank'])]
            ui.rank_trend(pts, title=f"{pick} · 순위 추이")

            # 예상 방문자가 왜 비어 있는지 설명한다
            if not info.get("visits"):
                if info.get("has_post"):
                    ui.note("이 키워드로 쓴 <b>내 글</b>이 아직 상위에 노출되지 않아 "
                            "<b>예상 방문자를 집계할 수 없습니다.</b> "
                            "순위가 올라오면 자동으로 표시됩니다.")
                else:
                    ui.note("아직 이 키워드로 쓴 <b>내 글</b>이 없어서 "
                            "<b>예상 방문자를 집계할 수 없습니다.</b> "
                            "글을 발행한 뒤 위에서 "
                            "<b>내가 쓴 키워드로 전환</b>해주세요.", gold=True)

            if info.get("opp_breakdown"):
                ui.score_breakdown(info["opp_breakdown"], info["opportunity"])
            if info.get("opp_note"):
                ui.note(f"<b>{info.get('opp_label','')}</b> — {info['opp_note']}")

        # ⚠️ Streamlit은 어느 탭에서 무엇을 누르든 스크립트 전체를 다시 실행한다.
        # 그래서 세션에 남은 값으로 팝업을 띄우면, 다른 탭에서 라디오 버튼 하나만
        # 눌러도 추적기 팝업이 계속 따라 나온다.
        # '한 번만 보여주고 지우는' 방식으로 바꿔서 그걸 막는다.
        target_kw = st.session_state.pop("track_detail", None)
        if target_kw and any(x["keyword"] == target_kw for x in summary):
            try:
                @st.dialog(f"{target_kw} · 추이", width="large")
                def _detail_dialog():
                    _render_detail(target_kw)
                _detail_dialog()
            except AttributeError:
                # 구버전 Streamlit에는 st.dialog가 없다 — 아래에 펼쳐서 보여준다
                st.divider()
                ui.section("키워드별 추이", target_kw)
                _render_detail(target_kw)

# ------------------------------------------------------------
# 2. 내 블로그
# ------------------------------------------------------------
with tabs[2]:
    ui.section("내 블로그 진단", "지금 내 블로그는 어떤 상태인가")

    tab_blog_input = st.text_input(
        "내 블로그 주소 입력",
        value=my_blog_id,
        key="blog_input_tab",
    )

    if tab_blog_input:
        my_blog_id = extract_blog_id(tab_blog_input)
        st.session_state["blog_id"] = my_blog_id

    st.write("")

    if not my_blog_id:
        ui.note("위 칸에 블로그 주소를 넣어주세요. "
                "예: <code>blog.naver.com/myid</code> 또는 <code>myid</code>", gold=True)
    else:
        with st.spinner("블로그를 읽는 중"):
            feed = get_my_blog_feed(my_blog_id)

        if feed["error"]:
            ui.note(f"{feed['error']}<br>아이디가 맞는지, 블로그가 공개 상태인지 확인해주세요.")
        else:
            power = estimate_blog_power(feed["posts"])
            posts = feed["posts"]

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                ui.kpi("주당 발행", f"{power['posts_per_week']}편",
                       "최근 90일 평균")
            with c2:
                gap = power.get('avg_gap_days')
                ui.kpi("평균 발행 간격", f"{gap}일" if gap is not None else "—",
                       "글과 글 사이")
            with c3:
                last_txt = f"{power['days_since_last']}일 전" if power['days_since_last'] is not None else "—"
                ui.kpi("마지막 글", last_txt, "최근 발행일")
            with c4:
                ui.kpi("활동 등급", power['level'], f"수집된 글 {len(posts)}편")

            st.write("")
            ui.gauge("발행 활동성", power["score"], ("휴면", "보통", "매우활발"))

            # 주간 발행 리듬 — 꾸준함이 한눈에 보인다
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
                ui.bar_series(series, "최근 12주 발행 리듬", accent=ui.DEEP)

                empty_weeks = sum(1 for _, v in series if v == 0)
                if empty_weeks >= 6:
                    ui.note("최근 12주 중 절반 이상 글이 없습니다. "
                            "발행 간격이 벌어지면 노출에 불리하게 작용하는 경향이 있습니다.")
                elif empty_weeks == 0:
                    ui.note("12주 내내 빠짐없이 발행했습니다. 꾸준함이 잘 유지되고 있습니다.",
                            gold=True)

                # 요일 패턴
                wd_names = ['월', '화', '수', '목', '금', '토', '일']
                wd_count = {i: 0 for i in range(7)}
                for d in dated:
                    wd_count[d.weekday()] += 1
                ui.bar_series([(wd_names[i], wd_count[i]) for i in range(7)],
                              "요일별 발행 분포", height=130, accent=ui.GOOD)

            ui.note(
                "네이버는 블로그 지수를 공개하지 않습니다. 여기 점수는 "
                "<b>공개된 RSS로 관측한 발행 빈도와 최근성</b>을 조합한 추정치이며, "
                "네이버 내부 지수와는 다릅니다. 꾸준한 발행이 노출에 유리하다는 "
                "일반적 경향을 참고 지표로 만든 것입니다.")

            if posts:
                st.write("")
                ui.section("최근 발행", "내가 최근에 쓴 글")
                now_ = datetime.now(timezone.utc)
                rows = []
                for i, p in enumerate(posts[:20]):
                    d = p["date"]
                    gap = ""
                    if d and i + 1 < len(posts) and posts[i + 1]["date"]:
                        gap = f"{(d - posts[i + 1]['date']).days}일"
                    rows.append({
                        "제목": p["title"],
                        "발행일": d.strftime("%Y-%m-%d") if d else "—",
                        "경과": f"{(now_ - d).days}일 전" if d else "—",
                        "직전 글과 간격": gap or "—",
                    })
                pdf = pd.DataFrame(rows)
                pdf.index = pdf.index + 1
                show_table(pdf)



            st.divider()
            ui.section("골든타임 대조", "지금 뜨는 키워드 중 내가 노려볼 만한 것")

            golden = latest_snapshot(df[df['source'] == 'golden_time'], hours=24) if not df.empty else pd.DataFrame()
            if golden.empty:
                ui.note("골든타임 데이터가 아직 없습니다. collector.py를 실행해주세요.")
            else:
                top = golden.sort_values('rise_score', ascending=False).head(10)
                rows = []
                for _, row in top.iterrows():
                    ratio = row.get('comp_ratio') or None
                    win = calc_win_score(ratio if ratio else None, power["score"])
                    rows.append({
                        "키워드": row['keyword'],
                        "월 검색량": int(row['총 검색량']),
                        "경쟁률": row.get('comp_grade', '정보없음'),
                        # ⚠️ 숫자와 문자열을 한 컬럼에 섞으면 표 변환이 실패한다.
                        # (Arrow 변환 시 "Expected bytes, got a 'int' object")
                        # 전부 문자열로 통일한다.
                        "내 승산": (f"{win['score']}점"
                                  if win["score"] is not None else "—"),
                        "판단": win["verdict"],
                    })
                wdf = pd.DataFrame(rows)
                wdf.index = wdf.index + 1
                show_table(wdf)

# ------------------------------------------------------------
# 나머지 탭 — 수집 데이터 기반
# ------------------------------------------------------------
if df.empty:
    for t in tabs[2:]:
        with t:
            ui.note("수집된 데이터가 없습니다. collector.py를 먼저 실행해주세요.")
else:
    with sub_discover[0]:
        ui.section("구글 트렌드", "지금 사람들이 검색하는 것")
        _, hours = period_picker("g_period", kind="trend", default="최근")
        render_table(latest_snapshot(df[df['source'] == 'google_trend'], hours=hours),
                     show_docs=False, source='google_trend', label="구글 트렌드")

    with sub_discover[1]:
        ui.section("골든타임", "뜨고 있는데 아직 안 붐비는 선점 구간")
        ui.note("찾는 사람은 있는데 <b>최근에 쓰인 글이 적은</b> 키워드입니다. "
                "먼저 쓰면 선점 효과를 기대할 수 있습니다.<br>"
                "<small>검색량이 오르는 중이면 위로 올라옵니다. 다만 네이버 검색량은 "
                "월 단위 집계라 며칠로는 잘 안 변합니다.</small>", gold=True)
        st.write("")
        _, h = period_picker("gt_period", kind="slow", default="일별")
        golden = latest_snapshot(df[df['source'] == 'golden_time'], hours=h)
        if golden.empty:
            empty_note('golden_time', h, "골든타임")
        else:
            # ⚠️ 시드 키워드를 없애면서 분류 기준이 바뀌었다.
            # 예전엔 '상품/서비스'였지만, 이제는 어디서 나왔는지로 나눈다.
            #   트렌드 — 오늘 구글 트렌드에 뜬 키워드 그 자체
            #   세부   — 그 트렌드에서 파생된 연관 검색어
            sub = st.tabs(["🔥 오늘 트렌드", "🔍 파생 키워드", "전체"])
            _extra = [('blog_competition', '최근 30일 글')]
            with sub[0]:
                render_table(golden[golden['keyword_category'] == '트렌드'],
                             sort_col='rise_score', show_docs=False,
                             extra_cols=_extra, source='golden_time',
                             label="골든타임")
            with sub[1]:
                render_table(golden[golden['keyword_category'] == '세부'],
                             sort_col='rise_score', show_docs=False,
                             extra_cols=_extra, source='golden_time',
                             label="골든타임")
            with sub[2]:
                render_table(golden, sort_col='rise_score', show_docs=False,
                             extra_cols=_extra)

    with sub_discover[2]:
        ui.section("주간 캘린더", "미리 써두면 유리한 앞으로 4주")
        ui.note("검색량이 큰 행사가 위에 옵니다. "
                "<b>0으로 나오는 건</b> 아직 사람들이 안 찾거나, "
                "공식 명칭이 너무 길어 검색어로 안 쓰이는 경우입니다.")
        weekly = latest_snapshot(df[df['source'] == 'weekly_event'])
        if weekly.empty:
            ui.note("예정된 이벤트가 없거나 아직 수집되지 않았습니다.")
        else:
            weekly = weekly.copy()
            weekly['d'] = pd.to_datetime(weekly['event_date'], errors='coerce').dt.date
            weekly = weekly.dropna(subset=['d']).sort_values('d')

            today = datetime.now(timezone.utc).date()
            monday = today - timedelta(days=today.weekday())
            weekly['wk'] = weekly['d'].apply(lambda x: (x - monday).days // 7)

            labels = {0: "이번 주", 1: "다음 주", 2: "2주 후", 3: "3주 후"}
            wd = ['월', '화', '수', '목', '금', '토', '일']

            for off in sorted(weekly['wk'].unique()):
                off = int(off)
                if off < 0:
                    continue
                ws = monday + timedelta(weeks=off)
                st.markdown(
                    f"**{labels.get(off, f'{off}주 후')}** "
                    f"<span class='mono' style='color:{ui.MUTED};font-size:.82rem'>"
                    f"{ws.strftime('%m/%d')} – {(ws + timedelta(days=6)).strftime('%m/%d')}</span>",
                    unsafe_allow_html=True)
                ev = weekly[weekly['wk'] == off].copy()
                ev['요일'] = ev['d'].apply(lambda x: wd[x.weekday()])
                # 검색량이 있는 것을 위로 (0인 건 글감으로 쓸모가 적다)
                ev = ev.sort_values(['총 검색량', 'd'], ascending=[False, True])
                out = ev[['d', '요일', 'keyword', 'comp_level', '총 검색량']].copy()
                out.columns = ['날짜', '요일', '이벤트', '종류', '월 검색량']
                out.index = range(1, len(out) + 1)
                show_table(out)
                st.write("")

        st.divider()
        ui.section("계절 캘린더", "해마다 같은 시기에 오르는 키워드")
        m = datetime.now(timezone.utc).month
        nm = m % 12 + 1
        c1, c2 = st.columns(2)
        with c1:
            ui.kpi(f"{m}월 · 지금 쓸 것", "", ", ".join(SEASONAL_CALENDAR.get(m, [])))
        with c2:
            ui.kpi(f"{nm}월 · 미리 쓸 것", "", ", ".join(SEASONAL_CALENDAR.get(nm, [])))

    with sub_discover[3]:
        ui.section("뉴스", "지금 많이 읽히는 기사")
        _, h = period_picker("news_period", kind="trend", default="최근")
        render_table(latest_snapshot(df[df['source'] == 'naver_news'], hours=h),
                     show_docs=False, show_volume=False,
                     source='naver_news', label="뉴스")


# ------------------------------------------------------------
# 관리 탭 — 비밀번호를 아는 사람만
#
# 회원 로그인이 아니라 '나만 보는 화면'용 간단한 잠금이다.
# 나중에 회원을 받게 되면 이 구조를 확장하면 된다.
# ------------------------------------------------------------
if admin_tab is not None:
    with admin_tab:
        if not st.session_state.get("admin_ok"):
            ui.section("관리자 화면", "비밀번호를 입력하세요")
            ui.note("이 탭은 주소에 열쇠말을 붙였을 때만 나타납니다. "
                    "주소를 즐겨찾기에 저장해두면 편합니다.")
            with st.container(border=True):
                pw = st.text_input("비밀번호", type="password", key="admin_pw")
                if st.button("확인", key="admin_go"):
                    if pw == config.ADMIN_PASSWORD:
                        st.session_state["admin_ok"] = True
                        st.rerun()
                    else:
                        st.error("비밀번호가 맞지 않습니다.")
        else:
            ui.section("관리자 화면", "수집 상태와 키워드 풀 현황")

            if cache is None:
                ui.note("cache.py가 없어 현황을 볼 수 없습니다.")
            else:
                # ⚠️ Streamlit은 어떤 탭을 보고 있든 스크립트 전체를 다시 실행한다.
                # 그래서 이 조회들을 그냥 두면 키워드 분석 탭을 쓰는 동안에도
                # 매번 DB를 6번씩 두드린다. 두 가지로 막는다.
                #   ① 버튼을 눌렀을 때만 불러온다
                #   ② 불러온 뒤에는 60초간 캐시한다
                @st.cache_data(ttl=60, show_spinner=False)
                def load_admin(sort_key):
                    return {
                        "stats": cache.pool_stats(),
                        "usage": cache.usage(),
                        "hist": cache.usage_history(7),
                        "rows": (cache.pool_recent(100) if sort_key == "최근 추가순"
                                 else cache.pool_top(100)),
                    }

                sort_by = st.radio("정렬", ["최근 추가순", "검색량 많은순"],
                                   horizontal=True, key="pool_sort")

                b1, b2 = st.columns([1, 4])
                with b1:
                    if st.button("불러오기", key="admin_load",
                                 use_container_width=True):
                        st.session_state["admin_loaded"] = True
                        load_admin.clear()

                if not st.session_state.get("admin_loaded"):
                    ui.note("<b>불러오기</b>를 누르면 현황을 조회합니다. "
                            "자동으로 부르지 않는 이유는, 이 화면을 안 보고 있을 때도 "
                            "DB를 계속 두드리면 대시보드 전체가 느려지기 때문입니다.")
                else:
                    with st.spinner("현황을 불러오는 중..."):
                        d = load_admin(sort_by)
                    stats, u, hist, rows = d["stats"], d["usage"], d["hist"], d["rows"]

                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        ui.kpi("쌓인 키워드", compact_num(stats["total"]),
                               f"오늘 +{stats['today']:,}개")
                    with c2:
                        # 문서수는 미리 안 쌓는다. 조회된 것만 채워지므로
                        # '전체의 0%'로 보이면 잘못된 것처럼 오해하기 쉽다.
                        ui.kpi("문서수 잰 키워드", compact_num(stats["with_docs"]),
                               "조회된 것만 채워집니다")
                    with c3:
                        ui.kpi("오늘 API 호출", f"{u['calls']:,}",
                               f"한도 {u['limit']:,}회의 {u['pct']}%")
                    with c4:
                        ui.kpi("남은 조회", f"{u['remaining']:,}",
                               f"{cache.reset_time()} 초기화")

                    ui.note("<b>검색량</b>은 한 번 호출에 연관어 20개가 딸려와 빠르게 쌓입니다. "
                            "<b>문서수</b>는 키워드마다 따로 불러야 해서, "
                            "실제로 조회된 것만 채워집니다. 두 숫자가 크게 차이나는 건 정상입니다.")

                    st.write("")
                    ui.gauge("오늘 사용량", min(100, int(u["pct"])),
                             ("여유", "보통", "한도"),
                             color=(ui.BAD if u["pct"] >= 70 else
                                    (ui.WARN if u["pct"] >= 40 else ui.GOOD)))

                    if hist:
                        st.write("")
                        ui.bar_series(
                            [(h["day"][5:], int(h["calls"] or 0))
                             for h in reversed(hist)],
                            "최근 7일 API 호출", height=170, accent=ui.DEEP)

                    st.write("")
                    ui.section("키워드 풀", "실제로 어떤 단어가 쌓였나")

                    if not rows:
                        ui.note("아직 쌓인 키워드가 없습니다. "
                                "<b>7_키워드_미리쌓기.bat</b>을 돌리거나 "
                                "GitHub Actions의 <b>seed-pool</b>을 실행해보세요.")
                    else:
                        df_pool = pd.DataFrame([{
                            "키워드": r["keyword"],
                            "월 검색량": (r.get("monthly_pc") or 0)
                                       + (r.get("monthly_mobile") or 0),
                            "경쟁": r.get("comp_level") or "-",
                            "문서수": r.get("blog_total_docs") or None,
                            "쌓인 시각": (r.get("updated_at") or "")[:16].replace("T", " "),
                        } for r in rows])
                        df_pool.index = df_pool.index + 1
                        st.dataframe(df_pool, use_container_width=True, height=420)
                        st.caption(f"{len(rows)}개 표시 중 · 전체 {stats['total']:,}개 "
                                   "· 60초간 저장된 값을 씁니다")

            st.write("")
            if st.button("잠그기", key="admin_lock"):
                for k in ("admin_ok", "admin_loaded", "admin_visible"):
                    st.session_state.pop(k, None)
                # 주소에서도 열쇠말을 지운다
                try:
                    st.query_params.clear()
                except Exception:
                    pass
                st.rerun()