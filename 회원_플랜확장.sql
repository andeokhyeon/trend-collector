-- 플랜 4단계 + 프로 체험(얼리버드 100명) 확장 (2026-09-05)
-- Supabase SQL Editor에 한 줄씩 붙여넣고 실행하세요.
-- (이 SQL을 아직 안 돌려도 사이트는 그대로 돕니다 — 체험 부여만 조용히 쉽니다)

alter table profiles add column if not exists trial_ends_at timestamptz;
alter table profiles add column if not exists early_bird boolean default false;
