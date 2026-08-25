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
한도의 60%에 닿으면 스스로 멈춘다.
"""

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


def gather_seeds():
    """출발점을 모은다. 이미 쌓인 것 중 아직 안 펼친 키워드를 우선."""
    seeds = []

    # ① 오늘의 구글 트렌드
    try:
        import collector
        seeds += collector.fetch_google_top_30()
    except Exception as e:
        print(f"   구글 트렌드를 못 가져왔습니다: {e}")

    # ② 이미 수집된 키워드 (검색량 큰 순)
    try:
        res = (supabase.table("trends_master").select("keyword")
               .order("created_at", desc=True).limit(300).execute())
        seeds += [r["keyword"] for r in (res.data or []) if r.get("keyword")]
    except Exception:
        pass

    # ③ 풀에 있지만 아직 연관어를 펼치지 않은 것
    try:
        res = (supabase.table("keyword_pool").select("keyword")
               .is_("pl_avg_depth", 0)
               .order("updated_at", desc=False).limit(500).execute())
        seeds += [r["keyword"] for r in (res.data or []) if r.get("keyword")]
    except Exception:
        pass

    # 중복 제거하면서 순서 유지
    out, seen = [], set()
    for s in seeds:
        s = (s or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def run(max_calls=None):
    start_size = cache.pool_size()
    u = cache.usage(force=True)
    budget_limit = int(cache.DAILY_LIMIT * cache.SEED_RATIO)

    print("=" * 58)
    print("  씨앗 채우기 — 검색량 미리 쌓기")
    print("=" * 58)
    print(f"\n현재 풀: {start_size:,}개")
    print(f"오늘 사용: {u['calls']:,} / {cache.DAILY_LIMIT:,}회")
    print(f"이번에 쓸 수 있는 한도: {budget_limit:,}회까지 (한도의 "
          f"{cache.SEED_RATIO*100:.0f}%)")

    if not cache.can_seed(1):
        print("\n⚠️ 이미 한도에 도달했습니다. 자정 이후 다시 실행해주세요.")
        print(f"   초기화까지 {cache.reset_time()}")
        return

    queue = deque(gather_seeds())
    if not queue:
        print("\n출발할 키워드를 찾지 못했습니다. 먼저 수집기를 한 번 돌려주세요.")
        return

    print(f"출발 키워드: {len(queue):,}개\n")
    print("-" * 58)

    done, calls, added = set(), 0, 0
    t0 = time.time()

    while queue:
        if not cache.can_seed(1):
            print("\n한도에 도달해 여기서 멈춥니다.")
            break
        if max_calls and calls >= max_calls:
            print(f"\n지정한 {max_calls}회를 다 썼습니다.")
            break

        kw = queue.popleft()
        if kw in done:
            continue
        done.add(kw)

        try:
            data = api.get_keyword_data(kw, related_limit=20)
        except Exception as e:
            print(f"  {kw} 실패: {e}")
            continue
        calls += 1

        rel = data.get("related") or []
        added += len(rel) + 1

        # 받은 연관어를 다음 출발점으로 (검색량 있는 것만)
        for r in rel:
            k = (r.get("keyword") or "").strip()
            if k and k not in done and len(queue) < 20000:
                if (r.get("monthly_pc", 0) + r.get("monthly_mobile", 0)) >= 50:
                    queue.append(k)

        # 무슨 단어가 들어왔는지 보여준다.
        # 개수만 나오면 잘 되고 있는지 감이 안 온다.
        if rel:
            sample = ", ".join(r["keyword"] for r in rel[:5])
            more = f" 외 {len(rel)-5}개" if len(rel) > 5 else ""
            print(f"  [{calls:>4}] {kw}  →  {sample}{more}")

        if calls % 20 == 0:
            cache.flush_calls()          # 모아둔 것을 DB에 반영
            now = cache.usage(force=True)
            elapsed = int(time.time() - t0)
            print(f"       ── 호출 {calls:,} · 대기열 {len(queue):,} · "
                  f"오늘 {now['calls']:,}/{budget_limit:,}회 · {elapsed//60}분 경과 ──")

        time.sleep(0.12)

    cache.flush_calls()
    end_size = cache.pool_size()
    fin = cache.usage(force=True)
    print("-" * 58)
    print(f"\n호출 {calls:,}회 → 풀 {start_size:,} → {end_size:,}개 "
          f"(+{end_size - start_size:,})")
    if calls:
        print(f"호출 1회당 평균 {(end_size - start_size) / calls:.1f}개 확보")
    print(f"오늘 총 사용: {fin['calls']:,} / {cache.DAILY_LIMIT:,}회 ({fin['pct']}%)")
    print(f"\n남은 조회 {fin['remaining']:,}회 · 자정에 초기화 "
          f"({cache.reset_time()})")


if __name__ == "__main__":
    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            pass
    run(max_calls=limit)
