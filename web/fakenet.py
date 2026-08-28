# -*- coding: utf-8 -*-
"""
개발용 가짜 네이버.

⚠️ 왜 있나. 진짜 API 키는 사용자 PC의 .env에만 있고, 여기(개발 환경)서
   진짜 네이버를 두드리면 한도만 닳는다. 화면을 만드는 동안에는
   그럴싸한 가짜 응답이면 충분하다. 배포할 때는 이 파일을 부르지 않는다.
   (main.py 맨 위에서 KH_FAKE=1 일 때만 심는다)
"""
import random
import sys
import types
from datetime import datetime, timedelta, timezone

random.seed(5)


class R:
    def __init__(s, c, p, t=""):
        s.status_code = c; s._p = p; s.text = t
        s.content = t.encode("utf-8") if isinstance(t, str) else (t or b"")
    def json(s):
        return s._p


def _blog(**kw):
    return {"total": random.randint(500, 300000),
            "items": [{"title": "캠핑의자 추천 <b>정리</b>",
                       "bloggername": "블로거%d" % i,
                       "link": "https://blog.naver.com/user%d/1" % i,
                       "postdate": (datetime.now() - timedelta(
                           days=random.randint(0, 900))).strftime("%Y%m%d"),
                       "description": "본문 요약"} for i in range(30)]}


def _kwtool(**kw):
    return {"keywordList": [{"relKeyword": f"캠핑의자{i}",
                             "monthlyPcQcCnt": random.randint(0, 9000),
                             "monthlyMobileQcCnt": random.randint(0, 50000),
                             "compIdx": "중간",
                             "plAvgDepth": random.randint(0, 15)}
                            for i in range(30)]}


def fget(url, **kw):
    # 실제 config는 API HUB 주소(apigw.ntruss.com)를 쓴다 — 그것도 받아준다
    if ("search/blog" in url or "openapi.naver.com/v1/search" in url
            or "apigw.ntruss.com" in url or "/blog" in url):
        return R(200, _blog())
    if "keywordstool" in url:
        return R(200, _kwtool())
    if "ac.search.naver" in url:
        return R(200, {"items": [[["캠핑의자 추천"], ["캠핑의자 경량"]]]})
    if "rss.blog.naver" in url:
        # 개발용 가짜 RSS — 최근 90일에 걸쳐 글 20개
        items = []
        for i in range(20):
            d = datetime.now(timezone.utc) - timedelta(days=i * 4 + 1)
            items.append(
                "<item><title>포스팅 %d</title>"
                "<pubDate>%s</pubDate><link>https://blog.naver.com/x/%d</link>"
                "</item>" % (i, d.strftime("%a, %d %b %Y %H:%M:%S +0900"), i))
        xml = ("<?xml version='1.0'?><rss><channel>"
               + "".join(items) + "</channel></rss>")
        return R(200, {}, xml)
    return R(404, {})


def fpost(url, **kw):
    if "datalab" in url:
        end = datetime.now(timezone.utc) + timedelta(hours=9)
        k = ((kw.get("json") or {}).get("keywordGroups") or [{}])[0].get(
            "keywords", [""])[0]
        h = sum(ord(c) for c in k)
        spike_at = 350 - (h % 20)
        ramp = 8 + (h % 10)
        data = []
        for i in range(365, -1, -1):
            base = 6 + (h % 5)
            if 0 <= (i - spike_at) <= ramp:
                v = base + (base * 7) * (1 - (i - spike_at) / ramp) ** 2
            else:
                v = base + random.uniform(-1, 1)
            data.append({"period": (end - timedelta(days=i)).strftime("%Y-%m-%d"),
                         "ratio": round(max(0.5, v), 2)})
        return R(200, {"results": [{"title": "kw", "data": data}]})
    if "exposure-minimum-bid" in url:
        items = kw.get("json", {}).get("items", [])
        return R(200, {"estimate": [{"keyword": k, "bid": random.randint(90, 2600)}
                                    for k in items]})
    return R(404, {})


def install():
    # 가짜 열쇠 — naver_api가 '키 없음'으로 조회를 건너뛰지 않게 한다.
    import os
    os.environ.setdefault("NAVER_API_KEY", "k")
    os.environ.setdefault("NAVER_SECRET_KEY", "s")
    os.environ.setdefault("NAVER_CUSTOMER_ID", "1")
    os.environ.setdefault("NAVER_HUB_CLIENT_ID", "c")
    os.environ.setdefault("NAVER_HUB_CLIENT_SECRET", "cs")
    os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "k")
    req = types.ModuleType("requests")
    req.get, req.post = fget, fpost

    class _E(Exception):
        pass
    req.exceptions = types.SimpleNamespace(RequestException=_E)
    sys.modules["requests"] = req
