-- Phase 2 L1c — 사용자 세션 영속 테이블 + RLS
-- 각 사용자(익명 포함)는 자기 행만 접근. 백엔드는 service key로 쓰되,
-- RLS는 publishable key 직접접근(프론트/외부)까지 방어한다.
-- 적용: Supabase SQL 에디터에 붙여넣고 Run (멱등).

create table if not exists public.user_sessions (
  user_id        uuid primary key references auth.users(id) on delete cascade,
  last_request   jsonb,
  current_choice jsonb,
  updated_at     timestamptz not null default now()
);

alter table public.user_sessions enable row level security;

-- 자기 행만 select / insert / update (익명 user 포함 — role=authenticated)
drop policy if exists "own session select" on public.user_sessions;
create policy "own session select" on public.user_sessions
  for select using (auth.uid() = user_id);

drop policy if exists "own session insert" on public.user_sessions;
create policy "own session insert" on public.user_sessions
  for insert with check (auth.uid() = user_id);

drop policy if exists "own session update" on public.user_sessions;
create policy "own session update" on public.user_sessions
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- PostgREST 직접 접근용 권한(익명=authenticated 포함). 백엔드 service key는 무관.
grant select, insert, update on public.user_sessions to authenticated;
