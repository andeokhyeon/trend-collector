"""
네이버 API 공용 모듈.  [VERSION 2026-08-21-a]

collector.py(수집기)와 app.py(대시보드)가 함께 쓴다.
app.py에서도 이 모듈을 import하면, 미리 수집된 데이터를 보여주는 것뿐 아니라
사용자가 입력한 키워드를 '그 자리에서 실시간 분석'하는 기능을 만들 수 있다.
(블랙키위/키워드마스터/판다랭크의 핵심 UX가 바로 이 실시간 조회다)
"""

import time
import base64
import hmac
import hashlib
import requests

MODULE_VERSION = "2026-08-25-admin"

# --- 설정은 config.py 한 곳에서 읽는다 (키를 코드에 두지 않는다) ---
from config import (
    NAVER_API_KEY, NAVER_SECRET_KEY, NAVER_CUSTOMER_ID, NAVER_BASE_URL,
    NAVER_HUB_CLIENT_ID, NAVER_HUB_CLIENT_SECRET, NAVER_HUB_BLOG_URL,
    USE_AUTOCOMPLETE,
)


def get_naver_headers(method, uri):
    timestamp = str(int(time.time() * 1000))
    signature = hmac.new(
        NAVER_SECRET_KEY.strip().encode("utf-8"),
        f"{timestamp}.{method}.{uri}".encode("utf-8"),
        hashlib.sha256
    ).digest()
    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": NAVER_API_KEY.strip(),
        "X-Customer": str(NAVER_CUSTOMER_ID).strip(),
        "X-Signature": base64.b64encode(signature).decode("utf-8")
    }


def get_naver_stat(keyword):
    """키워드의 월간 검색량(PC/모바일) 및 광고경쟁 지표 조회."""
    path = "/keywordstool"
    headers = get_naver_headers("GET", path)
    params = {"hintKeywords": keyword.strip(), "showDetail": "1"}
    try:
        _count_call()
        res = requests.get(NAVER_BASE_URL + path, params=params, headers=headers, timeout=10)
        if res.status_code == 200:
            kw_list = res.json().get("keywordList", [])
            if kw_list:
                matched = kw_list[0]
                pc_val = _to_int(matched.get('monthlyPcQcCnt'))
                mob_val = _to_int(matched.get('monthlyMobileQcCnt'))

                # plAvgDepth: 그 키워드에 붙는 평균 광고 개수 (CPC 대리 지표)
                pl_depth = matched.get('plAvgDepth')
                try:
                    pl_depth_val = int(float(pl_depth))
                except (TypeError, ValueError):
                    pl_depth_val = 0

                return {
                    "monthly_pc": pc_val,
                    "monthly_mobile": mob_val,
                    "comp_level": matched.get('compIdx', '중간'),
                    "pl_avg_depth": pl_depth_val
                }
    except Exception:
        pass
    return {"monthly_pc": 0, "monthly_mobile": 0, "comp_level": "-", "pl_avg_depth": 0}


def _to_int(v):
    """
    네이버 키워드도구는 검색량을 항상 숫자로 주지 않는다.
    검색량이 아주 적으면 "< 10" 같은 문자열을 주기 때문에,
    isdigit()만 쓰면 이런 값이 전부 0이 되어 연관 키워드가 통째로 걸러진다.
    숫자만 뽑아내서 해석한다.
    """
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    digits = re.sub(r"[^0-9]", "", str(v))
    return int(digits) if digits else 0


def get_related_keywords(keyword, limit=15):
    """
    연관(롱테일) 키워드 확장용.
    keywordstool은 한 번 호출로 연관키워드를 수십 개 돌려주므로 그걸 모두 활용한다.
    """
    path = "/keywordstool"
    headers = get_naver_headers("GET", path)
    params = {"hintKeywords": keyword.strip(), "showDetail": "1"}
    related = []
    try:
        _count_call()
        res = requests.get(NAVER_BASE_URL + path, params=params, headers=headers, timeout=10)
        if res.status_code == 200:
            kw_list = res.json().get("keywordList", [])
            for item in kw_list[:limit]:
                pc_val = _to_int(item.get('monthlyPcQcCnt'))
                mob_val = _to_int(item.get('monthlyMobileQcCnt'))
                related.append({
                    "keyword": item.get("relKeyword", "").strip(),
                    "monthly_pc": pc_val,
                    "monthly_mobile": mob_val,
                    "comp_level": item.get('compIdx', '중간')
                })
    except Exception as e:
        print(f"연관키워드 조회 실패({keyword}): {e}")
    return related


def get_blog_doc_count(keyword):
    """
    💡 핵심 신규 지표: 그 키워드로 이미 발행된 '전체 블로그 문서 수'.

    블랙키위의 '콘텐츠 포화도', 키워드마스터의 '문서수'에 해당하는 값이다.
    NAVER API HUB 블로그 검색 응답의 total 필드가 바로 이 값이라,
    추가 키 발급 없이 지금 가진 인증정보로 바로 얻을 수 있다.
    실패 시 None (호출부에서 건너뜀).
    """
    if not NAVER_HUB_CLIENT_ID or not NAVER_HUB_CLIENT_SECRET:
        return None

    # 풀에 최근에 잰 값이 있으면 다시 부르지 않는다
    if _shared is not None:
        cached_docs = _shared.pool_get_docs(keyword)
        if cached_docs is not None:
            return cached_docs

    headers = {
        "X-NCP-APIGW-API-KEY-ID": NAVER_HUB_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NAVER_HUB_CLIENT_SECRET,
    }
    # ⚠️ sort를 반드시 맞춰야 한다.
    # 네이버 블로그 검색은 정렬 방식에 따라 total 값이 크게 달라진다.
    # (sim은 관련도 높은 문서만, date는 훨씬 넓게 집계)
    # get_blog_stats가 date를 쓰므로 여기도 date로 통일한다.
    # 통일하지 않으면 같은 키워드인데 회차마다 문서수가 수십 배 튀어
    # '글이 2500% 늘었다' 같은 엉뚱한 결과가 나온다.
    params = {"query": keyword, "display": 1, "sort": "date"}
    try:
        _count_call()
        res = requests.get(NAVER_HUB_BLOG_URL, headers=headers, params=params, timeout=5)
        if res.status_code == 200:
            total = int(res.json().get("total", 0))
            if _shared is not None:
                _shared.pool_put_docs(keyword, total)
            return total
        else:
            print(f"블로그 문서수 조회 오류(status {res.status_code}): {res.text[:150]}")
    except Exception as e:
        print(f"블로그 문서수 조회 실패({keyword}): {e}")
    return None


def ad_density_pct(pl_avg_depth):
    """
    광고 경쟁도(plAvgDepth)를 0~100%로 환산한다.

    plAvgDepth는 '그 키워드에 평균 몇 개의 광고가 붙는가'인데,
    숫자 9가 높은 건지 낮은 건지 감이 안 온다.
    네이버 검색 결과에 붙는 광고는 최대 15개 안팎이므로 이를 기준으로 환산한다.
    """
    try:
        d = float(pl_avg_depth or 0)
    except (TypeError, ValueError):
        return 0, "없음"
    pct = int(min(100, max(0, d / 15 * 100)))
    if pct >= 80:
        label = "매우 치열"
    elif pct >= 55:
        label = "치열"
    elif pct >= 30:
        label = "보통"
    elif pct > 0:
        label = "한산"
    else:
        label = "없음"
    return pct, label


def calc_competition(total_search, doc_count):
    """
    💡 진짜 '경쟁률' 계산: 문서수 ÷ 월간검색량.

    지금까지 대시보드의 '경쟁 정도'는 검색량만 보고 매겨서, 사실상 경쟁률이
    아니라 인기도였다. (검색량 많다고 경쟁이 센 게 아니다)
    비율이 낮을수록 = 찾는 사람에 비해 쓴 글이 적다 = 뚫기 좋은 키워드.

    반환: (비율, 등급문자열)
    """
    if not total_search or total_search <= 0:
        return None, "검색량없음"
    if doc_count is None:
        return None, "정보없음"

    ratio = doc_count / total_search
    if ratio < 0.1:
        grade = "최고"
    elif ratio < 0.5:
        grade = "좋음"
    elif ratio < 2:
        grade = "보통"
    elif ratio < 10:
        grade = "나쁨"
    else:
        grade = "최악"
    return round(ratio, 2), grade


# ============================================================
# 호출 통합 계층
#
# 같은 API에 같은 파라미터로 두 번 요청하던 부분을 하나로 묶는다.
#  · get_naver_stat 과 get_related_keywords → 둘 다 /keywordstool 동일 요청
#  · get_blog_doc_count 와 get_recent_doc_count → 둘 다 블로그 검색이고,
#    최신순 첫 페이지 응답에 total(누적 문서수)이 이미 들어 있다
# 결과적으로 키워드 1건당 4회 → 2회로 줄어든다.
# ============================================================

_CALL_CACHE = {}
_CACHE_TTL = 1800  # 30분 (프로세스 안 임시 캐시)

# 공용 캐시. app.py / collector.py가 cache.attach()로 Supabase를 물려주면
# 사용자끼리 결과를 나눠 쓴다. 없으면 프로세스 안 캐시만 쓴다.
try:
    import cache as _shared
except Exception:
    _shared = None


def _key(k):
    return "|".join(str(p) for p in k) if isinstance(k, (tuple, list)) else str(k)


def _cache_get(key):
    k = _key(key)
    hit = _CALL_CACHE.get(k)
    if hit and time.time() - hit[0] <= _CACHE_TTL:
        return hit[1]
    if _shared is not None:
        val = _shared.get(k, ttl_hours=24)
        if val is not None:
            _CALL_CACHE[k] = (time.time(), val)
            return val
    return None


def _cache_put(key, val):
    k = _key(key)
    _CALL_CACHE[k] = (time.time(), val)
    if _shared is not None:
        _shared.put(k, val)
    return val


def _count_call(n=1):
    """실제로 네이버를 부른 횟수만 기록한다 (캐시로 해결된 건 세지 않는다)."""
    if _shared is not None:
        _shared.add_calls(n)


def _quota_ok(n=1):
    """한도에 여유가 있는지. 공용 캐시가 없으면 항상 통과."""
    return _shared.can_call(n) if _shared is not None else True


# 붙여 쓴 말을 쪼갤 때 쓰는 꼬리말.
# ⚠️ 예전에는 단서가 없으면 글자 수 절반으로 잘랐는데,
# '현대노조' → '현대노' 같은 말이 안 되는 조각이 나왔다.
# 사전에 있는 꼬리말만 떼고, 없으면 쪼개지 않는다.
_TAIL_WORDS = (
    "축제", "박람회", "페스티벌", "행사", "대회", "전시회", "콘서트",
    "추천", "후기", "리뷰", "순위", "비교", "가격", "최저가", "할인",
    "예약", "숙소", "맛집", "카페", "여행", "코스", "일정",
    "방법", "사용법", "설치", "수리", "청소", "관리",
    "효능", "부작용", "증상", "치료", "병원",
    "파업", "노조", "채용", "연봉", "주가", "배당",
)


def _build_hints(keyword, max_hints=5):
    """
    검색어 하나로 여러 힌트를 만든다.

    ⚠️ 네이버 키워드도구는 두 가지 특성이 있다.
      1) 공백에 민감하다. '반딧불축제'와 '반딧불 축제'가 다른 결과를 준다.
      2) 쉼표로 최대 5개까지 한 번에 물을 수 있다. 호출은 여전히 1회다.

    다만 억지로 쪼개지는 않는다. 뜻이 없는 조각을 보내면
    엉뚱한 연관어가 섞이거나 아무것도 안 나온다.
    """
    raw = (keyword or "").strip()
    if not raw:
        return []

    hints, seen = [], set()

    def add(h):
        h = h.strip()
        if h and h not in seen and len(hints) < max_hints:
            seen.add(h)
            hints.append(h)

    joined = raw.replace(" ", "")
    add(joined)                         # 공백 뺀 원형 (가장 중요)

    if " " in raw:
        add(raw)                        # 띄어쓴 형태도 함께
        for part in raw.split():        # 조각별로도 물어본다
            if len(part) >= 2:
                add(part)
        return hints

    # 붙여 쓴 말은 사전에 있는 꼬리말만 떼어본다.
    # 앞부분이 2글자 이상 남을 때만 유효한 조각으로 본다.
    for tail in _TAIL_WORDS:
        if joined.endswith(tail) and len(joined) - len(tail) >= 2:
            add(joined[:-len(tail)])
            add(tail)
            break

    return hints


def get_volumes(keywords):
    """
    여러 키워드의 검색량을 한 번에 조회한다 (최대 5개씩).

    _build_hints를 거치지 않는다. 이미 완성된 키워드 목록이라
    쪼개거나 변형하면 안 되기 때문이다.
    반환: {키워드(공백제거): 검색량}
    """
    words = [w.strip() for w in keywords if w and w.strip()][:5]
    if not words:
        return {}

    ck = ("vols", "|".join(sorted(words)))
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    if not _quota_ok():
        return {}

    out = {}
    path = "/keywordstool"
    try:
        _count_call()
        res = requests.get(NAVER_BASE_URL + path,
                           params={"hintKeywords": ",".join(words),
                                   "showDetail": "1"},
                           headers=get_naver_headers("GET", path), timeout=10)
        if res.status_code == 200:
            for it in res.json().get("keywordList", []):
                rk = (it.get("relKeyword") or "").replace(" ", "").upper()
                if rk:
                    out[rk] = (_to_int(it.get("monthlyPcQcCnt"))
                               + _to_int(it.get("monthlyMobileQcCnt")))
    except Exception:
        pass
    return _cache_put(ck, out)


def get_keyword_data(keyword, related_limit=200):
    """
    /keywordstool 한 번으로 '이 키워드의 통계'와 '연관 키워드'를 함께 얻는다.
    (예전에는 같은 요청을 두 번 보내고 있었다)
    """
    ck = ("kwdata", keyword.strip(), related_limit)
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    # 풀에 이미 쌓여 있으면 네이버를 부르지 않는다.
    # (연관어까지 필요할 때는 풀만으로 부족하므로 그때는 호출한다)
    if _shared is not None and related_limit <= 1:
        row = _shared.pool_get(keyword)
        if row:
            return _cache_put(ck, {
                "stat": {
                    "monthly_pc": row.get("monthly_pc", 0),
                    "monthly_mobile": row.get("monthly_mobile", 0),
                    "comp_level": row.get("comp_level", "-"),
                    "pl_avg_depth": row.get("pl_avg_depth", 0),
                },
                "related": [],
            })

    empty = {"stat": {"monthly_pc": 0, "monthly_mobile": 0,
                      "comp_level": "-", "pl_avg_depth": 0},
             "related": [], "hints": []}
    if not _quota_ok():
        return empty
    path = "/keywordstool"
    hints = _build_hints(keyword)
    if not hints:
        return _cache_put(ck, empty)
    try:
        _count_call()
        res = requests.get(NAVER_BASE_URL + path,
                           params={"hintKeywords": ",".join(hints),
                                   "showDetail": "1"},
                           headers=get_naver_headers("GET", path), timeout=10)
        if res.status_code != 200:
            return _cache_put(ck, empty)
        kw_list = res.json().get("keywordList", [])
        if not kw_list:
            return _cache_put(ck, empty)

        # ⚠️ kw_list[0]이 내가 검색한 키워드라는 보장이 없다.
        # 네이버는 관련도 순으로 돌려주기 때문에 첫 항목이 전혀 다른 키워드일 수 있고,
        # 그걸 그대로 쓰면 '삼성'을 조회했는데 다른 키워드의 검색량이 표시된다.
        # 정확히 일치하는 항목을 먼저 찾는다.
        norm = keyword.strip().replace(" ", "").upper()
        head = None
        for it in kw_list:
            if (it.get("relKeyword") or "").replace(" ", "").upper() == norm:
                head = it
                break
        if head is None:
            head = kw_list[0]

        try:
            depth = int(float(head.get("plAvgDepth")))
        except (TypeError, ValueError):
            depth = 0
        stat = {
            "monthly_pc": _to_int(head.get("monthlyPcQcCnt")),
            "monthly_mobile": _to_int(head.get("monthlyMobileQcCnt")),
            "comp_level": head.get("compIdx", "중간"),
            "pl_avg_depth": depth,
            "exact_match": head is not kw_list[0] or
                           (kw_list[0].get("relKeyword") or "").replace(" ", "").upper() == norm,
        }

        # 연관 키워드는 '키워드를 품고 있는 것'을 앞에 둔다.
        # 네이버는 같은 업종의 다른 키워드도 관련어로 주는데,
        # 사냥 지도에서는 실제로 파생된 세부어가 훨씬 쓸모 있다.
        rel_all = []
        for it in kw_list:
            rk = (it.get("relKeyword") or "").strip()
            if not rk or rk.replace(" ", "").upper() == norm:
                continue
            rel_all.append({
                "keyword": rk,
                "monthly_pc": _to_int(it.get("monthlyPcQcCnt")),
                "monthly_mobile": _to_int(it.get("monthlyMobileQcCnt")),
                "comp_level": it.get("compIdx", "중간"),
                "contains": norm in rk.replace(" ", "").upper(),
            })
        # 키워드를 품은 것을 앞에 두고, 그 안에서 검색량 순으로 정렬한다.
        rel_all.sort(key=lambda x: (not x["contains"],
                                    -(x["monthly_pc"] + x["monthly_mobile"])))
        related = rel_all[:related_limit]

        # 💡 한 번 부른 김에 연관어를 통째로 풀에 쌓는다.
        # 지금까지는 1개만 쓰고 20개를 버렸는데, 그게 가장 큰 낭비였다.
        # 다음에 누가 그 키워드를 조회하면 네이버를 안 불러도 된다.
        if _shared is not None:
            _shared.pool_put_many(
                [{"keyword": keyword.strip(), **stat}]
                + [{"keyword": r["keyword"], "monthly_pc": r["monthly_pc"],
                    "monthly_mobile": r["monthly_mobile"],
                    "comp_level": r["comp_level"], "pl_avg_depth": 0}
                   for r in rel_all])

        return _cache_put(ck, {"stat": stat, "related": related,
                               "hints": hints})
    except Exception:
        return _cache_put(ck, empty)


def get_blog_stats(keyword, days=30, exact=True):
    """
    블로그 검색 한 번으로 '누적 문서수'와 '최근 N일 새 글 수'를 함께 얻는다.
    최신순 첫 페이지 응답에 total이 들어 있어서 따로 부를 이유가 없다.
    exact=True일 때만 100건을 넘는 구간을 이분탐색으로 정확히 센다.
    """
    ck = ("blogstats", keyword.strip(), days, exact)
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    first = _fetch_serp_page(keyword, start=1, display=100, sort="date")
    # 문서수를 재는 김에 풀에도 남긴다.
    # (문서수는 키워드마다 따로 불러야 해서 미리 못 쌓지만,
    #  한 번 잰 것은 재사용할 수 있다)
    if first is None:
        return {"total_docs": None, "recent": None, "capped": False}

    total_docs = int(first.get("total", 0) or 0)
    if _shared is not None:
        _shared.pool_put_docs(keyword, total_docs)
    items = first.get("items", [])
    now = datetime.now(timezone.utc)

    fresh = 0
    for it in items:
        age = _postdate_age(it, now)
        if age is not None and age <= days:
            fresh += 1
        else:
            break

    if fresh < len(items) or not items:
        return _cache_put(ck, {"total_docs": total_docs, "recent": fresh, "capped": False})

    if not exact:
        return _cache_put(ck, {"total_docs": total_docs, "recent": len(items), "capped": True})

    upper = min(total_docs, MAX_START)
    if upper <= len(items):
        return _cache_put(ck, {"total_docs": total_docs, "recent": len(items),
                               "capped": total_docs > MAX_START})

    lo, hi = len(items), upper
    while lo < hi:
        mid = (lo + hi + 1) // 2
        page = _fetch_serp_page(keyword, start=mid, display=1, sort="date")
        if page is None:
            break
        arr = page.get("items", [])
        if not arr:
            hi = mid - 1
            continue
        age = _postdate_age(arr[0], now)
        if age is not None and age <= days:
            lo = mid
        else:
            hi = mid - 1
    return _cache_put(ck, {"total_docs": total_docs, "recent": lo,
                           "capped": lo >= MAX_START and total_docs > MAX_START})


def analyze_keyword(keyword, with_recent=True, exact_recent=True,
                    with_related=True):
    """
    단일 키워드 종합 분석.

    API 호출을 최대 2회로 묶었다.
      · /keywordstool 1회 → 검색량 + 연관 키워드
      · 블로그 검색 1회 → 누적 문서수 + 최근 30일 새 글
    (exact_recent=True이고 최근 글이 100건을 넘을 때만 이분탐색이 추가된다)

    with_related=False면 연관 키워드를 담지 않는다.
    사냥 지도처럼 여러 키워드를 잴 때 각 키워드의 연관어까지는 필요 없다.
    """
    # ⚠️ 네이버 키워드도구는 한 번 호출에 연관어를 수백 개까지 돌려준다.
    # 예전에는 그중 20개만 쓰고 나머지를 버려서, 경쟁 서비스가 200개를
    # 보여주는 것에 비해 초라해 보였다. 이제 받은 만큼 다 쓴다.
    data = get_keyword_data(keyword, related_limit=200 if with_related else 1)
    stat = data["stat"]
    total_search = stat["monthly_pc"] + stat["monthly_mobile"]

    doc_count = None
    recent, recent_ratio, recent_grade, recent_capped = None, None, "정보없음", False

    if with_recent:
        blog = get_blog_stats(keyword, exact=exact_recent)
        doc_count = blog["total_docs"]
        recent = blog["recent"]
        recent_capped = blog["capped"]
        if recent is not None and total_search:
            recent_ratio, recent_grade = calc_recent_competition(total_search, recent)
    else:
        doc_count = get_blog_doc_count(keyword)

    ratio, grade = calc_competition(total_search, doc_count)
    opportunity = calc_opportunity(ratio, recent_ratio, total_search=total_search)

    related = data["related"] if with_related else []

    # 자동완성으로 빈틈을 메운다.
    # 키워드도구는 광고 데이터라 이슈성 키워드가 비어 있는데,
    # 자동완성은 실제 검색어라 그런 것까지 잡힌다.
    if with_related and USE_AUTOCOMPLETE:
        have = {r["keyword"].replace(" ", "") for r in related}
        for t in autocomplete_keywords(keyword):
            if t.replace(" ", "") in have:
                continue
            have.add(t.replace(" ", ""))
            related.append({
                "keyword": t,
                "monthly_pc": 0,
                "monthly_mobile": 0,
                "comp_level": "-",
                "contains": keyword.replace(" ", "") in t.replace(" ", ""),
                "source": "자동완성",     # 검색량은 아직 모른다
            })
        # 검색량이 있는 것(광고 데이터)을 앞에, 자동완성을 뒤에
        related.sort(key=lambda x: (
            x.get("source") == "자동완성",
            not x.get("contains", True),
            -(x["monthly_pc"] + x["monthly_mobile"])))

    return {
        "keyword": keyword,
        "monthly_pc": stat["monthly_pc"],
        "monthly_mobile": stat["monthly_mobile"],
        "total_search": total_search,
        "doc_count": doc_count,
        "comp_ratio": ratio,
        "comp_grade": grade,
        "recent_docs": recent,
        "recent_capped": recent_capped,
        "recent_ratio": recent_ratio,
        "recent_grade": recent_grade,
        "opportunity": opportunity,
        "pl_avg_depth": stat["pl_avg_depth"],
        "related": related,
        "hints": data.get("hints", []),
    }


# ============================================================
# 💡 신규: 내 블로그 진단 & 키워드별 승산 분석
# ============================================================
#
# ⚠️ 솔직한 전제: 네이버는 '블로그 지수'를 공식적으로 공개하지 않습니다.
# 블덱스/블로그차트가 보여주는 지수도 전부 외부에서 관측 가능한 신호를
# 조합한 추정치입니다. 여기서도 마찬가지로, 공개된 두 가지 실제 신호만 씁니다.
#   1) 블로그 RSS - 발행 주기/최근 활동성 (로그인 불필요, 공개 데이터)
#   2) 블로그 검색 결과 - 내 글이 실제로 상위에 노출되고 있는지
# 이 두 가지는 실측값이고, '승산 점수'는 그걸 조합한 추정임을 UI에 명시합니다.

import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import re


def get_my_blog_feed(blog_id, limit=30):
    """
    네이버 블로그 RSS로 내 글 목록을 가져온다 (공개 데이터, 로그인 불필요).
    반환: {"posts": [{"title","date"}], "error": None}
    """
    url = f"https://rss.blog.naver.com/{blog_id.strip()}.xml"
    try:
        res = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if res.status_code != 200:
            return {"posts": [], "error": f"RSS를 불러오지 못했습니다 (상태 {res.status_code})"}
        root = ET.fromstring(res.content)
        channel = root.find("channel")
        if channel is None:
            return {"posts": [], "error": "RSS 형식을 해석하지 못했습니다"}

        posts = []
        for item in channel.findall("item")[:limit]:
            title = (item.findtext("title") or "").strip()
            pub = item.findtext("pubDate") or ""
            dt = None
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass
            posts.append({"title": title, "date": dt})
        return {"posts": posts, "error": None}
    except Exception as e:
        return {"posts": [], "error": f"블로그를 찾을 수 없습니다 ({e})"}


def estimate_blog_power(posts):
    """
    RSS로 관측된 발행 활동성을 0~100 점수로 환산.
    ⚠️ 네이버 공식 지수가 아니라 '발행 활동성' 추정치입니다.
    """
    dated = [p["date"] for p in posts if p.get("date")]
    if not dated:
        return {"score": 0, "level": "정보없음", "posts_per_week": 0, "days_since_last": None}

    now = datetime.now(timezone.utc)
    days_since_last = (now - max(dated)).days

    recent_90 = [d for d in dated if (now - d).days <= 90]
    posts_per_week = round(len(recent_90) / 12.9, 1) if recent_90 else 0

    # 발행 빈도(최대 70점) + 최근성(최대 30점)
    freq_score = min(70, posts_per_week * 20)
    if days_since_last <= 3:
        recency = 30
    elif days_since_last <= 7:
        recency = 24
    elif days_since_last <= 14:
        recency = 16
    elif days_since_last <= 30:
        recency = 8
    else:
        recency = 0

    score = int(freq_score + recency)
    if score >= 75:
        level = "매우활발"
    elif score >= 55:
        level = "활발"
    elif score >= 35:
        level = "보통"
    elif score >= 15:
        level = "저조"
    else:
        level = "휴면"

    # 발행 간격의 들쭉날쭉함 — 꾸준함을 보는 지표
    gaps = []
    srt = sorted(dated)
    for a, b in zip(srt, srt[1:]):
        gaps.append((b - a).days)
    avg_gap = round(sum(gaps) / len(gaps), 1) if gaps else None

    return {
        "score": score,
        "level": level,
        "posts_per_week": posts_per_week,   # 최근 90일 평균
        "days_since_last": days_since_last,
        "avg_gap_days": avg_gap,            # 글과 글 사이 평균 간격
        "total_posts": len(dated),
    }


def check_post_exposure(post_title, blog_id, max_words=6):
    """
    내 글이 제 제목으로 검색했을 때 상위에 잡히는지 확인한다.

    ⚠️ 조회수는 확인할 수 없습니다.
    네이버 블로그 조회수는 작성자 본인만 볼 수 있는 정보라
    RSS에도 검색 API에도 들어 있지 않습니다.
    대신 '이 글이 검색으로 발견될 수 있는 상태인가'는 확인 가능하므로,
    제목의 앞부분을 검색어로 삼아 상위 노출 여부를 본다.
    """
    words = _tokens(post_title)[:max_words]
    if not words:
        return None
    query = " ".join(words)
    rank = check_my_rank(query, blog_id, display=100)
    return {"query": query, "rank": rank}


def check_my_rank(keyword, blog_id, display=100):
    """
    그 키워드 블로그 검색 상위 결과에 내 블로그가 실제로 있는지 확인 (실측값).
    반환: 순위(1부터) 또는 None
    ⚠️ 검색 API는 한 번에 최대 100건까지 준다. 100위까지 확인한다.
    """
    if not NAVER_HUB_CLIENT_ID or not NAVER_HUB_CLIENT_SECRET:
        return None
    headers = {
        "X-NCP-APIGW-API-KEY-ID": NAVER_HUB_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NAVER_HUB_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": display, "sort": "sim"}
    try:
        _count_call()
        res = requests.get(NAVER_HUB_BLOG_URL, headers=headers, params=params, timeout=6)
        if res.status_code == 200:
            for i, item in enumerate(res.json().get("items", []), start=1):
                link = (item.get("bloggerlink") or "") + " " + (item.get("link") or "")
                if blog_id.strip().lower() in link.lower():
                    return i
    except Exception:
        pass
    return None


def calc_win_score(comp_ratio, blog_power_score, opportunity_score=None):
    """
    '이 키워드를 내 블로그로 뚫을 수 있는가'를 추정한다.

    opportunity_score를 넘기면 그걸(누적+최근 발행량을 합친 값) 그대로 쓰고,
    없으면 예전처럼 누적 경쟁률만으로 환산한다.
    ⚠️ 네이버 알고리즘을 재현한 게 아니라, 공개 지표를 조합한 추정치입니다.
    """
    if opportunity_score is not None:
        opportunity = opportunity_score
    else:
        if comp_ratio is None:
            return {"score": None, "verdict": "정보없음"}
        if comp_ratio < 0.1:
            opportunity = 100
        elif comp_ratio < 0.5:
            opportunity = 80
        elif comp_ratio < 2:
            opportunity = 55
        elif comp_ratio < 10:
            opportunity = 30
        else:
            opportunity = 10

    score = int(opportunity * 0.65 + blog_power_score * 0.35)

    if score >= 75:
        verdict = "충분히 노려볼 만함"
    elif score >= 55:
        verdict = "해볼 만함"
    elif score >= 35:
        verdict = "쉽지 않음"
    else:
        verdict = "지금은 비추천"
    return {"score": score, "verdict": verdict}


def extract_blog_id(raw):
    """사용자가 URL을 통째로 붙여넣어도 블로그 아이디만 뽑아낸다."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    m = re.search(r"blog\.naver\.com/([A-Za-z0-9_-]+)", raw)
    if m:
        return m.group(1)
    return raw.lstrip("@").split("/")[0]


# ============================================================
# 💡 신규: 최근 30일 발행량 · 누적/최근을 나눠 본 기회 진단
# ============================================================
#
# 누적 문서수는 10년 치가 쌓인 값이라 '시장 포화도'는 알려주지만
# '지금 몰리고 있는지'는 알려주지 못한다. 두 축을 나눠서 본다.
#   - 누적 경쟁률 = 전체 문서수     ÷ 월 검색량  → 얼마나 포화됐나
#   - 최근 경쟁률 = 최근 30일 문서수 ÷ 월 검색량  → 지금 몰리고 있나
# 한 달 검색량과 한 달 발행량을 맞대는 것이므로 단위가 자연스럽게 맞는다.

RECENT_FETCH_MAX = 100  # 검색 API 1회 최대 조회 건수


def _fetch_serp_page(keyword, start=1, display=1, sort="date"):
    """검색 API 한 페이지. 실패 시 None."""
    if not NAVER_HUB_CLIENT_ID or not NAVER_HUB_CLIENT_SECRET:
        return None
    headers = {
        "X-NCP-APIGW-API-KEY-ID": NAVER_HUB_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NAVER_HUB_CLIENT_SECRET,
    }
    if not _quota_ok():
        return None
    params = {"query": keyword, "display": display, "start": start, "sort": sort}
    try:
        _count_call()
        res = requests.get(NAVER_HUB_BLOG_URL, headers=headers, params=params, timeout=6)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None


def _postdate_age(item, now=None):
    """검색 결과 1건의 나이(일). 날짜를 못 읽으면 None."""
    now = now or datetime.now(timezone.utc)
    pd_ = item.get("postdate")
    if pd_ and len(pd_) == 8:
        try:
            d = datetime.strptime(pd_, "%Y%m%d").replace(tzinfo=timezone.utc)
            return (now - d).days
        except ValueError:
            pass
    return None


MAX_START = 1000  # 검색 API가 허용하는 최대 시작 위치


def get_recent_doc_count(keyword, days=30, exact=True):
    """
    최근 N일 안에 발행된 블로그 글 수를 센다.

    ⚠️ 한 번에 100건까지만 받을 수 있어서, 예전에는 100건을 넘으면
    '100+'로만 표시했다. 이제는 최신순 정렬을 이용해 이분탐색으로
    '몇 번째 글부터 N일보다 오래됐는지' 경계를 찾아 정확한 수를 구한다.
    최신순이라 나이가 단조 증가하므로 이분탐색이 성립한다.
    API 호출은 약 10회. 정확도를 위해 감수한다.

    exact=False면 이분탐색을 건너뛰고 100건에서 멈춘다.
    연관 키워드 20개를 한꺼번에 잴 때는 정밀도보다 속도가 중요하다.
    (정확히 세려면 키워드마다 API를 10회 더 불러야 한다)

    반환: {"count": int, "capped": bool}
      capped=True면 그 이상이라 정확히 셀 수 없다는 뜻.
    """
    now = datetime.now(timezone.utc)

    first = _fetch_serp_page(keyword, start=1, display=100, sort="date")
    if first is None:
        return None
    items = first.get("items", [])
    if not items:
        return {"count": 0, "capped": False}

    total = int(first.get("total", 0) or 0)

    # 100건 안에서 경계가 잡히면 추가 호출 없이 끝낸다
    fresh_in_page = 0
    for it in items:
        age = _postdate_age(it, now)
        if age is not None and age <= days:
            fresh_in_page += 1
        else:
            break
    if fresh_in_page < len(items):
        return {"count": fresh_in_page, "capped": False}

    # 100건이 전부 최근 글인 경우
    if not exact:
        return {"count": len(items), "capped": True}

    # 이분탐색으로 정확한 경계를 찾는다
    upper = min(total, MAX_START)
    if upper <= len(items):
        return {"count": len(items), "capped": total > MAX_START}

    lo, hi = len(items), upper   # lo는 '최근'이 확실한 지점
    while lo < hi:
        mid = (lo + hi + 1) // 2
        page = _fetch_serp_page(keyword, start=mid, display=1, sort="date")
        if page is None:
            break
        arr = page.get("items", [])
        if not arr:
            hi = mid - 1
            continue
        age = _postdate_age(arr[0], now)
        if age is not None and age <= days:
            lo = mid
        else:
            hi = mid - 1

    return {"count": lo, "capped": lo >= MAX_START and total > MAX_START}


def calc_recent_competition(total_search, recent_count):
    """최근 30일 발행량 대비 경쟁 강도. 반환: (비율, 등급)"""
    if not total_search or total_search <= 0:
        return None, "검색량없음"
    if recent_count is None:
        return None, "정보없음"

    ratio = recent_count / total_search
    if ratio < 0.005:
        grade = "매우한산"
    elif ratio < 0.02:
        grade = "한산"
    elif ratio < 0.1:
        grade = "보통"
    elif ratio < 0.5:
        grade = "붐빔"
    else:
        grade = "과열"
    return round(ratio, 4), grade


def score_demand(total_search):
    """
    ① 수요 — 애초에 찾는 사람이 있는가.

    ⚠️ 이 축이 없으면 '아무도 안 찾는 키워드'가 만점을 받는다.
    검색량 10, 문서수 0이면 경쟁률이 0이라 이론상 최고 점수가 나오지만,
    1위를 해도 방문자가 없으니 아무 의미가 없다.
    """
    if not total_search or total_search <= 0:
        return 0, "검색량 없음"
    if total_search < 100:
        return 5, "거의 안 찾음"
    if total_search < 500:
        return 30, "매우 적음"
    if total_search < 2000:
        return 60, "적당함"
    if total_search < 20000:
        return 90, "충분함"
    return 100, "매우 많음"


def score_saturation(total_ratio):
    """
    ② 글 여유 — 수요 대비 이미 쌓인 글이 적은가.

    ⚠️ 이전 이름은 '포화도'였는데, 막대가 길수록 좋은 상태인데도
    이름 때문에 '포화가 심하다'로 읽히는 문제가 있었다.
    모든 축을 '높을수록 좋다'로 통일하기 위해 이름을 바꿨다.
    """
    if total_ratio is None:
        return None, "정보없음"
    if total_ratio < 0.1:
        return 100, "거의 비어 있음"
    if total_ratio < 0.5:
        return 80, "여유 있음"
    if total_ratio < 2:
        return 55, "보통"
    if total_ratio < 10:
        return 30, "빽빽함"
    return 10, "포화"


def score_competition(recent_ratio):
    """③ 요즘 한산 — 최근에 새 글이 적게 들어오는가. 높을수록 조용하다."""
    if recent_ratio is None:
        return None, "정보없음"
    if recent_ratio < 0.005:
        return 100, "거의 없음"
    if recent_ratio < 0.02:
        return 80, "한산함"
    if recent_ratio < 0.1:
        return 55, "보통"
    if recent_ratio < 0.5:
        return 25, "붐빔"
    return 5, "과열"


def score_trend(search_change_pct):
    """
    ④ 추세 — 검색량이 늘고 있는가 줄고 있는가.

    ⚠️ 이 축이 없으면 '한물 간 시장'과 '아직 발견 안 된 기회'를 구분할 수 없다.
    둘 다 최근 발행이 적어서 똑같이 높은 점수를 받아버린다.
    search_change_pct: 검색량 변화율(%). 추적 기록이 쌓여야 계산 가능.
    """
    if search_change_pct is None:
        return None, "추적하면 표시"
    if search_change_pct <= -30:
        return 10, "빠르게 식는 중"
    if search_change_pct <= -10:
        return 35, "식는 중"
    if search_change_pct < 10:
        return 60, "제자리"
    if search_change_pct < 30:
        return 85, "오르는 중"
    return 100, "빠르게 오르는 중"


def calc_opportunity(total_ratio, recent_ratio, total_search=None,
                     search_change_pct=None):
    """
    기회 점수(0~100). 네 축을 조합한다.

      ① 수요    — 찾는 사람이 있는가        (없으면 나머지가 무의미)
      ② 포화도  — 이미 쌓인 글이 많은가
      ③ 최근경쟁 — 요즘도 새 글이 들어오는가
      ④ 추세    — 검색량이 늘고 있는가

    ①은 가중치가 아니라 '문지기'로 쓴다. 수요가 없으면 나머지가 아무리
    좋아도 점수를 눌러버린다. 1위를 해도 아무도 안 오는 키워드이기 때문.
    """
    dem, dem_label = score_demand(total_search) if total_search is not None else (None, None)
    sat, sat_label = score_saturation(total_ratio)
    comp, comp_label = score_competition(recent_ratio)
    trd, trd_label = score_trend(search_change_pct)

    breakdown = {
        "수요": (dem, dem_label),
        "글 여유": (sat, sat_label),
        "요즘 한산": (comp, comp_label),
        "추세": (trd, trd_label),
    }

    if sat is None:
        return {"score": 0, "label": "정보없음",
                "note": "검색량 데이터가 없어 판단할 수 없습니다.",
                "breakdown": breakdown}

    # 수요가 바닥이면 여기서 끝낸다
    if dem is not None and dem <= 5:
        return {"score": min(15, sat // 4), "label": "찾는 사람이 없음",
                "note": ("월 검색량이 너무 적습니다. 경쟁이 없는 게 아니라 "
                         "수요 자체가 없는 것이라, 1위를 해도 방문자가 거의 없습니다."),
                "breakdown": breakdown}

    # 확보된 축만 가중 평균 (기록이 없으면 그 축은 빼고 계산)
    weights = []
    if sat is not None:
        weights.append((sat, 0.30))
    if comp is not None:
        weights.append((comp, 0.35))
    if trd is not None:
        weights.append((trd, 0.20))
    if dem is not None:
        weights.append((dem, 0.15))

    total_w = sum(w for _, w in weights)
    score = int(sum(v * w for v, w in weights) / total_w) if total_w else 0

    # 수요가 적으면 상한을 씌운다
    if dem is not None and dem <= 30:
        score = min(score, 50)

    # 검색이 뚜렷하게 줄고 있으면 상한을 씌운다.
    # 가중평균만으로는 '새 글이 없다'는 점이 점수를 끌어올려서,
    # 한물 간 시장이 높은 점수를 받는 모순이 생긴다.
    if trd is not None and trd <= 35:
        score = min(score, 45 if trd > 10 else 30)

    label, note = _opportunity_label(sat, comp, trd, score)
    return {"score": score, "label": label, "note": note, "breakdown": breakdown}


def _opportunity_label(sat, comp, trd, score):
    """네 축의 조합을 사람이 읽을 수 있는 상황 설명으로 옮긴다."""
    # 추세가 확보됐을 때만 내릴 수 있는 판정을 먼저 본다
    if trd is not None:
        if trd <= 35 and comp is not None and comp >= 80:
            return ("한물 간 시장",
                    "검색이 줄고 있습니다. 새 글이 없는 건 기회가 아니라 "
                    "다들 떠났기 때문일 수 있습니다.")
        if trd >= 85 and comp is not None and comp >= 55:
            return ("떠오르는 자리",
                    "검색이 늘고 있는데 아직 글은 많지 않습니다. "
                    "지금 선점하면 유리합니다.")
        if trd >= 85 and comp is not None and comp < 55:
            return ("경쟁 시작됨",
                    "검색이 늘면서 글도 빠르게 쌓이고 있습니다. 서두르셔야 합니다.")

    if comp is None:
        return "누적만 반영", "최근 발행량을 확인하지 못해 누적 포화도만 반영했습니다."

    if sat >= 80 and comp >= 80:
        return "비어 있는 자리", "쌓인 글도 적고 지금 쓰는 사람도 적습니다. 가장 좋은 조건입니다."
    if sat <= 30 and comp >= 80:
        return ("오래된 글만 많음",
                "글은 많이 쌓였지만 요즘은 아무도 안 씁니다. "
                "최신 정보로 새로 쓰면 밀어낼 수 있습니다.")
    if sat >= 80 and comp <= 25:
        return "지금 몰리는 중", "쌓인 글은 적지만 요즘 갑자기 많이 쓰이고 있습니다."
    if sat <= 30 and comp <= 25:
        return "이미 꽉 참", "글도 많고 지금도 계속 쓰이고 있습니다. 더 좁은 키워드로 돌아가세요."
    if score >= 70:
        return "해볼 만함", "찾는 사람에 비해 글이 여유 있는 편입니다."
    if score >= 45:
        return "보통", "글을 잘 써야 이기는 구간입니다."
    return "어려움", "경쟁이 만만치 않습니다. 더 좁은 키워드를 찾아보세요."


def expected_visits(total_search, rank):
    """
    ⑤ 예상 방문자 — 이 키워드로 한 달에 몇 명이나 들어올까.

    순위가 같아도 검색량이 다르면 실속이 완전히 다르다.
    (검색량 30에서 1위 = 월 8명 / 검색량 10,000에서 7위 = 월 300명)
    클릭률은 검색 결과에서 일반적으로 관찰되는 대략치이며 추정값이다.
    """
    if not total_search or rank is None:
        return None
    ctr = {1: 0.28, 2: 0.16, 3: 0.11, 4: 0.08, 5: 0.06,
           6: 0.045, 7: 0.035, 8: 0.028, 9: 0.022, 10: 0.018}
    if rank <= 10:
        r = ctr[rank]
    elif rank <= 20:
        r = 0.008
    elif rank <= 30:
        r = 0.003
    else:
        r = 0.001
    return int(total_search * r)


def calc_search_change(history):
    """
    수집 기록에서 검색량 변화율(%)을 낸다.
    앞쪽 절반 평균과 뒤쪽 절반 평균을 비교한다.

    ⚠️ 네이버가 주는 월간 검색량은 한 달 단위 집계값이라
    매일 수집해도 며칠간 같은 숫자가 나온다. 그래서 기록이 2회만 있어도
    계산은 되지만 의미가 없고, 값이 바뀌는 시점(보통 월 갱신)이 지나야
    실제 추세가 드러난다. 최소 3회는 있어야 계산한다.
    """
    vals = [v for v in (history or []) if v is not None and v > 0]
    if len(vals) < 3:
        return None
    half = len(vals) // 2
    old = sum(vals[:half]) / half
    new = sum(vals[half:]) / (len(vals) - half)
    if old <= 0:
        return None
    return round((new - old) / old * 100, 1)


# ============================================================
# 💡 상위노출 글 해부 (SERP 분석)
# ============================================================
#
# "이 키워드로 지금 1~N위 한 글들은 어떻게 생겼나"를 본다.
# 경쟁률 숫자만으로는 안 보이는 것들이 여기서 드러난다.
#  - 상위권이 전부 몇 년 전 글이면 → 새 글로 밀어낼 여지가 크다
#  - 특정 블로그가 여러 자리를 먹고 있으면 → 그 주제의 강자가 있다
#  - 제목 길이/패턴이 일정하면 → 그 형식이 먹히고 있다는 신호

def _strip_tags(text):
    """검색 API가 돌려주는 <b> 강조 태그와 HTML 엔티티를 걷어낸다."""
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", "", text)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")):
        t = t.replace(a, b)
    return t.strip()


def get_serp(keyword, display=30, sort="sim"):
    """
    키워드의 블로그 검색 상위 결과를 정돈해서 돌려준다.
    sort="sim"  → 네이버 노출 순위(정확도) 순
    sort="date" → 최신 발행 순
    반환: [{"rank","title","blogger","blog_id","postdate","age_days","link"}]
    """
    if not NAVER_HUB_CLIENT_ID or not NAVER_HUB_CLIENT_SECRET:
        return []
    headers = {
        "X-NCP-APIGW-API-KEY-ID": NAVER_HUB_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NAVER_HUB_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": min(display, 100),
              "sort": "date" if sort == "date" else "sim"}
    out = []
    try:
        _count_call()
        res = requests.get(NAVER_HUB_BLOG_URL, headers=headers, params=params, timeout=8)
        if res.status_code != 200:
            return []
        now = datetime.now(timezone.utc)
        for i, item in enumerate(res.json().get("items", []), start=1):
            pd_ = item.get("postdate") or ""
            age = None
            dt = None
            if len(pd_) == 8:
                try:
                    dt = datetime.strptime(pd_, "%Y%m%d").replace(tzinfo=timezone.utc)
                    age = (now - dt).days
                except ValueError:
                    pass
            link = item.get("bloggerlink") or item.get("link") or ""
            m = re.search(r"blog\.naver\.com/([A-Za-z0-9_-]+)", link)
            out.append({
                "rank": i,
                "title": _strip_tags(item.get("title")),
                "blogger": _strip_tags(item.get("bloggername")),
                "blog_id": m.group(1) if m else "",
                "postdate": dt.strftime("%Y-%m-%d") if dt else "",
                "age_days": age,
                "link": item.get("link") or "",
            })
    except Exception as e:
        print(f"SERP 조회 실패({keyword}): {e}")
    return out


def analyze_serp(serp, top_n=10):
    """
    상위 N개 글의 공통점을 뽑아낸다.
    나이, 제목 길이, 블로그 집중도, 진입 난이도 판정.
    """
    top = [s for s in serp[:top_n]]
    if not top:
        return None

    # ⚠️ 발행일을 못 읽은 글이 섞이면 분모가 어긋난다.
    # (상위 10개 중 3개가 날짜 불명이면 '10개 중 10개'가 아니라 '7개 중 7개'가 맞다)
    ages = [s["age_days"] for s in top if s["age_days"] is not None]
    unknown_date = len(top) - len(ages)
    titles = [s["title"] for s in top if s["title"]]
    ids = [s["blog_id"] for s in top if s["blog_id"]]

    median_age = None
    if ages:
        srt = sorted(ages)
        mid = len(srt) // 2
        median_age = srt[mid] if len(srt) % 2 else (srt[mid - 1] + srt[mid]) // 2

    fresh_90 = sum(1 for a in ages if a <= 90)
    old_365 = sum(1 for a in ages if a >= 365)

    # 같은 블로그가 몇 자리를 먹었나
    counts = {}
    for b in ids:
        counts[b] = counts.get(b, 0) + 1
    top_blogger = max(counts.items(), key=lambda x: x[1]) if counts else None
    unique_ratio = len(set(ids)) / len(ids) if ids else 1.0

    avg_title = round(sum(len(t) for t in titles) / len(titles), 1) if titles else 0

    # 진입 난이도 판정 — 오래된 글이 많을수록 뚫기 쉽다
    if ages:
        if old_365 >= len(ages) * 0.6:
            verdict = "오래된 글이 1등"
            advice = ("상위권 대부분이 1년 넘은 글입니다. "
                      "최신 정보로 제대로 쓴 글이면 밀어낼 가능성이 높습니다.")
        elif fresh_90 >= len(ages) * 0.7:
            verdict = "최신 글 경쟁"
            advice = ("상위권이 최근 3개월 안에 쓰인 글로 채워져 있습니다. "
                      "계속 새 글이 들어오는 자리라 유지가 어렵습니다.")
        else:
            verdict = "새 글 옛 글 섞임"
            advice = "새 글과 오래된 글이 섞여 있습니다. 내용의 완성도가 승부처입니다."
    else:
        verdict, advice = "정보없음", "발행일 정보를 읽지 못했습니다."

    return {
        "count": len(top),
        "dated_count": len(ages),      # 발행일을 읽을 수 있었던 글 수 (비율의 분모)
        "unknown_date": unknown_date,  # 날짜를 못 읽은 글 수
        "median_age": median_age,
        "fresh_90": fresh_90,
        "old_365": old_365,
        "avg_title_len": avg_title,
        "unique_ratio": round(unique_ratio, 2),
        "top_blogger": top_blogger,
        "verdict": verdict,
        "advice": advice,
        "age_buckets": _age_buckets(ages),
    }


def _age_buckets(ages):
    """
    글 나이를 구간별로 센다 (막대차트용).
    상위권 대부분이 최신 글인 경우가 흔해서, 최근 구간을 잘게 쪼개야
    '전부 3개월'로 뭉뚱그려지지 않고 실제 분포가 보인다.
    """
    labels = ["1주 이내", "1달 이내", "3달 이내", "6달 이내", "1년 이내", "1년 이상"]
    d = {k: 0 for k in labels}
    for a in ages:
        if a <= 7:
            d["1주 이내"] += 1
        elif a <= 30:
            d["1달 이내"] += 1
        elif a <= 90:
            d["3달 이내"] += 1
        elif a <= 180:
            d["6달 이내"] += 1
        elif a <= 365:
            d["1년 이내"] += 1
        else:
            d["1년 이상"] += 1
    return [(k, d[k]) for k in labels]


# ============================================================
# 💡 글감 제안
# ============================================================
#
# 상위노출 글들의 실제 제목과 연관검색어를 재료로 삼는다.
# 지어내는 게 아니라 '이미 검색되고 있는 것', '이미 상위에 있는 형식'에서 뽑는다.

def _tokens(text):
    """한글/영문/숫자 토큰만 뽑는다 (소제목 추출용)."""
    return [t for t in re.findall(r"[가-힣A-Za-z0-9]+", text or "") if len(t) >= 2]


def analyze_titles(keyword, serp, related, top_n=20):
    """
    상위노출 글의 제목을 '분석'한다. 제목을 지어내지 않는다.

    ⚠️ 이전 버전은 "두산 가격" 같은 말이 안 되는 제목을 만들어냈다.
    기계가 그럴듯한 문장을 조합하는 것보다,
    "상위권은 실제로 이렇게 쓴다"는 사실을 보여주는 편이 훨씬 쓸모 있다.
    """
    titles = [x.get("title", "") for x in serp[:top_n] if x.get("title")]
    if not titles:
        return None

    lens = sorted(len(t) for t in titles)
    mid = len(lens) // 2
    median_len = lens[mid] if len(lens) % 2 else (lens[mid - 1] + lens[mid]) // 2

    with_num = [t for t in titles if re.search(r"\d", t)]
    with_bracket = [t for t in titles if re.search(r"[\[\](){}｜|]", t)]
    with_q = [t for t in titles if "?" in t]
    # 후기형: 직접 경험을 내세우는 제목이 통하는지
    exp_words = ("후기", "내돈내산", "리뷰", "솔직", "직접", "써본", "사용기", "체험")
    with_exp = [t for t in titles if any(w in t for w in exp_words)]
    # 정리형: 목록·비교로 정보를 묶는 제목
    sum_words = ("정리", "총정리", "비교", "순위", "추천", "모음", "BEST", "베스트")
    with_sum = [t for t in titles if any(w in t for w in sum_words)]

    # 상위 제목에 실제로 자주 등장하는 표현
    kw_tokens = set(_tokens(keyword))
    stop = {"위한", "하는", "있는", "그리고", "하지만", "정말", "너무"}
    freq = {}
    for t in titles:
        for tok in set(_tokens(t)):
            if tok in kw_tokens or tok in stop or tok.isdigit() or len(tok) < 2:
                continue
            freq[tok] = freq.get(tok, 0) + 1
    common = [(w, c) for w, c in sorted(freq.items(), key=lambda x: (-x[1], x[0])) if c >= 2][:12]

    # 연관검색어 중 '키워드 + 무엇' 형태 — 실제 검색되는 세부 주제
    subtopics = []
    base = keyword.replace(" ", "")
    for r in (related or []):
        kw = (r.get("keyword") or "").strip()
        if not kw or kw == keyword:
            continue
        if base and base in kw.replace(" ", ""):
            vol = r.get("monthly_pc", 0) + r.get("monthly_mobile", 0)
            subtopics.append({"keyword": kw, "volume": vol})
    subtopics.sort(key=lambda x: -x["volume"])

    # ⚠️ 상위 글 제목 원문은 일부러 반환하지 않는다.
    # 화면에 나열하면 "형식만 참고하세요"라고 안내해도 결국 베끼게 되고,
    # 베낀 글은 상위노출에도 불리하다. 형식 지표만 뽑아서 넘긴다.
    return {
        "count": len(titles),
        "median_len": median_len,
        "min_len": lens[0],
        "max_len": lens[-1],
        "num_ratio": len(with_num) / len(titles),
        "bracket_ratio": len(with_bracket) / len(titles),
        "question_ratio": len(with_q) / len(titles),
        "experience_ratio": len(with_exp) / len(titles),
        "summary_ratio": len(with_sum) / len(titles),
        "common_words": common,
        "subtopics": subtopics[:15],
    }


def build_outline(keyword, analysis):
    """
    상위 글 제목에서 실제로 반복되는 단어와, 실제 검색되는 세부 주제로
    글의 뼈대를 만든다. 근거 없는 소제목은 넣지 않는다.
    """
    if not analysis:
        return []

    sections = []
    for w, c in analysis["common_words"][:6]:
        sections.append({
            "heading": w,
            "why": f"상위 {analysis['count']}개 중 {c}개가 제목에 쓴 단어",
            "kind": "필수",
        })
    for st_ in analysis["subtopics"][:6]:
        sections.append({
            "heading": st_["keyword"],
            "why": f"월 {st_['volume']:,}회 실제로 검색되는 세부 주제",
            "kind": "검색",
        })
    return sections




def calc_since_registered(first_row, last_row):
    """
    등록 당시와 지금을 비교한다.

    검색량만 보면 '수요가 느는지'만 알 수 있고,
    글 수를 함께 봐야 '남들이 몰려들었는지'가 드러난다.
    등록할 땐 비어 있었는데 그 사이 경쟁이 붙은 경우를 잡아내기 위함이다.

    first_row / last_row: {"total_search", "blog_total_docs"} 형태
    """
    def _pct(old, new):
        if not old or old <= 0:
            return None
        return round((new - old) / old * 100, 1)

    s0 = int(first_row.get("total_search") or 0)
    s1 = int(last_row.get("total_search") or 0)
    d0 = int(first_row.get("blog_total_docs") or 0)
    d1 = int(last_row.get("blog_total_docs") or 0)

    search_pct = _pct(s0, s1)
    docs_pct = _pct(d0, d1)

    # ⚠️ 며칠 사이에 글이 몇 배로 뛰는 일은 현실에서 일어나지 않는다.
    # 그런 값이 나왔다면 측정 방식이 달라졌거나 집계가 튄 것이므로
    # 비교를 포기한다. 잘못된 숫자를 그럴듯하게 보여주는 것보다 낫다.
    # 퍼센트로는 감소를 못 잡는다(최대 -100%). 배수로 본다.
    ratio_jump = False
    if d0 > 0 and d1 > 0:
        r = max(d0, d1) / min(d0, d1)
        ratio_jump = r >= 3          # 3배 이상 차이나면 측정이 튄 것

    if ratio_jump:
        return {
            "search_from": s0, "search_to": s1, "search_pct": search_pct,
            "docs_from": d0, "docs_to": d1, "docs_pct": None,
            "docs_added": None,
            "verdict": "비교 어려움",
            "note": ("문서수 집계가 크게 튀어 비교하지 않았습니다. "
                     "며칠 더 기록이 쌓이면 정상적으로 표시됩니다."),
        }

    return {
        "search_from": s0, "search_to": s1, "search_pct": search_pct,
        "docs_from": d0, "docs_to": d1, "docs_pct": docs_pct,
        "docs_added": d1 - d0 if (d0 and d1) else None,
        **_judge_since(search_pct, docs_pct),
    }


def _judge_since(search_pct, docs_pct):
    """검색량과 글 수의 변화를 조합해 상황을 읽는다."""
    if search_pct is None or docs_pct is None:
        return {"verdict": "비교 준비 중",
                "note": "등록 이후 기록이 더 쌓이면 변화를 보여드립니다."}

    s_up = search_pct >= 10
    s_down = search_pct <= -10
    d_up = docs_pct >= 10
    d_much = docs_pct >= 30

    if s_up and not d_up:
        return {"verdict": "지금이 기회",
                "note": "찾는 사람은 늘었는데 글은 그대로입니다. "
                        "등록할 때보다 조건이 좋아졌습니다."}
    if s_up and d_much:
        return {"verdict": "경쟁 붙는 중",
                "note": "수요도 늘었지만 글이 더 빠르게 쌓이고 있습니다. "
                        "쓰실 거면 서두르셔야 합니다."}
    if s_up and d_up:
        return {"verdict": "같이 커지는 중",
                "note": "수요와 글이 함께 늘고 있습니다. 아직 해볼 만합니다."}
    if not s_up and not s_down and d_much:
        return {"verdict": "불리해짐",
                "note": "찾는 사람은 그대로인데 글만 늘었습니다. "
                        "등록할 때보다 나빠졌습니다."}
    if s_down and d_up:
        return {"verdict": "빠져나올 때",
                "note": "수요는 줄고 글은 늘고 있습니다. 다른 키워드를 보시는 게 낫습니다."}
    if s_down:
        return {"verdict": "식는 중",
                "note": "등록할 때보다 찾는 사람이 줄었습니다."}
    return {"verdict": "큰 변화 없음",
            "note": "등록 이후 검색량과 글 수 모두 비슷합니다."}


# ============================================================
# 자동완성 기반 연관어 (선택 기능)
#
# ⚠️ 왜 필요한가
# 키워드도구는 '광고 도구'다. 광고주가 입찰하는 키워드만 데이터가 있어서
# '현대노조 파업' 같은 이슈성 키워드는 거의 안 나온다.
# 검색창 자동완성은 '사람들이 실제로 친 검색어'라 그런 것까지 잡힌다.
#
# ⚠️ 알아둘 점
# 이건 네이버가 공식 문서로 제공하는 API가 아니다.
# 예고 없이 형식이 바뀌거나 막힐 수 있어서, 실패해도 앱이 죽지 않게
# 만들었다. config의 USE_AUTOCOMPLETE를 끄면 통째로 비활성화된다.
# 유료 서비스로 갈 때는 이 부분을 빼거나 다른 소스로 갈아끼우면 된다.
# ============================================================

AC_URL = "https://ac.search.naver.com/nx/ac"


def _ac_fetch(query):
    """자동완성 한 번 조회. 실패하면 빈 리스트."""
    try:
        res = requests.get(
            AC_URL,
            params={"q": query, "st": "100", "r_format": "json",
                    "r_enc": "UTF-8", "r_unicode": "0", "t_koreng": "1",
                    "q_enc": "UTF-8", "ans": "2"},
            headers={"User-Agent": "Mozilla/5.0",
                     "Referer": "https://search.naver.com/"},
            timeout=5)
        if res.status_code != 200:
            return []
        return _ac_parse(res.json())
    except Exception:
        return []


def _ac_parse(data):
    """
    응답에서 문자열만 긁어낸다.

    구조가 items > [[["키워드", ...], ...], ...] 형태로 중첩돼 있는데,
    형식이 바뀔 수 있으므로 구조를 가정하지 않고 재귀로 훑는다.
    """
    out = []

    def walk(node, depth=0):
        if depth > 6:
            return
        if isinstance(node, str):
            t = node.strip()
            # 숫자나 내부 코드가 섞여 들어오므로 걸러낸다
            if t and not t.isdigit() and len(t) >= 2 and len(t) <= 40:
                out.append(t)
        elif isinstance(node, (list, tuple)):
            for x in node:
                walk(x, depth + 1)
        elif isinstance(node, dict):
            for k in ("items", "answer", "list"):
                if k in node:
                    walk(node[k], depth + 1)

    walk(data.get("items") if isinstance(data, dict) else data)

    # 중복 제거하면서 순서 유지
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def autocomplete_keywords(keyword, expand=True, limit=60):
    """
    자동완성으로 연관 검색어를 모은다.

    expand=True면 뒤에 자모를 붙여 더 넓게 훑는다.
    ('현대노조' → '현대노조ㄱ', '현대노조ㄴ' ... 식으로 물어보면
     자동완성이 더 다양한 결과를 준다)
    """
    ck = ("ac", keyword.strip(), expand, limit)
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    base = keyword.strip()
    if not base:
        return []

    found = list(_ac_fetch(base))

    if expand and len(found) < limit:
        # 자모를 붙여 가지치기. 호출이 늘지만 네이버 광고 API 한도와는
        # 무관하고, 응답도 가벼워서 부담이 적다.
        for ch in "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ":
            if len(found) >= limit:
                break
            found += _ac_fetch(f"{base} {ch}")
            time.sleep(0.05)

    # 원본과 무관한 것, 원본 자체는 제외
    norm = base.replace(" ", "")
    out, seen = [], set()
    for t in found:
        if t in seen or t.replace(" ", "") == norm:
            continue
        seen.add(t)
        out.append(t)

    return _cache_put(ck, out[:limit])
