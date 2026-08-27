# -*- coding: utf-8 -*-
"""
회원 — 가입 / 로그인 / 크레딧.

⚠️ 설계 원칙 두 가지.

  1) 여기서 무슨 일이 나도 앱은 살아 있어야 한다.
     테이블이 아직 없거나 Supabase가 잠깐 흔들려도, 로그인 화면만
     '안 된다'고 말할 뿐 키워드 조사까지 죽으면 안 된다.
     그래서 모든 함수는 예외를 삼키고 (성공여부, 메시지) 꼴로 돌려준다.

  2) 나중에 결제를 붙일 자리를 지금 비워둔다.
     크레딧을 깎는 곳을 spend() 한 군데로 모아뒀다. 결제가 붙으면
     '떨어졌을 때 무엇을 보여줄지'만 그 자리에서 바꾸면 된다.
"""
import sys
import base64
import hashlib
import hmac
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_sb = None
_URL = ""

# 플랜 — 지금은 코드에 적어둔다. 결제가 붙으면 표만 바꾸면 된다.
PLANS = {
    "free":  {"name": "무료",   "credits": 30,   "price": 0},
    "basic": {"name": "베이직", "credits": 500,  "price": 9900},
    "pro":   {"name": "프로",   "credits": 3000, "price": 19900},
}

ANALYZE_COST = 1          # 키워드 하나 분석 = 1 크레딧


def attach(client, secret="", url=""):
    global _sb, _SECRET, _URL
    _sb = client
    if url:
        _URL = str(url).rstrip("/")
    if secret:
        # ⚠️ 열쇠 그 자체를 쓰지 않고 한 번 뭉개서 쓴다.
        #    혹시 이 값이 새더라도 원래 열쇠를 되돌릴 수 없게.
        _SECRET = hashlib.sha256(("kh-session|" + str(secret)).encode()).digest()


# ------------------------------------------------------------
# 로그인 유지 (브라우저 쿠키에 넣을 표)
#
# ⚠️ 왜 필요한가. 스트림릿은 페이지를 새로 열면 기억을 전부 잃는다.
#    F5 한 번, 로고 한 번에 로그아웃되면 아무도 안 쓴다.
#
# ⚠️ 쿠키에 '나는 u123이다'라고만 적으면 누구나 고쳐 쓸 수 있다.
#    그래서 서버만 아는 열쇠로 도장(HMAC)을 찍는다.
#    도장이 안 맞거나 기한이 지나면 없는 것으로 친다.
#    쿠키에는 회원번호와 기한뿐, 이름·메일 같은 건 담지 않는다.
# ------------------------------------------------------------
_SECRET = None
TOKEN_DAYS = 14
COOKIE = "kh_s"


def _sign(body):
    return hmac.new(_SECRET, body.encode(), hashlib.sha256).hexdigest()[:32]


def make_token(uid, days=TOKEN_DAYS):
    """회원번호를 도장 찍은 짧은 글자로. 열쇠가 없으면 빈 글자."""
    if not _SECRET or not uid:
        return ""
    body = "%s|%d" % (uid, int(time.time()) + days * 86400)
    raw = ("%s|%s" % (body, _sign(body))).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def read_token(tok):
    """도장과 기한을 확인하고 회원번호를 돌려준다. 아니면 None."""
    if not _SECRET or not tok:
        return None
    try:
        pad = "=" * (-len(tok) % 4)
        raw = base64.urlsafe_b64decode(tok + pad).decode()
        uid, exp, sig = raw.rsplit("|", 2)
        if not hmac.compare_digest(sig, _sign("%s|%s" % (uid, exp))):
            return None
        if int(exp) < time.time():
            return None
        return uid
    except Exception:
        return None


def user_from_token(tok):
    """쿠키 한 장으로 로그인 상태를 되살린다. 안 되면 None."""
    uid = read_token(tok)
    if not uid or not ready():
        return None
    p = profile(uid)
    if not p:
        return None
    _touch(uid)
    return {"id": uid, "email": p.get("email") or ""}


def ready():
    return _sb is not None


# ------------------------------------------------------------
# 가입 · 로그인
# ------------------------------------------------------------
def _msg(e):
    """Supabase가 주는 영어 오류를 사람 말로."""
    t = str(e).lower()
    if "already registered" in t or "already been registered" in t:
        return "이미 가입된 이메일입니다. 로그인해주세요."
    if "invalid login" in t or "invalid credentials" in t:
        return "이메일이나 비밀번호가 맞지 않습니다."
    if "password should be" in t or "weak password" in t:
        return "비밀번호는 6자 이상이어야 합니다."
    if "invalid email" in t or "unable to validate email" in t:
        return "이메일 형식이 맞지 않습니다."
    if "email not confirmed" in t:
        return "메일함에서 인증 링크를 눌러주세요."
    if "rate limit" in t or "too many" in t:
        return "잠시 후 다시 시도해주세요."
    if "does not exist" in t or "relation" in t:
        return "회원 테이블이 없습니다. `회원_DB설정.sql`을 Supabase에서 실행해주세요."
    return f"실패했습니다: {e}"


def sign_up(email, password, nickname=""):
    """가입. 반환 (성공, 메시지, 사용자dict|None)"""
    if not ready():
        return False, "서버에 연결되지 않았습니다.", None
    email = (email or "").strip()
    if not email or not password:
        return False, "이메일과 비밀번호를 넣어주세요.", None
    if len(password) < 6:
        return False, "비밀번호는 6자 이상이어야 합니다.", None
    try:
        res = _sb.auth.sign_up({"email": email, "password": password})
        user = getattr(res, "user", None)
        if user is None:
            return False, "가입에 실패했습니다.", None
        if nickname.strip():
            try:
                _sb.table("profiles").update(
                    {"nickname": nickname.strip()}).eq("id", user.id).execute()
            except Exception:
                pass
        # 메일 인증을 켜둔 프로젝트면 세션이 안 온다
        if getattr(res, "session", None) is None:
            return True, "가입했습니다. 메일함에서 인증 링크를 눌러주세요.", None
        return True, "가입했습니다.", _pack(user)
    except Exception as e:
        return False, _msg(e), None


def sign_in(email, password):
    """로그인. 반환 (성공, 메시지, 사용자dict|None)"""
    if not ready():
        return False, "서버에 연결되지 않았습니다.", None
    try:
        res = _sb.auth.sign_in_with_password(
            {"email": (email or "").strip(), "password": password or ""})
        user = getattr(res, "user", None)
        if user is None:
            return False, "이메일이나 비밀번호가 맞지 않습니다.", None
        _touch(user.id)
        return True, "", _pack(user)
    except Exception as e:
        return False, _msg(e), None


def sign_out():
    try:
        _sb.auth.sign_out()
    except Exception:
        pass


def _pack(user):
    return {"id": str(user.id), "email": getattr(user, "email", "") or ""}


def _touch(uid):
    try:
        _sb.table("profiles").update(
            {"last_seen": datetime.now(timezone.utc).isoformat()}
        ).eq("id", uid).execute()
    except Exception:
        pass


# ------------------------------------------------------------
# 프로필 · 크레딧
# ------------------------------------------------------------
def profile(uid):
    """회원 한 명의 프로필. 없으면 None."""
    if not ready() or not uid:
        return None
    try:
        r = _sb.table("profiles").select("*").eq("id", uid).limit(1).execute()
        return (r.data or [None])[0]
    except Exception:
        return None


def credits(uid):
    p = profile(uid)
    return int((p or {}).get("credits") or 0)


def spend(uid, n=ANALYZE_COST, reason="analyze", keyword=""):
    """
    크레딧을 깎는다. 반환 (썼는가, 남은 크레딧, 메시지)

    ⚠️ 크레딧을 깎는 곳은 여기 하나뿐이다.
    여기저기서 깎으면 '왜 줄었는지' 추적이 안 되고,
    나중에 결제를 붙일 때 손댈 곳이 흩어진다.
    """
    if not ready() or not uid:
        return True, 0, ""            # 회원 기능이 꺼져 있으면 막지 않는다
    p = profile(uid)
    if p is None:
        return True, 0, ""
    left = int(p.get("credits") or 0)
    if left < n:
        return False, left, "크레딧이 모두 떨어졌습니다."
    new = left - n
    try:
        _sb.table("profiles").update({"credits": new}).eq("id", uid).execute()
        _sb.table("credit_log").insert({
            "user_id": uid, "delta": -n, "reason": reason,
            "keyword": keyword or None, "balance": new,
        }).execute()
    except Exception:
        return True, left, ""         # 기록에 실패해도 사용은 막지 않는다
    return True, new, ""


def grant(uid, n, reason="admin"):
    """크레딧을 채운다 (관리자·결제 완료 시)."""
    if not ready() or not uid or n == 0:
        return False
    p = profile(uid)
    if p is None:
        return False
    new = int(p.get("credits") or 0) + int(n)
    try:
        _sb.table("profiles").update({"credits": new}).eq("id", uid).execute()
        _sb.table("credit_log").insert({
            "user_id": uid, "delta": int(n), "reason": reason, "balance": new,
        }).execute()
        return True
    except Exception:
        return False


def set_plan(uid, plan):
    """플랜을 바꾸고 그 플랜의 크레딧을 채운다."""
    if plan not in PLANS or not ready():
        return False
    try:
        _sb.table("profiles").update({
            "plan": plan,
            "credits": PLANS[plan]["credits"],
            "plan_started": datetime.now(timezone.utc).isoformat(),
        }).eq("id", uid).execute()
        _sb.table("credit_log").insert({
            "user_id": uid, "delta": PLANS[plan]["credits"],
            "reason": f"plan:{plan}", "balance": PLANS[plan]["credits"],
        }).execute()
        return True
    except Exception:
        return False


# ------------------------------------------------------------
# 회원별 사용량 — 종류별로 하루 한 줄
# ------------------------------------------------------------
def log_usage(uid, kind, n=1):
    """
    누가 무엇을 몇 번 불렀는지. 실패해도 조용히 넘어간다.

    ⚠️ 매 호출마다 DB를 두드리면 느려진다. app 쪽에서 화면 한 번에
    한 번씩만 부르도록 모아서 넘긴다.
    """
    if not ready() or not uid or n <= 0:
        return
    day = datetime.now(timezone.utc).date().isoformat()
    try:
        cur = (_sb.table("user_usage").select("id,calls")
               .eq("user_id", uid).eq("day", day).eq("kind", kind)
               .limit(1).execute().data or [])
        if cur:
            _sb.table("user_usage").update(
                {"calls": int(cur[0]["calls"] or 0) + n,
                 "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", cur[0]["id"]).execute()
        else:
            _sb.table("user_usage").insert(
                {"user_id": uid, "day": day, "kind": kind, "calls": n}).execute()
    except Exception:
        pass


# ------------------------------------------------------------
# 관리자용 — service_role 키라 RLS를 통과한다
# ------------------------------------------------------------
def all_members(limit=200):
    if not ready():
        return []
    try:
        return (_sb.table("profiles").select("*")
                .order("created_at", desc=True).limit(limit).execute().data or [])
    except Exception:
        return []


def usage_by_user(days=7):
    """회원별 최근 사용량 합계 {user_id: {kind: calls}}"""
    if not ready():
        return {}
    from datetime import timedelta
    since = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    out = {}
    try:
        rows = (_sb.table("user_usage").select("user_id,kind,calls")
                .gte("day", since).limit(5000).execute().data or [])
        for r in rows:
            u = out.setdefault(r["user_id"], {})
            u[r["kind"]] = u.get(r["kind"], 0) + int(r["calls"] or 0)
    except Exception:
        pass
    return out


def recent_credit_log(limit=50):
    if not ready():
        return []
    try:
        return (_sb.table("credit_log").select("*")
                .order("created_at", desc=True).limit(limit).execute().data or [])
    except Exception:
        return []


def table_ready():
    """회원 테이블이 만들어져 있는지. (안내 문구를 띄우려고)"""
    if not ready():
        return False
    try:
        _sb.table("profiles").select("id").limit(1).execute()
        return True
    except Exception:
        return False


# ------------------------------------------------------------
# 소셜 로그인
#
# ⚠️ 네이버는 넣지 못했다. Supabase가 기본 제공하는 제공자 목록에
#    네이버가 없다 (요청 논의만 올라와 있는 상태다).
#    한국 블로거는 대부분 카카오 계정이 있으니 카카오 + 구글로 간다.
#
# ⚠️ 스트림릿에서 소셜 로그인이 까다로운 이유:
#    보통 OAuth는 돌아올 때 토큰을 주소의 # 뒤에 붙여 보낸다.
#    그런데 # 뒤는 브라우저에만 남고 서버로 오지 않아서 스트림릿이 못 읽는다.
#    다행히 supabase-py는 기본이 PKCE 방식이라 ?code=... 로 돌아온다.
#    그건 st.query_params로 읽을 수 있다.
# ------------------------------------------------------------
PROVIDERS = {
    "kakao":  ("카카오", "#FEE500", "#191600"),
    "google": ("구글",   "#FFFFFF", "#3C4043"),
}

# 무엇을 달라고 할지.
#
# ⚠️ 확인된 사실 (2026-08, supabase/supabase#36878):
#    Supabase 서버가 카카오에 account_email(이메일)을 '기본으로' 요구한다.
#    여기서 scopes를 적어줘도 그 기본값을 '대체'하지 않고 '더하기'만 하므로,
#    account_email은 우리 코드로는 뺄 수 없다.  ← 클라이언트 수정으로 못 고침
#    account_email은 비즈앱만 켤 수 있어서, 개인 개발자 앱이면 KOE205가 난다.
#    해결: 카카오 개발자 → 앱 → 일반 → 비즈니스 정보 →
#          '개인 개발자 비즈 앱 전환' (사업자등록번호 없이도 신청 가능).
#          전환 후 동의항목에서 '카카오계정(이메일)'을 켜면 끝난다.
#    아래 profile_nickname은 그대로 둔다 (닉네임은 우리가 실제로 쓴다).
#
# ⚠️ 구글은 기본값이 맞으므로 건드리지 않는다 (None이면 Supabase 기본).
#
# ⚠️ 2026-08-27 확인: 아무것도 안 보내도 Supabase가 알아서
#    account_email profile_image profile_nickname 을 붙인다.
#    여기에 profile_nickname을 또 적으면 주소에 두 번 들어간다.
#    (실제로 scope=... profile_nickname profile_nickname 이 나갔다)
#    비즈앱 전환이 끝나 account_email도 켜졌으니 이제 우리가 보탤 게 없다.
SCOPES = {
    "kakao": None,
    "google": None,
}

_VERIFIER_KEY = "supabase.auth.token-code-verifier"


def _auth_base():
    """Supabase 인증 주소. attach에서 못 받았으면 라이브러리에서 꺼낸다."""
    if _URL:
        return _URL + "/auth/v1"
    try:
        return str(_sb.auth._url).rstrip("/")
    except Exception:
        return ""


def new_verifier():
    """
    PKCE '확인코드'를 우리가 직접 만든다.

    ⚠️ 왜 직접 만드나. 라이브러리에 맡기면 부를 때마다 새로 만들어
    라이브러리 안쪽에 덮어써 버린다. 버튼을 카카오·구글 두 개 그리면
    나중에 만든 구글 것만 남아서, 카카오로 눌러도 구글 확인코드를 대게 된다
    — 실제로 카카오만 로그인이 안 되는 사고가 났다.
    우리가 하나 만들어 두 버튼에 똑같이 쓰면 돌아왔을 때 헷갈릴 일이 없다.
    """
    try:
        from supabase_auth.helpers import (generate_pkce_verifier,
                                           generate_pkce_challenge)
        v = generate_pkce_verifier()
        return v, generate_pkce_challenge(v)
    except Exception:
        import secrets
        v = secrets.token_urlsafe(64)[:96]
        c = base64.urlsafe_b64encode(
            hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
        return v, c


def oauth_url(provider, redirect_to, verifier_pair=None):
    """
    소셜 로그인 주소를 만든다. 반환 (주소|None, 확인코드|None, 메시지)

    ⚠️ 라이브러리의 sign_in_with_oauth를 쓰지 않고 주소를 직접 조립한다.
    이유는 new_verifier() 설명 참고. 주소 모양은 Supabase 문서 그대로다.
    """
    if not ready():
        return None, None, "서버에 연결되지 않았습니다."
    if provider not in PROVIDERS:
        return None, None, "지원하지 않는 로그인입니다."
    base = _auth_base()
    if not base:
        return None, None, "인증 주소를 찾지 못했습니다."
    try:
        verifier, challenge = verifier_pair or new_verifier()
        q = [("provider", provider),
             ("code_challenge", challenge),
             ("code_challenge_method", "s256")]
        if redirect_to:
            q.append(("redirect_to", redirect_to))
        sc = SCOPES.get(provider)
        if sc:
            q.append(("scopes", sc))
        return base + "/authorize?" + urlencode(q), verifier, ""
    except Exception as e:
        return None, None, _msg(e)


def exchange(code, verifier=None):
    """돌아온 code를 세션으로 바꾼다. 반환 (성공, 메시지, 사용자|None)"""
    if not ready() or not code:
        return False, "로그인 정보를 받지 못했습니다.", None
    try:
        # ⚠️ 확인코드는 인자로 그대로 넘긴다.
        #    예전에는 라이브러리 안쪽 저장소에 몰래 넣어뒀는데,
        #    그 저장소는 접속하는 사람 모두가 함께 쓰는 자리라
        #    두 사람이 동시에 로그인하면 서로 덮어쓴다.
        args = {"auth_code": code}
        if verifier:
            args["code_verifier"] = verifier
        res = _sb.auth.exchange_code_for_session(args)
        user = getattr(res, "user", None)
        if user is None:
            return False, "로그인하지 못했습니다.", None
        _touch(user.id)
        return True, "", _pack(user)
    except Exception as e:
        t = str(e).lower()
        if "code verifier" in t or "invalid request" in t or "challenge" in t:
            # ⚠️ 원문을 뒤에 붙여둔다. 이게 없어서 지난번에 원인을 못 찾고
            #    며칠을 헤맸다. 짧게라도 남겨야 화면만 보고 짚을 수 있다.
            return False, ("로그인 확인에 실패했습니다. 다시 한 번 눌러주세요.\n\n"
                           "(사유: %s)" % str(e)[:200]), None
        return False, _msg(e), None


# ------------------------------------------------------------
# 관리자
#
# ⚠️ 관리자용 아이디를 따로 만들지 않는다.
#    계정이 둘이면 비밀번호도 둘이고, 누가 무엇을 했는지도 안 남는다.
#    이미 있는 회원 계정에 '관리자' 표시만 단다.
#    첫 관리자는 SQL 한 줄로 지정한다 (회원_DB설정.sql 아래쪽 참고).
# ------------------------------------------------------------
def is_admin(uid):
    p = profile(uid)
    return bool((p or {}).get("is_admin"))


def set_admin(uid, flag=True):
    if not ready() or not uid:
        return False
    try:
        _sb.table("profiles").update({"is_admin": bool(flag)}) \
            .eq("id", uid).execute()
        return True
    except Exception:
        return False


def admin_count():
    """관리자가 몇 명인지. 0이면 아직 아무도 지정 안 된 것."""
    if not ready():
        return 0
    try:
        r = (_sb.table("profiles").select("id")
             .eq("is_admin", True).limit(50).execute().data or [])
        return len(r)
    except Exception:
        return 0
