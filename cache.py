"""
공용 캐시 + API 사용량 관리.

⚠️ 왜 필요한가
지금은 사용자마다 따로 네이버를 부른다. 100명이 '제습기'를 검색하면
같은 요청이 200번 나간다. 결과를 Supabase에 하루 저장해두면 2번으로 끝난다.
블로거들이 찾는 키워드는 상당히 겹치기 때문에 효과가 크다.

여기에 하루 사용량을 세어두고, 한도에 가까워지면 스스로 멈춘다.
한도를 넘겨도 계정이 막히거나 요금이 나오지는 않지만(429가 뜨고 자정에 초기화),
조회가 안 되는 상태로 방치되는 것보다는 미리 아는 편이 낫다.
"""

import json
import time
from datetime import datetime, timezone, timedelta

# 하루 한도 (네이버 검색 API 기준). 여유를 두고 90%에서 스스로 멈춘다.
DAILY_LIMIT = 25000
SAFE_RATIO = 0.70          # 이 비율에 닿으면 스스로 멈춘다
SEED_RATIO = 0.60          # 씨앗 채우기는 여기까지만 (일반 조회 몫을 남긴다)

_supabase = None
_mem = {}          # 프로세스 안 캐시 (같은 실행 중 반복 호출 방지)
_usage_cache = {"day": None, "calls": 0, "checked": 0}


def attach(supabase_client):
    """app.py / collector.py가 자기 Supabase 연결을 넘겨준다."""
    global _supabase
    _supabase = supabase_client


def _today():
    return datetime.now(timezone.utc).date().isoformat()


# ------------------------------------------------------------
# 캐시
# ------------------------------------------------------------
def get(key, ttl_hours=24):
    """캐시에서 꺼낸다. 없거나 오래됐으면 None."""
    hit = _mem.get(key)
    if hit and time.time() - hit[0] < ttl_hours * 3600:
        return hit[1]

    if _supabase is None:
        return None
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=ttl_hours)).isoformat()
        res = (_supabase.table("api_cache").select("payload")
               .eq("cache_key", key).gte("created_at", cutoff)
               .limit(1).execute())
        if res.data:
            val = res.data[0]["payload"]
            if isinstance(val, str):
                val = json.loads(val)
            _mem[key] = (time.time(), val)
            return val
    except Exception:
        pass
    return None


def put(key, value):
    """캐시에 넣는다. 실패해도 조용히 넘어간다 (캐시는 있으면 좋은 것)."""
    _mem[key] = (time.time(), value)
    if _supabase is None:
        return value
    try:
        _supabase.table("api_cache").upsert({
            "cache_key": key,
            "payload": value,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception:
        pass
    return value


# ------------------------------------------------------------
# 사용량
# ------------------------------------------------------------
def add_calls(n=1):
    """실제로 네이버를 부른 횟수를 기록한다."""
    if _supabase is None or n <= 0:
        return
    day = _today()
    try:
        res = (_supabase.table("api_usage").select("calls")
               .eq("day", day).limit(1).execute())
        cur = res.data[0]["calls"] if res.data else 0
        _supabase.table("api_usage").upsert(
            {"day": day, "calls": cur + n}).execute()
        _usage_cache.update(day=day, calls=cur + n, checked=time.time())
    except Exception:
        pass


def usage(force=False):
    """
    오늘 얼마나 썼는지. 60초간은 기억해둔 값을 쓴다.
    반환: {"calls", "limit", "pct", "remaining", "blocked"}
    """
    day = _today()
    if (not force and _usage_cache["day"] == day
            and time.time() - _usage_cache["checked"] < 60):
        calls = _usage_cache["calls"]
    else:
        calls = 0
        if _supabase is not None:
            try:
                res = (_supabase.table("api_usage").select("calls")
                       .eq("day", day).limit(1).execute())
                calls = res.data[0]["calls"] if res.data else 0
            except Exception:
                calls = _usage_cache["calls"] if _usage_cache["day"] == day else 0
        _usage_cache.update(day=day, calls=calls, checked=time.time())

    pct = calls / DAILY_LIMIT * 100
    return {
        "calls": calls,
        "limit": DAILY_LIMIT,
        "pct": round(pct, 1),
        "remaining": max(0, DAILY_LIMIT - calls),
        "blocked": calls >= DAILY_LIMIT * SAFE_RATIO,
    }


def can_call(n=1):
    """이만큼 더 불러도 되는지."""
    u = usage()
    return u["calls"] + n < DAILY_LIMIT * SAFE_RATIO


def reset_time():
    """언제 다시 풀리는지 (한국 시간 자정)."""
    kst = datetime.now(timezone(timedelta(hours=9)))
    tomorrow = (kst + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    left = tomorrow - kst
    h, m = divmod(int(left.total_seconds() // 60), 60)
    return f"{h}시간 {m}분 후"


# ------------------------------------------------------------
# 키워드 풀 — 검색량을 미리 쌓아두는 곳
#
# 네이버 키워드도구는 한 번 호출에 연관 키워드를 20개씩 돌려준다.
# 지금까지 1개만 쓰고 버리던 걸 전부 저장한다.
# 문서수는 여기 넣지 않는다 (키워드마다 따로 불러야 해서 미리 못 쌓는다).
# ------------------------------------------------------------

POOL_FRESH_DAYS = 30       # 검색량은 월 단위 집계라 30일이면 충분
DOCS_FRESH_DAYS = 30       # 문서수도 천천히 변한다


def pool_get(keyword, fresh_days=POOL_FRESH_DAYS):
    """풀에서 키워드 하나를 꺼낸다. 없거나 낡았으면 None."""
    if _supabase is None:
        return None
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=fresh_days)).isoformat()
        res = (_supabase.table("keyword_pool").select("*")
               .eq("keyword", keyword.strip())
               .gte("updated_at", cutoff).limit(1).execute())
        return res.data[0] if res.data else None
    except Exception:
        return None


def pool_put_many(rows):
    """
    여러 키워드를 한꺼번에 저장한다.
    rows: [{"keyword","monthly_pc","monthly_mobile","comp_level","pl_avg_depth"}]
    반환: 저장된 개수
    """
    if _supabase is None or not rows:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    payload = []
    seen = set()
    for r in rows:
        kw = (r.get("keyword") or "").strip()
        if not kw or kw in seen:
            continue
        seen.add(kw)
        payload.append({
            "keyword": kw,
            "monthly_pc": int(r.get("monthly_pc") or 0),
            "monthly_mobile": int(r.get("monthly_mobile") or 0),
            "comp_level": r.get("comp_level") or "-",
            "pl_avg_depth": int(r.get("pl_avg_depth") or 0),
            "updated_at": now,
        })
    if not payload:
        return 0
    try:
        # 한 번에 너무 많이 보내면 실패하므로 나눠서 저장
        saved = 0
        for i in range(0, len(payload), 500):
            _supabase.table("keyword_pool").upsert(
                payload[i:i + 500], on_conflict="keyword").execute()
            saved += len(payload[i:i + 500])
        return saved
    except Exception as e:
        print(f"키워드 풀 저장 실패: {e}")
        return 0


def pool_put_docs(keyword, total_docs):
    """문서수를 잰 김에 풀에도 남겨둔다."""
    if _supabase is None or total_docs is None:
        return
    try:
        _supabase.table("keyword_pool").upsert({
            "keyword": keyword.strip(),
            "blog_total_docs": int(total_docs),
            "docs_checked_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="keyword").execute()
    except Exception:
        pass


def pool_get_docs(keyword, fresh_days=DOCS_FRESH_DAYS):
    """풀에 저장된 문서수를 꺼낸다. 없거나 낡았으면 None."""
    if _supabase is None:
        return None
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=fresh_days)).isoformat()
        res = (_supabase.table("keyword_pool")
               .select("blog_total_docs, docs_checked_at")
               .eq("keyword", keyword.strip())
               .not_.is_("docs_checked_at", "null")
               .gte("docs_checked_at", cutoff).limit(1).execute())
        if res.data and res.data[0].get("blog_total_docs") is not None:
            return int(res.data[0]["blog_total_docs"])
    except Exception:
        pass
    return None


def pool_size():
    """풀에 몇 개가 쌓였는지."""
    if _supabase is None:
        return 0
    try:
        res = _supabase.table("keyword_pool").select(
            "keyword", count="exact").limit(1).execute()
        return res.count or 0
    except Exception:
        return 0


def can_seed(n=1):
    """씨앗 채우기용 여유가 있는지 (일반 조회 몫을 남겨둔다)."""
    u = usage()
    return u["calls"] + n < DAILY_LIMIT * SEED_RATIO