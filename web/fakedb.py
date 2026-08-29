# -*- coding: utf-8 -*-
"""Supabase 흉내 — 실제 스키마와 같은 모양의 가짜 데이터를 돌려준다."""
import random
from datetime import datetime, timezone, timedelta
random.seed(11)
NOW = datetime.now(timezone.utc)

KWS = ["캠핑의자", "제주도맛집", "롱패딩", "에어프라이어", "점심메뉴추천",
       "무주반딧불축제", "배당주", "대출", "삼성전자", "주말날씨"]

_EVENTS = [("추석","공휴일"),("처서","절기"),("말복","절기"),
           ("재산세 납부","세무/마감"),("종합소득세 신고","세무/마감"),
           # ⚠️ 실제 청약 공고 이름은 이만큼 길다 — 모바일 표가 밀려나는
           #    2026-08-28 버그를 재현하려고 일부러 긴 이름을 넣어둔다.
           ("힐스테이트 더 운정 라피아노 오피스텔 잔여세대 무순위 청약","청약"),
           ("래미안 원페를라 청약","청약"),("무주반딧불축제","축제/행사"),
           ("성수동 야시장","공연/행사"),("개천절","공휴일"),("한글날","공휴일")]


def _trend_rows():
    rows = []
    for i, k in enumerate(KWS):
        for src in ("google_trend", "golden_time", "naver_news",
                    "weekly_event", "naver_monthly"):
            rows.append({
                "keyword": (k if src != "weekly_event" else _EVENTS[i % len(_EVENTS)][0]),
                "source": src,
                "monthly_pc": random.randint(100, 20000),
                "monthly_mobile": random.randint(100, 90000),
                "comp_level": (random.choice(["높음","중간","낮음"]) if src!="weekly_event" else _EVENTS[i % len(_EVENTS)][1]),
                "blog_total_docs": random.randint(100, 300000),
                "blog_competition": random.randint(0, 900),
                "comp_ratio": round(random.uniform(0.05, 12), 2),
                "comp_grade": random.choice(["최고", "좋음", "보통", "나쁨"]),
                "rise_score": (random.choice([0, 12, 51, 82]) if src=="weekly_event"
                               else random.randint(0, 90)),
                "opportunity": random.randint(10, 95),
                "keyword_category": random.choice(["트렌드", "세부"]),
                "event_date": (NOW + timedelta(days=random.randint(1, 25))).strftime("%Y-%m-%d"),
                "created_at": (NOW - timedelta(minutes=random.randint(1, 300))).isoformat(),
            })
    return rows

def _tracked():
    return [{"id": i, "keyword": k, "has_post": i % 3 == 0,
             "created_at": (NOW - timedelta(days=20)).isoformat()}
            for i, k in enumerate(KWS[:8])]

def _history():
    out = []
    for i, k in enumerate(KWS[:8]):
        for d in range(20):
            out.append({
                "keyword": k,
                "my_rank": random.choice([None, 5, 12, 28, 45, 90]),
                "total_search": random.randint(1000, 90000),
                "blog_total_docs": random.randint(1000, 200000),
                "recent_docs": random.randint(0, 900),
                "comp_ratio": round(random.uniform(0.1, 9), 2),
                "created_at": (NOW - timedelta(days=20 - d)).isoformat(),
            })
    return out

class Res:
    def __init__(self, data): self.data = data

class Q:
    def __init__(self, table):
        self.t = table; self._eq = {}; self._ins = None; self._upd = None
    def select(self, *a, **k):
        # 진짜 DB처럼, 고른 열만 돌려주게 한다.
        # (열 하나 빠뜨리면 화면이 깨지는지 여기서 잡힌다)
        self._cols = None
        if a and isinstance(a[0], str) and a[0] != "*":
            self._cols = [c.strip() for c in a[0].split(",") if c.strip()]
        return self
    def order(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def eq(self, col=None, val=None, *a, **k):
        if not hasattr(self, "_eq"): self._eq = {}
        if col is not None: self._eq[col] = val
        return self
    def limit(self, *a, **k): return self
    def insert(self, rows=None, *a, **k):
        self._ins = rows if isinstance(rows, dict) else (rows or [{}])[0]
        return self
    def update(self, vals=None, *a, **k):
        self._upd = vals or {}
        return self
    def delete(self, *a, **k): return self
    def _trim(self, rows):
        cols = getattr(self, "_cols", None)
        if not cols:
            return rows
        missing = set(cols) - set(rows[0]) if rows else set()
        if missing:
            raise Exception("42703: column %s does not exist"
                            % ", ".join(sorted(missing)))
        return [{c: r.get(c) for c in cols} for r in rows]

    def execute(self):
        if self.t == "trends_master": return Res(self._trim(_trend_rows()))
        if self.t == "tracked_keywords": return Res(_tracked())
        if self.t == "tracking_history": return Res(_history())
        if self.t == "profiles":
            if getattr(self, "_ins", None) is not None:
                row = dict(self._ins); self._ins = None
                PROFILES[row["id"]] = {"plan": "free", "credits": 3,
                                       "is_admin": False, "last_seen": None,
                                       "created_at": "2026-08-29T00:00:00Z",
                                       **row}
                return Res([row])
            if getattr(self, "_upd", None) is not None:
                for pid in (self._eq.get("id"),) if self._eq.get("id") else PROFILES:
                    if pid in PROFILES: PROFILES[pid].update(self._upd)
                self._upd = None
                return Res([])
            rows = list(PROFILES.values())
            for c, v in (self._eq or {}).items():
                rows = [r for r in rows if r.get(c) == v]
            return Res(rows)
        if self.t == "credit_log":
            if getattr(self, "_ins", None) is not None:
                CREDIT_LOG.append(self._ins); self._ins = None; return Res([])
            return Res(list(reversed(CREDIT_LOG)))
        if self.t == "user_usage":
            if getattr(self, "_ins", None) is not None:
                r = dict(self._ins); r.setdefault("id", len(USER_USAGE) + 1)
                USER_USAGE.append(r); self._ins = None; return Res([])
            if getattr(self, "_upd", None) is not None:
                for r in USER_USAGE:
                    if r.get("id") == self._eq.get("id"): r.update(self._upd)
                self._upd = None; return Res([])
            rows = list(USER_USAGE)
            for c, v in (self._eq or {}).items():
                rows = [r for r in rows if r.get(c) == v]
            return Res(rows)
        return Res([])

class Client:
    def table(self, name): return Q(name)

    @property
    def auth(self): return _Auth()

def create_client(url, key): return Client()


# ── 가짜 Supabase Auth ───────────────────────────────────────
USERS = {}          # email -> {"id","password"}
PROFILES = {}       # id -> dict
CREDIT_LOG = []
USER_USAGE = []


class _Obj:
    def __init__(s, **kw): s.__dict__.update(kw)


class _Auth:
    def sign_up(s, d):
        e, pw = d.get("email", ""), d.get("password", "")
        if e in USERS:
            raise Exception("User already registered")
        if len(pw) < 6:
            raise Exception("Password should be at least 6 characters")
        if "@" not in e:
            raise Exception("Unable to validate email address")
        uid = "u%03d" % (len(USERS) + 1)
        USERS[e] = {"id": uid, "password": pw}
        PROFILES[uid] = {"id": uid, "email": e,
                         "nickname": e.split("@")[0], "plan": "free",
                         "credits": 30, "is_admin": False,
                         "created_at": "2026-08-27T00:00:00Z",
                         "last_seen": None}
        return _Obj(user=_Obj(id=uid, email=e), session=_Obj(access_token="t"))

    def sign_in_with_password(s, d):
        e, pw = d.get("email", ""), d.get("password", "")
        u = USERS.get(e)
        if not u or u["password"] != pw:
            raise Exception("Invalid login credentials")
        return _Obj(user=_Obj(id=u["id"], email=e), session=_Obj(access_token="t"))

    def sign_out(s): return None

    # 소셜 로그인 흉내
    _store = {}

    def sign_in_with_oauth(s, d):
        pv = d.get("provider", "?")
        s._store["supabase.auth.token-code-verifier"] = "v-" + pv
        return _Obj(provider=pv,
                    url=f"https://x.supabase.co/auth/v1/authorize?provider={pv}"
                        "&code_challenge=abc")

    @property
    def _storage(s):
        outer = s

        class _S:
            def get_item(x, k): return outer._store.get(k)
            def set_item(x, k, v): outer._store[k] = v
        return _S()

    def exchange_code_for_session(s, d):
        code = d.get("auth_code")
        if not code or code == "bad":
            raise Exception("invalid request: code verifier should be non-empty")
        # ⚠️ 진짜 Supabase처럼, 확인코드를 안 대면 통과시키지 않는다.
        v = d.get("code_verifier") or s._store.get(
            "supabase.auth.token-code-verifier")
        if not v or len(str(v)) < 40:
            raise Exception("invalid request: code verifier should be non-empty "
                            "(got %r)" % (v,))
        e = f"social{len(USERS)+1}@kakao.com"
        if e not in USERS:
            uid = "u%03d" % (len(USERS) + 1)
            USERS[e] = {"id": uid, "password": "-"}
            PROFILES[uid] = {"id": uid, "email": e, "nickname": e.split("@")[0],
                             "plan": "free", "credits": 30, "is_admin": False,
                             "created_at": "2026-08-27T00:00:00Z",
                             "last_seen": None}
        u = USERS[e]
        return _Obj(user=_Obj(id=u["id"], email=e), session=_Obj(access_token="t"))
