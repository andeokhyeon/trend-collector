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
from datetime import datetime, timedelta, timezone

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
        if stat["comp_level"] == "-" or total < 50:
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
                       calc_opportunity, get_related_keywords)


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
            "recent_docs": a.get("recent_docs") or 0,
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

        rise = get_rise_score(kw, stat, cutoff)
        if rise <= 0:
            no_rise += 1
            continue

        rc = get_recent_doc_count(kw)
        if rc is None:
            api_fail += 1
            continue
        recent = rc["count"]

        docs = get_blog_doc_count(kw)
        ratio, _ = calc_competition(total, docs)
        opp = calc_opportunity(ratio, (recent / total) if total else None,
                               total_search=total)

        # 최근 글이 적고, 종합 판단도 나쁘지 않은 것만
        if recent <= 30 and opp["score"] >= 45:
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
                "keyword_category": "트렌드" if stat.get("origin") == "trend" else "세부",
            })
        else:
            crowded += 1
        time.sleep(0.1)

    print(f"   (골든타임 진단: 풀 {len(pool)}개 중 상승없음 {no_rise} / "
          f"API실패 {api_fail} / 조건미달 {crowded} / 통과 {len(results)}건)")

    trend_rows = sorted([r for r in results if r["keyword_category"] == "트렌드"],
                        key=lambda x: x["opportunity"], reverse=True)[:30]
    detail_rows = sorted([r for r in results if r["keyword_category"] == "세부"],
                         key=lambda x: x["opportunity"], reverse=True)[:30]
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


def fetch_weekly_event_keywords():
    """
    💡 주별 추천키워드.

    "이번 주부터 4주 뒤까지 어떤 날짜에 무슨 일이 있는지"를 미리 모아서 키워드로
    던져준다. 공휴일(즉시 사용 가능)과 축제/행사(TourAPI, 키 발급 시 자동 포함)를
    합친다. 법령 시행일 정보도 같은 방식으로 확장 가능(법제처 Open API).
    """
    today = datetime.now(timezone.utc).date()
    four_weeks_later = today + timedelta(days=28)

    results = []

    # 1) 공휴일 (즉시 가능)
    for date_str, name in get_2026_holidays():
        event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        if today <= event_date <= four_weeks_later:
            results.append({
                "keyword": name,
                "source": "weekly_event",
                "monthly_pc": 0,
                "monthly_mobile": 0,
                "comp_level": "공휴일",
                "event_date": date_str
            })

    # 2) 축제/행사 (TourAPI 키 있을 때만 자동 포함)
    festivals = get_upcoming_festivals_tourapi(
        today.strftime("%Y%m%d"), four_weeks_later.strftime("%Y%m%d")
    )
    for date_str, title in festivals:
        formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}" if date_str and len(date_str) == 8 else None
        results.append({
            "keyword": title,
            "source": "weekly_event",
            "monthly_pc": 0,
            "monthly_mobile": 0,
            "comp_level": "축제/행사",
            "event_date": formatted_date
        })

    # 3) TODO: 법령 시행일 (법제처 Open API, open.law.go.kr, 무료 OC 발급 필요)

    # 검색량 조회해서 실제로 사람들이 찾는지도 같이 확인 (선택 정보)
    for r in results:
        stat = get_naver_stat(r["keyword"])
        r["monthly_pc"] = stat["monthly_pc"]
        r["monthly_mobile"] = stat["monthly_mobile"]
        time.sleep(0.1)

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
    "weekly_event":  True,   # 주간 캘린더      · 약 20회
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


def _should_run(name):
    """
    이 항목을 지금 돌려야 하는지.
    마지막 수집 시각을 DB에서 보고 판단한다.
    """
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


if __name__ == "__main__":
    main()