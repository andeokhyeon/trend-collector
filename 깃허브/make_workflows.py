"""
.github/workflows/ 폴더와 워크플로 파일을 만든다.

점으로 시작하는 폴더는 탐색기에서 만들기가 번거로워서
이 스크립트로 대신 생성한다.
"""
from pathlib import Path

d = Path(__file__).parent / ".github" / "workflows"
d.mkdir(parents=True, exist_ok=True)

SECRETS = """          NAVER_API_KEY:           ${{ secrets.NAVER_API_KEY }}
          NAVER_SECRET_KEY:        ${{ secrets.NAVER_SECRET_KEY }}
          NAVER_CUSTOMER_ID:       ${{ secrets.NAVER_CUSTOMER_ID }}
          SUPABASE_URL:            ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY:            ${{ secrets.SUPABASE_KEY }}
          NAVER_HUB_CLIENT_ID:     ${{ secrets.NAVER_HUB_CLIENT_ID }}
          NAVER_HUB_CLIENT_SECRET: ${{ secrets.NAVER_HUB_CLIENT_SECRET }}
          TOUR_API_SERVICE_KEY:    ${{ secrets.TOUR_API_SERVICE_KEY }}
          ANTHROPIC_API_KEY:       ${{ secrets.ANTHROPIC_API_KEY }}"""

BASE = """name: {name}

on:
  schedule:
    - cron: '{cron}'
  workflow_dispatch:

concurrency:
  group: {group}
  cancel-in-progress: false

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: {timeout}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - env:
{secrets}
        run: python {script}
"""

(d / "collector.yml").write_text(BASE.format(
    name="collector", cron="17 */2 * * *", group="collector",
    timeout=30, secrets=SECRETS, script="collector.py"), encoding="utf-8")

(d / "seed.yml").write_text(BASE.format(
    name="seed-pool", cron="23 18 * * *", group="seed",
    timeout=120, secrets=SECRETS, script="seed_pool.py"), encoding="utf-8")

print("Created:")
for f in sorted(d.iterdir()):
    print("  ", f.relative_to(Path(__file__).parent))
print()
print("Next: commit and push, then register 9 secrets on GitHub.")
print("See GitHub_auto_setup.md for details.")
