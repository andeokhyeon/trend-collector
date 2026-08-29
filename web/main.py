# -*- coding: utf-8 -*-
"""
키워드 헌터 — 웹 서버 (FastAPI)

⚠️ 스트림릿을 걷어내는 중이다. 지금은 첫 화면 하나만 있다.
   두뇌(naver_api, cache, accounts …)는 손대지 않는다.
   이 파일은 그 위에 얇게 얹혀 HTML을 만들어 보내는 일만 한다.

⚠️ CSS는 손으로 옮기지 않는다. `build_css.py`가 ui.py에서 뽑아낸다.
   눈으로 베끼면 미묘하게 달라지고, 달라진 걸 나중에 찾기가 더 어렵다.
"""
import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# ⚠️ 두뇌(naver_api, accounts …)는 web/의 부모 폴더에 있다.
#    경로를 절대값으로 박으면 다른 컴퓨터에서 못 찾는다 — 상대로 계산한다.
#    (다른 곳에 뒀다면 환경변수 KH_BRAIN으로 알려줄 수 있다)
PARENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
for _cand in (os.environ.get("KH_BRAIN", ""), PARENT):
    if _cand and os.path.exists(os.path.join(_cand, "naver_api.py")):
        sys.path.insert(0, _cand)
        break

# ⚠️ 개발 중에는 진짜 네이버 대신 가짜 응답을 쓴다 (한도를 안 태우려고).
#    배포에서는 이 변수를 안 켜면 그대로 진짜 API를 쓴다.
if os.environ.get("KH_FAKE") == "1":
    import fakenet
    fakenet.install()

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import auth

app = FastAPI(title="키워드 헌터")
auth.init()


# 쿠키에 Secure를 붙일지 — 프록시 뒤에서는 request.url.scheme이 http로
# 보이므로 주소 설정(SITE_URL)로 판단한다.
def _is_https():
    try:
        from config import SITE_URL
        return str(os.environ.get("KH_SITE") or SITE_URL or "").startswith("https")
    except Exception:
        return False


_SECURE = None


def _secure():
    global _SECURE
    if _SECURE is None:
        _SECURE = _is_https()
    return _SECURE


import re as _re


def _clean_kw(s, limit=60):
    """키워드 입력 소독 — 꺾쇠·따옴표류는 키워드에 있을 일이 없고,
    화면에 그대로 그려지는 경로가 많아 원천에서 걷어낸다 (XSS 방지)."""
    s = (s or "").strip()[:limit]
    return _re.sub(r'[<>"\'`\\]', "", s)


@app.middleware("http")
async def _sec_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy",
                            "camera=(), microphone=(), geolocation=()")
    # 글꼴은 절대 안 바뀐다 — 브라우저가 한 번 받으면 오래 기억하게
    if request.url.path.startswith("/static/fonts/"):
        resp.headers.setdefault("Cache-Control", "public, max-age=2592000, immutable")
    return resp
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")),
          name="static")
tpl = Jinja2Templates(directory=os.path.join(HERE, "templates"))


def logo_uri():
    """로고를 주소 안에 통째로 박는다 (파일 하나 덜 요청하게)."""
    p = os.path.join(HERE, "static", "logo.png")
    try:
        with open(p, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    except Exception:
        return ""


# 상위 탭 — 이름과 주소. 스트림릿의 st.tabs를 대신한다.
TABS = [
    ("키워드 조사", "/"),
    ("추적기", "/tracker"),
    ("내 블로그", "/blog"),
    ("키워드 발굴", "/discover"),
    ("마이페이지", "/me"),
]
SUB_RESEARCH = [
    ("키워드 분석", "/"),
    ("상위노출 해부", "/serp"),
    ("글감 만들기", "/ideas"),
]
SUB_DISCOVER = [
    ("구글 트렌드", "trend"),
    ("골든타임", "golden"),
    ("주간 캘린더", "weekly"),
    ("뉴스", "news"),
]


def _meta_line():
    try:
        import db
        f = db.freshness()
        return f"마지막 수집 {f}" if f else ""
    except Exception:
        return ""


def _profile(uid):
    import accounts
    try:
        return accounts.profile(uid)
    except Exception:
        return None


def _page(request, template, active_tab, active_sub, q, result,
          title="", subs=None):
    """공통 뼈대 — 탭·검색창·본문. (새 Starlette은 request가 첫 인자)"""
    user = auth.current_user(request)
    meta = _meta_line()
    me_label = ""
    if user:
        prof = _profile(user["id"]) or {}
        name = (prof.get("nickname")
                or (user.get("email") or "").split("@")[0] or "회원")
        cr = prof.get("credits")
        # ⚠️ 이름·크레딧은 meta에 섞지 않고 따로 — 마이페이지(/me) 링크가 된다
        me_label = name + (f" · 크레딧 {int(cr):,}" if cr is not None else "")
    return tpl.TemplateResponse(request, template, {
        "tabs": TABS, "active_tab": active_tab, "me_label": me_label,
        "subs": subs if subs is not None else SUB_RESEARCH,
        "active_sub": active_sub,
        "logo": logo_uri(),
        "meta": meta,
        "q": q, "result": result, "page_title": title,
        "chips": ["삼성전자", "주말날씨", "에어프라이어", "점심메뉴추천"],
        # ⚠️ 한때 "6분 전"으로 박혀 있었다 — 실제 수집 시각을 쓴다
        "freshness": (_fresh_short() or "수집 대기"),
    })


def _fresh_short():
    try:
        import db
        return db.freshness()
    except Exception:
        return ""


def _blog_of(request, prof=None):
    """내 블로그 아이디 — 계정(profiles.blog_id)이 먼저, 쿠키는 보조."""
    if prof and prof.get("blog_id"):
        return prof["blog_id"]
    return request.cookies.get("kh_blog", "")


def _adopt_blog(user, prof, request):
    """쿠키 시절(계정 저장 이전)에 등록한 블로그를 계정으로 승격한다.

    ⚠️ 2026-08-28: 같은 계정인데 PC엔 블로그가 있고 폰엔 없다는 제보.
    예전엔 쿠키에만 저장했기 때문 — 브라우저마다 따로 논다.
    로그인한 회원의 계정에 블로그가 비어 있는데 쿠키에 있으면
    그 값을 계정에 올려준다. 이후 어느 기기서든 같이 보인다."""
    ck = request.cookies.get("kh_blog", "")
    if not (user and ck) or prof is None or prof.get("blog_id"):
        return prof
    try:
        import db as _db
        _db.client().table("profiles").update(
            {"blog_id": ck}).eq("id", user["id"]).execute()
        prof = dict(prof)
        prof["blog_id"] = ck
    except Exception:
        pass
    return prof


def _login_box(next_path):
    """로그인 상자 — 문구는 스트림릿 login_gate 그대로."""
    from uihtml import ui, render
    from urllib.parse import quote
    out = [render(ui.pitch, "먼저 로그인해주세요",
                  "키워드 조사는 회원만 쓸 수 있습니다",
                  "카카오·구글 계정으로 3초면 됩니다. "
                  "가입하면 무료로 3번 조사할 수 있습니다.")]
    items = []
    import accounts
    for pid, (label, _bg, _fg) in accounts.PROVIDERS.items():
        items.append((pid, f"{label}로 시작하기",
                      f"/login/{pid}?next={quote(next_path)}"))
    out.append(render(ui.social_links, items))
    out.append('<p class="kh-guide-link">처음이신가요? '
               '<a href="/guide">이용 가이드 3분 읽기 →</a></p>')
    return "".join(out)


def _no_credit_box(why=""):
    from uihtml import ui, render
    if "로그인" in (why or ""):
        # 프로필을 확인 못 한 토큰 — 크레딧 문구를 보여주면 헷갈린다
        return (render(ui.pitch, "회원 정보를 확인하지 못했습니다",
                       "다시 로그인해주세요", "")
                + _login_box("/"))
    return render(ui.pitch, "크레딧을 다 쓰셨습니다",
                  "충전하면 이어서 볼 수 있습니다",
                  "관리자에게 문의하시거나 잠시 후 다시 시도해주세요.")


def _safe(build, *a, **k):
    """화면 하나가 죽어도 페이지는 산다."""
    try:
        return build(*a, **k)
    except Exception as e:
        return (f'<div class="note">불러오지 못했습니다. '
                f'<small>{type(e).__name__}: {e}</small></div>')


@app.get("/", response_class=HTMLResponse)
def home(request: Request, q: str = "", rank: int = 0,
         contains: int = 1, min: int = 0):
    result_html = ""
    q = _clean_kw(q)
    if q:
        user = auth.current_user(request)
        if not user:
            # ⚠️ 로그인 전에는 네이버를 한 번도 부르지 않는다 (스트림릿 때의 교훈)
            result_html = _login_box(f"/?q={q}")
        else:
            ok, left, why = _spend(user, q)
            if not ok:
                result_html = _no_credit_box(why)
            else:
                import analyze
                result_html = _safe(analyze.build, q, rank=bool(rank),
                                    only_contains=bool(contains), min_vol=min,
                                    my_blog_id=_blog_of(request))
    return _page(request, "analyze.html", "/", "/", q, result_html,
                 title=(f"{q} — 키워드 분석" if q else ""))


# 크레딧 — '같은 키워드 재조회는 무과금' 규칙을 서버에서 지킨다.
# (uid, keyword) 짝을 하루 동안 기억해 두 번 깎지 않는다.
#
# ⚠️ 기록은 파이썬 dict이 아니라 store(SQLite)에 둔다.
#    워커 2개일 때 dict은 절반 확률로 남의 워커 기억이라
#    새로고침마다 또 깎였다. claim()은 INSERT라 동시에 둘이 와도
#    한쪽만 성공한다 — 더블클릭·중복탭에도 한 번만 깎인다.
def _charged_key(user, kw):
    return "%s|%s" % (user["id"], kw)


def _spend(user, kw):
    import accounts
    import store
    key = _charged_key(user, kw)
    if not store.claim("charged", key, ttl=86400):
        return True, None, ""         # 오늘 이미 낸 키워드 — 무과금
    ok, left, why = accounts.spend(user["id"], reason="analyze", keyword=kw)
    if not ok:
        store.drop("charged", key)    # 못 깎았으면 자리도 되돌린다
    return ok, left, why


@app.get("/serp", response_class=HTMLResponse)
def serp_page(request: Request, q: str = "", sort: str = "sim"):
    import serp
    q = _clean_kw(q)
    user = auth.current_user(request) if q.strip() else None
    if q.strip() and not user:
        result_html = _login_box(f"/serp?q={q.strip()}")
    elif q.strip() and not (_sp := _spend(user, q.strip()))[0]:
        # ⚠️ 스트림릿 때 규칙 그대로: 조회한(과금된) 키워드만 본다.
        #    같은 날 분석에서 이미 낸 키워드면 여기선 안 깎인다.
        result_html = _no_credit_box(_sp[2])
    else:
        result_html = _safe(serp.build, q, sort=sort,
                            my_blog_id=_blog_of(request))
    return _page(request, "research.html", "/", "/serp", q.strip(), result_html,
                 title=(f"{q.strip()} — 상위노출 해부" if q.strip() else "상위노출 해부"))


@app.get("/ideas", response_class=HTMLResponse)
def ideas_page(request: Request, q: str = ""):
    import ideas
    q = _clean_kw(q)
    user = auth.current_user(request) if q.strip() else None
    if q.strip() and not user:
        result_html = _login_box(f"/ideas?q={q.strip()}")
    elif q.strip() and not (_sp := _spend(user, q.strip()))[0]:
        result_html = _no_credit_box(_sp[2])
    else:
        result_html = _safe(ideas.build, q)
    return _page(request, "research.html", "/", "/ideas", q.strip(), result_html,
                 title=(f"{q.strip()} — 글감 만들기" if q.strip() else "글감 만들기"))


# ------------------------------------------------------------
# 로그인
# ------------------------------------------------------------
@app.get("/login/{provider}")
def login_start(provider: str, next: str = "/"):
    import accounts
    # ⚠️ /login/naver 같은 없는 provider가 500으로 터졌었다 (전수 테스트에서 발견)
    if provider not in accounts.PROVIDERS:
        return RedirectResponse("/", status_code=302)
    url, msg = auth.start_oauth(provider, next)
    if not url:
        return HTMLResponse(f"<p>{msg}</p>", status_code=500)
    return RedirectResponse(url, status_code=302)


@app.get("/auth/cb")
def auth_cb(request: Request, code: str = "", vid: str = "", next: str = "/",
            error: str = "", error_description: str = ""):
    """카카오/구글에서 돌아오는 문.

    ⚠️ 코드→세션 교환은 수 초 걸릴 수 있는데, 그동안 흰 화면이 떠서
    '멈췄나?' 싶다는 제보 (2026-08-29). 그래서 두 단계로 쪼갠다:
    여기서는 도넛 화면을 즉시 보여주고, 무거운 교환은
    화면이 스스로 제출하는 /auth/finish 에서 한다."""
    if error:
        return HTMLResponse(
            f"<p>로그인이 거절됐습니다. ({error} — {error_description})</p>"
            f'<p><a href="/">돌아가기</a></p>', status_code=400)
    if not code:
        return HTMLResponse("<p>로그인 정보를 받지 못했습니다.</p>"
                            "<p><a href='/'>돌아가기</a></p>", status_code=400)
    from html import escape as _esc
    body = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>로그인 중 · 키워드 헌터</title><style>
body{{margin:0;min-height:100vh;display:flex;flex-direction:column;
align-items:center;justify-content:center;gap:14px;
font-family:'Gothic A1',sans-serif;background:#fff;color:#374151}}
.d{{width:44px;height:44px;border-radius:50%;border:5px solid #E3E8EF;
border-top-color:#1A56DB;animation:s .8s linear infinite}}
@keyframes s{{to{{transform:rotate(360deg)}}}}
p{{font-size:.95rem;font-weight:700}}</style></head><body>
<div class="d"></div><p>로그인 확인 중입니다…</p>
<form id="f" method="post" action="/auth/finish">
<input type="hidden" name="code" value="{_esc(code)}">
<input type="hidden" name="vid" value="{_esc(vid)}">
<input type="hidden" name="next" value="{_esc(next or '/')}">
<noscript><button type="submit">계속하기</button></noscript></form>
<script>document.getElementById("f").submit();</script></body></html>"""
    return HTMLResponse(body)


@app.post("/auth/finish")
def auth_finish(request: Request, code: str = Form(""), vid: str = Form(""),
                next: str = Form("/")):
    tok, msg = auth.finish_oauth(code, vid)
    if not tok:
        return HTMLResponse(f"<p>{msg}</p><p><a href='/'>돌아가기</a></p>",
                            status_code=400)
    # 열린 곳으로만 돌려보낸다 (밖의 주소를 넣어 보내는 장난 방지)
    dest = next if (next or "").startswith("/") else "/"
    resp = RedirectResponse(dest, status_code=303)
    resp.set_cookie(auth.COOKIE, tok, max_age=14 * 86400,
                    httponly=True, samesite="lax",
                    secure=_secure())
    return resp


@app.get("/guide", response_class=HTMLResponse)
def guide_page(request: Request):
    import guide
    html = _safe(guide.build, bool(auth.current_user(request)))
    return _page(request, "discover.html", "", "", "", html,
                 title="이용 가이드", subs=[])


@app.get("/me", response_class=HTMLResponse)
def me_page(request: Request):
    user = auth.current_user(request)
    if not user:
        html = _login_box("/me")
    else:
        import me
        prof = _adopt_blog(user, _profile(user["id"]), request)
        html = _safe(me.build, user, prof, _blog_of(request, prof))
    return _page(request, "discover.html", "", "", "", html,
                 title="마이페이지", subs=[])


@app.post("/me/blog")
def me_blog(request: Request, blog: str = Form("")):
    """블로그 주소를 계정(profiles.blog_id)에 저장. 쿠키는 보조로 같이."""
    user = auth.current_user(request)
    if not user:
        return RedirectResponse("/me", status_code=303)
    from naver_api import extract_blog_id
    bid = extract_blog_id(blog) if blog.strip() else ""
    try:
        import db as _db
        _db.client().table("profiles").update(
            {"blog_id": bid or None}).eq("id", user["id"]).execute()
    except Exception:
        pass                       # 컬럼이 없어도 쿠키로는 동작한다
    resp = RedirectResponse("/me", status_code=303)
    if bid:
        resp.set_cookie("kh_blog", bid, max_age=365 * 86400, samesite="lax")
    else:
        resp.delete_cookie("kh_blog")
    return resp


@app.post("/logout")
def logout():
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(auth.COOKIE)
    return resp


# ------------------------------------------------------------
# 추적기
# ------------------------------------------------------------
@app.get("/tracker", response_class=HTMLResponse)
def tracker_page(request: Request, detail: str = "", flash: str = ""):
    detail = _clean_kw(detail)
    user = auth.current_user(request)
    if not user:
        html = _login_box("/tracker")
    else:
        import tracker
        html = _safe(tracker.build, user["id"], _blog_of(request),
                     detail, flash)
    return _page(request, "discover.html", "/tracker", "", "", html,
                 title="키워드 추적기", subs=[])


@app.post("/tracker/add")
def tracker_add(request: Request, kw: str = Form(""), wrote: str = Form("")):
    user = auth.current_user(request)
    kw = _clean_kw(kw)
    if user and kw.strip():
        import db as _db
        row = {"keyword": kw.strip(), "blog_id": _blog_of(request) or "",
               "has_post": bool(wrote), "user_id": user["id"]}
        try:
            _db.client().table("tracked_keywords").insert(row).execute()
        except Exception as e:
            if "user_id" in str(e):
                row.pop("user_id", None)
                try:
                    _db.client().table("tracked_keywords").insert(row).execute()
                except Exception:
                    pass
        _track_dirty(user["id"])
    return RedirectResponse("/tracker", status_code=303)


def _track_dirty(uid):
    """추적 목록이 바뀌었다는 신호 — 어느 워커의 캐시든 다음 요청에 새로 읽는다."""
    import time as _t
    import store
    store.put("trackver", uid, str(_t.time()), ttl=7 * 86400)


@app.post("/tracker/stop")
def tracker_stop(request: Request, id: str = Form(""), kw: str = Form("")):
    user = auth.current_user(request)
    if user and id:
        import db as _db
        try:
            _db.client().table("tracked_keywords").delete().eq("id", id).execute()
        except Exception:
            pass
        _track_dirty(user["id"])
    return RedirectResponse("/tracker", status_code=303)


@app.post("/tracker/flip")
def tracker_flip(request: Request, id: str = Form("")):
    user = auth.current_user(request)
    if user and id:
        import db as _db
        try:
            sb = _db.client()
            cur = (sb.table("tracked_keywords").select("has_post")
                   .eq("id", id).limit(1).execute().data or [{}])[0]
            sb.table("tracked_keywords").update(
                {"has_post": not bool(cur.get("has_post"))}).eq("id", id).execute()
        except Exception:
            pass
        _track_dirty(user["id"])
    return RedirectResponse("/tracker", status_code=303)


# ------------------------------------------------------------
# 내 블로그
# ------------------------------------------------------------
@app.get("/blog", response_class=HTMLResponse)
def blog_page(request: Request):
    user = auth.current_user(request)
    if not user:
        html = _login_box("/blog")
    else:
        import blog
        prof = _adopt_blog(user, _profile(user["id"]), request)
        html = _safe(blog.build, user, _blog_of(request, prof), prof)
    return _page(request, "discover.html", "/blog", "", "", html,
                 title="내 블로그 진단", subs=[])


@app.post("/blog/set")
def blog_set(request: Request, blog: str = Form("")):
    from naver_api import extract_blog_id
    bid = extract_blog_id(blog) if blog.strip() else ""
    resp = RedirectResponse("/blog", status_code=303)
    if bid:
        # ⚠️ 블로그 주소는 비밀이 아니라서 쿠키에 그대로 둔다 (1년)
        resp.set_cookie("kh_blog", bid, max_age=365 * 86400, samesite="lax")
    else:
        resp.delete_cookie("kh_blog")
    return resp


@app.get("/dev/login")
def dev_login(request: Request):
    """개발용 — 가짜 계정으로 바로 로그인 (KH_FAKE에서만)."""
    if os.environ.get("KH_FAKE") != "1":
        return RedirectResponse("/", status_code=302)
    import accounts
    ok, msg, user = accounts.exchange("code-kakao", "v" * 48)
    if not ok:
        return HTMLResponse(f"<p>{msg}</p>", status_code=500)
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(auth.COOKIE, accounts.make_token(user["id"]),
                    max_age=86400, httponly=True, samesite="lax")
    return resp


# ------------------------------------------------------------
# 관리 콘솔
#
# ⚠️ 상단 탭에는 없다 — 주소를 아는 사람만 들어온다 (/manage).
#    문은 두 짝: 회원 계정의 관리자 표시, 또는 비밀번호(12시간 도장 쿠키).
# ------------------------------------------------------------
ADMIN_COOKIE = "kh_a"


def _is_admin(request):
    import accounts
    user = auth.current_user(request)
    if user:
        try:
            if accounts.is_admin(user["id"]):
                return True
        except Exception:
            pass
    tok = request.cookies.get(ADMIN_COOKIE)
    return bool(tok) and accounts.read_token(tok) == "pw-admin"


@app.get("/manage", response_class=HTMLResponse)
def manage(request: Request, view: str = "members", sort: str = "최근 추가순",
           wrong: int = 0, flash: str = ""):
    import admin
    if not _is_admin(request):
        html = admin.login_box(wrong=bool(wrong))
    elif view == "cost":
        html = _safe(admin.cost_view)
    elif view == "pool":
        html = _safe(admin.pool_view, sort)
    else:
        html = _safe(admin.members_view, flash)
    return _page(request, "discover.html", "", "", "", html,
                 title="관리자 콘솔", subs=[])


@app.post("/manage/login")
def manage_login(request: Request, pw: str = Form("")):
    import accounts
    import config as _cfg
    _set = getattr(_cfg, "ADMIN_PASSWORD", "") or ""
    # ⚠️ 비밀번호를 아예 안 정해뒀으면(빈 값) 이 문은 잠긴 채로 둔다.
    if _set and pw == _set:
        resp = RedirectResponse("/manage", status_code=303)
        resp.set_cookie(ADMIN_COOKIE, accounts.make_token("pw-admin", days=0.5),
                        max_age=12 * 3600, httponly=True, samesite="lax",
                        secure=_secure())
        return resp
    return RedirectResponse("/manage?wrong=1", status_code=303)


@app.post("/manage/lock")
def manage_lock():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(ADMIN_COOKIE)
    return resp


def _admin_act(request, fn, ok_msg, fail_msg):
    import admin
    from urllib.parse import quote as _q
    if not _is_admin(request):
        return RedirectResponse("/manage", status_code=303)
    try:
        done = fn()
    except Exception:
        done = False
    admin.clear_members()
    msg = ok_msg if done else fail_msg
    return RedirectResponse(f"/manage?flash={_q(msg)}", status_code=303)


@app.post("/manage/grant")
def manage_grant(request: Request, uid: str = Form(...), amt: int = Form(100)):
    import accounts
    return _admin_act(request, lambda: accounts.grant(uid, int(amt)),
                      "충전했습니다.", "충전하지 못했습니다.")


@app.post("/manage/plan")
def manage_plan(request: Request, uid: str = Form(...), plan: str = Form(...)):
    import accounts
    return _admin_act(request, lambda: accounts.set_plan(uid, plan),
                      "플랜을 바꿨습니다.", "바꾸지 못했습니다.")


@app.post("/manage/admin")
def manage_admin(request: Request, uid: str = Form(...), on: str = Form("1")):
    import accounts
    return _admin_act(request, lambda: accounts.set_admin(uid, on == "1"),
                      "지정했습니다." if on == "1" else "해제했습니다.",
                      "바꾸지 못했습니다.")


@app.get("/manage/csv")
def manage_csv(request: Request):
    if not _is_admin(request):
        return RedirectResponse("/manage", status_code=303)
    import admin
    return _csv(admin.members_csv(), "회원목록")


@app.get("/discover", response_class=HTMLResponse)
def discover_page(request: Request, v: str = "trend", p: str = "",
                  t: str = "파생 키워드"):
    import discover
    # 2026-08-29: 발굴 탭도 회원 전용 — 여기 데이터가 이 서비스의 알맹이다
    if not auth.current_user(request):
        subs0 = [(name, f"/discover?v={key}") for name, key in SUB_DISCOVER]
        return _page(request, "discover.html", "/discover", f"/discover?v={v}",
                     "", _login_box(f"/discover?v={v}"),
                     title="키워드 발굴", subs=subs0)
    if v == "golden":
        html = _safe(discover.build_golden, p or "일별", t)
    elif v == "weekly":
        html = _safe(discover.build_weekly)
    elif v == "news":
        html = _safe(discover.build_news, p or "최근")
    else:
        v = "trend"
        html = _safe(discover.build_trend, p or "최근")
    subs = [(name, f"/discover?v={key}") for name, key in SUB_DISCOVER]
    return _page(request, "discover.html", "/discover", f"/discover?v={v}",
                 "", html, title="키워드 발굴", subs=subs)


# ------------------------------------------------------------
# CSV 내려받기 — 화면과 같은 계산을 다시 해서 파일로 준다.
# (계산 결과는 naver_api 층이 캐시하고 있어 두 번 재지 않는다)
# ------------------------------------------------------------
def _csv(frame, name):
    from urllib.parse import quote as _q
    body = "\ufeff" + frame.to_csv(index=False)   # 엑셀이 한글을 읽게 BOM
    # ⚠️ 헤더는 latin-1만 허용된다. 한글 파일명은 퍼센트 표기로 넣어야 한다.
    return Response(
        content=body, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f"attachment; filename*=UTF-8''{_q(name)}.csv"})


def _csv_gate(request, q):
    """CSV는 '오늘 그 키워드를 조회한 회원'에게만 준다.
    ⚠️ 이 문이 없으면 로그인 없이 주소만 쳐도 네이버 호출이 나간다
       (스트림릿 때 '보고 있지 않은 탭' 사건과 같은 부류의 구멍)."""
    import store
    user = auth.current_user(request)
    if not user:
        return RedirectResponse(f"/?q={q}", status_code=303)
    if not store.has("charged", _charged_key(user, q)):
        return RedirectResponse(f"/?q={q}", status_code=303)
    return None


@app.get("/csv/rel")
def csv_rel(request: Request, q: str = "", contains: int = 1, min: int = 0):
    import pandas as pd
    q = _clean_kw(q)
    if not q:
        return RedirectResponse("/", status_code=303)
    blocked = _csv_gate(request, q)
    if blocked:
        return blocked
    from naver_api import analyze_keyword
    r = analyze_keyword(q.strip())
    rows = [{"키워드": i["keyword"],
             "월 검색량": (i["monthly_pc"] + i["monthly_mobile"]
                        if i.get("source") != "자동완성" else None),
             "경쟁": i.get("comp_level") or "-",
             "출처": i.get("source", "검색광고")}
            for i in (r.get("related") or [])
            if (i.get("contains", True) or not contains)
            and (i.get("source") == "자동완성"
                 or (i["monthly_pc"] + i["monthly_mobile"]) >= min)]
    df = pd.DataFrame(rows).sort_values("월 검색량", ascending=False,
                                        na_position="last")
    return _csv(df, f"연관키워드_{q.strip()}")


@app.get("/csv/rank")
def csv_rank(request: Request, q: str = ""):
    import pandas as pd
    import analyze as _an
    q = _clean_kw(q)
    if not q:
        return RedirectResponse("/", status_code=303)
    blocked = _csv_gate(request, q)
    if blocked:
        return blocked
    from naver_api import analyze_keyword
    r = analyze_keyword(q.strip())
    rel = r.get("related") or []
    pool_rel = sorted([i for i in rel if i.get("contains", True)],
                      key=lambda x: (-(x["monthly_pc"] + x["monthly_mobile"]),
                                     x.get("source") == "자동완성"))
    known = {i["keyword"]: {"monthly_pc": i["monthly_pc"],
                            "monthly_mobile": i["monthly_mobile"],
                            "comp_level": i.get("comp_level", "-"),
                            "pl_avg_depth": 0}
             for i in pool_rel if (i["monthly_pc"] + i["monthly_mobile"]) > 0}
    subs, _f, _n = _an.measure_batch(
        tuple(i["keyword"] for i in pool_rel[:10]), known)
    rows = [{"키워드": s["keyword"], "월 검색량": s["total_search"],
             "누적 문서수": s["doc_count"] or 0,
             "기회 점수": (s.get("opportunity") or {}).get("score", 0),
             "진단": (s.get("opportunity") or {}).get("label", "정보없음")}
            for s in subs]
    df = pd.DataFrame(rows).sort_values("기회 점수", ascending=False)
    return _csv(df, f"기회키워드_{q.strip()}")
