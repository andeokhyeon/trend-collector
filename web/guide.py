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
                      "돈이 되는지 알 수 없습니다",
                      "키워드 헌터는 검색량·경쟁·문서수·추세에 "
                      "<b>광고주가 거는 금액</b>까지 함께 재서, 지금 써도 되는 "
                      "자리인지를 판정해주는 도구입니다."))

    # 시작 3단계
    out.append('<div class="box">')
    out.append(render(ui.section, "시작하기", "가입부터 첫 조회까지"))
    out.append('<div class="gd-steps">')
    out.append(_step(1, "카카오/구글로 시작",
                     "버튼 하나로 가입까지 끝납니다. 가입하면 무료 조회 3회를 드립니다."))
    out.append(_step(2, "내 블로그 등록 (선택)",
                     "오른쪽 위 내 이름 → 블로그 주소를 한 번 등록하면, 모든 화면에서 "
                     "내 글이 눈에 띄게 표시되고 순위 추적도 됩니다."))
    out.append(_step(3, "키워드 검사",
                     "첫 화면 검색창에 키워드를 넣으면 진단이 나옵니다. "
                     "쓸 게 없으면 <b>키워드 찾기</b>에서 후보부터 골라도 됩니다. "
                     "조회 1회에 크레딧 1개 — <b>같은 키워드는 그날 무료</b>입니다."))
    out.append('</div></div>')

    # 메뉴별 설명 — 2026-09-22 탭 구조 개편에 맞춰 다시 씀
    out.append(render(ui.section, "화면 세 개", "쓰는 순서대로 놓았습니다"))
    out.append(_menu("1", "키워드 검사", "내가 키워드를 넣는다",
                     "생각해둔 키워드가 있을 때 오는 곳입니다. 하나를 넣으면 "
                     "<b>검색량·경쟁률·문서수·추세</b>를 재서 "
                     "<b>지금 써도 되는 자리인지</b> 판정합니다.",
                     "안에 셋이 있습니다 — <b>진단</b>은 그 키워드의 종합 성적, "
                     "<b>상위노출 해부</b>는 1등 한 글들이 어떻게 생겼는지, "
                     "<b>글감 만들기</b>는 통하는 제목 형식과 글 뼈대입니다.",
                     "조회 1회에 크레딧 1개 · 같은 키워드는 그날 다시 봐도 무료입니다."))
    out.append(_menu("2", "키워드 찾기", "시스템이 후보를 준다",
                     "쓸 게 마땅히 없을 때 오는 곳입니다. 수집기가 모아둔 재료에서 "
                     "<b>지금 뜨는 것</b>과 <b>앞으로 뜰 것</b>을 골라 보여줍니다.",
                     "<b>골든타임</b> = 뜨는데 아직 안 붐비는 것 · "
                     "<b>주간 캘린더</b> = 미리 써두면 유리한 앞으로 4주 · "
                     "<b>구글 트렌드</b> = 지금 검색되는 것 · "
                     "<b>뉴스</b> = 많이 읽히는 기사.",
                     "여기서 목록을 보는 것만으로는 크레딧이 들지 않습니다. "
                     "눌러서 검사할 때만 씁니다."))
    out.append(_menu("3", "내 블로그", "내 것을 지켜본다",
                     "이미 손을 댄 키워드와 내 블로그 상태를 보는 곳입니다.",
                     "<b>순위 추적</b>은 저장해둔 키워드의 검색량·문서수·내 글 순위가 "
                     "매일 자동으로 기록되는 곳입니다. 카드의 '자세히'를 누르면 "
                     "추이가 열립니다. <b>발행 진단</b>은 내 블로그의 발행 리듬·"
                     "요일 패턴·최근 글을 봅니다.",
                     "변화 비교는 최소 하루가 지나야 의미가 있습니다. "
                     "마이페이지에서 블로그 주소를 한 번 등록해두면 모든 화면에서 "
                     "내 글이 표시됩니다."))
    out.append(render(ui.note,
                      "계정 관련(크레딧·플랜·블로그 주소·로그아웃)은 탭이 아니라 "
                      "<b>오른쪽 위 내 이름</b>을 누르면 나옵니다. "
                      "휴대폰에서는 아래쪽 <b>내 정보</b>입니다."))

    # 크레딧 규칙
    out.append('<div class="box">')
    out.append(render(ui.section, "크레딧", "요금이 굴러가는 규칙"))
    out.append(render(ui.note,
                      "키워드 조회 1회 = 크레딧 1개 · <b>같은 키워드는 그날 다시 봐도 "
                      "무료</b> (분석·상위노출·글감 어디서 봐도 하루 1개만) · "
                      "가입하면 무료 3회 · 플랜별 차이는 "
                      '<a href="/pricing">요금 안내</a>에서 볼 수 있습니다.'))
    out.append('</div>')

    if not logged_in:
        out.append(render(ui.pitch, "준비되셨으면",
                          "지금 시작해보세요",
                          '<a href="/">첫 화면에서 카카오/구글로 3초면 됩니다 →</a>'))
    return "".join(out)
