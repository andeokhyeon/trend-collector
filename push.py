"""
바뀐 코드를 GitHub에 올린다.

⚠️ 올리기 전에 키가 새는지 스스로 검사한다.
   .env 같은 파일이 목록에 있으면 멈추고 알려준다.
   손으로 git status를 확인하는 걸 잊어도 사고가 안 나게 하기 위함이다.
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent

# 절대 올라가면 안 되는 것들
DANGER_NAMES = [".env", "secrets.toml"]
DANGER_EXT = [".env"]
DANGER_TEXT = ["sk-ant-api03", "sb_publishable", "sb_secret"]


def run(args, capture=True):
    return subprocess.run(args, cwd=HERE, capture_output=capture,
                          text=True, encoding="utf-8", errors="replace")


def main():
    print("=" * 58)
    print("  GitHub에 올리기")
    print("=" * 58)

    # git이 있는지
    if run(["git", "--version"]).returncode != 0:
        print("\n❌ git이 설치되어 있지 않습니다.")
        print("   git-scm.com 에서 설치한 뒤 다시 실행해주세요.")
        return 1

    if not (HERE / ".git").exists():
        print("\n❌ 이 폴더는 아직 GitHub와 연결되지 않았습니다.")
        return 1

    # 바뀐 게 있는지
    st = run(["git", "status", "--porcelain"])
    if not st.stdout.strip():
        print("\n바뀐 파일이 없습니다. 올릴 게 없어요.")
        return 0

    print("\n[1] 바뀐 파일")
    changed = []
    for line in st.stdout.splitlines():
        name = line[3:].strip().strip('"')
        changed.append(name)
        mark = {"M": "수정", "A": "추가", "D": "삭제",
                "?": "새 파일", "R": "이름변경"}.get(line[0].strip() or line[1], "변경")
        print(f"    {mark:<6} {name}")

    # 담기
    run(["git", "add", "-A"], capture=False)

    # 올라갈 목록 확인
    staged = run(["git", "diff", "--cached", "--name-only"])
    files = [f.strip().strip('"') for f in staged.stdout.splitlines() if f.strip()]

    print("\n[2] 키 유출 검사")
    blocked = []
    for f in files:
        base = f.split("/")[-1]
        if base in DANGER_NAMES or any(f.endswith(e) for e in DANGER_EXT):
            blocked.append((f, "키가 든 파일"))
            continue
        if base == "push.py":
            continue          # 이 파일은 검사 패턴 자체를 갖고 있어 제외
        p = HERE / f
        if p.exists() and p.suffix in (".py", ".txt", ".md", ".yml", ".toml", ".sql"):
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
                for pat in DANGER_TEXT:
                    if pat in txt:
                        blocked.append((f, f"'{pat}' 문자열 발견"))
                        break
            except Exception:
                pass

    if blocked:
        print("\n  ⛔ 올리면 안 되는 파일이 있어 중단합니다.\n")
        for f, why in blocked:
            print(f"     {f}  ← {why}")
        print("\n  해결 방법:")
        print("    · .env 파일이면 → .gitignore에 등록되어 있는지 확인")
        print("    · 코드에 키가 있으면 → config.py를 쓰도록 고치기")
        print("\n  담아둔 것을 되돌립니다...")
        run(["git", "reset"], capture=False)
        return 1

    print(f"    ✅ 이상 없음 ({len(files)}개 파일)")

    # 커밋 메시지
    msg = " ".join(sys.argv[1:]).strip()
    if not msg:
        msg = f"update {datetime.now().strftime('%m-%d %H:%M')}"

    print(f"\n[3] 저장 및 업로드")
    print(f"    메시지: {msg}")

    c = run(["git", "commit", "-m", msg])
    if c.returncode != 0 and "nothing to commit" not in (c.stdout + c.stderr):
        print(f"\n❌ 저장 실패:\n{c.stdout}{c.stderr}")
        return 1

    p = run(["git", "push"])
    out = p.stdout + p.stderr
    if p.returncode != 0:
        print(f"\n❌ 업로드 실패:\n{out}")
        if "no upstream" in out:
            print("\n   처음 올리는 브랜치라면 아래를 한 번 실행해주세요:")
            print("     git push -u origin main")
        return 1

    print(f"    ✅ 완료")
    print("\n" + "=" * 58)
    print("  GitHub에 반영됐습니다.")
    print("  Actions 탭에서 자동 실행 상태를 볼 수 있습니다.")
    print("=" * 58)
    return 0


if __name__ == "__main__":
    sys.exit(main())
