# -*- coding: utf-8 -*-
"""
워커들이 나눠 쓰는 작은 저장소 (SQLite 파일).

⚠️ 왜 필요한가 (2026-08-28 실측)
   uvicorn을 --workers 2로 돌리면 프로세스가 둘이다.
   로그인 확인코드(verifier)를 파이썬 dict에 두면 A워커가 만든 걸
   B워커가 모른다 → 카카오 갔다 오는 로그인이 정확히 절반 실패했다.
   크레딧 '같은 키워드 무과금' 기록도 같은 이유로 절반이 이중차감됐다.

   그래서 프로세스 밖(디스크)에 둔다. SQLite는 WAL 모드에서
   여러 프로세스가 함께 읽고 써도 안전하고, 서버 재시작도 견딘다.

⚠️ 여기는 '잠깐 기억'만 둔다 — 로그인 확인코드(20분), 과금 기록(24시간).
   회원·크레딧의 원본은 Supabase다. 이 파일이 지워져도
   로그인 중이던 사람이 다시 누르면 그만이다.
"""
import os
import sqlite3
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# 서버에서는 git pull이 건드리지 않는 곳(web/data/)에 둔다.
PATH = os.environ.get("KH_RUNTIME_DB") or os.path.join(HERE, "data", "runtime.db")


def _conn():
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    c = sqlite3.connect(PATH, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=10000")
    c.execute("CREATE TABLE IF NOT EXISTS kv ("
              " kind TEXT NOT NULL, k TEXT NOT NULL,"
              " v TEXT NOT NULL DEFAULT '',"
              " exp REAL NOT NULL,"
              " PRIMARY KEY (kind, k))")
    return c


def _sweep(c):
    """지난 것 청소 — 부를 때마다 슬쩍 한다 (따로 청소부를 안 둬도 되게)."""
    c.execute("DELETE FROM kv WHERE exp < ?", (time.time(),))


def _run(fn):
    """연결을 열고 → 트랜잭션으로 실행하고 → 반드시 닫는다.

    ⚠️ 2026-08-29 사고: `with _conn() as c`만 쓰면 커밋은 되지만
    연결이 **닫히지 않는다**. 요청마다 연결이 하나씩 새고,
    몇 시간 뒤 열린 파일 한도에 걸려 서버 전체가 매달렸다(504).
    """
    c = _conn()
    try:
        with c:
            return fn(c)
    finally:
        c.close()


def put(kind, key, value="", ttl=1200):
    """저장 (같은 키면 덮어쓴다)."""
    def _f(c):
        _sweep(c)
        c.execute("INSERT OR REPLACE INTO kv (kind, k, v, exp) VALUES (?,?,?,?)",
                  (kind, str(key), str(value), time.time() + ttl))
    _run(_f)


def take(kind, key):
    """꺼내면서 지운다 (한 번만 쓰는 값 — 로그인 확인코드).
    없거나 만료됐으면 None."""
    def _f(c):
        row = c.execute("SELECT v, exp FROM kv WHERE kind=? AND k=?",
                        (kind, str(key))).fetchone()
        c.execute("DELETE FROM kv WHERE kind=? AND k=?", (kind, str(key)))
        _sweep(c)
        return row
    row = _run(_f)
    if not row or row[1] < time.time():
        return None
    return row[0]


def claim(kind, key, ttl):
    """'내가 처음인가?'를 원자적으로 판정한다.
    처음이면 True(기록하고), 이미 있으면 False."""
    def _f(c):
        _sweep(c)
        try:
            c.execute("INSERT INTO kv (kind, k, v, exp) VALUES (?,?,?,?)",
                      (kind, str(key), "", time.time() + ttl))
            return True
        except sqlite3.IntegrityError:
            return False
    return _run(_f)


def drop(kind, key):
    """기록 취소 (과금 실패했을 때 자리를 되돌려 준다)."""
    _run(lambda c: c.execute("DELETE FROM kv WHERE kind=? AND k=?",
                             (kind, str(key))))


def get(kind, key):
    """지우지 않고 읽는다. 없거나 만료면 None."""
    row = _run(lambda c: c.execute(
        "SELECT v, exp FROM kv WHERE kind=? AND k=?",
        (kind, str(key))).fetchone())
    if not row or row[1] < time.time():
        return None
    return row[0]


def has(kind, key):
    row = _run(lambda c: c.execute(
        "SELECT exp FROM kv WHERE kind=? AND k=?",
        (kind, str(key))).fetchone())
    return bool(row) and row[0] >= time.time()
