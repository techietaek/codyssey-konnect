-- Phase 2 — 저장된 B 문화루트(현재 선택과 별도 슬롯) 영속
-- user_sessions 에 current_route jsonb 컬럼 추가. A '현재 선택'(current_choice)과 독립 슬롯이라
-- 사용자는 "선택한 장소"와 "저장한 루트"를 동시에 보유할 수 있다. 저장값은 **참조만**
-- (origin · 스톱 제목 · 시간창 · note/conditions) — 외부 API 응답(가격·경로선)은 저장하지 않고
-- 열 때 라이브 재조립한다(캐싱 금지 규약 준수 + 신선도). 적용: Supabase SQL 에디터에 Run(멱등).

alter table public.user_sessions
  add column if not exists current_route jsonb;
