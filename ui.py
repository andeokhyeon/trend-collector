"""
디자인 시스템 및 공용 UI 컴포넌트.

컨셉: '정밀 계측기(instrument panel)'
이 제품이 하는 일은 키워드를 재는 것이므로, 계기판처럼 보이게 만든다.
 - 모든 수치는 등폭(mono) 서체로 자릿수를 맞춰 읽기 쉽게
 - 골드는 오직 '기회 신호'에만 쓰고, 나머지는 절제
 - 등급은 어디서나 같은 색 칩으로 표시해서 학습 비용을 없앤다
"""

import streamlit as st

# --- 토큰 ---------------------------------------------------
INK = "#111827"        # 본문
MUTED = "#6B7280"      # 보조 텍스트
LINE = "#E8EAED"       # 경계선
BASE = "#F6F7F9"       # 배경
SURFACE = "#FFFFFF"    # 카드
DEEP = "#1A56DB"       # 포인트 파랑 (구조/강조)
GOLD = "#C8963E"       # 기회 신호 (골든타임)
GOOD = "#0E9F6E"       # 좋음
WARN = "#C27803"       # 주의
BAD = "#E02424"        # 나쁨

GRADE_COLORS = {
    # 누적 경쟁률
    "최고": GOOD, "좋음": GOOD,
    "보통": WARN,
    "나쁨": BAD, "최악": BAD,
    # 최근 30일 발행 강도
    "매우한산": GOOD, "한산": GOOD,
    "붐빔": BAD, "과열": BAD,
    # 종합 진단
    "비어 있는 자리": GOOD, "오래된 글만 많음": GOOD, "해볼 만함": GOOD,
    "오래된 글이 1등": GOOD,
    "지금 몰리는 중": WARN, "누적만 반영": WARN, "새 글 옛 글 섞임": WARN,
    "이미 꽉 참": BAD, "어려움": BAD, "최신 글 경쟁": BAD,
    "정보없음": MUTED, "검색량없음": MUTED,
}

LEVEL_COLORS = {
    "매우활발": GOOD, "활발": GOOD,
    "보통": WARN,
    "저조": BAD, "휴면": BAD,
    "정보없음": MUTED,
}


def inject_css():
    # ⚠️ 이 문자열 안에 빈 줄이 있으면 안 된다.
    # 마크다운 규칙상 빈 줄을 만나면 HTML 덩어리가 거기서 끝난 것으로 보고,
    # 그 뒤의 CSS가 화면에 글자로 쏟아진다. (실제로 한 번 그렇게 터졌다)
    # 사람이 매번 조심하는 대신, 아래에서 빈 줄을 자동으로 걷어낸다.
    _css = f"""<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
html, body, [class*="css"], .stApp {{
font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif;
}}
.stApp {{ background: {BASE}; }}
/* Streamlit 기본 UI 숨김
   상단의 Share·별·연필과 하단 'Manage app'은 개발자용이라
   실제 사용자에게는 혼란만 준다. 사이드바도 안 쓰므로 헤더째 없앤다. */
#MainMenu, footer, header {{ display: none !important; }}
[data-testid="stToolbar"],
[data-testid="stToolbarActions"],
[data-testid="stMainMenu"],
[data-testid="stDeployButton"],
.stAppDeployButton,
[data-testid="stStatusWidget"],
[data-testid="stDecoration"],
[data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stActionButtonIcon"],
[data-testid="stAppDeployButton"],
.stActionButton,
[data-testid="manage-app-button"],
[data-testid="stStatusWidget"] > div {{
display: none !important;
}}
[data-testid="stHeader"] {{
display: none !important;
background: transparent !important;
height: 0 !important; min-height: 0 !important;
}}
/* 하단 'Manage app' 배지 — 여러 이름으로 나타나므로 넓게 잡는다 */
iframe[title="streamlitApp"] ~ div,
div[class*="viewerBadge"],
div[class*="ViewerBadge"],
a[href*="streamlit.io/cloud"],
a[href*="share.streamlit.io"] {{
display: none !important;
}}
.block-container {{ padding-top: 2.2rem; max-width: 1180px; }}
/* 수치는 전부 등폭으로 — 계측기 감각의 핵심 */
.mono, .metric-val, .kpi-val {{
font-family: 'IBM Plex Mono', monospace;
font-variant-numeric: tabular-nums;
}}
/* 마스트헤드 */
.masthead {{
background: {DEEP};
border-radius: 14px;
padding: 22px 26px;
margin-bottom: 18px;
color: #fff;
}}
.masthead h1 {{
font-size: 1.7rem; font-weight: 800; margin: 0;
letter-spacing: -0.02em; color: #fff;
}}
.masthead p {{
margin: 8px 0 0; font-size: .96rem;
color: rgba(255,255,255,.62); line-height: 1.5;
}}
.masthead .rule {{
height: 3px; width: 46px; background: {GOLD};
margin-bottom: 10px; border-radius: 2px;
}}
.mast-head-row {{ display: flex; align-items: center; gap: 15px; }}
.mast-head-row svg {{ flex-shrink: 0; }}
/* 탭 */
/* 탭 - 버튼 느낌 (표준 ARIA 속성으로 잡아 버전 무관하게 적용) */
[role="tablist"] {{
gap: 9px !important; border-bottom: none !important;
padding: 6px 0 16px !important; flex-wrap: wrap !important;
background: transparent !important; box-shadow: none !important;
}}
[role="tab"] {{
height: auto !important; min-height: 44px !important;
padding: 10px 20px !important; margin: 0 !important;
background: {SURFACE} !important;
border: 1.5px solid {LINE} !important;
border-radius: 999px !important;
color: #4A5560 !important;
transition: all .16s ease !important;
box-shadow: 0 1px 3px rgba(20,22,26,.05) !important;
opacity: 1 !important;
}}
[role="tab"] *, [role="tab"] p, [role="tab"] div, [role="tab"] span {{
font-size: 1rem !important; font-weight: 700 !important;
color: inherit !important; margin: 0 !important;
}}
[role="tab"]:hover {{
background: #FDF4E3 !important;
border-color: {GOLD} !important;
color: {DEEP} !important;
transform: translateY(-1px);
box-shadow: 0 4px 10px rgba(200,150,62,.22) !important;
}}
[role="tab"][aria-selected="true"] {{
background: {DEEP} !important;
border-color: {DEEP} !important;
color: #FFFFFF !important;
box-shadow: 0 4px 12px rgba(27,58,75,.30) !important;
}}
[role="tab"][aria-selected="true"] *, [role="tab"][aria-selected="true"] p {{
color: #FFFFFF !important;
}}
[role="tab"][aria-selected="true"]:hover {{
background: #24506A !important; border-color: {GOLD} !important;
}}
/* Streamlit 기본 밑줄/하이라이트 완전 제거 */
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"],
[role="tablist"] [class*="highlight"],
[role="tablist"] > div:not([role="tab"]),
[role="tablist"]::after, [role="tablist"]::before {{
display: none !important; background: transparent !important;
height: 0 !important; width: 0 !important;
border: none !important; opacity: 0 !important;
content: none !important;
}}
[role="tab"] {{ border-bottom: 1.5px solid {LINE} !important; }}
[role="tab"][aria-selected="true"] {{ border-bottom-color: {DEEP} !important; }}
[role="tab"]:hover {{ border-bottom-color: {GOLD} !important; }}
[role="tab"][aria-selected="true"]:hover {{ border-bottom-color: {GOLD} !important; }}
/* 하위 탭 - 상위 탭보다 작고 가볍게, 선택 시 골드 */
[role="tabpanel"] [role="tab"] {{
min-height: 36px !important; padding: 6px 15px !important;
background: #F4F4EF !important; border-color: transparent !important;
box-shadow: none !important; color: #5A6570 !important;
}}
[role="tabpanel"] [role="tab"] * {{ font-size: .92rem !important; font-weight: 600 !important; }}
[role="tabpanel"] [role="tab"]:hover {{
background: #FDF4E3 !important; border-color: {GOLD} !important;
transform: none !important; box-shadow: none !important;
}}
[role="tabpanel"] [role="tab"][aria-selected="true"] {{
background: {GOLD} !important; border-color: {GOLD} !important;
color: #fff !important; box-shadow: 0 2px 6px rgba(200,150,62,.30) !important;
}}
[role="tabpanel"] [role="tab"][aria-selected="true"] * {{ color: #fff !important; }}
[role="tabpanel"] [role="tab"][aria-selected="true"]:hover {{
background: #B8873B !important; border-color: #B8873B !important;
}}
[role="tabpanel"] [role="tablist"] {{ padding: 2px 0 12px !important; }}
/* 3단계(골든타임 안 상품/서비스)는 더 작게 */
[role="tabpanel"] [role="tabpanel"] [role="tab"] {{
min-height: 32px !important; padding: 5px 13px !important;
}}
[role="tabpanel"] [role="tabpanel"] [role="tab"] * {{ font-size: .86rem !important; }}
/* KPI 카드 */
.kpi {{
background: {SURFACE}; border: 1.5px solid {LINE};
border-radius: 12px; padding: 17px 19px; height: 100%;
}}
.kpi-label {{
font-size: .82rem; font-weight: 600; color: {MUTED};
letter-spacing: .04em; text-transform: uppercase; margin-bottom: 6px;
}}
.kpi-val {{
font-size: 1.85rem; font-weight: 600; color: {INK}; line-height: 1.15;
white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
letter-spacing: -0.01em;
}}
.kpi-sub {{ font-size: .86rem; color: {MUTED}; margin-top: 4px; }}
/* 등급 칩 */
.chip {{
display: inline-block; padding: 5px 14px; border-radius: 999px;
font-size: .92rem; font-weight: 700; color: #fff;
}}
/* 기회 게이지 — 시그니처 요소 */
.gauge-wrap {{
background: {SURFACE}; border: 1px solid {LINE};
border-radius: 12px; padding: 16px 18px; margin: 4px 0 2px;
}}
.gauge-top {{
display: flex; justify-content: space-between;
align-items: baseline; margin-bottom: 10px;
}}
.gauge-title {{ font-size: .96rem; font-weight: 700; color: {INK}; }}
.gauge-num {{
font-family: 'IBM Plex Mono', monospace; font-size: 1.6rem;
font-weight: 600; color: {DEEP};
}}
.gauge-track {{
height: 8px; background: #EFEFEA; border-radius: 999px; overflow: hidden;
}}
.gauge-fill {{ height: 100%; border-radius: 999px; }}
.gauge-scale {{
display: flex; justify-content: space-between;
font-size: .78rem; color: {MUTED}; margin-top: 7px;
font-family: 'IBM Plex Mono', monospace;
}}
/* 섹션 라벨 */
.eyebrow {{
font-size: .78rem; font-weight: 700; letter-spacing: .1em;
text-transform: uppercase; color: {GOLD}; margin-bottom: 2px;
}}
.section-title {{
font-size: 1.25rem; font-weight: 700; color: {INK}; margin-bottom: 10px;
}}
/* 안내 박스 */
.note {{
background: {SURFACE}; border: 1px solid {LINE};
border-left: 3px solid {DEEP};
border-radius: 8px; padding: 11px 14px;
font-size: .94rem; color: #40454C; line-height: 1.65;
}}
.note-gold {{ border-left-color: {GOLD}; }}
/* 입력창 - 눈에 띄게 */
.stTextInput input {{
border: 2px solid {LINE} !important;
border-radius: 10px !important;
background: {SURFACE} !important;
font-size: 1rem !important;
padding: 11px 14px !important;
color: {INK} !important;
}}
.stTextInput input:focus {{
border-color: {DEEP} !important;
box-shadow: 0 0 0 3px rgba(27,58,75,.10) !important;
}}
.stTextInput input::placeholder {{ color: #A8AEB6 !important; }}
/* 최상단 검색창 — 도구의 핵심 동작이라 가장 눈에 띄어야 한다 */
.st-key-research_kw input {{
font-size: 1.12rem !important;
padding: 15px 18px !important;
border: 2px solid {LINE} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-research_kw input:focus {{
border-color: {DEEP} !important;
box-shadow: 0 0 0 4px rgba(27,58,75,.10) !important;
}}
.st-key-research_go button {{
height: 52px !important;
background: {DEEP} !important;
border-color: {DEEP} !important;
font-size: 1rem !important;
}}
.st-key-research_go button:hover {{
background: {GOLD} !important; border-color: {GOLD} !important;
}}
/* 큰 검색창 (키워드 분석 / 내 블로그) */
.st-key-kw_main input, .st-key-blog_input_tab input,
.st-key-blog_input_main input {{
font-size: 1.24rem !important;
padding: 18px 22px !important;
border: 2.5px solid {DEEP} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-kw_main input:focus, .st-key-blog_input_tab input:focus,
.st-key-blog_input_main input:focus {{
box-shadow: 0 0 0 4px rgba(200,150,62,.22) !important;
border-color: {GOLD} !important;
}}
.st-key-kw_main label, .st-key-blog_input_tab label,
.st-key-blog_input_main label {{
font-size: 1rem !important; font-weight: 700 !important; color: {INK} !important;
}}
/* 최상단 검색창 — 도구의 핵심 동작이라 가장 눈에 띄어야 한다 */
.st-key-research_kw input {{
font-size: 1.12rem !important;
padding: 15px 18px !important;
border: 2px solid {LINE} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-research_kw input:focus {{
border-color: {DEEP} !important;
box-shadow: 0 0 0 4px rgba(27,58,75,.10) !important;
}}
.st-key-research_go button {{
height: 52px !important;
background: {DEEP} !important;
border-color: {DEEP} !important;
font-size: 1rem !important;
}}
.st-key-research_go button:hover {{
background: {GOLD} !important; border-color: {GOLD} !important;
}}
/* 큰 검색창 (키워드 분석 / 내 블로그) */
.st-key-kw_main input, .st-key-blog_input_tab input,
.st-key-blog_input_main input {{
font-size: 1.24rem !important;
padding: 18px 22px !important;
border: 2.5px solid {DEEP} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-kw_main input:focus, .st-key-blog_input_tab input:focus,
.st-key-blog_input_main input:focus {{
box-shadow: 0 0 0 4px rgba(200,150,62,.22) !important;
border-color: {GOLD} !important;
}}
.st-key-kw_main label, .st-key-blog_input_tab label,
.st-key-blog_input_main label {{
font-size: 1rem !important; font-weight: 700 !important; color: {INK} !important;
}}
/* 최상단 검색창 — 도구의 핵심 동작이라 가장 눈에 띄어야 한다 */
.st-key-research_kw input {{
font-size: 1.12rem !important;
padding: 15px 18px !important;
border: 2px solid {LINE} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-research_kw input:focus {{
border-color: {DEEP} !important;
box-shadow: 0 0 0 4px rgba(27,58,75,.10) !important;
}}
.st-key-research_go button {{
height: 52px !important;
background: {DEEP} !important;
border-color: {DEEP} !important;
font-size: 1rem !important;
}}
.st-key-research_go button:hover {{
background: {GOLD} !important; border-color: {GOLD} !important;
}}
/* 큰 검색창 (키워드 분석 / 내 블로그) */
.st-key-kw_main input, .st-key-blog_input_tab input,
.st-key-blog_input_main input {{
font-size: 1.24rem !important;
padding: 18px 22px !important;
border: 2.5px solid {DEEP} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-kw_main input:focus, .st-key-blog_input_tab input:focus,
.st-key-blog_input_main input:focus {{
box-shadow: 0 0 0 4px rgba(200,150,62,.22) !important;
border-color: {GOLD} !important;
}}
.st-key-kw_main label, .st-key-blog_input_tab label,
.st-key-blog_input_main label {{
font-size: 1rem !important; font-weight: 700 !important; color: {INK} !important;
}}
/* 최상단 검색창 — 도구의 핵심 동작이라 가장 눈에 띄어야 한다 */
.st-key-research_kw input {{
font-size: 1.12rem !important;
padding: 15px 18px !important;
border: 2px solid {LINE} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-research_kw input:focus {{
border-color: {DEEP} !important;
box-shadow: 0 0 0 4px rgba(27,58,75,.10) !important;
}}
.st-key-research_go button {{
height: 52px !important;
background: {DEEP} !important;
border-color: {DEEP} !important;
font-size: 1rem !important;
}}
.st-key-research_go button:hover {{
background: {GOLD} !important; border-color: {GOLD} !important;
}}
/* 큰 검색창 (키워드 분석 / 내 블로그) */
.st-key-kw_main input, .st-key-blog_input_tab input,
.st-key-blog_input_main input {{
font-size: 1.24rem !important;
padding: 18px 22px !important;
border: 2.5px solid {DEEP} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-kw_main input:focus, .st-key-blog_input_tab input:focus,
.st-key-blog_input_main input:focus {{
box-shadow: 0 0 0 4px rgba(200,150,62,.22) !important;
border-color: {GOLD} !important;
}}
.st-key-kw_main label, .st-key-blog_input_tab label,
.st-key-blog_input_main label {{
font-size: 1rem !important; font-weight: 700 !important; color: {INK} !important;
}}
/* 최상단 검색창 — 도구의 핵심 동작이라 가장 눈에 띄어야 한다 */
.st-key-research_kw input {{
font-size: 1.12rem !important;
padding: 15px 18px !important;
border: 2px solid {LINE} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-research_kw input:focus {{
border-color: {DEEP} !important;
box-shadow: 0 0 0 4px rgba(27,58,75,.10) !important;
}}
.st-key-research_go button {{
height: 52px !important;
background: {DEEP} !important;
border-color: {DEEP} !important;
font-size: 1rem !important;
}}
.st-key-research_go button:hover {{
background: {GOLD} !important; border-color: {GOLD} !important;
}}
/* 큰 검색창 (키워드 분석 / 내 블로그) */
.st-key-kw_main input, .st-key-blog_input_tab input,
.st-key-blog_input_main input {{
font-size: 1.24rem !important;
padding: 18px 22px !important;
border: 2.5px solid {DEEP} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-kw_main input:focus, .st-key-blog_input_tab input:focus,
.st-key-blog_input_main input:focus {{
box-shadow: 0 0 0 4px rgba(200,150,62,.22) !important;
border-color: {GOLD} !important;
}}
.st-key-kw_main label, .st-key-blog_input_tab label,
.st-key-blog_input_main label {{
font-size: 1rem !important; font-weight: 700 !important; color: {INK} !important;
}}
/* 최상단 검색창 — 도구의 핵심 동작이라 가장 눈에 띄어야 한다 */
.st-key-research_kw input {{
font-size: 1.12rem !important;
padding: 15px 18px !important;
border: 2px solid {LINE} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-research_kw input:focus {{
border-color: {DEEP} !important;
box-shadow: 0 0 0 4px rgba(27,58,75,.10) !important;
}}
.st-key-research_go button {{
height: 52px !important;
background: {DEEP} !important;
border-color: {DEEP} !important;
font-size: 1rem !important;
}}
.st-key-research_go button:hover {{
background: {GOLD} !important; border-color: {GOLD} !important;
}}
/* 큰 검색창 (키워드 분석 / 내 블로그) */
.st-key-kw_main input, .st-key-blog_input_tab input,
.st-key-blog_input_main input {{
font-size: 1.24rem !important;
padding: 18px 22px !important;
border: 2.5px solid {DEEP} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-kw_main input:focus, .st-key-blog_input_tab input:focus,
.st-key-blog_input_main input:focus {{
box-shadow: 0 0 0 4px rgba(200,150,62,.22) !important;
border-color: {GOLD} !important;
}}
.st-key-kw_main label, .st-key-blog_input_tab label,
.st-key-blog_input_main label {{
font-size: 1rem !important; font-weight: 700 !important; color: {INK} !important;
}}
/* 최상단 검색창 — 도구의 핵심 동작이라 가장 눈에 띄어야 한다 */
.st-key-research_kw input {{
font-size: 1.12rem !important;
padding: 15px 18px !important;
border: 2px solid {LINE} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-research_kw input:focus {{
border-color: {DEEP} !important;
box-shadow: 0 0 0 4px rgba(27,58,75,.10) !important;
}}
.st-key-research_go button {{
height: 52px !important;
background: {DEEP} !important;
border-color: {DEEP} !important;
font-size: 1rem !important;
}}
.st-key-research_go button:hover {{
background: {GOLD} !important; border-color: {GOLD} !important;
}}
/* 큰 검색창 (키워드 분석 / 내 블로그) */
.st-key-kw_main input, .st-key-blog_input_tab input,
.st-key-blog_input_main input {{
font-size: 1.24rem !important;
padding: 18px 22px !important;
border: 2.5px solid {DEEP} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-kw_main input:focus, .st-key-blog_input_tab input:focus,
.st-key-blog_input_main input:focus {{
box-shadow: 0 0 0 4px rgba(200,150,62,.22) !important;
border-color: {GOLD} !important;
}}
.st-key-kw_main label, .st-key-blog_input_tab label,
.st-key-blog_input_main label {{
font-size: 1rem !important; font-weight: 700 !important; color: {INK} !important;
}}
/* 최상단 검색창 — 도구의 핵심 동작이라 가장 눈에 띄어야 한다 */
.st-key-research_kw input {{
font-size: 1.12rem !important;
padding: 15px 18px !important;
border: 2px solid {LINE} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-research_kw input:focus {{
border-color: {DEEP} !important;
box-shadow: 0 0 0 4px rgba(27,58,75,.10) !important;
}}
.st-key-research_go button {{
height: 52px !important;
background: {DEEP} !important;
border-color: {DEEP} !important;
font-size: 1rem !important;
}}
.st-key-research_go button:hover {{
background: {GOLD} !important; border-color: {GOLD} !important;
}}
/* 큰 검색창 (키워드 분석 / 내 블로그) */
.st-key-kw_main input, .st-key-blog_input_tab input,
.st-key-blog_input_main input {{
font-size: 1.24rem !important;
padding: 18px 22px !important;
border: 2.5px solid {DEEP} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-kw_main input:focus, .st-key-blog_input_tab input:focus,
.st-key-blog_input_main input:focus {{
box-shadow: 0 0 0 4px rgba(200,150,62,.22) !important;
border-color: {GOLD} !important;
}}
.st-key-kw_main label, .st-key-blog_input_tab label,
.st-key-blog_input_main label {{
font-size: 1rem !important; font-weight: 700 !important; color: {INK} !important;
}}
/* 최상단 검색창 — 도구의 핵심 동작이라 가장 눈에 띄어야 한다 */
.st-key-research_kw input {{
font-size: 1.12rem !important;
padding: 15px 18px !important;
border: 2px solid {LINE} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-research_kw input:focus {{
border-color: {DEEP} !important;
box-shadow: 0 0 0 4px rgba(27,58,75,.10) !important;
}}
.st-key-research_go button {{
height: 52px !important;
background: {DEEP} !important;
border-color: {DEEP} !important;
font-size: 1rem !important;
}}
.st-key-research_go button:hover {{
background: {GOLD} !important; border-color: {GOLD} !important;
}}
/* 큰 검색창 (키워드 분석 / 내 블로그) */
.st-key-kw_main input, .st-key-blog_input_tab input,
.st-key-blog_input_main input {{
font-size: 1.24rem !important;
padding: 18px 22px !important;
border: 2.5px solid {DEEP} !important;
border-radius: 12px !important;
font-weight: 600 !important;
}}
.st-key-kw_main input:focus, .st-key-blog_input_tab input:focus,
.st-key-blog_input_main input:focus {{
box-shadow: 0 0 0 4px rgba(200,150,62,.22) !important;
border-color: {GOLD} !important;
}}
.st-key-kw_main label, .st-key-blog_input_tab label,
.st-key-blog_input_main label {{
font-size: 1rem !important; font-weight: 700 !important; color: {INK} !important;
}}
/* 상위노출 글 목록 */
.serp-box {{ padding: 6px 10px; }}
.serp-row {{
display: flex; align-items: center; gap: 12px;
padding: 9px 8px; border-bottom: 1px solid {LINE};
font-size: .92rem; border-radius: 6px;
}}
.serp-row:last-child {{ border-bottom: none; }}
.serp-head {{
font-size: .78rem; font-weight: 700; color: {MUTED};
letter-spacing: .05em; text-transform: uppercase;
border-bottom: 2px solid #D6DDE3;
}}
.serp-rank {{
flex: 0 0 34px; text-align: center; font-weight: 800;
font-family: 'IBM Plex Mono', monospace; font-size: 1rem;
}}
.serp-head .serp-rank {{ font-size: .78rem; }}
.serp-title {{
flex: 1 1 auto; color: {INK}; overflow: hidden;
text-overflow: ellipsis; white-space: nowrap;
}}
.serp-blogger {{
flex: 0 0 130px; color: {MUTED}; font-size: .84rem;
overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}}
.serp-age {{
flex: 0 0 74px; text-align: right; font-weight: 700; font-size: .85rem;
font-family: 'IBM Plex Mono', monospace;
}}
.mine-tag {{
background: {GOLD}; color: #fff; font-size: .72rem; font-weight: 700;
padding: 2px 7px; border-radius: 999px; margin-left: 6px;
}}
/* 제목 단어 칩 - 자주 나올수록 진하게 */
.wchip {{
display: inline-flex; align-items: center; gap: 6px;
padding: 6px 13px; border-radius: 999px; margin: 3px;
font-size: .92rem; font-weight: 700; color: #fff;
}}
.wchip b {{
font-family: 'IBM Plex Mono', monospace; font-size: .8rem;
background: rgba(255,255,255,.28); padding: 1px 6px; border-radius: 999px;
}}
/* 개요 항목 */
.outline-item {{
display: flex; gap: 12px; padding: 10px 0;
border-bottom: 1px dashed {LINE};
}}
.outline-item:last-child {{ border-bottom: none; }}
.outline-num {{
flex: 0 0 auto; min-width: 46px; height: 26px; border-radius: 999px;
background: {DEEP}; color: #fff; font-size: .76rem; font-weight: 700;
display: flex; align-items: center; justify-content: center;
padding: 0 10px;
}}
.outline-h {{ font-size: .98rem; font-weight: 700; color: {INK}; }}
.outline-w {{ font-size: .82rem; color: {MUTED}; margin-top: 2px; }}
/* AI 판단 브리핑 */
.brief-box {{
background: {SURFACE}; border: 2px solid {LINE}; border-radius: 12px;
padding: 16px 19px; margin: 8px 0 12px;
}}
.brief-top {{ display: flex; align-items: center; gap: 9px; margin-bottom: 9px; }}
.brief-tag {{
color: #fff; font-size: .8rem; font-weight: 800;
padding: 4px 12px; border-radius: 999px;
}}
.brief-title {{
font-size: .78rem; font-weight: 700; letter-spacing: .1em;
text-transform: uppercase; color: {MUTED};
}}
.brief-head {{
font-size: 1.18rem; font-weight: 800; color: {INK};
line-height: 1.45; margin-bottom: 10px;
}}
.brief-reasons {{
margin: 0 0 11px; padding-left: 19px;
font-size: .94rem; color: #40454C; line-height: 1.75;
}}
.brief-action {{
background: #F6F7F4; border-radius: 9px; padding: 11px 14px;
font-size: .94rem; color: #2A2F35; line-height: 1.6;
}}
.brief-action b {{ color: {DEEP}; font-size: .82rem; }}
.brief-watch {{
margin-top: 8px; font-size: .86rem; color: {BAD}; font-weight: 600;
}}
/* 추적 키워드 카드 */
.track-grid {{
display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
gap: 10px; margin-bottom: 6px;
}}
/* 카드 높이를 고정한다.
   내용 길이에 따라 카드가 들쭉날쭉하면 줄이 어긋나 읽기 어렵다.
   내용은 위에서부터 채우고, 남는 공간은 아래에 둔다. */
.track-card {{
background: {SURFACE}; border: 2px solid #D8DDE2; border-radius: 12px;
padding: 12px 15px 14px;
min-height: 214px;
display: flex; flex-direction: column;
box-shadow: 0 1px 3px rgba(20,22,26,.05);
}}
.track-card:hover {{ border-color: {DEEP}; }}
/* 내가 쓴 키워드 — 두꺼운 테두리 + 다른 배경으로 확실히 구분 */
.track-card.mine {{
border: 3px solid {DEEP};
background: linear-gradient(180deg, #F4F8FA 0%, {SURFACE} 55%);
box-shadow: 0 2px 8px rgba(27,58,75,.14);
}}
.track-card.watching {{
background: {SURFACE};
border-style: dashed;
}}
.tc-head {{ margin-bottom: 6px; }}
.tc-tag {{
display: inline-block; font-size: .7rem; font-weight: 800;
padding: 2px 9px; border-radius: 999px;
background: {DEEP}; color: #fff; letter-spacing: -.01em;
}}
.tc-tag.watch {{
background: transparent; color: {MUTED};
border: 1px dashed #C6CCD2; font-weight: 700;
}}
.tc-kw {{
font-size: .98rem; font-weight: 800; color: {INK};
margin-bottom: 8px; padding-bottom: 8px;
border-bottom: 1px solid {LINE};
overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}}
.tc-rank {{
font-family: 'IBM Plex Mono', monospace;
font-size: 1.6rem; font-weight: 600; line-height: 1.1;
}}
.tc-chg {{ font-size: .86rem; font-weight: 700; margin-top: 3px; }}
.tc-up {{ color: {GOOD}; }}
.tc-down {{ color: {BAD}; }}
.tc-flat {{ color: {MUTED}; font-weight: 600; }}
.tc-meta {{
display: flex; align-items: center; gap: 7px;
margin-top: auto; padding-top: 9px; border-top: 1px solid {LINE};
flex-wrap: wrap;
}}
.tc-pill {{
color: #fff; font-size: .74rem; font-weight: 700;
padding: 2px 9px; border-radius: 999px;
}}
.tc-rec {{ font-size: .76rem; color: {MUTED}; font-family: 'IBM Plex Mono', monospace; }}
.tc-since {{ color: {MUTED}; font-weight: 500; font-size: .78rem; }}
.track-card {{ margin-bottom: 6px; }}
.tc-pill {{ max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
/* 5열이라 칸이 좁다 — 카드 안 버튼은 작게 */
.track-card + div .stButton button {{
padding: 7px 6px !important; font-size: .84rem !important;
border-radius: 8px !important;
}}
/* 중간 폭에서는 3열, 좁으면 2열로 자연스럽게 접히도록
   (Streamlit 컬럼은 고정이라, 폭이 좁아지면 카드 안쪽을 줄여 대응) */
@media (max-width: 1100px) {{
.track-card {{ min-height: 196px; padding: 12px 12px; }}
.tc-kw {{ font-size: .9rem; }}
.tc-rank {{ font-size: 1.4rem; }}
.tc-sub, .tc-chg {{ font-size: .76rem; }}
.tc-pill {{ font-size: .7rem; padding: 2px 7px; }}
.tc-rec {{ font-size: .7rem; }}
}}
/* 등록 당시와 비교 */
.sc-top {{
display: flex; justify-content: space-between; align-items: center;
margin-bottom: 3px;
}}
.sc-top .chart-title {{ margin-bottom: 0; }}
.sc-verdict {{
color: #fff; font-size: .8rem; font-weight: 800;
padding: 3px 11px; border-radius: 999px;
}}
.sc-since {{ font-size: .78rem; color: {MUTED}; margin-bottom: 11px; }}
.sc-row {{
display: flex; align-items: center; gap: 9px;
padding: 8px 0; border-bottom: 1px solid {LINE};
font-family: 'IBM Plex Mono', monospace; font-size: .92rem;
}}
.sc-label {{
flex: 0 0 66px; font-family: 'Pretendard', sans-serif;
font-size: .88rem; font-weight: 700; color: {INK};
}}
.sc-from {{ flex: 1 1 0; text-align: right; color: {MUTED}; }}
.sc-arrow {{ flex: 0 0 16px; text-align: center; color: {MUTED}; }}
.sc-to {{ flex: 1 1 0; text-align: right; font-weight: 600; color: {INK}; }}
.sc-pct {{ flex: 0 0 74px; text-align: right; font-weight: 700; font-size: .85rem; }}
.sc-foot {{
font-size: .84rem; color: {MUTED}; padding-top: 9px;
font-family: 'Pretendard', sans-serif;
}}
.sc-foot b {{ color: {BAD}; }}
.sc-note {{
margin-top: 8px; padding-top: 9px; border-top: 1px solid {LINE};
font-size: .9rem; color: #40454C; line-height: 1.6;
}}
/* 조회에 쓴 힌트 표시 */
.hint-row {{
font-size: .82rem; color: {MUTED}; margin: -4px 0 10px;
display: flex; align-items: center; flex-wrap: wrap; gap: 5px;
}}
.hint-chip {{
background: #F1F6F8; color: {DEEP}; border: 1px solid #D6E2E8;
padding: 2px 9px; border-radius: 999px;
font-size: .78rem; font-weight: 700;
}}
/* 사냥 순위 — 가로 막대 */
.hb-main {{
display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
padding-bottom: 11px; margin-bottom: 10px;
border-bottom: 1.5px solid {LINE};
}}
.hb-main-label {{
font-size: .68rem; font-weight: 800; letter-spacing: .09em;
color: {MUTED}; text-transform: uppercase;
}}
.hb-main b {{ font-size: 1.02rem; color: {INK}; }}
.hb-main-sub {{
font-size: .78rem; color: {MUTED};
font-family: 'IBM Plex Mono', monospace;
}}
.hb-row {{
display: grid;
grid-template-columns: 130px 1fr 190px;
align-items: center; gap: 11px;
padding: 7px 0;
}}
.hb-kw {{
font-size: .92rem; font-weight: 700; color: {INK};
text-align: right;
overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}}
.hb-track {{
height: 26px; background: #F4F4EF; border-radius: 7px;
overflow: hidden;
}}
.hb-fill {{
height: 100%; border-radius: 7px;
display: flex; align-items: center; justify-content: flex-end;
padding-right: 9px; min-width: 34px;
transition: width .25s ease;
}}
.hb-score {{
color: #fff; font-size: .82rem; font-weight: 700;
font-family: 'IBM Plex Mono', monospace;
}}
.hb-sub {{
font-size: .76rem; color: {MUTED};
font-family: 'IBM Plex Mono', monospace;
overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}}
/* 표 — 컬럼이 화면 전체로 벌어지지 않게 */
.stDataFrame {{ max-width: 100%; }}
.stDataFrame [role="columnheader"],
.stDataFrame [role="gridcell"] {{
padding-left: 10px !important; padding-right: 10px !important;
}}
/* 첫 컬럼(대개 키워드)이 지나치게 넓어지는 것을 막는다 */
.stDataFrame [role="row"] > [role="gridcell"]:nth-child(2),
.stDataFrame [role="row"] > [role="columnheader"]:nth-child(2) {{
max-width: 320px;
}}
/* 상단 정보 줄 *//* 상단 정보 줄 */
.topbar {{
display: flex; flex-wrap: wrap; gap: 7px;
margin: -8px 0 14px;
}}
.tb-item {{
font-size: .8rem; font-weight: 600; color: {MUTED};
background: {SURFACE}; border: 1px solid {LINE};
padding: 4px 11px; border-radius: 999px;
}}
.tb-on {{
color: {DEEP}; border-color: {DEEP}; background: #F1F6F8;
}}
.tb-off {{ color: #9AA3AC; border-style: dashed; }}
.tb-dim {{
color: #B4BAC1; font-family: 'IBM Plex Mono', monospace;
font-size: .72rem; font-weight: 400;
}}
/* 접이식 영역 */
[data-testid="stExpander"] {{
border: 1.5px solid {LINE} !important;
border-radius: 12px !important;
background: {SURFACE} !important;
margin-bottom: 14px;
}}
[data-testid="stExpander"] summary {{
font-weight: 700 !important; font-size: .95rem !important;
color: {INK} !important; padding: 12px 16px !important;
}}
[data-testid="stExpander"] summary:hover {{ color: {DEEP} !important; }}
/* 진단 2x2 매트릭스 */
.diag-grid {{
display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;
}}
.diag-cell {{
border: 1.5px solid; border-radius: 10px; padding: 13px 15px;
position: relative; min-height: 74px;
}}
.diag-name {{ font-size: 1rem; font-weight: 800; margin-bottom: 3px; }}
.diag-desc {{ font-size: .82rem; opacity: .88; }}
.diag-mark {{
position: absolute; top: -9px; right: 11px;
background: {INK}; color: #fff; font-size: .7rem; font-weight: 700;
padding: 2px 9px; border-radius: 999px;
}}
.diag-axis {{
display: flex; justify-content: space-between;
font-size: .76rem; color: {MUTED}; padding: 2px 2px 8px;
}}
.diag-note {{
border-top: 1px solid {LINE}; padding-top: 9px;
font-size: .9rem; color: #40454C; line-height: 1.6;
}}
.diag-note b {{ color: {INK}; }}
/* 진행률 바 */
.prog-label {{
font-size: .92rem; color: {DEEP}; font-weight: 600;
margin-bottom: 4px;
}}
.prog-label b {{
font-family: 'IBM Plex Mono', monospace; color: {GOLD};
}}
.stProgress > div > div > div > div {{
background: linear-gradient(90deg, {DEEP}, {GOLD}) !important;
}}
.stProgress > div > div > div {{
background: #EFEFEA !important; height: 10px !important; border-radius: 999px !important;
}}
/* 차트 */
.chart-box {{
background: {SURFACE}; border: 1.5px solid {LINE};
border-radius: 12px; padding: 16px 18px; margin: 6px 0 10px;
}}
/* 사냥 지도 점 - 마우스 올리면 강조 */
.chart-box g.pt {{ cursor: pointer; }}
.chart-box g.pt circle {{ transition: r .12s ease, opacity .12s ease; }}
.chart-box g.pt:hover circle:last-child {{
r: 8; opacity: 1; stroke-width: 2.2;
}}
.chart-title {{
font-size: .92rem; font-weight: 700; color: {INK};
display: block; margin-bottom: 10px;
}}
.donut-box {{ text-align: center; }}
.donut-box .legend {{ margin-top: 10px; }}
.legend .lg {{
display: inline-flex; align-items: center; gap: 5px;
font-size: .84rem; color: #4A5560; margin: 0 8px;
}}
.legend .lg i {{
width: 10px; height: 10px; border-radius: 3px; display: inline-block;
}}
.legend .lg b {{ font-family: 'IBM Plex Mono', monospace; color: {INK}; }}
.fresh-top {{
display: flex; justify-content: space-between; align-items: baseline;
}}
.fresh-top .chart-title {{ margin-bottom: 0; }}
.fresh-num {{
font-family: 'IBM Plex Mono', monospace; font-size: 1.5rem;
font-weight: 600; color: {DEEP};
}}
.fresh-num small {{ font-size: .9rem; color: {MUTED}; margin-left: 2px; }}
.fresh-track {{
height: 10px; background: #EFEFEA; border-radius: 999px;
overflow: hidden; margin: 10px 0 8px;
}}
.fresh-fill {{ height: 100%; border-radius: 999px; }}
.fresh-foot {{ font-size: .84rem; color: {MUTED}; }}
/* 표 - 글자 크기 및 테두리 */
.stDataFrame {{ border: 1.5px solid {LINE}; border-radius: 10px; overflow: hidden; }}
.stDataFrame [data-testid="stTable"] {{ font-size: .95rem; }}
div[data-testid="stDataFrameResizable"] {{ font-size: .95rem; }}
/* 셀 여백을 줄여 행이 뜨지 않게 */
.stDataFrame [role="gridcell"], .stDataFrame [role="columnheader"] {{
padding-top: 6px !important; padding-bottom: 6px !important;
}}
/* 헤더 - 네이비 톤으로 본문과 확실히 구분 */
.stDataFrame [role="columnheader"] {{
background: #EDF0F3 !important; font-weight: 700 !important;
color: {DEEP} !important; font-size: .89rem !important;
border-bottom: 2px solid #D6DDE3 !important;
}}
.stDataFrame [role="row"]:hover [role="gridcell"] {{
background: rgba(200,150,62,.07) !important;
}}
/* 라디오 버튼 */
.stRadio label {{ font-size: .95rem !important; }}
div[role="radiogroup"] {{
background: {SURFACE}; border: 1px solid {LINE};
border-radius: 10px; padding: 8px 14px;
}}
/* 본문 기본 크기 상향 */
.stMarkdown p, .stCheckbox label {{ font-size: .96rem; }}
div[data-testid="stMetricValue"] {{ font-family: 'IBM Plex Mono', monospace; }}
/* 점수 구성 막대 */
.sb-top {{
display: flex; justify-content: space-between; align-items: baseline;
margin-bottom: 12px;
}}
.sb-top .chart-title {{ margin-bottom: 0; }}
.sb-total {{
font-family: 'IBM Plex Mono', monospace; font-size: 1.7rem;
font-weight: 600; color: {DEEP};
}}
.sb-row {{ display: flex; align-items: center; gap: 12px; padding: 7px 0; }}
.sb-name {{ flex: 0 0 74px; font-size: .9rem; font-weight: 700; color: {INK}; }}
.sb-track {{
flex: 1 1 auto; height: 9px; background: #EFEFEA;
border-radius: 999px; overflow: hidden;
}}
.sb-fill {{ height: 100%; border-radius: 999px; }}
.sb-val {{ flex: 0 0 108px; text-align: right; font-size: .88rem; font-weight: 700; }}
.sb-none {{ color: {MUTED} !important; font-weight: 500; }}
/* 검색 버튼 */
.stButton button {{
background: {DEEP} !important; color: #fff !important;
border: 1.5px solid {DEEP} !important; border-radius: 10px !important;
font-weight: 700 !important; font-size: .98rem !important;
padding: 11px 18px !important; transition: all .15s ease;
}}
.stButton button:hover {{
background: #24506A !important; border-color: {GOLD} !important;
transform: translateY(-1px);
box-shadow: 0 3px 9px rgba(27,58,75,.24) !important;
}}
.stButton button:active {{ transform: translateY(0); }}
/* 검색 버튼을 입력창 라벨 높이만큼 내려서 나란히 맞춘다 */
.search-btn-pad {{ height: 30px; }}
.st-key-research_go button {{
height: 48px; font-size: 1.02rem !important;
}}
/* ============================================================
   모바일 최적화
   좁은 화면에서는 여백을 줄이고, 가로로 넘치는 요소를 접는다.
   ============================================================ */
@media (max-width: 640px) {{
.block-container {{ padding: 1.2rem .6rem 3rem !important; }}
.masthead {{ padding: 14px 15px; border-radius: 12px; }}
.masthead h1 {{ font-size: 1.2rem; }}
.masthead p {{ font-size: .84rem; line-height: 1.5; }}
.mast-head-row {{ gap: 10px; }}
.mast-head-row svg {{ width: 32px; height: 32px; }}
.topbar {{ gap: 5px; margin: -4px 0 10px; }}
.tb-item {{ font-size: .72rem; padding: 3px 9px; }}
/* 탭 — 한 화면에 다 안 들어가므로 가로로 밀어서 본다.
   끝에 그림자를 둬서 '더 있다'는 걸 알린다. */
[role="tablist"] {{
flex-wrap: nowrap !important; overflow-x: auto !important;
gap: 5px !important; padding: 2px 0 8px !important;
-webkit-overflow-scrolling: touch;
scrollbar-width: none;
-webkit-mask-image: linear-gradient(to right,
  #000 0, #000 calc(100% - 24px), transparent 100%);
mask-image: linear-gradient(to right,
  #000 0, #000 calc(100% - 24px), transparent 100%);
}}
[role="tablist"]::-webkit-scrollbar {{ display: none; }}
[role="tab"] {{
min-height: 36px !important; padding: 6px 12px !important;
flex-shrink: 0 !important; white-space: nowrap !important;
}}
[role="tab"] *, [role="tab"] p {{ font-size: .85rem !important; }}
[role="tabpanel"] [role="tab"] {{ min-height: 31px !important; padding: 4px 10px !important; }}
[role="tabpanel"] [role="tab"] * {{ font-size: .8rem !important; }}
/* KPI */
.kpi {{ padding: 11px 12px; }}
.kpi-val {{ font-size: 1.35rem; }}
.kpi-label {{ font-size: .72rem; }}
.kpi-sub {{ font-size: .74rem; }}
/* 표 — 모바일에서 가장 보기 힘든 부분.
   글자를 키우고 행 간격을 넓혀 손가락으로 짚기 쉽게 한다. */
.stDataFrame {{ border-radius: 10px; }}
.stDataFrame [data-testid="stTable"],
div[data-testid="stDataFrameResizable"] {{ font-size: .9rem !important; }}
.stDataFrame [role="gridcell"] {{
padding-top: 10px !important; padding-bottom: 10px !important;
}}
.stDataFrame [role="columnheader"] {{
font-size: .8rem !important;
padding-top: 8px !important; padding-bottom: 8px !important;
}}
/* 첫 열(키워드)은 스크롤해도 남게 */
.stDataFrame [role="row"] > [role="gridcell"]:first-child,
.stDataFrame [role="row"] > [role="columnheader"]:first-child {{
position: sticky; left: 0; z-index: 2;
background: {SURFACE}; box-shadow: 1px 0 0 {LINE};
}}
/* 사냥 순위 — 좁은 화면에서는 이름을 막대 위로 올린다 */
.hb-row {{
grid-template-columns: 1fr !important;
gap: 3px !important; padding: 8px 0 !important;
border-bottom: 1px solid #F2F2ED;
}}
.hb-kw {{ text-align: left !important; font-size: .88rem; }}
.hb-track {{ height: 22px; }}
.hb-sub {{ font-size: .72rem; }}
.hb-main-sub {{ font-size: .74rem; }}
/* 진단·추적 카드는 1열 */
.diag-grid {{ grid-template-columns: 1fr !important; }}
.diag-cell {{ min-height: 0; padding: 11px 13px; }}
.diag-axis {{ flex-direction: column; gap: 3px; }}
.track-grid {{ grid-template-columns: 1fr !important; }}
.track-card {{ min-height: 0 !important; }}
.title-grid {{ grid-template-columns: 1fr !important; }}
/* 상위노출 목록 */
.serp-row {{ gap: 8px; padding: 9px 5px; font-size: .86rem; }}
.serp-rank {{ flex: 0 0 24px; font-size: .88rem; }}
.serp-age {{ flex: 0 0 58px; font-size: .74rem; }}
/* 점수 구성 */
.sb-name {{ flex: 0 0 54px; font-size: .8rem; }}
.sb-val {{ flex: 0 0 72px; font-size: .76rem; }}
.sb-total {{ font-size: 1.3rem; }}
/* 차트 — 가로 넘침 방지 */
.chart-box {{ padding: 12px 11px; overflow-x: auto; -webkit-overflow-scrolling: touch; }}
.chart-box svg[viewBox^="0 0 760"] {{ min-width: 520px; }}
.donut-box svg {{ min-width: 0 !important; }}
.gauge-wrap {{ padding: 12px 13px; }}
/* 글자 */
.note {{ font-size: .85rem; padding: 10px 12px; }}
.section-title {{ font-size: 1.05rem; }}
.brief-box {{ padding: 13px 14px; }}
.brief-head {{ font-size: 1rem; }}
.brief-reasons {{ font-size: .85rem; padding-left: 16px; }}
/* 입력창 — 16px 미만이면 iOS가 화면을 확대한다 */
.stTextInput input {{ font-size: 16px !important; }}
.st-key-kw_main input, .st-key-blog_input_main input {{
font-size: 16px !important; padding: 13px 14px !important;
}}
/* 최상단 검색창 — 모바일에서는 세로로 쌓인다 */
.st-key-research_kw input {{
font-size: 16px !important; padding: 13px 14px !important;
}}
.st-key-research_go button {{
height: 48px !important; margin-top: 6px; font-size: .95rem !important;
}}
/* 라디오·버튼 */
div[role="radiogroup"] {{ padding: 5px 9px; flex-wrap: wrap; gap: 2px; }}
.stRadio label {{ font-size: .84rem !important; }}
.stButton button {{ width: 100%; padding: 12px 14px !important; }}
.search-btn-pad {{ height: 0 !important; }}
.st-key-research_go button {{ height: 46px; margin-top: 2px; }}
[data-testid="stExpander"] summary {{ font-size: .88rem !important; padding: 11px 13px !important; }}
}}
/* 아주 좁은 화면 */
@media (max-width: 400px) {{
.masthead h1 {{ font-size: 1.15rem; }}
.kpi-val {{ font-size: 1.32rem; }}
.serp-age {{ display: none; }}
}}
/* ============================================================
   표 — 키워드 열은 붙박이, 나머지는 옆으로 민다
   ⚠️ 모바일에서 열이 많은 표는 어떻게 줄여도 안 들어간다.
   글씨를 줄이는 대신, 첫 열(키워드)만 고정하고
   나머지를 가로로 밀어 보게 한다. 무엇의 숫자인지 항상 보인다.
   ============================================================ */
.kh-tw {{
overflow-x: auto;
-webkit-overflow-scrolling: touch;
border: 1px solid {LINE};
border-radius: 4px;
background: {SURFACE};
}}
.kh-t {{
border-collapse: separate; border-spacing: 0;
width: 100%; font-size: .9rem; color: {INK};
}}
.kh-t th {{
font-size: .74rem; color: {MUTED}; font-weight: 600;
text-align: left; padding: 10px 13px;
background: #F7F7F4; border-bottom: 1px solid {LINE};
white-space: nowrap; letter-spacing: .02em;
/* 긴 목록을 세로로 굴릴 때 머리글이 따라 올라가지 않게 */
position: sticky; top: 0; z-index: 3;
}}
.kh-t th.kh-key {{ z-index: 4; }}
/* 행이 많은 목록은 표 안에서 굴린다 (페이지가 끝없이 길어지지 않게) */
.kh-tw.kh-scroll {{ overflow-y: auto; }}
.kh-t td {{
padding: 11px 13px; border-bottom: 1px solid #F1F1EC;
white-space: nowrap;
}}
.kh-t tbody tr:last-child td {{ border-bottom: 0; }}
.kh-t .kh-num {{
font-family: 'IBM Plex Mono', monospace;
font-variant-numeric: tabular-nums;
text-align: right; color: #4B5563;
}}
.kh-t th.kh-num {{ text-align: right; }}
/* 붙박이 열 — 배경이 투명하면 뒤 칸이 비쳐 보인다 */
.kh-t .kh-key {{
position: sticky; left: 0; z-index: 2;
background: {SURFACE};
border-right: 1px solid {LINE};
font-weight: 600;
/* ⚠️ 키워드는 절대 줄바꿈하지 않는다.
   두 줄로 접히면 행 높이가 제각각이 되어 표가 울퉁불퉁해진다.
   width:1% + nowrap = 내용 길이에 딱 맞게 줄어드는 칸. */
white-space: nowrap;
width: 1%;
}}
.kh-t th.kh-key {{ background: #F7F7F4; }}
.kh-t tbody tr:nth-child(even) td {{ background: #FCFCFA; }}
.kh-t tbody tr:nth-child(even) td.kh-key {{ background: #FCFCFA; }}
.kh-rk {{
color: #B6BAC0; font-family: 'IBM Plex Mono', monospace;
font-size: .74rem; margin-right: 8px;
}}
.kh-chip {{
font-size: .76rem; font-weight: 600;
padding: 3px 8px; border-radius: 4px; display: inline-block;
}}
.kh-hint {{
display: none; font-size: .74rem; color: {MUTED};
text-align: right; margin: 6px 2px 14px;
}}
@media (max-width: 700px) {{
.kh-hint {{ display: block; }}
.kh-t {{ font-size: .84rem; }}
.kh-t td {{ padding: 10px 11px; }}
.kh-t th {{ padding: 9px 11px; }}
.kh-t .kh-key {{ padding-right: 14px; }}
}}

/* ============================================================
   A 톤 — 흰 배경 / 옅은 회색 선 / 파란 포인트
   ⚠️ 위쪽 규칙이 오래 쌓이면서 같은 선택자가 여러 번 겹쳐 있다.
   하나씩 고치면 어느 게 이겼는지 알기 어려워서,
   최종 모습은 여기 한 곳에서만 정한다. (뒤에 오는 규칙이 이긴다)
   ============================================================ */
.stApp {{ background: {BASE}; }}
.block-container {{ padding-top: 1.1rem; max-width: 1180px; }}

/* 상단 바 — 짙은 카드에서 흰 바로 */
.masthead {{
background: {SURFACE}; border: 1px solid {LINE};
border-radius: 12px; padding: 15px 20px;
margin-bottom: 14px; color: {INK};
}}
.masthead h1 {{ font-size: 1.3rem; font-weight: 800; color: {INK}; }}
.masthead p {{ margin: 6px 0 0; font-size: .89rem; color: {MUTED}; }}
.masthead .rule {{ display: none; }}
.mast-head-row {{ gap: 12px; }}

/* 상위 탭 — 알약을 버리고 밑줄로 */
[role="tablist"] {{
gap: 0 !important; padding: 0 !important;
margin-bottom: 18px !important;
border-bottom: 1px solid {LINE} !important;
flex-wrap: nowrap !important; overflow-x: auto !important;
scrollbar-width: none;
}}
[role="tablist"]::-webkit-scrollbar {{ display: none; }}
[role="tab"] {{
min-height: 42px !important; padding: 11px 16px !important;
background: transparent !important;
border: 0 !important; border-radius: 0 !important;
border-bottom: 2px solid transparent !important;
box-shadow: none !important; color: {MUTED} !important;
white-space: nowrap !important; transform: none !important;
}}
[role="tab"] *, [role="tab"] p, [role="tab"] div, [role="tab"] span {{
font-size: .95rem !important; font-weight: 600 !important; color: inherit !important;
}}
[role="tab"]:hover {{
background: transparent !important; color: {INK} !important;
box-shadow: none !important; transform: none !important;
border-bottom-color: #C7CDD6 !important;
}}
[role="tab"][aria-selected="true"] {{
background: transparent !important; color: {INK} !important;
box-shadow: none !important;
border-bottom: 2px solid {DEEP} !important;
}}
[role="tab"][aria-selected="true"] *,
[role="tab"][aria-selected="true"] p,
[role="tab"][aria-selected="true"] div,
[role="tab"][aria-selected="true"] span {{
color: {INK} !important; font-weight: 700 !important;
}}
[role="tab"][aria-selected="true"]:hover {{
background: transparent !important; border-bottom-color: {DEEP} !important;
}}

/* 하위 탭 — 작은 회색 알약, 선택하면 옅은 파랑 */
[role="tabpanel"] [role="tablist"] {{
border-bottom: 0 !important; gap: 6px !important;
margin-bottom: 14px !important; padding: 0 !important;
}}
[role="tabpanel"] [role="tab"] {{
min-height: 32px !important; padding: 6px 13px !important;
background: #F1F3F6 !important; border-radius: 999px !important;
border: 0 !important; color: #55606D !important;
/* ⚠️ 옛 규칙이 선택된 알약에 금색 그림자를 깔아둬서
   밑줄이 그어진 것처럼 보였다. 여기서 확실히 지운다. */
box-shadow: none !important;
}}
[role="tabpanel"] [role="tab"] *,
[role="tabpanel"] [role="tab"] p {{
font-size: .87rem !important; font-weight: 600 !important; color: inherit !important;
}}
[role="tabpanel"] [role="tab"]:hover {{
background: #E6EAEF !important; border: 0 !important;
box-shadow: none !important; color: {INK} !important;
}}
[role="tabpanel"] [role="tab"][aria-selected="true"] {{
background: #EAF1FD !important; color: {DEEP} !important;
border: 0 !important; box-shadow: none !important;
}}
[role="tabpanel"] [role="tab"][aria-selected="true"] *,
[role="tabpanel"] [role="tab"][aria-selected="true"] p {{ color: {DEEP} !important; }}
[role="tabpanel"] [role="tab"][aria-selected="true"]:hover {{
background: #DCE8FB !important; box-shadow: none !important; border: 0 !important;
}}

/* 카드 · 입력 · 버튼 */
.kpi {{ border: 1px solid {LINE}; border-radius: 12px; padding: 15px 17px; }}
.kpi-label {{ text-transform: none; letter-spacing: 0; font-size: .8rem; font-weight: 500; }}
.kpi-val {{ font-size: 1.55rem; }}
.note {{ border-left: 3px solid {DEEP}; border-radius: 10px; color: #4B5563; }}
.note-gold {{ border-left-color: {GOLD}; }}
.chip {{ border-radius: 6px; padding: 4px 10px; font-size: .84rem; }}
.stTextInput input {{
border: 1px solid #D9DDE3 !important; border-radius: 10px !important;
}}
.stTextInput input:focus {{
border-color: {DEEP} !important;
box-shadow: 0 0 0 3px rgba(26,86,219,.12) !important;
}}
.stButton button {{
border-radius: 10px !important; border: 1px solid #D9DDE3 !important;
background: {SURFACE} !important; color: #374151 !important; font-weight: 600 !important;
}}
.st-key-research_go button, .st-key-map_go button {{
background: {DEEP} !important; border-color: {DEEP} !important; color: #fff !important;
}}
.st-key-research_go button:hover, .st-key-map_go button:hover {{
background: #1447B5 !important; border-color: #1447B5 !important; color: #fff !important;
}}
/* 입력칸 테두리·포커스 링에 남아 있던 금색을 파랑으로 */
.st-key-kw_main input, .st-key-blog_input_tab input,
.st-key-blog_input_main input {{ border-width: 1px !important; border-color: #D9DDE3 !important; }}
.st-key-research_kw input:focus, .st-key-kw_main input:focus,
.st-key-blog_input_tab input:focus, .st-key-blog_input_main input:focus {{
border-color: {DEEP} !important;
box-shadow: 0 0 0 3px rgba(26,86,219,.12) !important;
}}
.eyebrow {{ color: {MUTED}; letter-spacing: .08em; }}
.section-title {{ font-size: 1.12rem; }}
.gauge-num {{ color: {DEEP}; }}

/* ---- 로고 + 탭을 한 줄로 ----
   높이 0짜리 칸에 로고와 상태를 띄워두고,
   바로 아래 오는 탭 막대에 왼쪽 여백을 줘서 같은 줄처럼 보이게 한다. */
.masthead {{
height: 0; overflow: visible; position: relative; z-index: 4;
background: transparent; border: 0; border-radius: 0;
padding: 0; margin: 0;
}}
.mast-brand {{
position: absolute; left: 2px; top: 13px;
display: flex; align-items: center; gap: 8px;
}}
.mast-brand svg {{ flex: none; }}
.mast-name {{
font-size: 1.06rem; font-weight: 800; color: {INK};
letter-spacing: -.03em; white-space: nowrap;
}}
.mast-name b {{ color: {DEEP}; font-weight: 800; }}
.mast-meta {{
position: absolute; right: 2px; top: 19px;
font-size: .78rem; color: #9AA1AB; white-space: nowrap;
}}
[role="tablist"] {{ padding-left: 152px !important; height: 54px !important; align-items: center !important; }}
[role="tabpanel"] [role="tablist"] {{ padding-left: 0 !important; height: auto !important; }}
/* ---- 추적 카드: 쓴 키워드 / 지켜보는 키워드를 파스텔로 구분 ---- */
.track-card {{
border: 1.5px solid #E3E6EB; border-radius: 14px;
box-shadow: none; min-height: 208px;
}}
.track-card:hover {{ border-color: #C3CBD6; }}
/* 내가 쓴 키워드 — 연한 파랑 */
.track-card.mine {{
border: 1.5px solid #C3D7F7;
background: #F2F7FF;
box-shadow: none;
}}
.track-card.mine:hover {{ border-color: #9CBEF0; }}
/* 지켜보는 키워드 — 연한 살구 */
.track-card.watching {{
border: 1.5px solid #EFE1C6; border-style: solid;
background: #FFFAF2;
}}
.track-card.watching:hover {{ border-color: #E3CB9C; }}
.tc-tag {{
background: #DCE8FB; color: #1A4FB0;
font-weight: 700; padding: 3px 10px;
}}
.tc-tag.watch {{
background: #F7EBD6; color: #91661A;
border: 0; font-weight: 700;
}}
.tc-kw {{ border-bottom-color: #E7E9ED; }}
/* 표 안에서 가운데로 세울 칸 */
.kh-t .kh-center, .kh-t th.kh-center {{ text-align: center; }}
/* ---- 글 뼈대 후보: 세로 목록 대신 가로 카드 ---- */
.outline-grid {{
display: grid; grid-template-columns: repeat(auto-fill, minmax(215px, 1fr));
gap: 10px;
}}
.outline-card {{
background: {SURFACE}; border: 1px solid {LINE}; border-radius: 12px;
padding: 12px 13px 13px;
}}
.outline-top {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
.outline-num {{
flex: none; min-width: 0; height: 22px; border-radius: 6px;
font-size: .72rem; font-weight: 700; color: #fff;
display: inline-flex; align-items: center; padding: 0 8px;
}}
.outline-h {{
font-size: .92rem; font-weight: 700; color: {INK};
overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}}
.outline-w {{ font-size: .78rem; color: {MUTED}; line-height: 1.55; margin: 0; }}
/* ---- 추적 카드 ----
   ⚠️ 높이를 못 박았더니 flex가 안쪽 줄을 눌러 짜서
   키워드 글자가 위아래로 잘렸다. 높이는 최소값만 주고,
   대신 두 종류의 카드가 같은 줄 수를 갖도록 내용을 맞춘다. */
.track-card {{ min-height: 232px; height: auto; overflow: visible; }}
.track-card > * {{ flex: 0 0 auto; }}
.tc-meta {{ flex-wrap: nowrap !important; gap: 6px; }}
.tc-pill {{ flex: 0 1 auto; min-width: 0; }}
.tc-rec {{ flex: none; white-space: nowrap; }}
/* ⚠️ '.track-card + div' 로는 Streamlit 버튼이 안 잡힌다.
   (카드와 버튼이 서로 다른 컨테이너에 들어간다)
   버튼 글자는 어디서든 줄바꿈될 이유가 없으니 전부에 건다. */
.stButton button, .stButton button p, .stButton button div {{
white-space: nowrap !important; word-break: keep-all !important;
}}
.track-card ~ div .stButton button {{
font-size: .82rem !important; padding: 7px 4px !important;
}}
@media (max-width: 1100px) {{
.track-card {{ min-height: 214px; height: auto; }}
}}
/* ---- 등록 당시와 비교: 오른쪽 % 칸을 없애고 아래 두 줄로 말한다 ---- */
.sc-to {{ flex: 0 0 auto; min-width: 92px; }}
.sc-delta {{
font-family: 'Pretendard', sans-serif;
font-size: .88rem; color: {MUTED};
padding-top: 9px; line-height: 1.6;
}}
.sc-delta b {{ font-weight: 700; }}
/* ---- 상단 로고 ---- */
.mast-brand {{ text-decoration: none !important; top: 10px; }}
.mast-brand:hover {{ opacity: .82; }}
.mast-logo {{ height: 34px; width: auto; display: block; }}
/* 글씨도 로고와 같은 색으로 맞춰 한 덩어리로 보이게 */
.mast-name {{ color: #0057A7 !important; }}
.mast-name b {{ color: #F96F00 !important; }}
/* ---- 모바일: G처럼 촘촘하게 ---- */
@media (max-width: 700px) {{
.block-container {{ padding: .7rem .65rem 2rem !important; }}
/* 좁은 화면에서는 로고 줄과 탭 줄을 위아래로 나눈다 */
.masthead {{
height: auto; position: static; display: flex;
align-items: center; justify-content: space-between;
padding: 2px 0 8px; margin-bottom: 2px;
}}
.mast-brand, .mast-meta {{ position: static; }}
.mast-brand {{ flex: none; }}
.mast-name {{ font-size: 1rem; }}
.mast-logo {{ height: 26px; }}
/* 좁은 화면에서 상태 글이 로고를 밀지 않게, 남는 만큼만 쓰고 잘라낸다 */
.mast-meta {{
font-size: .72rem; flex: 1; min-width: 0; margin-left: 12px;
text-align: right; overflow: hidden; text-overflow: ellipsis;
}}
[role="tablist"] {{ padding-left: 0 !important; height: auto !important; }}
[role="tablist"] {{ margin-bottom: 13px !important; }}
[role="tab"] {{ padding: 9px 12px !important; min-height: 38px !important; }}
[role="tab"] *, [role="tab"] p {{ font-size: .87rem !important; }}
[role="tabpanel"] [role="tablist"] {{ flex-wrap: nowrap !important; overflow-x: auto !important; }}
[role="tabpanel"] [role="tab"] {{ padding: 5px 11px !important; min-height: 29px !important; }}
[role="tabpanel"] [role="tab"] *, [role="tabpanel"] [role="tab"] p {{ font-size: .81rem !important; }}
.kpi {{ padding: 11px 12px; border-radius: 10px; }}
.kpi-label {{ font-size: .72rem; margin-bottom: 4px; }}
.kpi-val {{ font-size: 1.18rem; }}
.kpi-sub {{ font-size: .74rem; }}
.section-title {{ font-size: 1rem; }}
.note {{ font-size: .85rem; padding: 9px 11px; line-height: 1.6; }}
/* 가로로 늘어선 카드는 모바일에서 2개씩 접는다.
   4개를 그대로 두면 칸이 좁아 숫자가 잘린다. */
[data-testid="stHorizontalBlock"] {{
gap: .5rem !important; flex-wrap: wrap !important;
}}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
min-width: calc(50% - .5rem) !important; flex: 1 1 calc(50% - .5rem) !important;
}}
}}
</style>"""
    st.markdown("\n".join(ln for ln in _css.splitlines() if ln.strip()),
                unsafe_allow_html=True)


def hunter_icon(size=34):
    """
    헌터 표식 — 과녁에 꽂힌 화살.

    이전에는 사파리햇을 쓴 캐릭터를 그렸는데, 작게 줄이면 뭉개져서
    무엇인지 알아보기 어려웠다. 도구의 표식은 캐릭터보다
    단순한 기하 도형이 어느 크기에서든 또렷하다.
    과녁은 '노린다', 화살은 '맞힌다'를 뜻해서 이름과도 맞는다.
    """
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 48 48" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<circle cx="24" cy="24" r="21" fill="none" stroke="{GOLD}" '
        f'stroke-width="2.5" opacity=".45"/>'
        f'<circle cx="24" cy="24" r="14" fill="none" stroke="{GOLD}" '
        f'stroke-width="2.5" opacity=".7"/>'
        f'<circle cx="24" cy="24" r="6.5" fill="{GOLD}"/>'
        f'<path d="M24 24 L41 7" stroke="#FFFFFF" stroke-width="4.5" '
        f'stroke-linecap="round"/>'
        f'<path d="M24 24 L41 7" stroke="{DEEP}" stroke-width="2.6" '
        f'stroke-linecap="round"/>'
        f'<path d="M41 7 L41 14 M41 7 L34 7" stroke="{DEEP}" '
        f'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="24" cy="24" r="2.4" fill="#FFFFFF"/>'
        f'</svg>')


def topbar(blog_id="", freshness="", version=""):
    """
    화면 맨 위 정보 줄.

    사이드바를 없애면서 거기 있던 것들(블로그 등록 상태, 마지막 수집 시각)을
    옮겨왔다. 사이드바는 모바일에서 기본으로 접히고, 여는 버튼을 찾기 어려워
    쓰이지 않는 공간이 되기 쉽다.
    """
    bits = []
    if blog_id:
        bits.append(f'<span class="tb-item tb-on">내 블로그 · {_esc(blog_id)}</span>')
    else:
        bits.append('<span class="tb-item tb-off">블로그 미등록</span>')
    if freshness:
        bits.append(f'<span class="tb-item">수집 {_esc(freshness)}</span>')
    if version:
        bits.append(f'<span class="tb-item tb-dim">{_esc(version)}</span>')
    st.markdown(f'<div class="topbar">{"".join(bits)}</div>',
                unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _logo_uri():
    """
    상단바 로고. 파일을 base64로 박아 넣는다.

    ⚠️ st.markdown 안의 <img>는 로컬 경로(logo.png)를 못 읽는다.
    브라우저가 그 주소로 다시 요청하는데 Streamlit이 파일을 내주지 않는다.
    그래서 파일을 통째로 문자열에 담아 보낸다. (한 번 읽고 캐시)
    """
    import base64
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
    try:
        with open(path, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    except Exception:
        return ""


def _home_href():
    """
    로고를 누르면 첫 화면(키워드 조사 → 키워드 분석)으로 돌아간다.

    ⚠️ Streamlit은 탭을 코드로 바꿀 수가 없다. 대신 페이지를 다시 열면
    항상 첫 번째 탭과 첫 번째 하위 탭이 열린 상태로 시작한다.
    주소의 열쇠말(관리 탭)은 잃지 않도록 그대로 붙여준다.
    """
    try:
        qp = dict(st.query_params)
    except Exception:
        qp = {}
    bits = [f"{k}={v}" for k, v in qp.items() if isinstance(v, str)]
    return ("?" + "&".join(bits)) if bits else "./"


def masthead(title, subtitle="", meta=""):
    """
    화면 맨 위 한 줄 — 왼쪽에 이름, 오른쪽에 상태.

    ⚠️ 탭을 이 줄의 가운데에 올려야 하는데, Streamlit은 탭 막대 안에
    다른 것을 끼워 넣을 수가 없다. 그래서 이 칸의 높이를 0으로 만들고
    안의 것들을 띄워서, 바로 아래 오는 탭 막대와 같은 줄에 겹쳐 보이게 한다.
    (CSS의 .masthead / .mast-brand / .mast-meta 참고)

    subtitle은 더 이상 쓰지 않는다. 한 줄 막대에 설명까지 넣으면
    줄이 두꺼워져서 탭을 같은 줄에 올릴 수 없다.
    """
    parts = str(title).split()
    name = (f'{parts[0]}<b>{"".join(parts[1:])}</b>'
            if len(parts) > 1 else str(title))
    uri = _logo_uri()
    mark = (f'<img class="mast-logo" src="{uri}" alt="">' if uri
            else hunter_icon(24))
    st.markdown(f"""<div class="masthead">
<a class="mast-brand" href="{_home_href()}" target="_self">{mark}<span class="mast-name">{name}</span></a>
<div class="mast-meta">{meta}</div>
</div>""", unsafe_allow_html=True)


def kpi(label, value, sub=""):
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    st.markdown(f"""<div class="kpi">
<div class="kpi-label">{label}</div>
<div class="kpi-val">{value}</div>
{sub_html}
</div>""", unsafe_allow_html=True)


def chip(text, color):
    return f'<span class="chip" style="background:{color}">{text}</span>'


def grade_chip_html(grade):
    return chip(grade, GRADE_COLORS.get(grade, MUTED))


def gauge(title, score, scale_labels=("0", "50", "100"), color=None):
    """시그니처 요소: 기회/승산을 한눈에 읽는 가로 게이지."""
    score = max(0, min(100, int(score or 0)))
    if color is None:
        color = GOOD if score >= 70 else (WARN if score >= 40 else BAD)
    st.markdown(f"""<div class="gauge-wrap">
<div class="gauge-top">
<span class="gauge-title">{title}</span>
<span class="gauge-num">{score}</span>
</div>
<div class="gauge-track">
<div class="gauge-fill" style="width:{score}%;background:{color}"></div>
</div>
<div class="gauge-scale">
<span>{scale_labels[0]}</span><span>{scale_labels[1]}</span><span>{scale_labels[2]}</span>
</div>
</div>""", unsafe_allow_html=True)


def section(eyebrow, title):
    st.markdown(f"""<div class="eyebrow">{eyebrow}</div>
<div class="section-title">{title}</div>""", unsafe_allow_html=True)


def note(text, gold=False):
    cls = "note note-gold" if gold else "note"
    st.markdown(f'<div class="{cls}">{text}</div>', unsafe_allow_html=True)


# ============================================================
# 차트 — 전부 손으로 그린 SVG (외부 차트 라이브러리 없음)
# 계측기 컨셉이라 눈금, 기준선, 영역 구분을 직접 통제한다.
# ============================================================

import math


def _log(v):
    """0을 허용하는 로그 스케일. 검색량/문서수는 자릿수 차이가 커서 로그가 맞다."""
    return math.log10(max(v, 0) + 1)


def hunting_map(points, main=None, height=380, focus=None):
    """
    🏹 사냥 지도 — 이 제품의 시그니처 차트.

    가로축 검색량, 세로축 문서수. 대각선은 '문서수 ÷ 검색량 = 경쟁률'의 등고선이다.
    같은 대각선 위의 키워드는 경쟁률이 같고, 오른쪽 아래로 갈수록
    '찾는 사람은 많은데 쓰인 글은 적은' 사냥터가 된다.
    표로는 절대 보이지 않는 배치가 한눈에 들어온다.

    points: [{"keyword","search","docs"}], main: 강조할 중심 키워드 dict
    """
    data = [p for p in (points or []) if p.get("search", 0) > 0]
    if main and main.get("search", 0) > 0:
        data = [p for p in data if p["keyword"] != main["keyword"]] + [main]
    if not data:
        return

    W, H = 760, height
    L, R, T, B = 62, 22, 22, 46
    pw, ph = W - L - R, H - T - B

    xs = [_log(p["search"]) for p in data]
    ys = [_log(p.get("docs", 0)) for p in data]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    x0, x1 = math.floor(x0), math.ceil(max(x1, x0 + 1))
    y0, y1 = math.floor(y0), math.ceil(max(y1, y0 + 1))

    def px(v):
        return L + (_log(v) - x0) / (x1 - x0) * pw

    def py(v):
        return T + ph - (_log(v) - y0) / (y1 - y0) * ph

    parts = []

    steps = 28

    def band(k_lo, k_hi, fill, opacity):
        """경쟁률 k_lo ~ k_hi 사이의 띠를 칠한다 (로그 평면에서 대각 띠).
        k가 None이면 그쪽은 그래프 경계까지 채운다."""
        upper, lower = [], []
        for i in range(steps + 1):
            lx = x0 + (x1 - x0) * i / steps
            sx = L + (lx - x0) / (x1 - x0) * pw

            ly_hi = y1 if k_hi is None else max(y0, min(y1, lx + math.log10(k_hi)))
            ly_lo = y0 if k_lo is None else max(y0, min(y1, lx + math.log10(k_lo)))

            upper.append((sx, T + ph - (ly_hi - y0) / (y1 - y0) * ph))
            lower.append((sx, T + ph - (ly_lo - y0) / (y1 - y0) * ph))

        pts = upper + list(reversed(lower))
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        parts.append(f'<polygon points="{poly}" fill="{fill}" opacity="{opacity}"/>')

    # 구역 3단계 — 아래(문서 적음)부터 위로
    band(None, 0.1, GOLD, ".20")    # 당장 사냥
    band(0.1, 2.0, GOOD, ".11")     # 추천
    band(2.0, None, BAD, ".08")     # 비추천

    # 경계선 + 구역 이름
    for k, name, color in ((0.1, "당장 사냥 구역", GOLD), (2.0, "추천 구역", GOOD)):
        pts = []
        for i in range(steps + 1):
            lx = x0 + (x1 - x0) * i / steps
            sx = L + (lx - x0) / (x1 - x0) * pw
            ly = lx + math.log10(k)
            if ly < y0 or ly > y1:
                continue
            sy = T + ph - (ly - y0) / (y1 - y0) * ph
            pts.append(f"{sx:.1f},{sy:.1f}")
        if len(pts) > 1:
            parts.append(f'<polyline points="{" ".join(pts)}" fill="none" '
                         f'stroke="{color}" stroke-width="1.6" stroke-dasharray="6 4" opacity=".75"/>')

    # 구역 라벨을 모서리에 배치
    parts.append(f'<text x="{L + pw - 14}" y="{T + ph - 16}" text-anchor="end" '
                 f'font-size="13" font-weight="800" fill="{GOLD}">당장 사냥 구역</text>')
    parts.append(f'<text x="{L + pw - 14}" y="{T + ph - 34}" text-anchor="end" '
                 f'font-size="11.5" fill="{MUTED}">경쟁률 0.1 미만</text>')
    parts.append(f'<text x="{L + 14}" y="{T + 22}" font-size="13" '
                 f'font-weight="800" fill="{BAD}" opacity=".8">비추천 구역</text>')
    parts.append(f'<text x="{L + 14}" y="{T + 39}" font-size="11.5" fill="{MUTED}">경쟁률 2 이상</text>')

    # 축 눈금
    for i in range(int(x0), int(x1) + 1):
        sx = L + (i - x0) / (x1 - x0) * pw
        parts.append(f'<line x1="{sx:.1f}" y1="{T}" x2="{sx:.1f}" y2="{T + ph}" '
                     f'stroke="{LINE}" stroke-width="1" opacity=".7"/>')
        parts.append(f'<text x="{sx:.1f}" y="{T + ph + 18}" text-anchor="middle" '
                     f'font-size="10.5" fill="{MUTED}" font-family="IBM Plex Mono,monospace">'
                     f'{_si(10 ** i)}</text>')
    for i in range(int(y0), int(y1) + 1):
        sy = T + ph - (i - y0) / (y1 - y0) * ph
        parts.append(f'<line x1="{L}" y1="{sy:.1f}" x2="{L + pw}" y2="{sy:.1f}" '
                     f'stroke="{LINE}" stroke-width="1" opacity=".7"/>')
        parts.append(f'<text x="{L - 9}" y="{sy + 3.5:.1f}" text-anchor="end" '
                     f'font-size="10.5" fill="{MUTED}" font-family="IBM Plex Mono,monospace">'
                     f'{_si(10 ** i)}</text>')

    # 점 — <title>을 넣으면 마우스를 올렸을 때 브라우저가 툴팁을 띄운다
    for p in data:
        is_main = main and p["keyword"] == main["keyword"]
        s_, d_ = p["search"], p.get("docs", 0)
        ratio = d_ / s_ if s_ else 999
        if ratio < 0.1:
            color, zone_name = GOLD, "당장 사냥"
        elif ratio < 2:
            color, zone_name = GOOD, "추천"
        else:
            color, zone_name = BAD, "비추천"
        cx, cy = px(s_), py(d_)
        tip = (f'{p["keyword"]}\n검색량 {s_:,} · 문서수 {d_:,}\n'
               f'경쟁률 {ratio:.2f} · {zone_name} 구역')

        is_focus = focus and p["keyword"] == focus and not is_main
        if is_focus:
            # 4번: 목록에서 고른 키워드를 지도에서 바로 찾을 수 있게 강조한다.
            # (모바일에서는 점에 마우스를 올릴 수 없어 툴팁이 무용지물이다)
            parts.append(
                f'<g><title>{_esc(tip)}</title>'
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="16" fill="{GOLD}" opacity=".25"/>'
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="9" fill="{GOLD}" '
                f'stroke="{INK}" stroke-width="2.5"/></g>')
            parts.append(f'<text x="{cx:.1f}" y="{cy - 22:.1f}" text-anchor="middle" '
                         f'font-size="12.5" font-weight="800" fill="{INK}" '
                         f'paint-order="stroke" stroke="#fff" stroke-width="3.5">'
                         f'{_esc(p["keyword"])}</text>')
        elif is_main:
            parts.append(
                f'<g><title>{_esc(tip)}</title>'
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="14" fill="{DEEP}" opacity=".18"/>'
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="8" fill="{DEEP}" '
                f'stroke="#fff" stroke-width="2.5"/></g>')
            parts.append(f'<text x="{cx:.1f}" y="{cy - 21:.1f}" text-anchor="middle" '
                         f'font-size="12.5" font-weight="700" fill="{DEEP}" '
                         f'paint-order="stroke" stroke="#fff" stroke-width="3.5">'
                         f'{_esc(p["keyword"])}</text>')
        else:
            parts.append(
                f'<g class="pt"><title>{_esc(tip)}</title>'
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="10" fill="transparent"/>'
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5.5" fill="{color}" '
                f'opacity=".85" stroke="#fff" stroke-width="1.4"/></g>')

    # 축 이름 + 사냥터 라벨
    parts.append(f'<text x="{L + pw / 2:.0f}" y="{H - 8}" text-anchor="middle" '
                 f'font-size="11.5" font-weight="700" fill="{MUTED}">월 검색량 →</text>')
    parts.append(f'<text x="14" y="{T + ph / 2:.0f}" text-anchor="middle" font-size="11.5" '
                 f'font-weight="700" fill="{MUTED}" transform="rotate(-90 14 {T + ph / 2:.0f})">'
                 f'← 누적 문서수</text>')

    svg = (f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" '
           f'style="max-width:100%;height:auto">'
           f'<rect x="{L}" y="{T}" width="{pw}" height="{ph}" fill="{SURFACE}" '
           f'stroke="{LINE}" stroke-width="1.5" rx="8"/>' + "".join(parts) + '</svg>')
    st.markdown(f'<div class="chart-box">{svg}</div>', unsafe_allow_html=True)


def _si(v):
    """축 눈금을 짧게 (1000 → 1K)"""
    v = int(v)
    if v >= 1_000_000:
        return f"{v // 1_000_000}M"
    if v >= 1000:
        return f"{v // 1000}K"
    return str(v)


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def donut(segments, center_top="", center_bottom="", size=170):
    """
    도넛 차트. segments: [(라벨, 값, 색)]
    PC/모바일 검색 비중처럼 '구성비'를 보여줄 때 쓴다.
    """
    total = sum(v for _, v, _ in segments) or 1
    r, sw = size / 2 - 14, 20
    cx = cy = size / 2
    parts, angle = [], -90.0

    for label, value, color in segments:
        sweep = value / total * 360
        if sweep <= 0:
            continue
        a1, a2 = math.radians(angle), math.radians(angle + sweep)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        x2, y2 = cx + r * math.cos(a2), cy + r * math.sin(a2)
        large = 1 if sweep > 180 else 0
        if sweep >= 359.9:
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
                         f'stroke="{color}" stroke-width="{sw}"/>')
        else:
            parts.append(f'<path d="M {x1:.2f} {y1:.2f} A {r} {r} 0 {large} 1 {x2:.2f} {y2:.2f}" '
                         f'fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="butt"/>')
        angle += sweep

    parts.append(f'<text x="{cx}" y="{cy - 3}" text-anchor="middle" font-size="13" '
                 f'font-weight="700" fill="{INK}">{_esc(center_top)}</text>')
    parts.append(f'<text x="{cx}" y="{cy + 15}" text-anchor="middle" font-size="11.5" '
                 f'fill="{MUTED}" font-family="IBM Plex Mono,monospace">{_esc(center_bottom)}</text>')

    legend = "".join(
        f'<span class="lg"><i style="background:{c}"></i>{_esc(l)} '
        f'<b>{v / total * 100:.0f}%</b></span>'
        for l, v, c in segments if v > 0)

    svg = (f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
           f'xmlns="http://www.w3.org/2000/svg">' + "".join(parts) + '</svg>')
    st.markdown(f'<div class="chart-box donut-box">{svg}<div class="legend">{legend}</div></div>',
                unsafe_allow_html=True)


def bar_series(items, title="", height=150, accent=None, show_pct=False):
    """
    막대 시계열. items: [(라벨, 값)]
    show_pct=True 면 전체 대비 비율도 함께 표시한다.
    값이 0인 구간도 옅은 바닥선을 남겨서 '데이터가 빠진 것'처럼 보이지 않게 한다.
    """
    if not items:
        return
    accent = accent or DEEP
    W, H = 720, height
    T, B, L, R = 20, 34, 10, 10
    ph = H - T - B
    n = len(items)
    gap = 7
    bw = max(6, (W - L - R - gap * (n - 1)) / n)
    vals = [v for _, v in items]
    top = max(vals) or 1
    total = sum(vals) or 1

    parts = []
    for i, (label, v) in enumerate(items):
        x = L + i * (bw + gap)
        if v > 0:
            bh = max(3, v / top * ph)
            y = T + ph - bh
            opacity = .45 + .55 * (v / top)
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
                         f'rx="4" fill="{accent}" opacity="{opacity:.2f}"/>')
            cap = f"{v}" + (f" ({v / total * 100:.0f}%)" if show_pct else "")
            parts.append(f'<text x="{x + bw / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle" '
                         f'font-size="11.5" font-weight="700" fill="{INK}" '
                         f'font-family="IBM Plex Mono,monospace">{cap}</text>')
        else:
            # 값이 0이어도 자리를 표시해 데이터 누락처럼 보이지 않게
            parts.append(f'<rect x="{x:.1f}" y="{T + ph - 3:.1f}" width="{bw:.1f}" height="3" '
                         f'rx="1.5" fill="{LINE}"/>')
            parts.append(f'<text x="{x + bw / 2:.1f}" y="{T + ph - 8:.1f}" text-anchor="middle" '
                         f'font-size="10.5" fill="{MUTED}" '
                         f'font-family="IBM Plex Mono,monospace">0</text>')
        parts.append(f'<text x="{x + bw / 2:.1f}" y="{H - 10}" text-anchor="middle" '
                     f'font-size="10.5" fill="{MUTED}">{_esc(label)}</text>')

    parts.append(f'<line x1="{L}" y1="{T + ph:.1f}" x2="{W - R}" y2="{T + ph:.1f}" '
                 f'stroke="{LINE}" stroke-width="1.5"/>')
    svg = (f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" '
           f'style="max-width:100%;height:auto">' + "".join(parts) + '</svg>')
    head = f'<div class="chart-title">{_esc(title)}</div>' if title else ""
    st.markdown(f'<div class="chart-box">{head}{svg}</div>', unsafe_allow_html=True)


def scale_gauge(value, stops, title="", unit="", note="", height=118):
    """
    눈금 위에 현재 값이 어디쯤인지 표시하는 게이지.

    '시장 신선도'(최근 발행 ÷ 누적 문서)는 누적이 수백만이면 늘 0.00%가 나와
    지표 구실을 못했다. 대신 경쟁률처럼 '구간별 의미가 정해진 값'을
    눈금 위에 얹어 보여주는 편이 훨씬 잘 읽힌다.

    stops: [(경계값, 구간이름, 색)] — 경계값 오름차순
    """
    if value is None:
        return
    W, H = 720, height
    L, R, T = 16, 16, 44
    pw = W - L - R
    bar_y, bar_h = T, 16
    n = len(stops)

    parts, seg_w = [], pw / n
    cur_name, cur_color = stops[-1][1], stops[-1][2]
    for i, (bound, name, color) in enumerate(stops):
        x = L + i * seg_w
        r1 = "8" if i == 0 else "0"
        r2 = "8" if i == n - 1 else "0"
        parts.append(f'<path d="M {x + float(r1):.1f} {bar_y} h {seg_w - float(r1) - float(r2):.1f} '
                     f'a {r2} {r2} 0 0 1 {r2} {r2} v {bar_h - 2 * float(r2)} '
                     f'a {r2} {r2} 0 0 1 -{r2} {r2} h -{seg_w - float(r1) - float(r2):.1f} '
                     f'a {r1} {r1} 0 0 1 -{r1} -{r1} v -{bar_h - 2 * float(r1)} '
                     f'a {r1} {r1} 0 0 1 {r1} -{r1} z" fill="{color}" opacity=".82"/>')
        parts.append(f'<text x="{x + seg_w / 2:.1f}" y="{bar_y + bar_h + 17}" '
                     f'text-anchor="middle" font-size="11.5" font-weight="700" '
                     f'fill="{color}">{_esc(name)}</text>')
        if bound is not None:
            parts.append(f'<text x="{x + seg_w:.1f}" y="{bar_y - 7}" text-anchor="middle" '
                         f'font-size="10" fill="{MUTED}" '
                         f'font-family="IBM Plex Mono,monospace">{bound}</text>')

    # 값이 속한 구간 찾기 → 그 구간 안에서의 위치 계산
    idx = n - 1
    for i, (bound, name, color) in enumerate(stops):
        if bound is not None and value < bound:
            idx, cur_name, cur_color = i, name, color
            break
    lo = 0 if idx == 0 else stops[idx - 1][0]
    hi = stops[idx][0] if stops[idx][0] is not None else max(value, lo * 2 or 1)
    frac = 0.5 if hi == lo else min(1, max(0, (value - lo) / (hi - lo)))
    mx = L + idx * seg_w + frac * seg_w

    parts.append(f'<polygon points="{mx:.1f},{bar_y - 4} {mx - 6:.1f},{bar_y - 13} '
                 f'{mx + 6:.1f},{bar_y - 13}" fill="{INK}"/>')
    parts.append(f'<line x1="{mx:.1f}" y1="{bar_y - 2}" x2="{mx:.1f}" '
                 f'y2="{bar_y + bar_h + 2}" stroke="{INK}" stroke-width="2.5"/>')

    val_txt = f"{value:g}{unit}"
    parts.append(f'<text x="{L}" y="20" font-size="13" font-weight="700" fill="{INK}">'
                 f'{_esc(title)}</text>')
    parts.append(f'<text x="{W - R}" y="22" text-anchor="end" font-size="19" '
                 f'font-weight="700" fill="{cur_color}" '
                 f'font-family="IBM Plex Mono,monospace">{val_txt}</text>')
    parts.append(f'<text x="{W - R}" y="{H - 4}" text-anchor="end" font-size="11.5" '
                 f'fill="{MUTED}">{_esc(note)}</text>')

    svg = (f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" '
           f'style="max-width:100%;height:auto">' + "".join(parts) + '</svg>')
    st.markdown(f'<div class="chart-box">{svg}</div>', unsafe_allow_html=True)


def diagnosis_matrix(total_grade, recent_grade, label, note):
    """
    진단을 2×2 표로 보여준다.
    가로축 = 누적 문서가 많은가, 세로축 = 요즘도 쓰이는가.
    지금 키워드가 어느 칸에 있는지 색으로 칠해 한눈에 알 수 있게 한다.
    """
    saturated = total_grade in ("나쁨", "최악")
    busy = recent_grade in ("붐빔", "과열")

    cells = [
        (False, False, "비어 있는 자리", "글도 적고 요즘도 조용함", GOOD),
        (False, True, "지금 몰리는 중", "글은 적은데 요즘 많이 씀", WARN),
        (True, False, "오래된 글만 많음", "글은 많은데 요즘은 조용함", GOLD),
        (True, True, "이미 꽉 참", "글도 많고 요즘도 많이 씀", BAD),
    ]

    html = ['<div class="chart-box"><div class="chart-title">진단 · 지금 이 키워드의 자리</div>',
            '<div class="diag-grid">']
    for sat, bz, name, desc, color in cells:
        on = (sat == saturated and bz == busy)
        style = (f'background:{color};color:#fff;border-color:{color}'
                 if on else f'background:{SURFACE};color:{MUTED};border-color:{LINE}')
        mark = '<div class="diag-mark">지금 여기</div>' if on else ''
        html.append(f'<div class="diag-cell" style="{style}">{mark}'
                    f'<div class="diag-name">{name}</div>'
                    f'<div class="diag-desc">{desc}</div></div>')
    html.append('</div>')
    html.append('<div class="diag-axis"><span>← 누적 문서 적음 / 많음 →</span>'
                '<span>위: 요즘 조용함 · 아래: 요즘 활발함</span></div>')
    html.append(f'<div class="diag-note"><b>{_esc(label)}</b> — {_esc(note)}</div>')
    html.append('</div>')
    st.markdown("".join(html), unsafe_allow_html=True)


def rank_trend(points, height=200, title="순위 추이"):
    """
    📈 순위 꺾은선 — 추적기의 핵심 시각화.
    순위는 낮을수록 좋으므로 y축을 뒤집는다(1위가 맨 위).
    points: [(라벨, 순위 or None)]  None은 순위권 밖.
    """
    if not points:
        return
    ranked = [(i, r) for i, (_, r) in enumerate(points) if r is not None]
    if not ranked:
        st.markdown(f'<div class="chart-box"><div class="chart-title">{_esc(title)}</div>'
                    f'<div class="fresh-foot">아직 순위권(30위) 안에 든 기록이 없습니다.</div>'
                    f'</div>', unsafe_allow_html=True)
        return

    W, H = 720, height
    L, R, T, B = 44, 18, 20, 34
    pw, ph = W - L - R, H - T - B
    n = len(points)
    worst = max(r for _, r in ranked)
    best = min(r for _, r in ranked)
    lo, hi = max(1, best - 2), worst + 2

    def sx(i):
        return L + (pw if n == 1 else pw * i / (n - 1))

    def sy(r):
        return T + (r - lo) / (hi - lo) * ph      # 순위가 클수록 아래로

    parts = []
    for gr in (lo, (lo + hi) // 2, hi):
        y = sy(gr)
        parts.append(f'<line x1="{L}" y1="{y:.1f}" x2="{L + pw}" y2="{y:.1f}" '
                     f'stroke="{LINE}" stroke-width="1"/>')
        parts.append(f'<text x="{L - 8}" y="{y + 3.5:.1f}" text-anchor="end" font-size="10.5" '
                     f'fill="{MUTED}" font-family="IBM Plex Mono,monospace">{int(gr)}위</text>')

    # 상위 10위 구간을 초록으로 강조
    if lo <= 10 <= hi:
        y10 = sy(10)
        parts.insert(0, f'<rect x="{L}" y="{T}" width="{pw}" height="{max(0, y10 - T):.1f}" '
                        f'fill="{GOOD}" opacity=".08"/>')
        parts.append(f'<text x="{L + pw - 6}" y="{T + 13}" text-anchor="end" font-size="10.5" '
                     f'fill="{GOOD}" font-weight="700">상위 10위</text>')

    # 선 (순위권 밖 구간은 끊어서 그린다)
    seg = []
    for i, (_, r) in enumerate(points):
        if r is None:
            if len(seg) > 1:
                parts.append(f'<polyline points="{" ".join(seg)}" fill="none" '
                             f'stroke="{DEEP}" stroke-width="2.4" stroke-linejoin="round"/>')
            seg = []
        else:
            seg.append(f"{sx(i):.1f},{sy(r):.1f}")
    if len(seg) > 1:
        parts.append(f'<polyline points="{" ".join(seg)}" fill="none" '
                     f'stroke="{DEEP}" stroke-width="2.4" stroke-linejoin="round"/>')

    # 점 + 라벨
    step = max(1, n // 8)
    for i, (label, r) in enumerate(points):
        if r is not None:
            c = GOOD if r <= 10 else (WARN if r <= 20 else BAD)
            parts.append(f'<g><title>{_esc(label)} · {r}위</title>'
                         f'<circle cx="{sx(i):.1f}" cy="{sy(r):.1f}" r="4.5" fill="{c}" '
                         f'stroke="#fff" stroke-width="1.6"/></g>')
        if i % step == 0 or i == n - 1:
            parts.append(f'<text x="{sx(i):.1f}" y="{H - 10}" text-anchor="middle" '
                         f'font-size="10" fill="{MUTED}">{_esc(label)}</text>')

    # 마지막 순위 강조
    last_i, last_r = ranked[-1]
    parts.append(f'<circle cx="{sx(last_i):.1f}" cy="{sy(last_r):.1f}" r="8" '
                 f'fill="{GOLD}" opacity=".28"/>')
    parts.append(f'<text x="{sx(last_i):.1f}" y="{sy(last_r) - 13:.1f}" text-anchor="middle" '
                 f'font-size="12" font-weight="800" fill="{DEEP}" paint-order="stroke" '
                 f'stroke="#fff" stroke-width="3">{last_r}위</text>')

    svg = (f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" '
           f'style="max-width:100%;height:auto">' + "".join(parts) + '</svg>')
    st.markdown(f'<div class="chart-box"><div class="chart-title">{_esc(title)}</div>{svg}</div>',
                unsafe_allow_html=True)


def serp_row(item, my_blog_id=""):
    """
    상위노출 글 한 줄 — 순위, 제목, 나이.
    ⚠️ 남의 블로그 이름은 표시하지 않는다. 어떤 글이 상위에 있는지가 중요하지,
    누가 썼는지를 노출할 이유는 없다. 내 글일 때만 따로 표시한다.
    """
    age = item.get("age_days")
    if age is None:
        age_txt, age_color = "—", MUTED
    elif age <= 90:
        age_txt, age_color = f"{age}일 전", BAD
    elif age <= 365:
        age_txt, age_color = f"{age // 30}개월 전", WARN
    else:
        age_txt, age_color = f"{age // 365}년 전", GOOD

    mine = my_blog_id and item.get("blog_id", "").lower() == my_blog_id.lower()
    bg = "background:rgba(200,150,62,.15);" if mine else ""
    badge = ' <span class="mine-tag">내 글</span>' if mine else ""
    r = item["rank"]
    rank_color = GOOD if r <= 3 else (DEEP if r <= 10 else MUTED)

    return (f'<div class="serp-row" style="{bg}">'
            f'<span class="serp-rank" style="color:{rank_color}">{r}</span>'
            f'<span class="serp-title">{_esc(item.get("title", ""))}{badge}</span>'
            f'<span class="serp-age" style="color:{age_color}">{age_txt}</span>'
            f'</div>')


def serp_list(items, my_blog_id="", limit=10):
    rows = "".join(serp_row(i, my_blog_id) for i in items[:limit])
    st.markdown(
        f'<div class="chart-box serp-box">'
        f'<div class="serp-row serp-head"><span class="serp-rank">순위</span>'
        f'<span class="serp-title">제목</span>'
        f'<span class="serp-age">발행</span></div>{rows}</div>',
        unsafe_allow_html=True)


VERDICT_STYLE = {
    "쓰세요": (GOOD, "쓰세요"),
    "조건부": (WARN, "조건부"),
    "피하세요": (BAD, "피하세요"),
}


def brief_card(data, title="AI 판단"):
    """
    AI 브리핑 카드.
    숫자를 늘어놓는 대신 '그래서 어떻게 하라'는 결론을 앞세운다.
    """
    if not data:
        return
    verdict = data.get("verdict", "조건부")
    color, label = VERDICT_STYLE.get(verdict, (WARN, verdict))

    reasons = "".join(
        f'<li>{_esc(r)}</li>' for r in (data.get("reasons") or []))
    action = data.get("action", "")
    watch = data.get("watch_out", "")

    html = [f'<div class="brief-box" style="border-color:{color}">']
    html.append(f'<div class="brief-top">'
                f'<span class="brief-tag" style="background:{color}">{_esc(label)}</span>'
                f'<span class="brief-title">{_esc(title)}</span></div>')
    html.append(f'<div class="brief-head">{_esc(data.get("headline", ""))}</div>')
    if reasons:
        html.append(f'<ul class="brief-reasons">{reasons}</ul>')
    if action:
        html.append(f'<div class="brief-action"><b>이렇게 하세요</b><br>{_esc(action)}</div>')
    if watch:
        html.append(f'<div class="brief-watch">주의 · {_esc(watch)}</div>')
    html.append('</div>')
    st.markdown("".join(html), unsafe_allow_html=True)


def tracked_cards(items, key_prefix="tc"):
    """
    추적 중인 키워드를 박스로 늘어놓아 한눈에 들어오게 한다.
    순위만 보면 실속을 알 수 없어서, 검색량 추세와 예상 방문자를 함께 보여준다.
    반환: (중단, 자세히, 변경) 요청 키워드 — 없으면 각각 None
    """
    if not items:
        return None, None, None

    stopped, detail, flipped = None, None, None
    # ⚠️ 5개씩 놓으면 칸이 좁아 '자세히' 글자가 세로로 쪼개진다.
    cols_per_row = 4

    # ⚠️ st.columns(len(chunk))로 만들면 마지막 줄의 칸 수가 달라져서
    # 카드 폭이 제각각이 된다. 항상 같은 수의 칸을 만들고 남는 칸은 비워둔다.
    for row_start in range(0, len(items), cols_per_row):
        chunk = items[row_start:row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for idx in range(cols_per_row):
            with cols[idx]:
                if idx >= len(chunk):
                    continue          # 빈 칸은 아무것도 그리지 않는다
                it = chunk[idx]
                _one_track_card(it)
                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button("자세히", key=f"{key_prefix}_view_{it['keyword']}",
                                 use_container_width=True):
                        detail = it["keyword"]
                with b2:
                    if st.button("중단", key=f"{key_prefix}_stop_{it['keyword']}",
                                 use_container_width=True):
                        stopped = it["keyword"]
                with b3:
                    # 글을 쓴 뒤 '내가 쓴 키워드'로, 반대로도 되돌린다.
                    if st.button(
                            "변경", key=f"{key_prefix}_flip_{it['keyword']}",
                            use_container_width=True,
                            help=("지켜보는 중으로 되돌립니다"
                                  if it.get("has_post")
                                  else "내가 쓴 키워드로 바꿉니다")):
                        flipped = it["keyword"]
    return stopped, detail, flipped


def _one_track_card(it):
    """
    추적 카드. 두 종류를 다르게 그린다.

    · 글을 쓴 키워드  → 순위를 크게. 실제로 오르내리는 걸 봐야 하니까
    · 지켜보는 키워드 → 검색량 추세를 크게. 순위는 잴 대상이 아직 없으니
      '순위 밖'이라고 크게 띄우면 문제가 생긴 것처럼 보인다
    """
    mine = bool(it.get("has_post"))
    cls = "track-card mine" if mine else "track-card watching"

    tag = ('<span class="tc-tag">내가 쓴 키워드</span>' if mine
           else '<span class="tc-tag watch">지켜보는 중</span>')

    cp = it.get("change_pct")
    since = it.get("since")
    if cp is None:
        trend_html = '<span class="tc-flat">추세 계산 중</span>'
    elif cp >= 10:
        trend_html = f'<span class="tc-up">검색 ↑ {cp:+.0f}%</span>'
    elif cp <= -10:
        trend_html = f'<span class="tc-down">검색 ↓ {cp:+.0f}%</span>'
    else:
        trend_html = f'<span class="tc-flat">검색 {cp:+.0f}%</span>'
    since_html = (f'<div class="tc-sub tc-since">{since} 최초 추적일부터</div>'
                  if since and cp is not None else "")

    # 등록 이후 글이 얼마나 늘었는지 — 남들이 몰려들었는지가 여기서 드러난다
    cmp_ = it.get("compare") or {}
    dp = cmp_.get("docs_pct")
    if dp is None:
        docs_html = ""
    elif dp >= 10:
        docs_html = f'<div class="tc-sub"><span class="tc-down">글 ↑ {dp:+.0f}%</span></div>'
    elif dp <= -10:
        docs_html = f'<div class="tc-sub"><span class="tc-up">글 ↓ {dp:+.0f}%</span></div>'
    else:
        docs_html = f'<div class="tc-sub tc-flat">글 {dp:+.0f}%</div>'

    label = it.get("opp_label") or it.get("grade", "정보없음")
    lcolor = GRADE_COLORS.get(label, MUTED)
    meta = (f'<div class="tc-meta">'
            f'<span class="tc-pill" style="background:{lcolor}">{_esc(label)}</span>'
            f'<span class="tc-rec">기록 {it.get("records", 0)}회</span></div>')

    if mine:
        # --- 글을 쓴 키워드: 순위가 주인공 -----------------
        rank = it.get("rank")
        chg = it.get("change")
        if rank is None:
            main_html = ('<div class="tc-rank" style="color:#C4553D">순위 밖</div>'
                         '<div class="tc-chg tc-flat">아직 100위 안에 없음</div>')
        else:
            color = GOOD if rank <= 10 else (WARN if rank <= 20 else BAD)
            if chg is None:
                chg_html = '<span class="tc-flat">기록 쌓는 중</span>'
            elif chg > 0:
                chg_html = f'<span class="tc-up">▲ {chg}계단</span>'
            elif chg < 0:
                chg_html = f'<span class="tc-down">▼ {abs(chg)}계단</span>'
            else:
                chg_html = '<span class="tc-flat">변화 없음</span>'
            main_html = (f'<div class="tc-rank" style="color:{color}">{rank}위</div>'
                         f'<div class="tc-chg">{chg_html}</div>')

        # 예상 방문자 — 왜 없는지까지 알려준다.
        # 그냥 '유입 미미'라고만 하면 뭐가 문제인지 알 수 없다.
        visits = it.get("visits")
        if visits:
            sub = f'<div class="tc-sub tc-visit">월 <b>{visits:,}</b>명 예상</div>'
        elif it.get("rank"):
            sub = '<div class="tc-sub tc-flat">방문자 거의 없음</div>'
        else:
            sub = '<div class="tc-sub tc-flat">내 글 상위노출 없음</div>' 
        # 지켜보는 카드와 줄 수를 맞춘다 (카드 높이가 들쭉날쭉해지지 않게)
        body = (main_html + sub
                + f'<div class="tc-sub">{trend_html}</div>'
                + docs_html + since_html)
    else:
        # --- 지켜보는 키워드: 검색량 추세가 주인공 ---------
        search = it.get("search")
        big = (f'<div class="tc-rank" style="color:{DEEP}">'
               f'{_compact(search)}</div>' if search
               else '<div class="tc-rank tc-flat">—</div>')
        body = (big
                + '<div class="tc-chg tc-flat">월 검색량</div>'
                + f'<div class="tc-sub">{trend_html}</div>'
                + docs_html + since_html)

    st.markdown(
        f'<div class="{cls}">'
        f'<div class="tc-head">{tag}</div>'
        f'<div class="tc-kw">{_esc(it["keyword"])}</div>'
        f'{body}{meta}</div>', unsafe_allow_html=True)


def _compact(v):
    """카드 안에 들어갈 만큼 숫자를 줄인다."""
    if not v:
        return "—"
    v = int(v)
    if v >= 100_000_000:
        return f"{v / 100_000_000:.1f}억"
    if v >= 10_000:
        return f"{v / 10_000:.1f}만"
    return f"{v:,}"


def score_breakdown(breakdown, total_score, title="기회 점수 구성"):
    """
    점수가 어떤 축에서 나왔는지 펼쳐 보여준다.
    종합 점수만 보면 '왜 이 점수인지' 알 수 없어서 신뢰가 안 간다.
    """
    if not breakdown:
        return
    rows = []
    for name, (val, label) in breakdown.items():
        if val is None:
            rows.append(
                f'<div class="sb-row"><span class="sb-name">{_esc(name)}</span>'
                f'<div class="sb-track"><div class="sb-fill" '
                f'style="width:0%;background:{LINE}"></div></div>'
                f'<span class="sb-val sb-none">{_esc(label)}</span></div>')
            continue
        color = GOOD if val >= 70 else (WARN if val >= 40 else BAD)
        rows.append(
            f'<div class="sb-row"><span class="sb-name">{_esc(name)}</span>'
            f'<div class="sb-track"><div class="sb-fill" '
            f'style="width:{val}%;background:{color}"></div></div>'
            f'<span class="sb-val" style="color:{color}">{_esc(label)}</span></div>')

    st.markdown(
        f'<div class="chart-box">'
        f'<div class="sb-top"><span class="chart-title">{_esc(title)}</span>'
        f'<span class="sb-total">{total_score}</span></div>'
        f'{"".join(rows)}</div>', unsafe_allow_html=True)


SINCE_COLORS = {
    "지금이 기회": GOOD, "같이 커지는 중": GOOD,
    "경쟁 붙는 중": WARN, "큰 변화 없음": MUTED, "비교 준비 중": MUTED,
    "비교 어려움": MUTED,
    "불리해짐": BAD, "빠져나올 때": BAD, "식는 중": BAD,
}


def since_compare(data, since_label=""):
    """
    등록 당시와 지금을 나란히 보여준다.

    검색량만으로는 '남들이 몰려들었는지'를 알 수 없다.
    글 수를 함께 놓아야 '등록할 땐 비어 있었는데 그새 붐볐다'가 드러난다.
    """
    if not data:
        return
    color = SINCE_COLORS.get(data["verdict"], MUTED)

    def row(label, a, b):
        """숫자만 나란히. 얼마나 변했는지는 아래 두 줄에서 따로 말한다."""
        return (f'<div class="sc-row">'
                f'<span class="sc-label">{_esc(label)}</span>'
                f'<span class="sc-from">{a:,}</span>'
                f'<span class="sc-arrow">→</span>'
                f'<span class="sc-to">{b:,}</span>'
                f'</div>')

    def delta(label, a, b, pct, unit, invert=False):
        """
        '추적 후 찾는 사람 100명 증가 / +3%' 한 줄.
        invert=True면 늘어나는 게 나쁜 항목(글 수)이라 색을 뒤집는다.
        """
        if a is None or b is None:
            return ""
        diff = b - a
        if diff > 0:
            word, c = "증가", (BAD if invert else GOOD)
        elif diff < 0:
            word, c = "감소", (GOOD if invert else BAD)
        else:
            word, c = "변화 없음", MUTED
        amt = f"{abs(diff):,}{unit} {word}" if diff else word
        pct_txt = f" / {pct:+.0f}%" if pct is not None else ""
        return (f'<div class="sc-delta">추적 후 {_esc(label)} '
                f'<b style="color:{c}">{amt}</b>'
                f'<span style="color:{c}">{pct_txt}</span></div>')

    added_txt = (
        delta("찾는 사람", data.get("search_from"), data.get("search_to"),
              data.get("search_pct"), "명")
        + delta("쓰인 글", data.get("docs_from"), data.get("docs_to"),
                data.get("docs_pct"), "편", invert=True))

    st.markdown(
        f'<div class="chart-box">'
        f'<div class="sc-top"><span class="chart-title">등록 당시와 비교</span>'
        f'<span class="sc-verdict" style="background:{color}">'
        f'{_esc(data["verdict"])}</span></div>'
        f'<div class="sc-since">{_esc(since_label)}</div>'
        + row("찾는 사람", data["search_from"], data["search_to"])
        + row("쓰인 글", data["docs_from"], data["docs_to"])
        + added_txt
        + f'<div class="sc-note">{_esc(data["note"])}</div>'
        f'</div>', unsafe_allow_html=True)


def _short_num(v):
    """큰 수를 짧게. 막대 옆 좁은 자리에 그대로 쓰면 잘린다."""
    if v is None:
        return "—"
    v = int(v)
    if v >= 100_000_000:
        return f"{v / 100_000_000:.1f}억"
    if v >= 10_000:
        return f"{v / 10_000:.1f}만"
    return f"{v:,}"


def hunt_rank(items, main=None, limit=10):
    """
    🏹 사냥 순위 — 노려볼 만한 순서대로 가로 막대로 세운다.

    ⚠️ 왜 산점도에서 바꿨나
    좌표에 점을 흩뿌리면 '어디가 좋은지'를 눈으로 읽어내야 한다.
    모바일에서는 점이 뭉쳐서 더 어렵다.
    막대는 길이만 비교하면 되니 판단이 즉시 된다.

    items: [{"keyword","search","docs","score","label"}]
    """
    if not items:
        return

    rows = sorted(items, key=lambda x: -x.get("score", 0))[:limit]
    top = max((r.get("score", 0) for r in rows), default=1) or 1

    parts = []
    for rank, it in enumerate(rows, 1):
        score = it.get("score", 0)
        label = it.get("label", "")
        # 1~3위는 눈에 띄는 색을 쓰고, 그 아래는 점수대로 정한다.
        if rank <= 3:
            color = (GOLD, "#7B9E8B", "#A8A093")[rank - 1]
        else:
            color = GRADE_COLORS.get(label)
            if not color:
                color = (GOOD if score >= 70 else
                         (GOLD if score >= 55 else
                          (WARN if score >= 40 else BAD)))
        width = max(6, int(score / top * 100))

        search = it.get("search") or 0
        docs = it.get("docs")
        # 큰 수는 줄여서 표시한다. 그대로 두면 오른쪽에서 잘린다.
        search_txt = _short_num(search)
        docs_txt = _short_num(docs) if docs is not None else "—"
        tip = (f"{it['keyword']} · {label} · "
               f"검색 {search:,} · 글 {docs:,}" if docs is not None
               else f"{it['keyword']} · {label} · 검색 {search:,}")

        parts.append(
            f'<div class="hb-row" title="{_esc(tip)}">'
            f'<span class="hb-kw">{_esc(it["keyword"])}</span>'
            f'<div class="hb-track">'
            f'<div class="hb-fill" style="width:{width}%;'
            f'background:linear-gradient(90deg,{color}B3,{color})">'
            f'<span class="hb-score">{score}</span></div>'
            f'</div>'
            f'<span class="hb-sub">검색 {search_txt} · 글 {docs_txt}</span>'
            f'</div>')

    head = ""
    if main:
        ms = main.get("search") or 0
        md = main.get("docs")
        sub = f"검색 {ms:,}" + (f" · 글 {md:,}" if md is not None else "")
        head = (f'<div class="hb-main">'
                f'<span class="hb-main-label">기준</span>'
                f'<b>{_esc(main["keyword"])}</b>'
                f'<span class="hb-main-sub">{sub}</span></div>')

    st.markdown(f'<div class="chart-box">{head}{"".join(parts)}</div>',
                unsafe_allow_html=True)
