"""
씨앗 채우기 — 검색량을 미리 쌓아두는 도구.

⚠️ 왜 필요한가
네이버 키워드도구는 한 번 호출에 연관 키워드를 20개씩 돌려준다.
지금까지는 그중 1개만 쓰고 19개를 버렸다. 그게 가장 큰 낭비였다.

이 도구는 구글 트렌드에서 출발해 연관어를 타고 계속 뻗어나가며
받은 걸 전부 저장한다. 호출 1회에 21개가 쌓이므로,
하루 한도의 60%만 써도 수십만 개까지 모을 수 있다.

⚠️ 문서수는 쌓지 않는다.
문서수는 키워드마다 따로 불러야 해서 100만 개면 100만 회, 40일이 걸린다.
애초에 성립하지 않는 계산이라 '물어봤을 때만' 재는 쪽이 맞다.

밤에 켜두고 자면 아침에 DB가 두꺼워져 있다.

⚠️ 두 가지 방식으로 돈다.
  · 그냥 실행       → 한도(60%)를 다 쓰면 끝난다.
  · forever 옵션    → 끝내지 않는다. 한도를 다 쓰면 초기화될 때까지 기다렸다가
                     스스로 다시 시작하고, 펼칠 키워드가 떨어지면 새로 긁어온다.
                     멈추는 건 사람이 Ctrl+C를 누르거나 창을 닫을 때뿐이다.
"""

# ⚠️ 윈도우 작업 스케줄러가 이 파일을 돌릴 때, 출력이 파일로 넘어가면
# 파이썬이 콘솔 코드페이지(cp949)로 글자를 쓴다. 그러면 첫 줄의 이모지에서
# UnicodeEncodeError가 나고 수집이 통째로 죽는다.
# (실제로 자동수집이 며칠간 이 한 줄에서 매번 죽고 있었다)
# 어디서 어떻게 실행되든 상관없게 출력 인코딩을 UTF-8로 고정한다.
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


import sys
import time
from collections import deque

import config
import cache
from supabase import create_client

missing, _ = config.check()
if missing:
    print("❌ API 키가 없습니다:", ", ".join(missing))
    print("   .env 파일을 확인해주세요.")
    sys.exit(1)

supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
cache.attach(supabase)

import naver_api as api


def _secs_to_reset():
    """
    한도 카운터가 초기화되기까지 남은 초.

    ⚠️ cache._today()가 UTC 날짜를 쓰므로 실제 초기화 시점은
    UTC 자정(= 한국시간 오전 9시)이다. 한국 자정이 아니다.
    """
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    nxt = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((nxt - now).total_seconds()))


def _sleep_with_countdown(seconds, reason):
    """
    기다리는 동안 남은 시간을 한 줄로 계속 갱신한다.
    가만히 멈춰 있으면 고장 난 줄 알기 때문이다. Ctrl+C로 언제든 끊을 수 있다.
    """
    end = time.time() + seconds
    while True:
        left = int(end - time.time())
        if left <= 0:
            break
        h, m = divmod(left // 60, 60)
        if h:
            left_txt = f"{h}시간 {m}분"
        elif m:
            left_txt = f"{m}분"
        else:
            left_txt = f"{left}초"          # 1분 미만은 초로 (0분으로 안 보이게)
        print(f"\r  {reason} · {left_txt} 뒤 재개  (Ctrl+C로 종료)      ",
              end="", flush=True)
        time.sleep(min(30, max(1, left)))
    print("\r" + " " * 64 + "\r", end="")


def _backoff(streak, reason=""):
    """
    네이버가 연달아 거절할 때만 쉰다. 이어질수록 더 오래.
    5회 30초 → 10회 1분 → 20회 3분 → 그 이상 10분.
    막힌 문을 계속 두드리지 않게 하는 장치다.

    ⚠️ '연관어가 없는 키워드'는 여기로 오지 않는다. 그건 거절이 아니라
    그냥 흔한 일이라, 예전에는 그것 때문에 멀쩡히 돌다가 멈춰 섰다.
    """
    if streak < 5:
        wait = 1
    elif streak < 10:
        wait = 30
    elif streak < 20:
        wait = 60
    elif streak < 40:
        wait = 180
    else:
        wait = 600
    if wait <= 2:
        time.sleep(wait)
        return
    why = {"quota": "한도", "http429": "너무 자주 불렀음",
           "http403": "권한 거절", "http401": "인증 오류"}.get(reason, reason or "거절")
    _sleep_with_countdown(wait, f"네이버가 거절함 · {why} ({streak}회 연속)")


def wait_until_quota(check_every=300):
    """한도를 다 썼을 때, 다시 쓸 수 있을 때까지 기다린다."""
    while not cache.can_seed(1):
        _sleep_with_countdown(min(check_every, _secs_to_reset()), "한도 소진")
        cache.usage(force=True)          # 날짜가 바뀌었는지 다시 확인
    print("\n한도가 초기화됐습니다. 다시 시작합니다.\n")


# 키워드도구에 넣어봐야 소용없는 것들.
#
# ⚠️ 출발 키워드는 trends_master에서도 가져오는데, 거기에는
# 네이버 뉴스 제목이 통째로 들어 있다.
# ("식당 만취난동 끝에 자기들끼리 '피 터지게' 치고받은 가족" 같은 것)
# 이런 문장을 키워드도구에 보내면 항상 빈 결과가 돌아오고,
# 그게 쌓이면 프로그램이 '네이버가 막았나 보다' 하고 30초씩 쉰다.
# 그래서 보내기 전에 걸러낸다. 호출 한 번도 낭비하지 않는다.
_BAD_CHARS = set("\"'\u2018\u2019\u201c\u201d[]()<>{}!?,.\u00b7\u2026~|/\\+*=&%#@;:\u3008\u3009\u300c\u300d\u300e\u300f")


def usable_seed(kw):
    """키워드도구가 알아들을 만한 낱말인지."""
    k = (kw or "").strip()
    if not k:
        return False
    if len(k.replace(" ", "")) > 20:     # 문장은 못 알아듣는다
        return False
    if len(k.split()) > 3:               # 낱말 서넛까지가 한계
        return False
    if any(c in _BAD_CHARS for c in k):
        return False
    return True


def gather_seeds(page=0, quiet=False):
    """
    출발점을 모은다. 이미 쌓인 것 중 아직 안 펼친 키워드를 우선.

    ⚠️ page를 올리면 풀의 더 깊은 곳을 가져온다.
    계속 도는 모드에서 같은 500개만 반복해 읽으면
    전부 '이미 펼친 것'이라 할 일이 없다고 오판한다.
    """
    seeds = []

    # ① 오늘의 구글 트렌드
    try:
        import collector
        seeds += collector.fetch_google_top_30()
    except Exception as e:
        if not quiet:
            print(f"   구글 트렌드를 못 가져왔습니다: {e}")

    # ② 이미 수집된 키워드 (최근 것부터)
    try:
        res = (supabase.table("trends_master").select("keyword")
               .order("created_at", desc=True).limit(300).execute())
        seeds += [r["keyword"] for r in (res.data or []) if r.get("keyword")]
    except Exception:
        pass

    # ③ 풀에 쌓여 있는 키워드 — 오래 안 건드린 것부터, 페이지를 넘겨가며
    #
    # ⚠️ 예전 코드는 .is_("pl_avg_depth", 0) 이었는데
    # PostgREST에서 IS는 null/true/false에만 쓴다. 0에 쓰면 요청이 거절돼
    # 이 줄이 조용히 아무것도 못 가져오고 있었다. (except가 삼켰다)
    PAGE = 1000
    try:
        lo = (page % 50) * PAGE
        res = (supabase.table("keyword_pool").select("keyword")
               .order("updated_at", desc=False)
               .range(lo, lo + PAGE - 1).execute())
        seeds += [r["keyword"] for r in (res.data or []) if r.get("keyword")]
    except Exception:
        try:
            res = (supabase.table("keyword_pool").select("keyword")
                   .order("updated_at", desc=False).limit(PAGE).execute())
            seeds += [r["keyword"] for r in (res.data or []) if r.get("keyword")]
        except Exception:
            pass

    # 중복 제거하면서 순서 유지. 문장·특수문자는 여기서 버린다.
    out, seen, dropped = [], set(), 0
    for s in seeds:
        s = (s or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        if usable_seed(s):
            out.append(s)
        else:
            dropped += 1
    if dropped and not quiet:
        print(f"   뉴스 제목처럼 낱말이 아닌 것 {dropped:,}개는 건너뜁니다.")
    return out


def run(max_calls=None, forever=False, ignore_limit=False):
    start_size = cache.pool_size()
    u = cache.usage(force=True)
    budget_limit = int(cache.DAILY_LIMIT * cache.SEED_RATIO)

    print("=" * 58)
    print("  씨앗 채우기 — 검색량 미리 쌓기"
          + ("  [멈출 때까지 계속]" if forever else ""))
    print("=" * 58)
    print(f"\n현재 풀: {start_size:,}개")
    print(f"오늘 사용: {u['calls']:,} / {cache.DAILY_LIMIT:,}회")
    print(f"이번에 쓸 수 있는 한도: {budget_limit:,}회까지 (한도의 "
          f"{cache.SEED_RATIO*100:.0f}%)")
    if ignore_limit:
        # ⚠️ 여기서 끄는 건 '우리가 스스로 걸어둔' 안전선이다.
        # 네이버 쪽 진짜 한도는 그대로 있다. 넘어가면 거절(429)이 돌아오고,
        # 그때부터는 아무것도 못 받으면서 계속 두드리게 된다.
        # 그래서 거절이 이어지면 스스로 쉬었다 간다.
        api.IGNORE_QUOTA = True
        print("\n⚠️  한도 무시 모드")
        print("   우리가 걸어둔 안전선(하루 60%)을 끕니다.")
        print("   네이버가 실제로 거절할 때까지 계속 부릅니다.")
        print("   거절이 이어지면 잠시 쉬었다가 다시 시도합니다.")
        print("   ※ 대시보드 조회 몫까지 당겨쓰게 되니, 낮에는 권하지 않습니다.")
    if forever:
        print("\n⏻ 멈추려면 Ctrl+C 를 누르거나 이 창을 닫으세요.")
        if not ignore_limit:
            print("   한도를 다 쓰면 초기화될 때까지 기다렸다가 알아서 다시 시작합니다.")

    done, calls, added = set(), 0, 0
    rounds = 0
    refused = 0          # 네이버가 연달아 거절한 횟수
    barren = 0           # 연관어가 없던 키워드 수 (정상)
    t0 = time.time()
    stop_reason = "끝"

    try:
        while True:
            if not ignore_limit and not cache.can_seed(1):
                if not forever:
                    print("\n⚠️ 한도에 도달했습니다. 자정 이후 다시 실행해주세요.")
                    print(f"   초기화까지 {cache.reset_time()}")
                    stop_reason = "한도"
                    break
                wait_until_quota()

            # ⚠️ 이미 펼친 키워드가 수십만 개까지 늘면 메모리를 계속 먹는다.
            # 한 바퀴 크게 돌았으면 기억을 비우고 처음부터 다시 훑는다.
            # (풀에 이미 저장돼 있으므로 중복 호출은 캐시가 막아준다)
            if len(done) > 300_000:
                print("\n  훑은 키워드가 30만 개를 넘어 목록을 비우고 다시 돕니다.\n")
                done.clear()

            queue = deque(k for k in gather_seeds(page=rounds, quiet=rounds > 0)
                           if k not in done)
            rounds += 1
            if not queue:
                if not forever:
                    print("\n출발할 키워드를 찾지 못했습니다. "
                          "먼저 수집기를 한 번 돌려주세요.")
                    stop_reason = "씨앗 없음"
                    break
                # 풀의 다음 페이지를 곧바로 시도한다. 50페이지를 다 훑어도
                # 새 게 없을 때만 쉰다. (수집기가 새 키워드를 넣어줄 때까지)
                if rounds % 50 != 0:
                    continue
                print("\n  새로 펼칠 키워드가 없습니다. 10분 뒤 다시 찾아봅니다.")
                _sleep_with_countdown(600, "대기 중")
                continue

            print(f"\n출발 키워드: {len(queue):,}개")
            print("-" * 58)

            while queue:
                if not ignore_limit and not cache.can_seed(1):
                    if not forever:
                        print("\n한도에 도달해 여기서 멈춥니다.")
                        stop_reason = "한도"
                    break
                if max_calls and calls >= max_calls:
                    print(f"\n지정한 {max_calls}회를 다 썼습니다.")
                    stop_reason = "지정 횟수"
                    break

                kw = queue.popleft()
                if kw in done:
                    continue
                done.add(kw)

                try:
                    data = api.get_keyword_data(kw, related_limit=20)
                except Exception as e:
                    print(f"  {kw} 실패: {e}")
                    refused += 1
                    _backoff(refused, type(e).__name__)
                    continue
                calls += 1

                rel = data.get("related") or []
                added += len(rel) + 1

                # ⚠️ 예전에는 '연관어가 없다'와 '네이버가 거절했다'를
                # 똑같이 취급해서, 멀쩡히 도는 중에도 30초씩 멈춰 섰다.
                # 연관어가 없는 키워드는 그냥 흔한 일이다 — 다음으로 넘어간다.
                # 진짜로 쉬어야 할 때는 네이버가 거절했을 때뿐이다.
                err = data.get("error")
                if err:
                    refused += 1
                    _backoff(refused, err)
                    if refused >= 40 and not forever:
                        print("\n네이버가 계속 거절합니다. 여기서 멈춥니다.")
                        stop_reason = "거절"
                        break
                    continue
                refused = 0
                if not rel:
                    barren += 1
                    continue

                # 받은 연관어를 다음 출발점으로 (검색량 있는 것만)
                for r in rel:
                    k = (r.get("keyword") or "").strip()
                    if k and k not in done and len(queue) < 20000:
                        if (r.get("monthly_pc", 0)
                                + r.get("monthly_mobile", 0)) >= 50 \
                                and usable_seed(k):
                            queue.append(k)

                # 무슨 단어가 들어왔는지 보여준다.
                # 개수만 나오면 잘 되고 있는지 감이 안 온다.
                if rel:
                    sample = ", ".join(r["keyword"] for r in rel[:5])
                    more = f" 외 {len(rel)-5}개" if len(rel) > 5 else ""
                    print(f"  [{calls:>5}] {kw}  →  {sample}{more}")

                if calls % 20 == 0:
                    cache.flush_calls()      # 모아둔 것을 DB에 반영
                    now = cache.usage(force=True)
                    elapsed = int(time.time() - t0)
                    hh, mm = divmod(elapsed // 60, 60)
                    barren_txt = f" · 연관어 없던 것 {barren:,}" if barren else ""
                    print(f"       ── 호출 {calls:,} · 대기열 {len(queue):,} · "
                          f"오늘 {now['calls']:,}/{budget_limit:,}회{barren_txt} · "
                          f"{hh}시간 {mm}분 경과 ──")

                time.sleep(0.12)

            if not forever:
                break
            # forever 모드에서는 대기열이 비면 씨앗을 새로 긁어 계속 돈다

    except KeyboardInterrupt:
        stop_reason = "사용자 중지"
        print("\n\n■ 중지 요청을 받았습니다. 지금까지 쌓은 것을 저장하고 끝냅니다.")

    cache.flush_calls()
    end_size = cache.pool_size()
    fin = cache.usage(force=True)
    elapsed = int(time.time() - t0)
    hh, mm = divmod(elapsed // 60, 60)

    print("-" * 58)
    print(f"\n[{stop_reason}]  {hh}시간 {mm}분 동안 호출 {calls:,}회")
    print(f"풀 {start_size:,} → {end_size:,}개 (+{end_size - start_size:,})")
    if calls:
        print(f"호출 1회당 평균 {(end_size - start_size) / calls:.1f}개 확보")
    print(f"오늘 총 사용: {fin['calls']:,} / {cache.DAILY_LIMIT:,}회 ({fin['pct']}%)")
    print(f"\n남은 조회 {fin['remaining']:,}회 · 초기화까지 {cache.reset_time()}")


if __name__ == "__main__":
    # 사용법
    #   python seed_pool.py            한도(60%)까지만 채우고 끝
    #   python seed_pool.py forever    멈출 때까지 계속 (Ctrl+C로 종료)
    #   python seed_pool.py nolimit    한도 무시하고 계속 (네이버가 막을 때까지)
    #   python seed_pool.py 500        500회만 쓰고 끝
    limit, forever, ignore = None, False, False
    for arg in sys.argv[1:]:
        a = arg.strip().lower()
        if a in ("forever", "loop", "--forever", "-f", "무한", "계속"):
            forever = True
            continue
        if a in ("nolimit", "--nolimit", "무제한", "한도무시"):
            ignore = True
            forever = True          # 한도를 무시한다는 건 곧 계속 돌겠다는 뜻
            continue
        try:
            limit = int(a)
        except ValueError:
            pass
    run(max_calls=limit, forever=forever, ignore_limit=ignore)
