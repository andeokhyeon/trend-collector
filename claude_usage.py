# -*- coding: utf-8 -*-
"""
Claude 사용량 · 비용 — Anthropic Admin API.

⚠️ 일반 API 키(sk-ant-api…)로는 안 된다. **Admin 키**(sk-ant-admin01-…)가 필요하고,
   그건 Claude Platform의 조직(Organization) 설정에서만 발급된다.
   개인 계정에는 조직이 없어서 발급 자체가 안 될 수 있다.
     발급: https://platform.claude.com  →  Settings → Admin keys
     넣는 곳: config.py 의 ANTHROPIC_ADMIN_KEY

키가 없으면 모든 함수가 조용히 (None, 안내문)을 돌려준다. 화면은 그대로 돈다.
"""
import sys
import requests
from datetime import datetime, timezone, timedelta

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = "https://api.anthropic.com/v1/organizations"
COST_URL = f"{BASE}/cost_report"
USAGE_URL = f"{BASE}/usage_report/messages"
VERSION = "2023-06-01"

NO_KEY = ("Admin 키가 없습니다. platform.claude.com → Settings → Admin keys 에서 "
          "발급한 뒤 config.py의 ANTHROPIC_ADMIN_KEY에 넣어주세요.")


def _key():
    try:
        import config
        return (getattr(config, "ANTHROPIC_ADMIN_KEY", "") or "").strip()
    except Exception:
        return ""


def _headers(k):
    return {"x-api-key": k, "anthropic-version": VERSION,
            "content-type": "application/json"}


def _window(days):
    end = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")


def cost(days=14):
    """
    일별 비용. 반환 (목록|None, 메시지)
    목록: [{"day": "MM-DD", "usd": 1.23}, ...]  오래된 것부터

    ⚠️ 응답의 cost는 '센트 문자열'이다. 그대로 더하면 100배가 된다.
    """
    k = _key()
    if not k:
        return None, NO_KEY
    days = max(1, min(int(days), 31))       # 하루 단위는 최대 31칸
    s, e = _window(days)
    try:
        res = requests.get(COST_URL, headers=_headers(k), timeout=12,
                           params={"starting_at": s, "ending_at": e,
                                   "bucket_width": "1d"})
    except Exception as ex:
        return None, f"연결하지 못했습니다: {ex}"
    if res.status_code == 401:
        return None, "Admin 키가 거절됐습니다. 일반 API 키를 넣지 않았는지 확인해주세요."
    if res.status_code == 403:
        return None, "이 키에는 조직 조회 권한이 없습니다. Admin 키가 맞는지 확인해주세요."
    if res.status_code != 200:
        return None, f"응답 {res.status_code} · {res.text[:150]}"
    out = []
    try:
        for row in (res.json().get("data") or []):
            cents = 0.0
            for c in (row.get("costs") or []):
                try:
                    cents += float(c.get("cost") or 0)
                except (TypeError, ValueError):
                    pass
            day = str(row.get("date") or "")[:10]
            out.append({"day": day[5:] or day, "usd": round(cents / 100.0, 4)})
    except Exception as ex:
        return None, f"응답을 읽지 못했습니다: {ex}"
    return out, ""


def tokens(days=7):
    """
    일별 토큰. 반환 (목록|None, 메시지)
    목록: [{"day","input","output","cache_read"}, ...]
    """
    k = _key()
    if not k:
        return None, NO_KEY
    days = max(1, min(int(days), 31))
    s, e = _window(days)
    try:
        res = requests.get(USAGE_URL, headers=_headers(k), timeout=12,
                           params={"starting_at": s, "ending_at": e,
                                   "bucket_width": "1d"})
    except Exception as ex:
        return None, f"연결하지 못했습니다: {ex}"
    if res.status_code != 200:
        return None, f"응답 {res.status_code} · {res.text[:150]}"
    out = []
    try:
        for row in (res.json().get("data") or []):
            inp = outp = cr = 0
            # 모델별로 나뉘어 오기도, 평평하게 오기도 한다. 둘 다 받는다.
            buckets = row.get("models")
            if isinstance(buckets, dict):
                vals = buckets.values()
            elif isinstance(row.get("results"), list):
                vals = row["results"]
            else:
                vals = [row]
            for v in vals:
                if not isinstance(v, dict):
                    continue
                inp += int(v.get("input_tokens") or 0)
                outp += int(v.get("output_tokens") or 0)
                cr += int(v.get("cache_read_input_tokens") or 0)
            day = str(row.get("date") or "")[:10]
            out.append({"day": day[5:] or day, "input": inp,
                        "output": outp, "cache_read": cr})
    except Exception as ex:
        return None, f"응답을 읽지 못했습니다: {ex}"
    return out, ""
