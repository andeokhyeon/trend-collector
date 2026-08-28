-- ============================================================
--  키워드 헌터 — 회원 / 크레딧 / 사용량
--  Supabase → SQL Editor 에 붙여넣고 한 번 실행하세요.
--  여러 번 실행해도 안전합니다 (있으면 건너뜁니다).
-- ============================================================

-- ① 회원 프로필 ------------------------------------------------
-- 로그인 계정(auth.users)은 Supabase가 관리한다.
-- 여기에는 '우리 서비스에서의 그 사람'만 담는다.
create table if not exists profiles (
  id           uuid primary key references auth.users(id) on delete cascade,
  email        text,
  nickname     text,
  blog_id      text,                              -- 등록한 블로그
  plan         text    not null default 'free',   -- free / basic / pro
  credits      integer not null default 3,        -- 남은 크레딧 (가입 시 무료 3회)
  is_admin     boolean not null default false,
  -- 결제를 붙일 때 쓸 자리. 지금은 비어 있어도 된다.
  billing_id   text,        -- 결제사(토스·아임포트 등)의 고객 번호
  plan_started timestamptz,
  plan_expires timestamptz,
  memo         text,        -- 관리자 메모
  created_at   timestamptz not null default now(),
  last_seen    timestamptz
);

-- ② 크레딧이 오간 기록 ----------------------------------------
-- '왜 줄었나 / 언제 채웠나'를 나중에 따질 수 있어야 결제 분쟁이 안 난다.
create table if not exists credit_log (
  id         bigserial primary key,
  user_id    uuid references auth.users(id) on delete cascade,
  delta      integer not null,      -- 쓰면 음수, 채우면 양수
  reason     text,                  -- 'analyze' / 'topup' / 'plan' / 'admin'
  keyword    text,
  balance    integer,               -- 그 시점 잔액
  created_at timestamptz not null default now()
);

-- ③ 회원별 API 사용량 -----------------------------------------
-- 하루 한 줄씩 쌓는다. 종류별로 나눠 담아야
-- '누가 무엇을 많이 쓰는지'가 보인다.
create table if not exists user_usage (
  id         bigserial primary key,
  user_id    uuid references auth.users(id) on delete cascade,
  day        date not null,
  kind       text not null,         -- searchad / blog / datalab / autocomplete
  calls      integer not null default 0,
  updated_at timestamptz not null default now(),
  unique (user_id, day, kind)
);

create index if not exists idx_credit_log_user on credit_log(user_id, created_at desc);
create index if not exists idx_user_usage_day  on user_usage(day desc);
create index if not exists idx_profiles_plan   on profiles(plan);

-- ④ 가입하면 프로필이 저절로 생기게 --------------------------
-- 이게 없으면 가입은 됐는데 프로필이 없어서 크레딧이 안 잡힌다.
-- ⚠️ 카카오 로그인은 이메일을 안 줄 수 있다.
--    (account_email 동의항목은 '비즈앱'으로 등록해야 쓸 수 있다)
--    그래서 이메일이 없어도 이름이 비지 않게 여러 곳을 차례로 본다.
create or replace function handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into profiles (id, email, nickname)
  values (
    new.id,
    new.email,
    coalesce(
      nullif(new.raw_user_meta_data->>'name', ''),
      nullif(new.raw_user_meta_data->>'full_name', ''),
      nullif(new.raw_user_meta_data->>'nickname', ''),
      nullif(new.raw_user_meta_data->>'preferred_username', ''),
      nullif(split_part(coalesce(new.email, ''), '@', 1), ''),
      '회원'
    )
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();

-- ⑤ 이미 가입한 사람이 있다면 프로필을 채워준다 ---------------
insert into profiles (id, email, nickname)
select u.id, u.email,
       coalesce(
         nullif(u.raw_user_meta_data->>'name', ''),
         nullif(u.raw_user_meta_data->>'nickname', ''),
         nullif(split_part(coalesce(u.email, ''), '@', 1), ''),
         '회원')
from auth.users u
where not exists (select 1 from profiles p where p.id = u.id);

-- ⑥ 남의 정보는 못 보게 ---------------------------------------
-- ⚠️ 이걸 켜두지 않으면 로그인한 사람이 다른 회원의 크레딧까지 읽을 수 있다.
alter table profiles   enable row level security;
alter table credit_log enable row level security;
alter table user_usage enable row level security;

drop policy if exists "본인 프로필 읽기" on profiles;
create policy "본인 프로필 읽기" on profiles
  for select using (auth.uid() = id);

drop policy if exists "본인 프로필 수정" on profiles;
create policy "본인 프로필 수정" on profiles
  for update using (auth.uid() = id);

drop policy if exists "본인 크레딧기록 읽기" on credit_log;
create policy "본인 크레딧기록 읽기" on credit_log
  for select using (auth.uid() = user_id);

drop policy if exists "본인 사용량 읽기" on user_usage;
create policy "본인 사용량 읽기" on user_usage
  for select using (auth.uid() = user_id);

-- ⚠️ 관리 화면은 service_role 키로 읽는다. service_role은 RLS를 통과하므로
--    관리자용 정책을 따로 만들 필요가 없다.
--    (그래서 service_role 키는 절대 화면이나 깃허브에 노출하면 안 된다)

-- ⑦ 추적 목록을 회원별로 -------------------------------------
-- ⚠️ 이 칸이 없으면 로그인해도 남의 추적 목록이 같이 보인다.
alter table tracked_keywords
  add column if not exists user_id uuid references auth.users(id) on delete cascade;

create index if not exists idx_tracked_user on tracked_keywords(user_id);

alter table tracked_keywords enable row level security;

drop policy if exists "본인 추적목록" on tracked_keywords;
create policy "본인 추적목록" on tracked_keywords
  for all using (auth.uid() = user_id or user_id is null);

-- ⑧ 첫 관리자 지정 --------------------------------------------
-- ⚠️ 관리자용 아이디를 따로 만들지 않는다. 계정이 둘이면 비밀번호도 둘이고,
--    누가 무엇을 했는지도 안 남는다. 이미 가입한 계정에 표시만 단다.
--    아래 이메일을 본인 것으로 바꾸고 실행하세요. (먼저 가입부터)
update profiles set is_admin = true where email = 'dog1128@nate.com';

-- ⚠️ 카카오로 가입해서 이메일이 없다면 위 줄로는 못 찾는다.
--    아래로 목록을 보고 id를 직접 넣으세요.
--      select id, email, nickname, created_at from profiles order by created_at;
--      update profiles set is_admin = true where id = '여기에-그-id';

-- 관리자를 확인하려면:
--   select email, is_admin, plan, credits from profiles order by created_at;
