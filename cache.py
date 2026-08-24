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
SAFE_RATIO = 0.90

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