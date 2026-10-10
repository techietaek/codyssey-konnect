-- Phase 2 L4 — 챗봇 대화 영속(Long-term memory) 테이블 + RLS
-- 정식 로그인 사용자의 대화 턴을 user_id 로 저장해 재접근·기기 간 복구(요구: 이전 대화 복구)
-- 와 멀티턴 맥락 재주입(요구: 이전 대화맥락 기억)을 지원한다.
--
-- 신뢰 불변식(CLAUDE §6 · 캐싱 금지 규약과의 경계):
--   여기 저장하는 content 는 **대화 라우팅 맥락 텍스트**(사용자 발화 + "무엇을 제안했다"는
--   요약)일 뿐, 외부 API 가 내려준 사실 필드(가격·운영시간·좌표·사진)가 아니다. 사실은
--   추천 때마다 매번 라이브 재조회한다(TourAPI/Places ToS·신선도 — 응답 캐싱 금지 유지).
--
-- 각 사용자는 자기 행만 접근(RLS). 백엔드는 service key로 쓰되, RLS 는 publishable key
-- 직접접근(프론트/외부)까지 방어한다. 적용: Supabase SQL 에디터에 붙여넣고 Run (멱등).

create table if not exists public.chat_messages (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references auth.users(id) on delete cascade,
  role        text not null check (role in ('user', 'assistant')),
  content     text not null,
  created_at  timestamptz not null default now()
);

-- 사용자별 시간순 조회(복구·맥락 로드)용 인덱스.
create index if not exists chat_messages_user_created_idx
  on public.chat_messages (user_id, created_at);

alter table public.chat_messages enable row level security;

-- 자기 행만 select / insert / delete (정식 로그인 user — role=authenticated)
drop policy if exists "own chat select" on public.chat_messages;
create policy "own chat select" on public.chat_messages
  for select using (auth.uid() = user_id);

drop policy if exists "own chat insert" on public.chat_messages;
create policy "own chat insert" on public.chat_messages
  for insert with check (auth.uid() = user_id);

-- Clear chat(초기화) — 자기 행만 삭제.
drop policy if exists "own chat delete" on public.chat_messages;
create policy "own chat delete" on public.chat_messages
  for delete using (auth.uid() = user_id);

-- PostgREST 직접 접근용 권한. 백엔드 service key는 무관. (update 는 불변 로그라 미부여)
grant select, insert, delete on public.chat_messages to authenticated;
