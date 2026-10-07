-- Phase 2 L2 — 장기 사용자 선호(P-09 온보딩) 테이블 + RLS
-- user_sessions(세션 연속성)와 **분리**한다 — 임시 상태를 장기 선호로 자동승격하지
-- 않기 위함(FR-L5). 각 사용자(익명 포함)는 자기 행만 접근.
-- 적용: Supabase SQL 에디터에 붙여넣고 Run (멱등).

create table if not exists public.user_preferences (
  user_id              uuid primary key references auth.users(id) on delete cascade,
  interests            text[] not null default '{}',  -- InterestCode 값만 (코드에서 검증)
  prefer_shorter_walks boolean,                        -- NULL=미선택 허용 (Soft signal only)
  onboarded_at         timestamptz,                    -- P-09 노출 완료 마커(Skip 포함) → 재노출 방지
  updated_at           timestamptz not null default now()
);

alter table public.user_preferences enable row level security;

-- 자기 행만 select / insert / update (익명 user 포함 — role=authenticated)
drop policy if exists "own preferences select" on public.user_preferences;
create policy "own preferences select" on public.user_preferences
  for select using (auth.uid() = user_id);

drop policy if exists "own preferences insert" on public.user_preferences;
create policy "own preferences insert" on public.user_preferences
  for insert with check (auth.uid() = user_id);

drop policy if exists "own preferences update" on public.user_preferences;
create policy "own preferences update" on public.user_preferences
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- PostgREST 직접 접근용 권한(익명=authenticated 포함). 백엔드 service key는 무관.
grant select, insert, update on public.user_preferences to authenticated;
