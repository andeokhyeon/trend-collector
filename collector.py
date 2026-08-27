import time
import base64
import hmac
import hashlib
import requests
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from supabase import create_client
from email.utils import parsedate_to_datetime
from urllib.parse import unquote
from datetime import datetime, timedelta, timezone, date

# --- 설정 ---
# 키는 config.py 한 곳에서 읽는다. 코드에는 키를 두지 않는다.
# 키를 넣는 방법은 .env.예시 파일을 참고.
from config import (
    NAVER_API_KEY, NAVER_SECRET_KEY, NAVER_CUSTOMER_ID, NAVER_BASE_URL,
    NAVER_HUB_CLIENT_ID, NAVER_HUB_CLIENT_SECRET, NAVER_HUB_BLOG_URL,
    TOUR_API_SERVICE_KEY, SUPABASE_URL, SUPABASE_KEY,
)

# 💡 여러 함수(급상승 인기상품, 고수익 키워드, 골든타임)에서 공통으로 쓰는 후보 키워드 풀.
# 상품 위주 풀과 고관여 서비스 풀을 분리해두고, 골든타임은 둘 다(+구글 트렌드) 섞어서 쓴다.
# ============================================================
# ⚠️ 고정 시드 키워드를 전부 제거했습니다.
#
# 예전에는 "래시가드, 임플란트, 노트북..." 같은 목록을 코드에 박아두고
# 그 안에서만 순위를 매겼습니다. 그러면 실제로 사람들이 무엇을 찾는지와
# 무관하게 늘 같은 후보군이 돌아서, 결과를 신뢰하기 어려웠습니다.
#
# 이제 모든 탭이 아래 한 갈래에서 출발합니다.
#   오늘의 구글 트렌드(실측)  →  네이버 연관검색어 확장(실측)
# 각 탭은 이 공용 풀에서 조건만 다르게 걸러냅니다.
# ============================================================

_POOL_CACHE = {"pool": None}


def build_keyword_pool(expand_limit=10, force=False):
    """
    오늘의 실데이터로 키워드 풀을 만든다.

    1) 구글 트렌드에서 오늘 실제로 검색되는 키워드를 받는다
    2) 그중 네이버에 검색 데이터가 있는 것만 남긴다
    3) 각각의 연관검색어로 넓힌다 (네이버가 실제로 돌려주는 값)

    한 번 만들면 같은 실행 안에서는 재사용한다. 수집기 한 번 돌 때
    구글 트렌드를 여러 번 부를 이유가 없다.
    """
    if _POOL_CACHE["pool"] is not None and not force:
        return _POOL_CACHE["pool"]

    seeds = fetch_google_top_30()
    print(f"   (풀 구성: 구글 트렌드 {len(seeds)}건에서 출발)")

    pool = {}
    for kw in seeds:
        stat = get_naver_stat(kw)
        total = stat["monthly_pc"] + stat["monthly_mobile"]
        # ⚠️ comp_level로 거르면 안 된다.
        # 구글 트렌드는 '지금 뜨는 이슈'라 네이버 광고 데이터가 없어
        # comp_level이 '-'로 나온다. 그걸 탈락시키면 골든타임의
        # '오늘 트렌드' 탭이 항상 비게 된다.
        # 검색량이 1이라도 있으면 사람들이 찾는 키워드다.
        if total < 1:
            time.sleep(0.05)
            continue
        pool[kw] = {**stat, "origin": "trend"}

        for r in get_related_keywords(kw, limit=expand_limit):
            rk = r.get("keyword", "").strip()
            if not rk or rk in pool:
                continue
            if (r["monthly_pc"] + r["monthly_mobile"]) < 50:
                continue
            pool[rk] = {
                "monthly_pc": r["monthly_pc"],
                "monthly_mobile": r["monthly_mobile"],
                "comp_level": r["comp_level"],
                "pl_avg_depth": 0,
                "origin": "related",
            }
        time.sleep(0.1)

    print(f"   (풀 구성 완료: 총 {len(pool)}개 키워드)")
    _POOL_CACHE["pool"] = pool
    return pool


supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 대시보드와 같은 캐시를 쓴다. 수집기가 채워두면 사용자가 검색할 때
# 이미 캐시에 있어서 네이버를 다시 부르지 않는다.
try:
    import cache
    cache.attach(supabase)
except ImportError:
    cache = None
    print("⚠️ cache.py가 없어 공용 캐시 없이 실행합니다.")

# 💡 신규: 공용 모듈에서 '진짜 경쟁률' 계산 도구를 가져온다.
# (블로그 총 문서수 ÷ 월간 검색량 = 블랙키위의 콘텐츠 포화도에 해당하는 핵심 지표)
from naver_api import (get_blog_doc_count, calc_competition, analyze_keyword,
                       check_my_rank, _to_int, get_recent_doc_count,
                       calc_opportunity, get_related_keywords,
                       get_event_volume)


def track_saved_keywords():
    """
    키워드 추적기 — 저장해둔 키워드의 오늘 상태를 기록한다.

    ⚠️ 호출을 크게 줄인 구조.
    예전에는 사용자마다 analyze_keyword를 따로 불렀다.
    100명이 '제습기 추천'을 추적하면 같은 검색량을 100번 조회한 셈이다.

    검색량과 문서수는 '그 키워드의 값'이지 '내 값'이 아니다.
    그래서 키워드별로 딱 한 번만 재고, 그 결과를 모두가 나눠 쓴다.
    사람마다 다른 건 '내 글의 순위'뿐이라 그것만 개별로 조회한다.

      이전: 사람수 × 추적수 × 3회
      이후: (고유 키워드 수 × 2회) + (글 쓴 항목 수 × 1회)
    """
    try:
        res = supabase.table("tracked_keywords").select("*").execute()
        targets = res.data or []
    except Exception as e:
        print(f"⚠️ 추적 목록을 불러오지 못했습니다: {e}")
        print("   (DB설정_전체.sql 을 Supabase에서 실행했는지 확인해주세요)")
        return []

    if not targets:
        print("   추적 중인 키워드가 없습니다. 대시보드에서 추가해주세요.")
        return []

    # ① 고유 키워드만 추려서 한 번씩만 조회
    unique_kw = []
    seen = set()
    for t in targets:
        kw = (t.get("keyword") or "").strip()
        if kw and kw not in seen:
            seen.add(kw)
            unique_kw.append(kw)

    kw_data = {}
    for kw in unique_kw:
        if not cache or not cache.can_call(2):
            print(f"   ⚠️ 한도에 가까워 여기서 멈춥니다 (조회 {len(kw_data)}개 완료)")
            break
        try:
            kw_data[kw] = analyze_keyword(kw, with_recent=True)
        except Exception as e:
            print(f"   · {kw} 조회 실패: {e}")
        time.sleep(0.12)

    print(f"   (추적 조회: 등록 {len(targets)}건 → 고유 키워드 {len(unique_kw)}개, "
          f"실제 조회 {len(kw_data)}개)")

    # ② 순위는 사람마다 다르므로 개별 조회 (글을 쓴 항목만)
    rows = []
    for t in targets:
        kw = (t.get("keyword") or "").strip()
        blog_id = t.get("blog_id") or ""
        a = kw_data.get(kw)
        if not kw or a is None:
            continue

        has_post = bool(t.get("has_post"))
        rank = None
        if blog_id and has_post:
            if cache and not cache.can_call(1):
                pass                       # 한도가 빠듯하면 순위는 건너뛴다
            else:
                try:
                    rank = check_my_rank(kw, blog_id)
                except Exception:
                    rank = None
                time.sleep(0.1)

        opp = (a.get("opportunity") or {}).get("score", 0)
        rows.append({
            "keyword": kw,
            "blog_id": blog_id,
            "my_rank": rank,
            "total_search": a.get("total_search", 0),
            "blog_total_docs": a.get("doc_count") or 0,
            # 1000건에서 잘린 경우 그대로 저장하면 나중에 계산이 헐거워진다.
            # 실제로는 그보다 많다는 뜻이므로 여유를 얹어 남긴다.
            "recent_docs": (int((a.get("recent_docs") or 0) * 1.5)
                            if a.get("recent_capped")
                            else (a.get("recent_docs") or 0)),
            "comp_ratio": a.get("comp_ratio") or 0,
            "opportunity": opp,
        })
        mark = f"{rank}위" if rank else ("순위밖" if has_post else "지켜보는 중")
        print(f"   · {kw} — {mark}, 기회 {opp}")

    return rows


def enrich_with_competition(results, label=""):
    """
    💡 신규: 수집 결과에 '블로그 총 문서수'와 '진짜 경쟁률'을 붙여준다.

    기존 '경쟁 정도'는 검색량만 보고 매겨서 사실상 인기도였다.
    (검색량이 많다고 경쟁이 센 게 아니다 - 찾는 사람 대비 이미 쓰인 글이
    얼마나 많은지가 진짜 경쟁률이다)
    비율이 낮을수록 = 수요 대비 공급이 적다 = 상위노출 뚫기 좋은 키워드.
    """
    enriched = 0
    for r in results:
        total = r.get("monthly_pc", 0) + r.get("monthly_mobile", 0)
        doc_count = get_blog_doc_count(r["keyword"])
        ratio, grade = calc_competition(total, doc_count)
        r["blog_total_docs"] = doc_count if doc_count is not None else 0
        r["comp_ratio"] = ratio if ratio is not None else 0
        r["comp_grade"] = grade
        if doc_count is not None:
            enriched += 1
        time.sleep(0.1)
    if label:
        print(f"   ({label} 경쟁률 분석: {enriched}/{len(results)}건 성공)")
    return results


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


def get_blog_competition(keyword):
    """
    💡 신규: NAVER API HUB(네이버클라우드)로 '경쟁 블로그 분석'.

    최근 30일 내 그 키워드로 발행된 블로그 글이 몇 개인지 세어서
    "지금 뛰어들면 경쟁이 얼마나 되는지"를 추정한다.

    ⚠️ NAVER API HUB 검색 API는 HMAC 서명이 아니라, 발급받은
    Client ID/Client Secret을 헤더 두 개(X-NCP-APIGW-API-KEY-ID,
    X-NCP-APIGW-API-KEY)에 그대로 넣는 단순한 방식이다.
    NAVER_HUB_CLIENT_ID/SECRET이 없으면(발급 전) None을 반환하고
    호출부에서 이 기능 전체를 건너뛴다 (에러로 죽지 않음).
    """
    if not NAVER_HUB_CLIENT_ID or not NAVER_HUB_CLIENT_SECRET:
        return None

    headers = {
        "X-NCP-APIGW-API-KEY-ID": NAVER_HUB_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NAVER_HUB_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": 30, "sort": "date"}  # 최신순 30건

    try:
        res = requests.get(NAVER_HUB_BLOG_URL, headers=headers, params=params, timeout=5)
        if res.status_code == 200:
            items = res.json().get("items", [])
            now = datetime.now(timezone.utc)
            recent_count = 0
            for item in items:
                postdate = item.get("postdate")  # 'YYYYMMDD' 형식
                if postdate and len(postdate) == 8:
                    try:
                        pdate = datetime.strptime(postdate, "%Y%m%d").replace(tzinfo=timezone.utc)
                        if (now - pdate).days <= 30:
                            recent_count += 1
                    except ValueError:
                        pass
            return recent_count
        else:
            print(f"블로그 검색 API 오류(status {res.status_code}): {res.text[:200]}")
    except Exception as e:
        print(f"블로그 검색 API 실패({keyword}): {e}")
    return None


def fetch_golden_time_keywords():
    """
    골든타임 — 검색이 늘고 있는데 아직 글은 안 쌓인 키워드.

    고정 시드를 쓰지 않는다. 오늘의 구글 트렌드와 그 연관검색어(공용 풀)에서
    아래 관문을 통과한 것만 남긴다.
      1) 직전 수집 대비 검색량이 늘었는가
      2) 최근 30일 새 글이 적은가
      3) 4축 기회 점수가 일정 수준 이상인가
    카테고리는 임의 목록이 아니라 '어디서 나왔는지'(트렌드 본체 / 파생 세부어)로 나눈다.
    """
    if not NAVER_HUB_CLIENT_ID or not NAVER_HUB_CLIENT_SECRET:
        print("⚠️ 골든타임: NAVER_HUB_CLIENT_ID/SECRET이 설정되지 않아 건너뜁니다.")
        return []

    pool = build_keyword_pool()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=20)

    results = []
    api_fail = crowded = no_rise = 0

    for kw, stat in pool.items():
        total = stat["monthly_pc"] + stat["monthly_mobile"]

        # ⚠️ 예전에는 '검색량이 늘어야만' 통과시켰다.
        # 그런데 네이버가 주는 검색량은 한 달 단위 집계라
        # 하루 이틀로는 값이 거의 안 변한다. 그래서 대부분 0이 나오고
        # 전부 탈락해서 골든타임이 늘 비어 있었다.
        #
        # 이제 상승은 '순위를 매기는 재료'로만 쓰고, 탈락 조건에서 뺀다.
        # 대신 '새 글이 적은가'와 '기회 점수'로 거른다.
        rise = get_rise_score(kw, stat, cutoff)
        if rise < 0:
            no_rise += 1
            continue

        rc = get_recent_doc_count(kw)
        if rc is None:
            api_fail += 1
            continue
        recent = rc["count"]

        # ⚠️ 트렌드 본체(구글 트렌드에 뜬 키워드 그 자체)는 이미 다들 쓰고 있어서
        # 세부 키워드와 같은 잣대로 재면 거의 전부 탈락한다.
        # (그래서 '오늘 트렌드' 탭이 늘 비어 있었다.)
        # 카테고리별로 관문을 따로 둔다.
        is_trend = stat.get("origin") == "trend"
        max_recent = 200 if is_trend else 50
        min_score = 30 if is_trend else 40

        docs = get_blog_doc_count(kw)
        ratio, _ = calc_competition(total, docs)
        opp = calc_opportunity(ratio, (recent / total) if total else None,
                               total_search=total)

        # 최근 글이 적고, 종합 판단도 나쁘지 않은 것만.
        # ⚠️ 기준이 빡빡하면 하루에 서너 건밖에 안 나와 화면이 비어 보인다.
        # 최근 글 30개 → 50개, 점수 45 → 40으로 조금 넓혔다.
        if recent <= max_recent and opp["score"] >= min_score:
            results.append({
                "keyword": kw,
                "source": "golden_time",
                "monthly_pc": stat["monthly_pc"],
                "monthly_mobile": stat["monthly_mobile"],
                "comp_level": stat["comp_level"],
                "rise_score": rise,
                "blog_competition": recent,
                "blog_total_docs": docs or 0,
                "comp_ratio": ratio or 0,
                "comp_grade": opp["label"],
                "opportunity": opp["score"],
                "keyword_category": "트렌드" if is_trend else "세부",
            })
        else:
            crowded += 1
        time.sleep(0.1)

    print(f"   (골든타임 진단: 풀 {len(pool)}개 중 검색량하락 {no_rise} / "
          f"API실패 {api_fail} / 조건미달 {crowded} / 통과 {len(results)}건)")

    # 상승폭이 있으면 그걸 먼저, 없으면 기회 점수로 줄 세운다
    def _rank(x):
        return (x["rise_score"] > 0, x["rise_score"], x["opportunity"])

    trend_rows = sorted([r for r in results if r["keyword_category"] == "트렌드"],
                        key=_rank, reverse=True)[:20]
    detail_rows = sorted([r for r in results if r["keyword_category"] == "세부"],
                         key=_rank, reverse=True)[:20]
    return trend_rows + detail_rows


def get_naver_stat(keyword):
    path = "/keywordstool"
    headers = get_naver_headers("GET", path)
    params = {"hintKeywords": keyword.strip(), "showDetail": "1"}
    try:
        res = requests.get(NAVER_BASE_URL + path, params=params, headers=headers)
        if res.status_code == 200:
            kw_list = res.json().get("keywordList", [])
            if kw_list:
                matched = kw_list[0]
                pc = matched.get('monthlyPcQcCnt')
                mobile = matched.get('monthlyMobileQcCnt')

                pc_val = _to_int(pc)
                mob_val = _to_int(mobile)

                # 💡 plAvgDepth: 해당 키워드에 평균적으로 노출되는 광고 개수.
                # 실제 원화 CPC는 아니지만, 광고주들이 얼마나 몰려서 입찰 경쟁을
                # 하는지를 보여주는 값이라 클릭단가(CPC)의 대리 지표로 활용한다.
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
    except:
        pass
    return {"monthly_pc": 0, "monthly_mobile": 0, "comp_level": "-", "pl_avg_depth": 0}


def fetch_google_top_30():
    """
    구글 트렌드 키워드 수집 (최대 30개).
    ⚠️ 상품/쇼핑과 무관한 인물명·이슈성 '짧은 키워드'는 필터링하지 않고 그대로 둔다.
    다만 순위가 내려갈수록 Google이 뉴스 헤드라인을 그대로 트렌드로 잡아주는 경우가
    있는데("MVP 경쟁?...오타니 2홈런 친 날" 같은 문장형), 이런 건 블로그 키워드로
    쓸모가 없으므로 길이/문장부호 패턴으로 걸러낸다. 억지로 30개를 채우지 않고,
    필터를 통과한 만큼만(30개 미만이어도) 반환한다.
    """
    url = "https://trends.google.co.kr/trending/rss?geo=KR"
    headers = {"User-Agent": "Mozilla/5.0"}
    keywords = []
    current_time = time.time()

    # 뉴스 헤드라인에 흔한 문장부호 패턴 (일반 따옴표 + 한글 문서에서 흔한 곱슬따옴표 포함)
    headline_markers = [
        '"', "'", '…', '[', ']', '：', '?', '!',
        '\u2018', '\u2019',  # ‘ ’ (곱슬 홑따옴표)
        '\u201c', '\u201d',  # “ ” (곱슬 겹따옴표)
    ]

    try:
        res = requests.get(url, headers=headers)
        root = ET.fromstring(res.content)

        # 💡 구글 뉴스 섞임 해결: 최상단 channel에 속한 item만 가져옴
        # (item/title = 실제 트렌드 키워드, ht:news_item/ht:news_item_title = 연관 뉴스 제목이라
        #  네임스페이스가 달라 item.find("title")로는 절대 섞이지 않음)
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item"):
                pub_date_str = item.find("pubDate")
                if pub_date_str is not None:
                    pub_ts = parsedate_to_datetime(pub_date_str.text).timestamp()
                    if current_time - pub_ts > 86400:
                        continue
                title = item.find("title")
                if title is not None and title.text:
                    kw = title.text.strip()

                    # 💡 뉴스 헤드라인형 제외: 너무 길거나(20자 초과) 따옴표/물음표/말줄임표 등을 포함
                    if len(kw) > 20:
                        continue
                    if '...' in kw or any(marker in kw for marker in headline_markers):
                        continue
                    # 문장부호가 없어도 단어 수가 많으면(5개 이상) 문장형 헤드라인일 가능성이 높음
                    if len(kw.split()) >= 5:
                        continue

                    if kw not in keywords:
                        keywords.append(kw)
    except Exception as e:
        print(f"구글 파싱 오류: {e}")

    return keywords[:30]


def get_rise_score(keyword, stat, cutoff):
    """
    공용 헬퍼: 어떤 키워드든 '직전 수집 대비 검색량 증가폭'을 계산한다.
    source를 가리지 않고 그 키워드의 가장 최근 이전 스냅샷과 비교한다.
    """
    today_total = stat["monthly_pc"] + stat["monthly_mobile"]
    prev_total = 0
    try:
        prev = supabase.table("trends_master") \
            .select("monthly_pc, monthly_mobile") \
            .eq("keyword", keyword) \
            .lte("created_at", cutoff.isoformat()) \
            .order("created_at", desc=True) \
            .limit(1).execute()
        if prev.data:
            prev_total = prev.data[0]["monthly_pc"] + prev.data[0]["monthly_mobile"]
    except Exception as e:
        print(f"직전 데이터 조회 실패({keyword}): {e}")
    return today_total - prev_total  # 첫 수집일엔 그냥 검색량과 동일


def fetch_monthly_naver_shopping():
    """
    월간 검색 TOP — 오늘의 실데이터 풀에서 검색량이 가장 많은 키워드.
    (예전에는 제가 고른 상품 30개를 고정으로 조회했습니다)
    """
    pool = build_keyword_pool()
    rows = [{
        "keyword": kw,
        "source": "naver_monthly",
        "monthly_pc": st_["monthly_pc"],
        "monthly_mobile": st_["monthly_mobile"],
        "comp_level": st_["comp_level"],
    } for kw, st_ in pool.items()]
    rows.sort(key=lambda x: x["monthly_pc"] + x["monthly_mobile"], reverse=True)
    return rows[:30]


def fetch_realtime_rising_keywords():
    """
    급상승 — 직전 수집 대비 검색량이 가장 많이 오른 키워드.
    풀 자체가 오늘의 트렌드에서 나오므로 후보가 매일 바뀐다.
    """
    pool = build_keyword_pool()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=20)

    rows = []
    for kw, st_ in pool.items():
        rise = get_rise_score(kw, st_, cutoff)
        rows.append({
            "keyword": kw,
            "source": "gmarket_realtime",
            "monthly_pc": st_["monthly_pc"],
            "monthly_mobile": st_["monthly_mobile"],
            "comp_level": st_["comp_level"],
            "rise_score": rise,
        })
    rows.sort(key=lambda x: x["rise_score"], reverse=True)
    print(f"   (급상승: 풀 {len(pool)}개 중 상위 30개 선정)")
    return rows[:30]


def fetch_high_value_keywords():
    """
    고수익 — 광고 경쟁이 치열한(=클릭단가가 높게 형성되는) 키워드.

    ⚠️ 성격이 바뀌었습니다. 예전에는 임플란트·대출 같은 고단가 업종을
    목록으로 박아두고 조회했는데, 그건 실제 트렌드와 무관한 고정값이었습니다.
    이제는 오늘의 실데이터 풀에서 광고가 많이 붙는 키워드를 추립니다.
    """
    pool = build_keyword_pool()

    rows = []
    for kw, st_ in pool.items():
        total = st_["monthly_pc"] + st_["monthly_mobile"]
        if total < 100:
            continue
        # 연관어로 들어온 키워드는 광고 깊이를 아직 모르므로 여기서 조회한다
        depth = st_.get("pl_avg_depth") or 0
        if not depth:
            depth = get_naver_stat(kw).get("pl_avg_depth", 0)
            time.sleep(0.1)
        if depth <= 0:
            continue
        rows.append({
            "keyword": kw,
            "source": "high_value_keyword",
            "monthly_pc": st_["monthly_pc"],
            "monthly_mobile": st_["monthly_mobile"],
            "comp_level": st_["comp_level"],
            "pl_avg_depth": depth,
        })
    rows.sort(key=lambda x: (x["pl_avg_depth"],
                             x["monthly_pc"] + x["monthly_mobile"]), reverse=True)
    print(f"   (고수익: 광고가 붙는 키워드 {len(rows)}개 중 상위 30개)")
    return rows[:30]


def fetch_longtail_keywords():
    """
    롱테일 — 풀 안에서 검색량은 있지만 크지 않고 경쟁이 낮은 세부 키워드.
    시드를 따로 두지 않고, 오늘의 트렌드에서 파생된 연관어 중에서만 고른다.
    """
    pool = build_keyword_pool(expand_limit=20)

    rows = []
    for kw, st_ in pool.items():
        if st_.get("origin") != "related":   # 트렌드 본체는 롱테일이 아니다
            continue
        total = st_["monthly_pc"] + st_["monthly_mobile"]
        if not (50 <= total <= 3000):
            continue
        if st_["comp_level"] not in ("낮음", "중간"):
            continue
        rows.append({
            "keyword": kw,
            "source": "longtail_keyword",
            "monthly_pc": st_["monthly_pc"],
            "monthly_mobile": st_["monthly_mobile"],
            "comp_level": st_["comp_level"],
        })
    rows.sort(key=lambda x: x["monthly_pc"] + x["monthly_mobile"], reverse=True)
    print(f"   (롱테일: 조건 통과 {len(rows)}개 중 상위 60개)")
    return rows[:60]


def get_2026_holidays():
    """
    💡 2026년 대한민국 공휴일 (공공데이터포털 키 없이 바로 쓰도록 하드코딩).
    새해가 바뀌면 이 리스트만 갱신해주면 된다.
    """
    return [
        ("2026-01-01", "신정"),
        ("2026-02-16", "설날 연휴"),
        ("2026-02-17", "설날"),
        ("2026-02-18", "설날 연휴"),
        ("2026-03-01", "삼일절"),
        ("2026-05-05", "어린이날"),
        ("2026-05-24", "부처님오신날"),
        ("2026-06-06", "현충일"),
        ("2026-08-15", "광복절"),
        ("2026-09-24", "추석 연휴"),
        ("2026-09-25", "추석"),
        ("2026-09-26", "추석 연휴"),
        ("2026-10-03", "개천절"),
        ("2026-10-09", "한글날"),
        ("2026-12-25", "크리스마스"),
    ]


def get_upcoming_festivals_tourapi(start_date, end_date):
    """
    💡 한국관광공사 TourAPI로 기간 내 축제/공연/행사 목록 조회.
    (KOPIS는 업종 종사자만 승인되는 경우가 있어 일반인도 자동승인되는 TourAPI로 대체)
    ⚠️ TOUR_API_SERVICE_KEY가 없으면(발급 전) 빈 리스트를 반환한다.
    발급: https://www.data.go.kr → '한국관광공사' 검색 → '국문 관광정보 서비스' 활용신청
    """
    if not TOUR_API_SERVICE_KEY:
        return []
    url = "https://apis.data.go.kr/B551011/KorService2/searchFestival2"
    params = {
        "serviceKey": TOUR_API_SERVICE_KEY,
        "numOfRows": 30,
        "pageNo": 1,
        "MobileOS": "ETC",
        "MobileApp": "KeywordHunter",
        "_type": "json",
        "eventStartDate": start_date,   # YYYYMMDD (필수)
        "eventEndDate": end_date,       # YYYYMMDD
        "arrange": "A",
    }
    events = []
    try:
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            items = res.json().get("response", {}).get("body", {}).get("items", {}).get("item", [])
            if isinstance(items, dict):  # 결과가 1건이면 dict로 오는 경우가 있어 리스트로 통일
                items = [items]
            for item in items:
                title = item.get("title")
                date = item.get("eventstartdate")
                if title:
                    events.append((date, title.strip()))
        else:
            print(f"TourAPI 오류(status {res.status_code}): {res.text[:200]}")
    except Exception as e:
        print(f"TourAPI 실패: {e}")
    return events


# ============================================================
# 공공데이터 — 주간 캘린더 재료
#
# ⚠️ data.go.kr은 계정마다 인증키가 하나다. 이미 TourAPI를 쓰고 있으면
#    같은 키로 아래 서비스도 쓸 수 있고, 포털에서 '활용신청'만 누르면 된다.
#    (대부분 자동승인이라 몇 분이면 끝난다)
#    안 눌렀거나 키가 없으면 각 함수는 조용히 빈 목록을 돌려주고,
#    프로그램은 있는 재료만으로 계속 돈다.
# ============================================================

# 한국천문연구원 특일 정보 — 공휴일 / 24절기 / 잡절(초복·말복 등)
# 활용신청: https://www.data.go.kr/data/15012690/openapi.do
KASI_BASE = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService"
KASI_OPS = [
    ("getRestDeInfo", "공휴일"),
    ("get24DivisionsInfo", "절기"),
    ("getSundryDayInfo", "절기"),      # 초복·중복·말복·한식 등
]

# 한국부동산원 청약홈 분양정보
# 활용신청: https://www.data.go.kr/data/15098547/openapi.do
# ⚠️ 승인 뒤 그 페이지에 적힌 '요청주소'를 그대로 여기에 붙여넣으면 된다.
APPLYHOME_URL = ("https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1"
                 "/getAPTLttotPblancDetail")

# 전국공연행사정보표준데이터 — 선택 항목이다.
#
# ⚠️ 표준데이터는 주소 끝에 계정마다 다른 uddi 값이 붙어서
#    (…/v1/uddi:3ecb3d51-…) 승인 화면을 보기 전에는 주소를 알 수 없다.
#    여기가 비어 있어도 축제/행사는 TourAPI로 이미 들어오니
#    캘린더는 아쉬운 대로 다 돈다. 주소를 넣으면 지자체 소규모 행사가 더해진다.
#    활용신청: 공공데이터포털에서 '전국공연행사정보표준데이터' 검색
PUBLIC_EVENT_URL = ""     # 예: https://api.odcloud.kr/api/15013106/v1/uddi:xxxx-xxxx

# 마지막 호출이 어떻게 됐는지 — 점검 도구가 원인을 보여주려고 쓴다
APPLYHOME_LAST = {"status": None, "body": "", "how": ""}
PUBLIC_EVENT_LAST = {"status": None, "body": "", "how": ""}


def _kasi_month(year, month, op, kind):
    """특일정보 한 달치. 실패하면 빈 목록."""
    if not TOUR_API_SERVICE_KEY:
        return []
    out = []
    try:
        res = requests.get(
            f"{KASI_BASE}/{op}",
            params={"serviceKey": TOUR_API_SERVICE_KEY,
                    "solYear": year, "solMonth": f"{month:02d}",
                    "numOfRows": 60, "_type": "json"},
            timeout=6)
        if res.status_code != 200:
            return []
        body = res.json().get("response", {}).get("body", {})
        items = (body.get("items") or {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        for it in items:
            loc = str(it.get("locdate") or "")
            name = (it.get("dateName") or "").strip()
            if len(loc) == 8 and name:
                out.append((f"{loc[:4]}-{loc[4:6]}-{loc[6:8]}", name, kind))
    except Exception:
        pass
    return out


def get_special_days_kasi(start_date, end_date):
    """
    💡 공휴일 + 24절기 + 잡절을 천문연구원에서 받아온다.

    ⚠️ 왜 하드코딩을 두고 이걸 붙였나.
      1) 해마다 손으로 공휴일을 적어 넣지 않아도 된다
      2) 임시공휴일·대체공휴일이 생기면 자동으로 따라 들어온다
      3) 초복·중복·말복(삼계탕), 동지(팥죽), 입춘 같은 자리가 새로 생긴다
         — 매년 확실하게 검색이 뛰는데 지금 캘린더에는 없던 것들이다
    """
    out, seen = [], set()
    y, m = start_date.year, start_date.month
    for _ in range(3):                 # 4주면 길어야 석 달에 걸친다
        for op, kind in KASI_OPS:
            for d, name, k in _kasi_month(y, m, op, kind):
                key = (d, name)
                if key in seen:
                    continue
                seen.add(key)
                dt = datetime.strptime(d, "%Y-%m-%d").date()
                if start_date <= dt <= end_date:
                    out.append((d, name, k))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def get_tax_deadlines(start_date, end_date):
    """
    💡 세금·신고·마감 일정.

    ⚠️ 국세청은 Open API가 없다. 대신 날짜가 법으로 정해져 있어서
       해마다 거의 안 바뀐다. 그래서 여기에 적어둔다.
       (주말·공휴일에 걸리면 하루 이틀 밀린다 — 국세청 공고로 확인)

    💰 한국 블로그에서 광고단가가 가장 높은 축인데 캘린더에 하나도 없었다.
       '종합소득세 신고'는 5월 한 달 검색이 폭발하고, 그 글은 1년 내내 돈다.
    """
    # (월, 일, 이름) — 이름은 사람들이 실제로 검색하는 형태로 적는다
    FIXED = [
        (1, 15, "연말정산 간소화"),
        (1, 25, "부가가치세 신고"),
        (2, 28, "연말정산 서류제출"),
        (3, 31, "법인세 신고"),
        (5, 1, "종합소득세 신고"),
        (5, 1, "근로장려금 신청"),
        (5, 31, "종합소득세 마감"),
        (6, 16, "자동차세 납부"),
        (7, 16, "재산세 납부"),
        (7, 25, "부가가치세 신고"),
        (8, 31, "주민세 납부"),
        (9, 16, "재산세 납부"),
        (12, 1, "종합부동산세 납부"),
        (12, 16, "자동차세 납부"),
    ]
    out = []
    for year in {start_date.year, end_date.year}:
        for mth, day, name in FIXED:
            try:
                d = date(year, mth, day)
            except ValueError:
                continue
            if start_date <= d <= end_date:
                out.append((d.strftime("%Y-%m-%d"), name, "세무/마감"))
    return out


def _odcloud_get(url, params=None, timeout=8):
    """
    odcloud(api.odcloud.kr) 계열 호출 — 청약홈·표준데이터가 여기에 산다.

    ⚠️ 여기서 막히는 이유는 대개 셋 중 하나다.
      ① data.go.kr이 인증키를 '인코딩'과 '디코딩' 두 가지로 준다.
         인코딩 키(%2B, %3D가 섞인 것)를 그대로 params에 넣으면
         requests가 %를 %25로 한 번 더 감싸서 다른 키가 돼버린다.
      ② odcloud는 쿼리 대신 'Authorization: Infuser <키>' 헤더도 받는다.
         쿼리 쪽이 막힐 때 헤더로는 되는 경우가 있다.
      ③ 주소 자체가 다르다 (표준데이터는 끝에 uddi:… 가 붙는다)

    그래서 되는 방법을 찾을 때까지 순서대로 시도하고,
    끝내 안 되면 마지막 응답을 그대로 돌려줘서 원인을 볼 수 있게 한다.
    반환: (json 또는 None, 상태코드, 본문 앞부분, 어떤 방법이 통했는지)
    """
    key = (TOUR_API_SERVICE_KEY or "").strip()
    if not key:
        return None, 0, "인증키 없음", ""
    dec = unquote(key)
    base = dict(params or {})

    attempts = [
        ("쿼리(원본 키)", {**base, "serviceKey": key}, None),
        ("쿼리(디코딩 키)", {**base, "serviceKey": dec}, None),
        ("헤더 Infuser(원본)", base, {"Authorization": f"Infuser {key}"}),
        ("헤더 Infuser(디코딩)", base, {"Authorization": f"Infuser {dec}"}),
    ]
    last = (None, 0, "", "")
    for how, prm, hdr in attempts:
        try:
            res = requests.get(url, params=prm, headers=hdr, timeout=timeout)
        except Exception as e:
            last = (None, 0, f"{type(e).__name__}: {e}", how)
            continue
        body = (res.text or "")[:180].replace("\n", " ")
        if res.status_code == 200:
            try:
                return res.json(), 200, body, how
            except Exception:
                last = (None, 200, body, how)
                continue
        last = (None, res.status_code, body, how)
        if res.status_code == 404:
            break          # 주소가 틀린 것 — 키를 바꿔봐야 소용없다
    return last


def get_apply_home_schedule(start_date, end_date):
    """
    💡 청약 일정 (한국부동산원 청약홈).

    모집공고일·청약접수일·당첨자발표일이 날짜로 나온다.
    단지 이름은 아직 아무도 안 썼기 때문에 경쟁 문서수가 거의 0이고,
    부동산은 광고단가가 높다. '미리 써두면 유리한' 자리의 표본이다.
    """
    # ⚠️ 예전에는 cond[RCRIT_PBLANC_DE::GTE] 로 서버에서 걸러 달라고 했는데,
    # 필드 이름이 조금만 달라도 통째로 거절당한다. 넉넉히 받아서 여기서 거른다.
    data, status, body, how = _odcloud_get(
        APPLYHOME_URL, {"page": 1, "perPage": 1000})
    if data is None:
        APPLYHOME_LAST["status"] = status
        APPLYHOME_LAST["body"] = body
        return []
    APPLYHOME_LAST["status"] = 200
    APPLYHOME_LAST["how"] = how

    out = []
    for it in (data.get("data") or []):
        name = (it.get("HOUSE_NM") or it.get("HOUSE_NM_NM") or "").strip()
        # 접수 시작일이 있으면 그 날, 없으면 모집공고일
        raw = (it.get("RCEPT_BGNDE") or it.get("RCRIT_PBLANC_DE") or "")
        d = str(raw)[:10].replace(".", "-").replace("/", "-")
        if not (name and len(d) == 10):
            continue
        try:
            dt = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            continue
        if start_date <= dt <= end_date:
            out.append((d, f"{name} 청약", "청약"))
    return out


def get_public_events(start_date, end_date):
    """
    💡 전국공연행사정보 (지자체 표준데이터).

    TourAPI 축제와 겹치는 것도 있지만, 이쪽에는 지자체가 여는
    작은 행사까지 들어온다. 검색량은 작아도 경쟁이 거의 없어서
    지역 블로그에는 오히려 이쪽이 낫다.
    """
    if not PUBLIC_EVENT_URL:
        PUBLIC_EVENT_LAST["status"] = "미입력"
        return []
    data, status, body, how = _odcloud_get(
        PUBLIC_EVENT_URL, {"page": 1, "perPage": 1000})
    if data is None:
        PUBLIC_EVENT_LAST["status"] = status
        PUBLIC_EVENT_LAST["body"] = body
        return []
    PUBLIC_EVENT_LAST["status"] = 200
    PUBLIC_EVENT_LAST["how"] = how

    out = []
    if True:
        for it in (data.get("data") or []):
            name = (it.get("공연행사명") or it.get("행사명") or "").strip()
            d = str(it.get("공연행사시작일자") or it.get("행사시작일자") or "")[:10]
            if not (name and len(d) == 10):
                continue
            try:
                dt = datetime.strptime(d, "%Y-%m-%d").date()
            except ValueError:
                continue
            if start_date <= dt <= end_date:
                out.append((d, name, "공연/행사"))
    return out


def fetch_weekly_event_keywords():
    """
    💡 주별 추천키워드 — 앞으로 4주 안에 무슨 일이 있는지.

    재료 다섯 가지를 합친다.
      ① 공휴일·24절기·잡절   천문연구원 (키 없으면 적어둔 공휴일로 물러남)
      ② 세금·신고 마감        적어둔 일정 (API 없음, 광고단가 최상위)
      ③ 축제/행사            TourAPI
      ④ 청약 일정            청약홈
      ⑤ 지자체 공연/행사      전국공연행사 표준데이터

    ⚠️ 어느 하나가 막혀도 나머지로 계속 돈다. 캘린더가 통째로 비지 않게.
    """
    today = datetime.now(timezone.utc).date()
    four_weeks_later = today + timedelta(days=28)

    picked = []          # (날짜문자열, 이름, 종류)

    # ① 공휴일 + 절기
    special = get_special_days_kasi(today, four_weeks_later)
    if special:
        picked += special
    else:
        # 천문연구원 키가 아직 승인 전 — 적어둔 공휴일로 버틴다
        for date_str, name in get_2026_holidays():
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if today <= d <= four_weeks_later:
                picked.append((date_str, name, "공휴일"))

    # ② 세금·신고 마감
    picked += get_tax_deadlines(today, four_weeks_later)

    # ③ 축제/행사 (TourAPI)
    for date_str, title in get_upcoming_festivals_tourapi(
            today.strftime("%Y%m%d"), four_weeks_later.strftime("%Y%m%d")):
        if date_str and len(date_str) == 8:
            picked.append((f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
                           title, "축제/행사"))

    # ④ 청약 일정
    picked += get_apply_home_schedule(today, four_weeks_later)

    # ⑤ 지자체 공연/행사
    picked += get_public_events(today, four_weeks_later)

    # 같은 날 같은 이름이 두 곳에서 들어오는 일이 있다 (축제 ↔ 공연행사)
    results, seen = [], set()
    for date_str, name, kind in picked:
        name = (name or "").strip()
        key = (date_str, name.replace(" ", ""))
        if not name or key in seen:
            continue
        seen.add(key)
        results.append({
            "keyword": name,
            "source": "weekly_event",
            "monthly_pc": 0,
            "monthly_mobile": 0,
            "comp_level": kind,
            "event_date": date_str,
        })

    results.sort(key=lambda r: r["event_date"])

    # 검색량 조회.
    # ⚠️ 공공데이터의 행사명은 공식 명칭이라 길고 장식이 많다.
    #    '국토정중앙 청춘양구 배꼽축제'를 그대로 조회하면 0이 나온다.
    #    사람들이 실제로 치는 형태('배꼽축제', '양구 배꼽축제')로 줄여서 찾는다.
    # ⚠️ 재료가 다섯 가지로 늘면서 이벤트가 수십 개가 된다.
    #    전부 검색량을 물어보면 그만큼 한도를 쓰는데,
    #    청약 단지명·지자체 행사명은 어차피 0이 나온다(아무도 그 이름으로 안 친다).
    #    캘린더가 판단에 쓰는 값은 '작년 급등폭'(데이터랩)이지 이 검색량이 아니다.
    #    그래서 값이 나올 만한 것만, 그것도 40개까지만 물어본다.
    SKIP_VOL = {"청약", "공연/행사"}
    asked = 0
    for r in results:
        if r["comp_level"] in SKIP_VOL or asked >= 40:
            continue
        asked += 1
        try:
            vol, used = get_event_volume(r["keyword"])
        except Exception:
            vol, used = 0, r["keyword"]
        # 모바일 비중이 큰 편이라 7:3으로 나눠 담는다 (표시용)
        r["monthly_mobile"] = int(vol * 0.7)
        r["monthly_pc"] = vol - int(vol * 0.7)
        if used != r["keyword"]:
            r["search_form"] = used     # 실제로 검색된 형태
        time.sleep(0.12)

    kinds = {}
    for r in results:
        kinds[r["comp_level"]] = kinds.get(r["comp_level"], 0) + 1
    if kinds:
        print("   " + " · ".join(f"{k} {v}개" for k, v in kinds.items()))

    return results


def fetch_naver_news_headlines_30():
    url = "https://news.naver.com/main/ranking/popularDay.naver"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    results = []
    try:
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        titles = soup.select(".list_content a.list_title")
        for t in titles:
            headline = t.text.strip()
            if headline and len(results) < 30:
                results.append({
                    "keyword": headline,
                    "source": "naver_news",
                    "monthly_pc": 0,
                    "monthly_mobile": 0,
                    "comp_level": "이슈"
                })
    except Exception as e:
        print("뉴스 크롤링 실패:", e)
    return results


# ============================================================
# 수집 항목 켜고 끄기
#
# 네이버 API 호출 한도가 넉넉하지 않다. 매번 전부 수집할 필요는 없으니
# 여기서 필요한 것만 True로 두면 된다.
# (한 번 돌 때 대략 몇 회를 쓰는지 옆에 적어뒀다)
# ============================================================
COLLECT = {
    # 대시보드에 살아 있는 탭만 수집한다.
    "google_trend":  True,   # 구글 트렌드      · 약 20회
    "golden_time":   True,   # 골든타임         · 약 60회
    "weekly_event":  True,   # 주간 캘린더      · 약 40회 (공공데이터 5종)
    "news":          True,   # 네이버 뉴스      · 약 0회 (크롤링, API 안 씀)
    "tracking":      True,   # 추적기 기록      · 고유 키워드 수 × 2회

    # 아래는 대시보드에서 탭을 내렸다. 필요하면 True로 켜고
    # app.py의 sub_discover 탭도 함께 되살려야 화면에 보인다.
    "monthly":       False,  # 월간 검색 TOP
    "rising":        False,  # 급상승
    "high_value":    False,  # 고수익
    "longtail":      False,  # 롱테일
}

# ⚠️ 항목마다 적정 주기가 다르다.
#
# 수집기를 1시간마다 돌리더라도 모든 항목을 매번 부를 이유는 없다.
# 네이버 검색량은 한 달 단위 집계라 1시간 만에 바뀌지 않고,
# 공휴일이나 축제 일정은 하루에 바뀔 일이 없다.
#
# 아래 숫자는 '최소 몇 시간 간격으로 돌릴지'다.
# 0이면 매번, 24면 하루 한 번.
# 전부 매시간 돌리면 하루 2,520회, 나눠 돌리면 740회로 줄어든다.
INTERVAL_HOURS = {
    "google_trend":  0,    # 실시간 트렌드라 매번 볼 가치가 있다
    "golden_time":   6,    # 검색량이 월 단위라 6시간이면 충분
    "weekly_event": 24,    # 공휴일·축제는 하루에 안 바뀐다
    "news":          0,    # 크롤링이라 API를 안 쓴다
    "tracking":     12,    # 순위는 하루 1~2번이면 충분
    "monthly":      24,
    "rising":        6,
    "high_value":   24,
    "longtail":     24,
}


# ⚠️ 명령줄에서 항목 이름을 주면 그것만, 간격을 무시하고 돌린다.
#    (예: python collector.py weekly)
#
#    왜 필요했나. 주간 캘린더는 24시간에 한 번만 수집한다.
#    그래서 캘린더에 새 재료(청약·절기 같은 것)를 붙여도
#    "최근 24시간 안에 이미 수집함"으로 건너뛰어, 하루를 기다려야
#    화면에 나타났다. 고쳐놓고도 안 나오니 안 고쳐진 줄 알게 된다.
ONLY = None          # None이면 평소대로 전부


def _should_run(name):
    """
    이 항목을 지금 돌려야 하는지.
    마지막 수집 시각을 DB에서 보고 판단한다.
    """
    if ONLY is not None:
        # 지목한 항목은 간격을 무시하고 돌리고, 나머지는 건너뛴다
        return name == ONLY
    hours = INTERVAL_HOURS.get(name, 0)
    if hours <= 0:
        return True
    try:
        src = {"google_trend": "google_trend", "golden_time": "golden_time",
               "weekly_event": "weekly_event", "news": "naver_news",
               "monthly": "naver_monthly", "rising": "gmarket_realtime",
               "high_value": "high_value_keyword",
               "longtail": "longtail_keyword"}.get(name)
        if not src:
            return True
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        res = (supabase.table("trends_master").select("created_at")
               .eq("source", src).gte("created_at", cutoff)
               .limit(1).execute())
        if res.data:
            print(f"   ⏭  {name}: 최근 {hours}시간 안에 이미 수집함, 건너뜁니다")
            return False
    except Exception:
        pass
    return True


ENRICH_COMPETITION = False


def main():
    import config
    missing, optional_missing = config.check()
    if missing:
        print("=" * 60)
        print("❌ API 키가 설정되지 않았습니다.")
        print("   .env.예시 파일을 복사해 .env 로 이름을 바꾸고 키를 넣어주세요.")
        print("   빠진 항목:", ", ".join(missing))
        print("=" * 60)
        return
    if optional_missing:
        print(f"⚠️ 선택 키가 없어 일부 기능을 건너뜁니다: {', '.join(optional_missing)}")

    print("=" * 60)
    print("🚀 데이터 수집을 시작합니다.")
    on = [k for k, v in COLLECT.items() if v]
    print(f"   수집 항목: {', '.join(on)}")
    if not ENRICH_COMPETITION:
        print("   (경쟁률 보강 꺼짐 — collector.py의 ENRICH_COMPETITION로 조절)")
    print("=" * 60)

    # 소스별로 "수집 → 즉시 저장"을 하나씩 처리한다.
    # 한 곳이 스키마 오류로 실패해도 나머지는 안전하게 저장된다.
    def save(label, rows):
        if not rows:
            print(f"⚠️ {label}: 수집된 데이터가 없어 저장을 건너뜁니다.")
            return
        try:
            supabase.table("trends_master").insert(rows).execute()
            print(f"✅ {label} 완료 및 저장 ({len(rows)}건)")
        except Exception as e:
            print(f"❌ {label} 저장 실패: {e}")

    def maybe_enrich(rows, label):
        return enrich_with_competition(rows, label) if ENRICH_COMPETITION else rows

    if COLLECT["google_trend"] and _should_run("google_trend"):
        google_data = []
        for kw in fetch_google_top_30():
            stat = get_naver_stat(kw)
            google_data.append({
                "source": "google_trend", "keyword": kw,
                "monthly_pc": stat["monthly_pc"],
                "monthly_mobile": stat["monthly_mobile"],
                "comp_level": stat["comp_level"],
            })
        save("구글 트렌드", google_data)

    if COLLECT["monthly"] and _should_run("monthly"):
        save("월간 네이버 검색", fetch_monthly_naver_shopping())

    if COLLECT["rising"] and _should_run("rising"):
        save("실시간 급상승",
             maybe_enrich(fetch_realtime_rising_keywords(), "급상승"))

    if COLLECT["news"] and _should_run("news"):
        save("네이버 뉴스", fetch_naver_news_headlines_30())

    if COLLECT["high_value"] and _should_run("high_value"):
        save("고수익 키워드",
             maybe_enrich(fetch_high_value_keywords(), "고수익"))

    if COLLECT["longtail"] and _should_run("longtail"):
        save("롱테일 키워드 확장",
             maybe_enrich(fetch_longtail_keywords(), "롱테일"))

    if COLLECT["golden_time"] and _should_run("golden_time"):
        save("골든타임 키워드", fetch_golden_time_keywords())

    if COLLECT["weekly_event"] and _should_run("weekly_event"):
        save("주별 추천키워드(공휴일/축제 등)", fetch_weekly_event_keywords())

    # 오래된 캐시 정리 (쌓이면 조회가 느려진다)
    if cache:
        cache.cleanup()

    if COLLECT["tracking"] and _should_run("tracking"):
        print("\n📌 추적 중인 키워드 기록...")
        rows = track_saved_keywords()
        if rows:
            try:
                supabase.table("tracking_history").insert(rows).execute()
                print(f"✅ 추적 기록 저장 ({len(rows)}건)")
            except Exception as e:
                print(f"❌ 추적 기록 저장 실패: {e}")

    try:
        if cache:
            cache.flush_calls()
        u = cache.usage(force=True) if cache else None
        if u is None:
            raise RuntimeError
        print(f"\n📊 오늘 네이버 호출 {u['calls']:,} / {u['limit']:,}회 "
              f"({u['pct']}%) · 남은 조회 {u['remaining']:,}회")
        if u["blocked"]:
            print(f"   ⚠️ 한도에 가까워 일부 조회를 건너뛰었습니다. "
                  f"{cache.reset_time()} 초기화됩니다.")
    except Exception:
        pass

    print("\n🎉 전체 수집 프로세스 종료")


ALIASES = {
    "weekly": "weekly_event", "캘린더": "weekly_event",
    "golden": "golden_time", "골든타임": "golden_time",
    "google": "google_trend", "트렌드": "google_trend",
    "news": "news", "뉴스": "news",
    "tracking": "tracking", "추적": "tracking",
}


if __name__ == "__main__":
    import sys
    arg = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if arg in ("-h", "--help", "help", "?"):
        print("\n사용법:")
        print("  python collector.py           전부 수집 (평소대로)")
        print("  python collector.py weekly    주간 캘린더만, 지금 바로")
        print("  python collector.py golden    골든타임만, 지금 바로")
        print("\n  쓸 수 있는 이름: " + ", ".join(sorted(set(ALIASES))))
        print()
    elif arg:
        picked = ALIASES.get(arg)
        if not picked:
            print(f"\n'{arg}'는 모르는 항목입니다.")
            print("  쓸 수 있는 이름: " + ", ".join(sorted(set(ALIASES))) + "\n")
        else:
            ONLY = picked
            print(f"\n▶ '{picked}'만 지금 바로 수집합니다 "
                  f"(수집 간격을 무시합니다)\n")
            main()
    else:
        main()
