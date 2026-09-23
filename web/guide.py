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
    out.append(render(ui.pitch, "클릭 한 번에",
                      "얼마인지부터 봅니다",
                      "키워드 헌터는 검색량과 추세에 <b>광고주가 거는 금액</b>까지 "
                      "함께 재서, 이 키워드가 돈 되는 자리인지를 판정해주는 도구입니다."))

    # 시작 3단계
    out.append('<div class="box">')
    out.append(render(ui.section, "시작하기", "가입부터 첫 조회까지"))
    out.append('<div class="gd-steps">')
    out.append(_step(1, "카카오/구글로 시작",
                     "버튼 하나로 가입까지 끝납니다. 가입하면 무료 조회 3회를 드립니다."))
    out.append(_step(2, "내 블로그 등록 (선택)",
                     "오른쪽 위 내 이름 → 블로그 주소를 한 번 등록하면 "
                     "<b>발행 진단</b>에서 내 발행 리듬·요일 패턴을 봅니다."))
    out.append(_step(3, "키워드 검사",
                     "첫 화면 검색창에 키워드를 넣으면 진단이 나옵니다. "
                     "쓸 게 없으면 <b>키워드 찾기</b>에서 후보부터 골라도 됩니다. "
                     "조회 1회에 크레딧 1개 — <b>같은 키워드는 그날 무료</b>입니다."))
    out.append('</div></div>')

    # 메뉴별 설명 — 2026-09-22 탭 구조 개편에 맞춰 다시 씀
    out.append(render(ui.section, "화면 세 개", "쓰는 순서대로 놓았습니다"))
    out.append(_menu("1", "키워드 검사", "내가 키워드를 넣는다",
                     "생각해둔 키워드가 있을 때 오는 곳입니다. 하나를 넣으면 "
                     "<b>클릭단가·월 검색량·모바일 비율·성수기</b>를 재서 "
                     "<b>돈 되는 자리인지</b> 한 마디로 판정합니다.",
                     "아래로 내리면 1년 검색 추이, 그리고 <b>연관 키워드를 단가 순</b>으로 "
                     "세운 표가 나옵니다. 같은 주제 안에서 더 비싼 말을 찾는 데 씁니다.",
                     "조회 1회에 크레딧 1개 · 같은 키워드는 그날 다시 봐도 무료입니다."))
    out.append(_menu("2", "키워드 찾기", "시스템이 후보를 준다",
                     "쓸 게 마땅히 없을 때 오는 곳입니다. 매일 모아둔 검색어 중 "
                     "<b>광고주가 돈을 거는 것</b>을 골라 보여줍니다.",
                     "<b>돈 되는 키워드</b> = 전체 중 단가 높은 순 · "
                     "<b>골든타임</b> = 오늘 뜬 것 중 단가 붙는 것 · "
                     "<b>주간 캘린더</b> = 미리 써두면 유리한 앞으로 4주 · "
                     "<b>구글 트렌드</b> = 지금 검색되는 것.",
                     "여기서 목록을 보는 것만으로는 크레딧이 들지 않습니다. "
                     "눌러서 검사할 때만 씁니다."))
    out.append(_menu("3", "내 블로그", "내 것을 지켜본다",
                     "찍어둔 키워드와 내 블로그 상태를 보는 곳입니다.",
                     "<b>관심 키워드</b>는 담아둔 키워드의 검색량이 매일 기록되고, "
                     "열 때마다 지금 단가와 판정이 함께 나옵니다. "
                     "<b>발행 진단</b>은 내 블로그의 발행 리듬·요일 패턴·최근 글을 봅니다.",
                     "검색량 추세는 기록이 3회 이상 쌓이면 나옵니다."))
    out.append(render(ui.tip,
                      "계정·크레딧·플랜은 <b>오른쪽 위 내 이름</b>에서 "
                      "(휴대폰은 아래쪽 <b>내 정보</b>)."))

    # 크레딧 규칙
    out.append('<div class="box">')
    out.append(render(ui.section, "크레딧", "요금이 굴러가는 규칙"))
    out.append(render(ui.tip,
                      "조회 1회 = 크레딧 1개 · <b>같은 키워드는 그날 무료</b> · "
                      "가입 시 무료 3회 · "
                      '<a href="/pricing">플랜별 차이</a>'))
    out.append('</div>')

    if not logged_in:
        out.append(render(ui.pitch, "준비되셨으면",
                          "지금 시작해보세요",
                          '<a href="/">첫 화면에서 카카오/구글로 3초면 됩니다 →</a>'))
    return "".join(out)
