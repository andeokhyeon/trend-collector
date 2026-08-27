# -*- coding: utf-8 -*-
"""
공공데이터 점검 — 주간 캘린더 재료 다섯 가지가 지금 되는지 하나씩 눌러본다.

⚠️ data.go.kr은 계정마다 인증키가 하나다. TourAPI가 되고 있다면 나머지도
   같은 키로 되는데, 서비스마다 '활용신청'을 한 번씩 눌러야 한다.
   무엇이 막혀 있는지 화면으로 알려주려고 만든 파일이다.

실행: 8_공공데이터_점검.bat
"""
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, ".")

OK, NO, WARN = "[ 됨 ]", "[안됨]", "[주의]"


def line(mark, name, msg=""):
    print(f"  {mark}  {name:<22} {msg}")


def _why(last, label, url, const_name, portal):
    """왜 안 되는지를 상태코드로 갈라서 알려준다."""
    st = (last or {}).get("status")
    body = (last or {}).get("body", "")
    if st == "미입력":
        line(WARN, label, "주소를 안 넣으셨습니다 (선택 항목)")
        print("           축제/행사는 ③번(TourAPI)으로 이미 들어옵니다.")
        print("           지자체 소규모 행사까지 원하시면:")
        print(f"           → {portal}")
        print("             승인 화면의 '요청주소'(끝에 uddi:… 가 붙습니다)를")
        print(f"             collector.py의 {const_name} 에 넣어주세요.")
        return
    if st == 404:
        line(NO, label, "주소가 틀립니다 (404)")
        print(f"           지금 쓰는 주소: {url}")
        print(f"           → {portal}")
        print("             승인 화면 아래 '요청주소'를 그대로 복사해서")
        print(f"             collector.py의 {const_name} 에 붙여넣어 주세요.")
        print("             표준데이터는 주소 끝에 uddi:… 가 붙습니다.")
        print("             (아직 활용신청 전이면 그 페이지에서 신청부터)")
    elif st in (401, 403):
        line(NO, label, f"인증이 막혔습니다 ({st})")
        print("           → 활용신청이 '승인'인지, 그리고 마이페이지의")
        print("             '일반 인증키(Decoding)'를 쓰고 있는지 확인해주세요.")
        print("             (Encoding 키에는 %2B 같은 게 섞여 있어 어긋납니다)")
    elif st == 0:
        line(NO, label, f"연결 실패 — {body}")
    elif st is None:
        line(NO, label, "활용신청을 아직 안 하셨습니다")
        print(f"           → {portal} 에서 활용신청")
    else:
        line(NO, label, f"응답 {st}")
        if body:
            print(f"           서버 답: {body}")
        print(f"           → {portal}")


def main():
    print()
    print("=" * 62)
    print("  공공데이터 점검 — 주간 캘린더 재료")
    print("=" * 62)

    try:
        import collector
    except Exception as e:
        print(f"\n  collector.py를 읽지 못했습니다: {e}")
        return

    key = getattr(collector, "TOUR_API_SERVICE_KEY", "")
    print()
    if not key:
        line(NO, "data.go.kr 인증키", "config.py의 TOUR_API_SERVICE_KEY가 비어 있습니다")
        print()
        print("  → https://www.data.go.kr 가입 후 마이페이지에서 '일반 인증키'를")
        print("    복사해 config.py의 TOUR_API_SERVICE_KEY에 넣어주세요.")
        print("    (키 하나로 아래 서비스를 전부 씁니다)")
        print()
        return
    line(OK, "data.go.kr 인증키", f"…{key[-6:]} (뒤 6자리)")

    today = datetime.now(timezone.utc).date()
    later = today + timedelta(days=28)
    print()
    print("-" * 62)

    # ① 천문연구원 특일정보
    try:
        sp = collector.get_special_days_kasi(today, later)
    except Exception as e:
        sp = []
        print(f"      ({e})")
    if sp:
        kinds = sorted({k for _, _, k in sp})
        line(OK, "① 공휴일·절기", f"{len(sp)}건 · {', '.join(kinds)}")
        for d, n, k in sp[:4]:
            print(f"           {d}  {n} ({k})")
    else:
        line(NO, "① 공휴일·절기", "활용신청이 필요합니다")
        print("           https://www.data.go.kr/data/15012690/openapi.do")
        print("           → 활용신청 (자동승인) 후 몇 분 뒤 다시 실행")

    # ② 세무·마감 — API가 없으니 항상 된다
    tx = collector.get_tax_deadlines(today, later)
    line(OK, "② 세무·마감 일정", f"앞으로 4주 안에 {len(tx)}건 (API 불필요)")
    for d, n, _ in tx[:4]:
        print(f"           {d}  {n}")

    # ③ TourAPI 축제
    try:
        fes = collector.get_upcoming_festivals_tourapi(
            today.strftime("%Y%m%d"), later.strftime("%Y%m%d"))
    except Exception as e:
        fes = []
        print(f"      ({e})")
    if fes:
        line(OK, "③ 축제/행사", f"{len(fes)}건")
        for d, n in fes[:3]:
            print(f"           {d}  {n}")
    else:
        line(NO, "③ 축제/행사", "활용신청 또는 키를 확인하세요")
        print("           https://www.data.go.kr → '국문 관광정보 서비스'")

    # ④ 청약홈
    try:
        ap = collector.get_apply_home_schedule(today, later)
    except Exception as e:
        ap = []
        print(f"      ({e})")
    if ap:
        line(OK, "④ 청약 일정", f"{len(ap)}건")
        for d, n, _ in ap[:3]:
            print(f"           {d}  {n}")
    else:
        _why(collector.APPLYHOME_LAST, "④ 청약 일정",
             collector.APPLYHOME_URL, "APPLYHOME_URL",
             "https://www.data.go.kr/data/15098547/openapi.do")

    # ⑤ 전국공연행사
    try:
        pe = collector.get_public_events(today, later)
    except Exception as e:
        pe = []
        print(f"      ({e})")
    if pe:
        line(OK, "⑤ 공연/행사", f"{len(pe)}건")
        for d, n, _ in pe[:3]:
            print(f"           {d}  {n}")
    else:
        _why(collector.PUBLIC_EVENT_LAST, "⑤ 공연/행사",
             collector.PUBLIC_EVENT_URL, "PUBLIC_EVENT_URL",
             "https://www.data.go.kr/data/15013106/standard.do")

    print("-" * 62)
    core = [sp, tx, fes, ap]          # ⑤는 선택 항목이라 세지 않는다
    got = sum(1 for x in core if x)
    print()
    print(f"  꼭 필요한 네 가지 중 {got}가지가 지금 들어옵니다."
          + (" (⑤ 공연/행사도 들어옴)" if pe else ""))
    if got < 4:
        print("  안 되는 것이 있어도 캘린더는 나머지로 그대로 돕니다.")
    print()


if __name__ == "__main__":
    main()
