"""
API 키와 설정을 한 곳에서 읽는다.

⚠️ 왜 이렇게 바꿨나
예전에는 키가 app.py, collector.py, naver_api.py, ai_brief.py에
그대로 적혀 있었다. 그러면 세 가지 문제가 생긴다.
  1) GitHub에 올리는 순간 봇이 몇 분 안에 긁어간다
  2) 키를 바꿀 때 네 파일을 다 고쳐야 한다
  3) 백업 파일 하나만 잘못 공유해도 통째로 샌다

이제 키는 코드에 없다. 아래 순서로 찾는다.
  1) .streamlit/secrets.toml   (Streamlit 배포 시 권장)
  2) 환경변수                   (서버 운영 시 권장)
  3) .env 파일                  (내 PC에서 쓸 때 가장 간편)

셋 다 없으면 그 기능만 조용히 꺼지고, 나머지는 정상 동작한다.
"""

import os
from pathlib import Path

_ENV_FILE = Path(__file__).parent / ".env"
_env_cache = None


def _load_env_file():
    """.env 파일을 읽는다. 형식은 KEY=값 한 줄에 하나."""
    global _env_cache
    if _env_cache is not None:
        return _env_cache
    _env_cache = {}
    if _ENV_FILE.exists():
        try:
            for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                _env_cache[k.strip()] = v.strip().strip('"').strip("'")
        except Exception as e:
            print(f"⚠️ .env 파일을 읽지 못했습니다: {e}")
    return _env_cache


def get(name, default=""):
    """설정값 하나를 가져온다."""
    # 1) Streamlit secrets — 배포 환경
    try:
        import streamlit as st
        if hasattr(st, "secrets") and name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass

    # 2) 환경변수
    val = os.environ.get(name)
    if val:
        return val

    # 3) .env 파일
    val = _load_env_file().get(name)
    if val:
        return val

    return default


# --- 네이버 검색광고 API (검색량·연관키워드) ---
NAVER_API_KEY = get("NAVER_API_KEY")
NAVER_SECRET_KEY = get("NAVER_SECRET_KEY")
NAVER_CUSTOMER_ID = get("NAVER_CUSTOMER_ID")
NAVER_BASE_URL = "https://api.searchad.naver.com"

# --- NAVER API HUB (블로그 검색) ---
NAVER_HUB_CLIENT_ID = get("NAVER_HUB_CLIENT_ID")
NAVER_HUB_CLIENT_SECRET = get("NAVER_HUB_CLIENT_SECRET")
NAVER_HUB_BLOG_URL = "https://naverapihub.apigw.ntruss.com/search/v1/blog"

# --- Supabase ---
SUPABASE_URL = get("SUPABASE_URL")
SUPABASE_KEY = get("SUPABASE_KEY")

# --- 한국관광공사 TourAPI (축제/행사) ---
TOUR_API_SERVICE_KEY = get("TOUR_API_SERVICE_KEY")

# --- 관리자 화면 ---
#
# 관리 탭은 평소에 아예 보이지 않는다.
# 주소 뒤에 열쇠말을 붙였을 때만 나타난다.
#
#   https://내주소.streamlit.app/?dog11286575=1
#
# 그렇게 들어가도 비밀번호를 한 번 더 물어보므로 이중으로 막힌다.
# ⚠️ 제대로 된 회원 로그인이 아니라 '나만 보는 화면' 용도의 간단한 잠금이다.
ADMIN_PASSWORD = get("ADMIN_PASSWORD")
ADMIN_KEY = get("ADMIN_KEY", "dog11286575")

# --- Anthropic (AI 판단 브리핑) ---
ANTHROPIC_API_KEY = get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def check():
    """
    어떤 키가 있고 없는지 알려준다.
    반환: (필수 중 빠진 것, 선택 중 빠진 것)
    """
    required = {
        "NAVER_API_KEY": NAVER_API_KEY,
        "NAVER_SECRET_KEY": NAVER_SECRET_KEY,
        "NAVER_CUSTOMER_ID": NAVER_CUSTOMER_ID,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY,
    }
    optional = {
        "NAVER_HUB_CLIENT_ID": NAVER_HUB_CLIENT_ID,
        "NAVER_HUB_CLIENT_SECRET": NAVER_HUB_CLIENT_SECRET,
        "TOUR_API_SERVICE_KEY": TOUR_API_SERVICE_KEY,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
    }
    return ([k for k, v in required.items() if not v],
            [k for k, v in optional.items() if not v])
