"""
.env 내용을 GitHub Secrets에 넣기 쉽게 보여준다.

GitHub는 키를 하나씩 따로 등록해야 해서,
어떤 이름에 어떤 값을 넣을지 헷갈리기 쉽다.
"""
from pathlib import Path

NAMES = [
    "NAVER_API_KEY", "NAVER_SECRET_KEY", "NAVER_CUSTOMER_ID",
    "SUPABASE_URL", "SUPABASE_KEY",
    "NAVER_HUB_CLIENT_ID", "NAVER_HUB_CLIENT_SECRET",
    "TOUR_API_SERVICE_KEY", "ANTHROPIC_API_KEY",
    "ADMIN_PASSWORD", "ADMIN_KEY",
]

env = Path(__file__).parent / ".env"
if not env.exists():
    print("[ERROR] .env 파일이 없습니다.")
    raise SystemExit(1)

vals = {}
for line in env.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip().strip('"').strip("'")

print("=" * 62)
print("  GitHub Secrets 등록용")
print("=" * 62)
print()
print("  저장소 > Settings > Secrets and variables > Actions")
print("  > New repository secret 을 눌러 하나씩 등록하세요.")
print()
print("  ⚠️ 값에 따옴표를 붙이지 마세요.")
print()
print("-" * 62)

for n in NAMES:
    v = vals.get(n, "")
    if not v:
        print(f"\n[{n}]")
        print("  (비어 있음 — 선택 키라면 건너뛰어도 됩니다)")
    else:
        print(f"\n[{n}]")
        print(f"  {v}")

print()
print("-" * 62)
print(f"  등록할 항목: {sum(1 for n in NAMES if vals.get(n))}개")
print("=" * 62)
