"""
AI 판단 브리핑.

⚠️ 설계 의도
경쟁 서비스들이 붙인 AI는 대부분 '글을 대신 써주는' 기능이다.
그건 ChatGPT를 직접 열면 되는 일이라 굳이 여기서 할 이유가 약하다.

이 모듈은 반대로 간다. 글을 쓰지 않고, **이미 측정한 숫자를 읽고 판단만** 내린다.
경쟁률·상위글 나이·내 블로그 발행 리듬·순위 기록은 이 서비스에만 있는 재료라,
ChatGPT를 따로 열어서는 얻을 수 없는 결론이 나온다.

⚠️ 키가 없으면 조용히 비활성화된다. 나머지 기능은 그대로 동작한다.
"""

import json
import requests

# 키는 config.py에서 읽는다. 없으면 브리핑 기능만 조용히 꺼진다.
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANTHROPIC_URL

SYSTEM_PROMPT = """당신은 네이버 블로그 SEO 애널리스트입니다.
주어진 측정값만 근거로 판단하세요. 측정되지 않은 것은 추측하지 마세요.

규칙:
- 한국어 존댓말, 담백하게. 과장·감탄사 금지.
- 숫자를 그대로 나열하지 말고 '그래서 어떻게 하라'는 결론을 내세요.
- 불리하면 불리하다고 분명히 말하세요. 억지로 긍정하지 마세요.
- 데이터에 없는 사실을 지어내지 마세요.
- 반드시 아래 JSON 형식만 출력하세요. 다른 텍스트·마크다운·코드펜스 금지.

{
  "verdict": "쓰세요" 또는 "조건부" 또는 "피하세요",
  "headline": "한 문장 결론 (40자 이내)",
  "reasons": ["근거 2~3개, 각 45자 이내"],
  "action": "구체적으로 무엇을 할지 한두 문장",
  "watch_out": "주의할 점 한 문장 (없으면 빈 문자열)"
}"""


def _call(prompt, max_tokens=1000):
    """Anthropic API 호출. 실패 시 (None, 오류메시지)."""
    if not ANTHROPIC_API_KEY:
        return None, "no_key"
    try:
        res = requests.post(
            ANTHROPIC_URL,
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": max_tokens,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=40,
        )
        if res.status_code != 200:
            return None, f"API 오류 {res.status_code}: {res.text[:180]}"
        blocks = res.json().get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return text.strip(), None
    except Exception as e:
        return None, f"호출 실패: {e}"


def _parse_json(text):
    """
    모델이 코드펜스나 앞뒤 설명을 붙이는 경우까지 감안해서 JSON만 뽑아낸다.
    중괄호 짝을 세어 첫 완결 객체를 찾는다.
    """
    if not text:
        return None
    t = text.strip()
    start = t.find("{")
    if start == -1:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        c = t[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def brief_keyword(kw, analysis, serp_meta=None, blog_power=None, my_rank=None):
    """
    키워드 하나에 대한 판단 브리핑.
    측정된 값만 넘긴다. 없는 항목은 '측정 안 됨'으로 명시해서 추측을 막는다.
    """
    opp = analysis.get("opportunity") or {}
    facts = {
        "키워드": kw,
        "월 검색량": analysis.get("total_search"),
        "PC 대 모바일": f"{analysis.get('monthly_pc')} / {analysis.get('monthly_mobile')}",
        "이미 쓰인 글(누적)": analysis.get("doc_count"),
        "최근 30일 새 글": analysis.get("recent_docs"),
        "경쟁률(문서수÷검색량)": analysis.get("comp_ratio"),
        "경쟁률 등급": analysis.get("comp_grade"),
        "최근 발행 강도": analysis.get("recent_grade"),
        "기회 점수(0~100)": opp.get("score"),
        "진단": opp.get("label"),
        "광고 경쟁도": analysis.get("pl_avg_depth"),
    }
    if serp_meta:
        facts["상위권 판정"] = serp_meta.get("verdict")
        facts["상위글 나이 중앙값(일)"] = serp_meta.get("median_age")
        facts["상위 10개 중 최근 3개월 글"] = serp_meta.get("fresh_90")
        facts["상위 10개 중 1년 이상 된 글"] = serp_meta.get("old_365")
    if blog_power:
        facts["내 블로그 주당 발행"] = blog_power.get("posts_per_week")
        facts["내 블로그 활동 등급"] = blog_power.get("level")
        facts["내 블로그 마지막 글(일 전)"] = blog_power.get("days_since_last")
    facts["이 키워드 내 순위"] = f"{my_rank}위" if my_rank else "상위 30위 밖"

    lines = [f"- {k}: {v if v is not None else '측정 안 됨'}" for k, v in facts.items()]
    prompt = ("아래는 네이버 블로그 키워드 '%s'의 측정값입니다.\n"
              "이 키워드로 글을 써야 할지 판단해주세요.\n\n%s" % (kw, "\n".join(lines)))

    text, err = _call(prompt)
    if err:
        return None, err
    data = _parse_json(text)
    if not data:
        return None, "응답을 해석하지 못했습니다."
    return data, None


def brief_tracking(rows):
    """
    추적 중인 키워드들의 순위 변화를 읽고 주간 브리핑을 만든다.
    rows: [{"keyword","first_rank","last_rank","records","opportunity","comp_grade"}]
    """
    if not rows:
        return None, "추적 데이터가 없습니다."

    lines = []
    for r in rows:
        fr, lr = r.get("first_rank"), r.get("last_rank")
        move = "기록 부족"
        if fr and lr:
            d = fr - lr
            move = f"{fr}위→{lr}위 ({'상승' if d > 0 else '하락' if d < 0 else '유지'} {abs(d)})"
        elif lr:
            move = f"현재 {lr}위"
        elif fr:
            move = "순위권 밖으로 이탈"
        lines.append(f"- {r['keyword']}: {move}, 기회점수 {r.get('opportunity')}, "
                     f"경쟁률등급 {r.get('comp_grade')}, 기록 {r.get('records')}회")

    prompt = ("아래는 제가 추적 중인 블로그 키워드들의 순위 변화입니다.\n"
              "무엇이 잘되고 있고, 다음에 무엇에 집중해야 할지 판단해주세요.\n\n"
              + "\n".join(lines))

    text, err = _call(prompt)
    if err:
        return None, err
    data = _parse_json(text)
    if not data:
        return None, "응답을 해석하지 못했습니다."
    return data, None


def is_enabled():
    return bool(ANTHROPIC_API_KEY)