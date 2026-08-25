"""
키가 제대로 들어갔는지 하나씩 확인한다.

어느 키가 문제인지 화면만 보고는 알 수 없어서,
각 API를 직접 한 번씩 불러보고 결과를 알려준다.
"""

import sys

print("=" * 58)
print("  키워드 헌터 · 키 진단")
print("=" * 58)

# --- 1. .env 파일 읽히는지 ---
try:
    import config
except Exception as e:
    print(f"\n❌ config.py를 읽지 못했습니다: {e}")
    sys.exit(1)

from pathlib import Path
env_path = Path(__file__).parent / ".env"
print(f"\n[1] .env 파일")
if env_path.exists():
    print(f"    ✅ 있음 ({env_path})")
else:
    print(f"    ❌ 없음! 폴더에 .env 파일이 있어야 합니다.")
    print(f"       찾는 위치: {env_path}")
    others = list(Path(__file__).parent.glob("*.env")) + \
             list(Path(__file__).parent.glob("*env*.txt"))
    if others:
        print(f"       혹시 이 파일인가요? {[o.name for o in others]}")
        print(f"       이름을 정확히 '.env' 로 바꿔주세요.")

# --- 2. 값이 들어왔는지 ---
print(f"\n[2] 키 값 확인")
keys = [
    ("NAVER_API_KEY", config.NAVER_API_KEY, True),
    ("NAVER_SECRET_KEY", config.NAVER_SECRET_KEY, True),
    ("NAVER_CUSTOMER_ID", config.NAVER_CUSTOMER_ID, True),
    ("SUPABASE_URL", config.SUPABASE_URL, True),
    ("SUPABASE_KEY", config.SUPABASE_KEY, True),
    ("NAVER_HUB_CLIENT_ID", config.NAVER_HUB_CLIENT_ID, False),
    ("NAVER_HUB_CLIENT_SECRET", config.NAVER_HUB_CLIENT_SECRET, False),
    ("ANTHROPIC_API_KEY", config.ANTHROPIC_API_KEY, False),
    ("TOUR_API_SERVICE_KEY", config.TOUR_API_SERVICE_KEY, False),
]
for name, val, required in keys:
    mark = "필수" if required else "선택"
    if not val:
        print(f"    {'❌' if required else '⚠️ '} {name:<26} 비어 있음 ({mark})")
    else:
        # 따옴표나 공백이 섞였는지
        issue = ""
        if val != val.strip():
            issue = " ← 앞뒤 공백이 있습니다!"
        elif val.startswith('"') or val.startswith("'"):
            issue = " ← 따옴표가 붙어 있습니다!"
        print(f"    ✅ {name:<26} {val[:14]}...({len(val)}자){issue}")

# --- 3. 실제로 불러보기 ---
print(f"\n[3] 실제 호출 테스트")

import requests

# 네이버 검색광고
try:
    import naver_api as n
    path = "/keywordstool"
    res = requests.get(n.NAVER_BASE_URL + path,
                       params={"hintKeywords": "제습기", "showDetail": "1"},
                       headers=n.get_naver_headers("GET", path), timeout=10)
    if res.status_code == 200:
        cnt = len(res.json().get("keywordList", []))
        print(f"    ✅ 네이버 검색광고      정상 (연관어 {cnt}개)")
    else:
        print(f"    ❌ 네이버 검색광고      실패 {res.status_code}")
        print(f"       {res.text[:160]}")
        print(f"       → searchad.naver.com > 도구 > API 사용 관리 에서 키 확인")
except Exception as e:
    print(f"    ❌ 네이버 검색광고      오류: {e}")

# NAVER API HUB
try:
    if not config.NAVER_HUB_CLIENT_ID:
        print(f"    ⚠️  NAVER API HUB      키가 없습니다")
    else:
        res = requests.get(
            config.NAVER_HUB_BLOG_URL,
            headers={"X-NCP-APIGW-API-KEY-ID": config.NAVER_HUB_CLIENT_ID,
                     "X-NCP-APIGW-API-KEY": config.NAVER_HUB_CLIENT_SECRET},
            params={"query": "제습기", "display": 1}, timeout=10)
        if res.status_code == 200:
            total = res.json().get("total", 0)
            print(f"    ✅ NAVER API HUB      정상 (문서 {total:,}건)")
        else:
            print(f"    ❌ NAVER API HUB      실패 {res.status_code}")
            print(f"       {res.text[:160]}")
            print(f"       → console.ncloud.com > NAVER API HUB > Application > 인증 정보")
except Exception as e:
    print(f"    ❌ NAVER API HUB      오류: {e}")

# Anthropic
try:
    if not config.ANTHROPIC_API_KEY:
        print(f"    ⚠️  Anthropic         키가 없습니다 (브리핑만 꺼집니다)")
    else:
        res = requests.post(
            config.ANTHROPIC_URL,
            headers={"Content-Type": "application/json",
                     "x-api-key": config.ANTHROPIC_API_KEY,
                     "anthropic-version": "2023-06-01"},
            json={"model": config.ANTHROPIC_MODEL, "max_tokens": 10,
                  "messages": [{"role": "user", "content": "hi"}]},
            timeout=20)
        if res.status_code == 200:
            print(f"    ✅ Anthropic         정상")
        else:
            print(f"    ❌ Anthropic         실패 {res.status_code}")
            print(f"       {res.text[:160]}")
            print(f"       → console.anthropic.com > API Keys 에서 새 키 발급")
except Exception as e:
    print(f"    ❌ Anthropic         오류: {e}")

# Supabase
try:
    from supabase import create_client
    sb = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    sb.table("trends_master").select("id").limit(1).execute()
    print(f"    ✅ Supabase          정상")
except Exception as e:
    print(f"    ❌ Supabase          오류: {str(e)[:160]}")

# --- 4. 사용량 기록이 되는지 ---
print(f"\n[4] 사용량 기록")
try:
    from supabase import create_client
    import cache
    sb = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    cache.attach(sb)
    before = cache.usage(force=True)["calls"]
    cache.add_calls(1)
    cache.flush_calls()
    after = cache.usage(force=True)["calls"]
    if after > before:
        print(f"    ✅ 정상 ({before:,} → {after:,})")
    else:
        print(f"    ❌ 기록이 안 됩니다 ({before:,} → {after:,})")
        print(f"       api_usage 테이블이 있는지 확인하세요 (DB설정_전체.sql)")
except Exception as e:
    print(f"    ❌ 오류: {str(e)[:160]}")

print("\n" + "=" * 58)
print("  ❌ 표시된 항목의 키를 .env 에서 고쳐주세요.")
print("  고친 뒤에는 검은 창을 닫고 다시 실행해야 합니다.")
print("=" * 58)
