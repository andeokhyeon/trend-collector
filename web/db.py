# -*- coding: utf-8 -*-
"""
DB 연결 + 수집 데이터 읽기 (app.py load_data 이식).

⚠️ 스트림릿의 @st.cache_data(ttl=900) 대신 시간표 딕셔너리로 캐시한다.
   서버는 접속자들이 프로세스 하나를 나눠 쓰므로 효과는 같다.
"""
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

if os.environ.get("KH_FAKE") == "1":
    from fakedb import create_client
else:
    from supabase import create_client

from config import SUPABASE_URL, SUPABASE_KEY

_client = None


def client():
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


_CACHE = {}


def _memo(key, ttl, fn):
    hit = _CACHE.get(key)
    now = time.time()
    if hit and now - hit[1] < ttl:
        return hit[0]
    val = fn()
    _CACHE[key] = (val, now)
    return val


def load_data():
    """최근 30일치 수집 원본. 15분 캐시. (app.py load_data와 같은 계산)"""
    return _memo("load_data", 900, _load_data)


def _load_data():
    try:
        wide_start = datetime.now(timezone.utc) - timedelta(days=30)
        _COLS = ("keyword,source,monthly_pc,monthly_mobile,comp_level,"
                 "comp_grade,comp_ratio,rise_score,pl_avg_depth,"
                 "blog_total_docs,blog_competition,opportunity,"
                 "keyword_category,event_date,created_at")
        try:
            res = (client().table("trends_master").select(_COLS)
                   .gte("created_at", wide_start.isoformat())
                   .order("created_at", desc=True).limit(20000).execute())
        except Exception:
            res = (client().table("trends_master").select("*")
                   .gte("created_at", wide_start.isoformat())
                   .order("created_at", desc=True).limit(20000).execute())
        df = pd.DataFrame(res.data)
        if df.empty:
            return pd.DataFrame()
        df['created_at_dt'] = pd.to_datetime(df['created_at'], utc=True,
                                             errors='coerce')
        df['총 검색량'] = df['monthly_pc'] + df['monthly_mobile']
        defaults = {
            'rise_score': 0, 'pl_avg_depth': 0, 'blog_competition': 0,
            'blog_total_docs': 0, 'comp_ratio': 0, 'comp_grade': '정보없음',
            'event_date': None, 'keyword_category': None,
        }
        for col, default in defaults.items():
            if col not in df.columns:
                df[col] = default
            if default is not None:
                df[col] = df[col].fillna(default)

        def volume_grade(total):
            if total < 500:
                return "매우낮음"
            if total < 5000:
                return "낮음"
            if total < 20000:
                return "보통"
            if total < 100000:
                return "높음"
            return "매우높음"

        df['검색량 등급'] = df['총 검색량'].apply(volume_grade)
        if 'comp_level' in df.columns:
            no_data = (df['source'] == 'google_trend') & (df['comp_level'] == '-')
            df.loc[no_data, '검색량 등급'] = "정보없음"
        df.loc[df['source'] == 'naver_news', '검색량 등급'] = "이슈"
        return df
    except Exception:
        return pd.DataFrame()


def latest_snapshot(df_source, hours=None):
    """(기간 제한 후) 키워드별 가장 최근 값만."""
    d = df_source
    if hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        d = d[d['created_at_dt'] >= cutoff]
    if d.empty:
        return d
    return (d.sort_values('created_at_dt', ascending=False)
            .drop_duplicates(subset='keyword', keep='first'))


def freshness():
    """'마지막 수집 N분 전' — 상단 표시용."""
    df = load_data()
    if df.empty:
        return ""
    last = df['created_at_dt'].max()
    mins = int((datetime.now(timezone.utc) - last).total_seconds() // 60)
    return f"{mins}분 전" if mins < 120 else f"{mins // 60}시간 전"


def cached_min_bids(keywords):
    """광고 최소 입찰가 (6시간 캐시 — app.py와 동일)."""
    key = "bids:" + "|".join(sorted(keywords))

    def _fn():
        from naver_api import get_min_bids
        try:
            return get_min_bids(list(keywords)) or {}
        except Exception:
            return {}
    return _memo(key, 6 * 3600, _fn)
