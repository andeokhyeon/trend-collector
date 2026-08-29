# -*- coding: utf-8 -*-
"""
관리 콘솔 — app.py L2613~ 이식 + 웹에서 가능해진 개선.

⚠️ 스트림릿에서는 '안 보는 탭도 매번 실행'되는 통에
   조회마다 '불러오기' 버튼을 거치게 막아뒀다.
   웹은 이 주소에 들어와야만 조회가 일어나므로 버튼 없이 바로 보여준다.
   (Claude 비용처럼 바깥 API를 부르는 것만 5분 캐시를 얹는다)

⚠️ 문은 두 짝: 회원 계정의 관리자 표시(is_admin) 또는 비밀번호.
   비밀번호로 들어오면 짧은(12시간) 도장 쿠키를 준다.
"""
import time
from urllib.parse import quote

import pandas as pd

from uihtml import ui, render
from tables import compact_num, table_html
import accounts

try:
    import cache            # 부모 폴더 — main.py가 경로를 잡아준다
except Exception:
    cache = None

_memo = {}


def _cached(key, ttl, fn):
    hit = _memo.get(key)
    now = time.time()
    if hit and now - hit[1] < ttl:
        return hit[0]
    val = fn()
    _memo[key] = (val, now)
    return val


def clear_members():
    _memo.pop("members", None)


def _members():
    return _cached("members", 120, lambda: (
        accounts.all_members(300),
        accounts.usage_by_user(7),
        accounts.recent_credit_log(40)))


def login_box(wrong=False):
    out = [render(ui.section, "관리자 화면", "비밀번호를 입력하세요")]
    if accounts.table_ready():
        out.append(render(ui.note,
                          "회원으로 로그인한 계정에 <b>관리자 표시</b>가 있으면 "
                          "비밀번호 없이 바로 들어옵니다. 아니면 아래 비밀번호로 "
                          "들어간 뒤 회원 탭에서 지정해두세요."))
    if wrong:
        out.append('<div class="note" style="border-left-color:#E02424">'
                   '비밀번호가 맞지 않습니다.</div>')
    out.append('''
<form class="search-box" method="post" action="/manage/login" style="max-width:460px">
  <div class="stTextInput"><input type="password" name="pw" placeholder="비밀번호"></div>
  <div class="stButton kh-primary"><button type="submit">확인</button></div>
</form>''')
    return "".join(out)


def _subnav(view):
    tabs = [("회원", "members"), ("비용", "cost"), ("수집·풀", "pool")]
    out = ['<div class="kh-filter" style="margin-bottom:14px">']
    for name, key in tabs:
        cls = "kh-pill on" if key == view else "kh-pill"
        out.append(f'<a class="{cls}" href="/manage?view={key}">{name}</a>')
    out.append('''<form method="post" action="/manage/lock" style="margin-left:auto">
<button class="kh-btn" style="margin-top:0;padding:5px 14px;font-size:.85rem"
 type="submit">잠그기</button></form>''')
    out.append('</div>')
    return "".join(out)


def _kpirow(cells):
    inner = "".join(f'<div class="cell">{c}</div>' for c in cells)
    return (f'<div class="row" style="grid-template-columns:'
            f'repeat({len(cells)},1fr)">{inner}</div>')


# ── 회원 ─────────────────────────────────────────────
def members_view(flash=""):
    out = [render(ui.section, "관리자 콘솔", "회원 · 비용 · 사용량 한 화면에"),
           _subnav("members")]
    if flash:
        out.append(f'<div class="kh-flash">{flash}</div>')
    if not accounts.table_ready():
        out.append(render(ui.pitch, "회원 테이블이 아직 없습니다",
                          "SQL 한 번만 실행하면 됩니다",
                          "함께 드린 `회원_DB설정.sql`을 Supabase의 "
                          "SQL Editor에 붙여넣고 실행해주세요."))
        return "".join(out)

    members, uu, clog = _members()
    paid = [m for m in members if (m.get("plan") or "free") != "free"]
    act = [m for m in members if m.get("last_seen")]
    tot = sum(sum(v.values()) for v in uu.values())
    out.append(_kpirow([
        render(ui.kpi, "전체 회원", f"{len(members):,}", "가입한 사람"),
        render(ui.kpi, "유료 회원", f"{len(paid):,}", "무료가 아닌 플랜"),
        render(ui.kpi, "한 번이라도 쓴 사람", f"{len(act):,}", "로그인 기록 있음"),
        render(ui.kpi, "7일 호출(회원분)", f"{tot:,}", "회원별로 기록된 것만"),
    ]))

    if not members:
        out.append(render(ui.note, "아직 가입한 회원이 없습니다."))
        return "".join(out)

    rows = []
    for m in members:
        u = uu.get(m["id"], {})
        rows.append({
            "회원": (m.get("nickname")
                    or (m.get("email") or "").split("@")[0] or "-"),
            "이메일": m.get("email") or "(카카오)",
            "플랜": accounts.PLANS.get(m.get("plan") or "free",
                                      {}).get("name", m.get("plan") or "-"),
            "크레딧": int(m.get("credits") or 0),
            "7일 호출": sum(u.values()),
            "가입": str(m.get("created_at") or "")[:10],
            "마지막 접속": str(m.get("last_seen") or "-")[:10],
        })
    mf = pd.DataFrame(rows)
    mf.index = range(1, len(mf) + 1)
    out.append(table_html(mf, center_cols=("플랜", "가입", "마지막 접속")))
    out.append('<a class="kh-btn" href="/manage/csv" download>CSV 내려받기</a>')

    # --- 크레딧 손보기 ---
    opts = "".join(
        f'<option value="{m["id"]}">'
        f'{(m.get("nickname") or m.get("email") or m["id"])[:24]}'
        f'  ·  {int(m.get("credits") or 0):,}크레딧</option>'
        for m in members)
    plan_opts = "".join(
        f'<option value="{k}">{v["name"]} · {v["credits"]:,}크레딧 · '
        f'{v["price"]:,}원</option>' for k, v in accounts.PLANS.items())
    out.append(render(ui.section, "크레딧 손보기", "충전하거나 플랜을 바꿉니다"))
    out.append(f'''
<div class="box">
  <form class="kh-adm-row" method="post" action="/manage/grant">
    <select name="uid" class="kh-sel">{opts}</select>
    <input class="kh-amt" type="number" name="amt" value="100" step="50">
    <button class="kh-btn kh-btn-primary kh-adm-btn" type="submit">충전</button>
  </form>
  <form class="kh-adm-row" method="post" action="/manage/plan">
    <select name="uid" class="kh-sel">{opts}</select>
    <select name="plan" class="kh-sel">{plan_opts}</select>
    <button class="kh-btn kh-adm-btn" type="submit">플랜 변경</button>
  </form>
</div>''')

    # --- 관리자 지정 ---
    out.append(render(ui.section, "관리자 지정",
                      "이 사람은 관리 콘솔에 들어올 수 있습니다"))
    admins = [m for m in members if m.get("is_admin")]
    if not admins:
        out.append(render(ui.note,
                          "아직 관리자가 없습니다. 지금은 비밀번호로만 들어올 수 "
                          "있습니다. 아래에서 본인 계정을 관리자로 지정해두면 "
                          "다음부터는 그냥 들어옵니다."))
    else:
        out.append(render(ui.note, "현재 관리자: <b>"
                          + "</b>, <b>".join((a.get("email") or a["id"])
                                             for a in admins) + "</b>"))
    out.append(f'''
<div class="box">
  <form class="kh-adm-row" method="post" action="/manage/admin">
    <select name="uid" class="kh-sel">{opts}</select>
    <button class="kh-btn kh-adm-btn" name="on" value="1" type="submit">관리자로</button>
    <button class="kh-btn kh-adm-btn" name="on" value="0" type="submit">해제</button>
  </form>
</div>''')

    if clog:
        out.append(render(ui.section, "최근 크레딧 변동", "누가 언제 얼마나"))
        emap = {m["id"]: (m.get("nickname") or m.get("email") or "-")
                for m in members}
        cf = pd.DataFrame([{
            "회원": emap.get(c.get("user_id"), "-"),
            "변동": f"{int(c.get('delta') or 0):+,}",
            "잔액": int(c.get("balance") or 0),
            "사유": c.get("reason") or "-",
            "키워드": c.get("keyword") or "-",
            "때": str(c.get("created_at") or "")[:16].replace("T", " "),
        } for c in clog])
        cf.index = range(1, len(cf) + 1)
        out.append(table_html(cf, center_cols=("변동", "사유", "때")))
    return "".join(out)


def members_csv():
    members, uu, _ = _members()
    rows = [{"회원": m.get("nickname") or "-", "이메일": m.get("email") or "",
             "플랜": m.get("plan") or "free",
             "크레딧": int(m.get("credits") or 0),
             "7일 호출": sum(uu.get(m["id"], {}).values()),
             "가입": str(m.get("created_at") or "")[:10]}
            for m in members]
    return pd.DataFrame(rows)


# ── 비용 ─────────────────────────────────────────────
def cost_view():
    out = [render(ui.section, "관리자 콘솔", "회원 · 비용 · 사용량 한 화면에"),
           _subnav("cost"),
           render(ui.section, "Claude 비용", "Anthropic Admin API로 직접 읽습니다")]

    def _load():
        try:
            import claude_usage
            return claude_usage.cost(14), claude_usage.tokens(7)
        except Exception as e:
            return (None, str(e)), (None, str(e))
    (cost, cmsg), (tok, _tmsg) = _cached("claude_cost", 300, _load)

    if cost is None:
        # ⚠️ 2026-08-29 확인: 개인(Individual) 조직은 콘솔에 Admin 키 발급
        #    메뉴가 아예 없다 (문서에는 있지만 UI에 없음, 일반 키는 403).
        #    그리고 지금 서비스는 클로드를 직접 부르는 기능이 없어서
        #    비용도 발생하지 않는다. 사실대로 안내한다.
        out.append(render(ui.note,
                          "자동 조회는 개인 조직에 Admin 키 발급이 열리면 연결됩니다. "
                          "현재 서비스는 클로드 API를 직접 부르지 않아 비용이 발생하지 "
                          "않으며, 계정 전체 지출은 "
                          '<a href="https://platform.claude.com" target="_blank">'
                          "Claude 콘솔 대시보드</a>에서 확인할 수 있습니다."))
    else:
        s = sum(d["usd"] for d in cost)
        last = cost[-1]["usd"] if cost else 0
        out.append(_kpirow([
            render(ui.kpi, "최근 14일 비용", f"${s:,.2f}", f"약 {int(s * 1400):,}원"),
            render(ui.kpi, "어제 비용", f"${last:,.2f}", "하루치"),
        ]))
        out.append(render(ui.bar_series,
                          [(d["day"], int(d["usd"] * 100)) for d in cost],
                          "일별 비용 (센트)", height=170, accent=ui.DEEP))
    if tok:
        tf = pd.DataFrame([{"날짜": t["day"], "입력 토큰": t["input"],
                            "출력 토큰": t["output"],
                            "캐시 읽기": t["cache_read"]} for t in tok])
        tf.index = range(1, len(tf) + 1)
        out.append(table_html(tf, center_cols=("날짜",)))

    out.append(render(ui.section, "네이버 사용량", "우리가 직접 센 숫자입니다"))
    out.append(render(ui.note,
                      "여기 숫자는 앱이 네이버를 부를 때마다 직접 센 <b>전 종류 합계</b>입니다 — "
                      "자동완성(한도 무관)·데이터랩(제한 없음)·검색광고·블로그 검색을 다 셉니다. "
                      "네이버 콘솔의 '블로그 N회'는 그중 <b>블로그 검색 하나만</b> 센 숫자라 "
                      "여기보다 훨씬 작게 보입니다. 25,000 한도가 실제로 걸리는 것도 "
                      "블로그 검색뿐이니, 콘솔 숫자가 진짜 한도 잔량이고 "
                      "여기 합계는 '무엇이 얼마나 부르는지' 감을 잡는 용도입니다."))
    if cache is not None:
        u2 = cache.usage()
        out.append(_kpirow([
            render(ui.kpi, "오늘 호출", f"{u2['calls']:,}", f"한도 {u2['limit']:,}회"),
            render(ui.kpi, "남은 조회", f"{u2['remaining']:,}",
                   f"{cache.reset_time()} 초기화"),
            render(ui.kpi, "사용률", f"{u2['pct']}%", "70%를 넘으면 조회를 아낍니다"),
        ]))
        h2 = cache.usage_history(14)
        if h2:
            out.append(render(ui.bar_series,
                              [(h["day"][5:], int(h["calls"] or 0))
                               for h in reversed(h2)],
                              "최근 14일 네이버 호출", height=170, accent=ui.GOOD))
    return "".join(out)


# ── 수집·풀 ──────────────────────────────────────────
def pool_view(sort="최근 추가순"):
    out = [render(ui.section, "관리자 콘솔", "회원 · 비용 · 사용량 한 화면에"),
           _subnav("pool")]
    if cache is None:
        out.append(render(ui.note, "cache.py가 없어 현황을 볼 수 없습니다."))
        return "".join(out)

    def _load():
        return {"stats": cache.pool_stats(), "usage": cache.usage(),
                "hist": cache.usage_history(7),
                "rows": (cache.pool_recent(100) if sort == "최근 추가순"
                         else cache.pool_top(100))}
    d = _cached(f"pool:{sort}", 300, _load)
    stats, u, hist, rows = d["stats"], d["usage"], d["hist"], d["rows"]

    pills = ['<div class="kh-filter">']
    for o in ("최근 추가순", "검색량 많은순"):
        cls = "kh-pill on" if o == sort else "kh-pill"
        pills.append(f'<a class="{cls}" href="/manage?view=pool'
                     f'&sort={quote(o)}">{o}</a>')
    pills.append('</div>')
    out.append("".join(pills))

    out.append(_kpirow([
        render(ui.kpi, "쌓인 키워드", compact_num(stats["total"]),
               f"오늘 +{stats['today']:,}개"),
        render(ui.kpi, "문서수 잰 키워드", compact_num(stats["with_docs"]),
               "조회된 것만 채워집니다"),
        render(ui.kpi, "오늘 API 호출", f"{u['calls']:,}",
               f"한도 {u['limit']:,}회의 {u['pct']}%"),
        render(ui.kpi, "남은 조회", f"{u['remaining']:,}",
               f"{cache.reset_time()} 초기화"),
    ]))
    out.append(render(ui.note,
                      "<b>검색량</b>은 한 번 호출에 연관어 20개가 딸려와 빠르게 쌓입니다. "
                      "<b>문서수</b>는 키워드마다 따로 불러야 해서, "
                      "실제로 조회된 것만 채워집니다. 두 숫자가 크게 차이나는 건 정상입니다."))
    out.append(render(ui.gauge, "오늘 사용량", min(100, int(u["pct"])),
                      ("여유", "보통", "한도"),
                      color=(ui.BAD if u["pct"] >= 70 else
                             (ui.WARN if u["pct"] >= 40 else ui.GOOD))))
    if hist:
        out.append(render(ui.bar_series,
                          [(h["day"][5:], int(h["calls"] or 0))
                           for h in reversed(hist)],
                          "최근 7일 API 호출", height=170, accent=ui.DEEP))

    out.append(render(ui.section, "키워드 풀", "실제로 어떤 단어가 쌓였나"))
    if not rows:
        out.append(render(ui.note,
                          "아직 쌓인 키워드가 없습니다. "
                          "<b>7_키워드_미리쌓기.bat</b>을 돌리거나 "
                          "GitHub Actions의 <b>seed-pool</b>을 실행해보세요."))
    else:
        dfp = pd.DataFrame([{
            "키워드": r["keyword"],
            "월 검색량": (r.get("monthly_pc") or 0) + (r.get("monthly_mobile") or 0),
            "경쟁": r.get("comp_level") or "-",
            "문서수": r.get("blog_total_docs") or None,
            "쌓인 시각": (r.get("updated_at") or "")[:16].replace("T", " "),
        } for r in rows])
        dfp.index = dfp.index + 1
        out.append(table_html(dfp, height=420))
        out.append(f'<div class="kh-cap">{len(rows)}개 표시 중 · '
                   f'전체 {stats["total"]:,}개</div>')
    return "".join(out)
