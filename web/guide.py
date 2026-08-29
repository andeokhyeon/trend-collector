# -*- coding: utf-8 -*-
"""이용 가이드 — 모든 메뉴를 한 화면에서 예시와 함께. (2026-08-29)"""
from uihtml import ui, render


def _step(n, title, body):
    return (f'<div class="gd-step"><span class="gd-n">{n}</span>'
            f'<div><b>{title}</b><p>{body}</p></div></div>')


def _menu(icon_label, title, path, what, how, tip=""):
    tip_html = f'<div class="gd-tip">{tip}</div>' if tip else ""
    return (f'<div class="box gd-card">'
            f'<div class="gd-head"><span class="gd-badge">{icon_label}</span>'
            f'<b>{title}</b><code class="gd-path">{path}</code></div>'
            f'<p class="gd-what">{what}</p>'
            f'<div class="gd-how">{how}</div>{tip_html}</div>')


def build(logged_in=False):
    out = [render(ui.section, "이용 가이드", "3분이면 전부 읽습니다")]
    out.append(render(ui.pitch, "검색량만 보면",
                      "경쟁을 알 수 없습니다",
                      "키워드 헌터는 검색량·경쟁·문서수·추세를 한 번에 재서 "
                      "<b>지금 써도 되는 키워드인지</b>를 판정해주는 도구입니다."))

    # 시작 3단계
    out.append('<div class="box">')
    out.append(render(ui.section, "시작하기", "가입부터 첫 조회까지"))
    out.append('<div class="gd-steps">')
    out.append(_step(1, "카카오/구글로 시작",
                     "버튼 하나로 가입까지 끝납니다. 가입하면 무료 조회 3회를 드립니다."))
    out.append(_step(2, "내 블로그 등록 (선택)",
                     "마이페이지에서 블로그 주소를 한 번 등록하면, 모든 화면에서 "
                     "내 글이 <b>금색</b>으로 표시되고 순위 추적도 됩니다."))
    out.append(_step(3, "키워드 조회",
                     "첫 화면 검색창에 키워드를 넣으면 진단이 나옵니다. "
                     "조회 1회에 크레딧 1개 — <b>같은 키워드는 그날 무료</b>입니다."))
    out.append('</div></div>')

    # 메뉴별 설명
    out.append(render(ui.section, "메뉴 안내", "화면별로 무엇을 보는 곳인지"))
    out.append(_menu("조사", "키워드 분석", "키워드 조사 › 키워드 분석",
                     "키워드 하나를 넣으면 <b>월 검색량·경쟁률·기회 점수·추세</b>를 "
                     "한 화면에 진단합니다.",
                     "예) <code>제습기 추천</code>을 조회하면 — 검색량 등급, 이미 쓰인 글 수, "
                     "1년 추이, 그리고 <b>노려볼 만한 연관 키워드</b> 순위까지 나옵니다.",
                     "CSV 버튼으로 연관 키워드 전체를 내려받을 수 있습니다."))
    out.append(_menu("조사", "상위노출 해부", "키워드 조사 › 상위노출 해부",
                     "그 키워드로 <b>1등 한 글들이 어떻게 생겼는지</b> 보여줍니다.",
                     "상위 10개의 제목·발행 시점을 보고, 상위권이 전부 옛날 글이면 "
                     "지금 밀어낼 수 있다는 신호입니다. 내 블로그 글은 금색으로 표시됩니다."))
    out.append(_menu("조사", "글감 만들기", "키워드 조사 › 글감 만들기",
                     "상위권 제목에서 <b>통하는 형식</b>과 <b>실제 검색되는 세부 주제</b>만 "
                     "뽑아줍니다. 남의 제목을 베끼는 게 아니라 재료를 얻는 곳입니다.",
                     "제목 길이·흔한 형식(숫자형/후기형/정리형) 비율과 글 뼈대 후보가 나옵니다."))
    out.append(_menu("추적", "추적기", "추적기",
                     "키워드를 저장해두면 <b>검색량·문서수·내 글 순위 변화</b>를 "
                     "자동으로 기록합니다.",
                     "'이 키워드로 이미 글을 썼습니다'에 체크하면 내 글 순위까지 추적합니다. "
                     "카드의 <b>자세히</b>를 누르면 추이 그래프가 열립니다.",
                     "기록은 수집기가 돌 때마다 쌓이며, 변화 비교는 최소 하루가 지나야 "
                     "의미가 있습니다."))
    out.append(_menu("진단", "내 블로그", "내 블로그",
                     "등록한 블로그의 <b>발행 리듬·요일 패턴·최근 글</b>을 진단합니다.",
                     "주당 발행 수, 글 사이 간격, 골든타임 대비 내 발행 시각을 비교해줍니다."))
    out.append(_menu("발굴", "구글 트렌드 · 골든타임 · 주간 캘린더 · 뉴스", "키워드 발굴",
                     "키워드를 직접 넣지 않아도, 수집기가 모아온 "
                     "<b>지금 뜨는 재료</b>를 보여주는 곳입니다.",
                     "구글 트렌드 = 지금 검색되는 것 · 골든타임 = 뜨는데 아직 안 붐비는 것 · "
                     "주간 캘린더 = 미리 써두면 유리한 앞으로 4주 · 뉴스 = 많이 읽히는 기사.",
                     "표의 첫 열은 고정이라, 옆으로 밀면 나머지 지표가 보입니다."))
    out.append(_menu("계정", "마이페이지", "마이페이지",
                     "크레딧·플랜·블로그 주소·로그아웃을 관리합니다.",
                     "블로그 주소는 여기서 한 번 등록하면 계정에 저장되어 "
                     "어느 기기에서든 유지됩니다."))

    # 크레딧 규칙
    out.append('<div class="box">')
    out.append(render(ui.section, "크레딧", "요금이 굴러가는 규칙"))
    out.append(render(ui.note,
                      "키워드 조회 1회 = 크레딧 1개 · <b>같은 키워드는 그날 다시 봐도 "
                      "무료</b> (분석·상위노출·글감 어디서 봐도 하루 1개만) · "
                      "가입하면 무료 3회 · 충전(월결제)은 준비 중입니다."))
    out.append('</div>')

    if not logged_in:
        out.append(render(ui.pitch, "준비되셨으면",
                          "지금 시작해보세요",
                          '<a href="/">첫 화면에서 카카오/구글로 3초면 됩니다 →</a>'))
    return "".join(out)
