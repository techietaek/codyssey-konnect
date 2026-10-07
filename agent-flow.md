# agent-flow.md — KONNECT 개발 진행 순서 · 체크리스트

> **문서 역할:** AI 에이전트(및 팀)가 KONNECT를 **어떤 순서로, 무엇을 확인하며** 개발하는지 정의하는 **오케스트레이션·체크리스트 문서**. 세션/에이전트가 바뀌어도 이 파일만 보면 "지금 어디까지 됐고, 다음에 뭘, 어떻게 검증하며" 이어갈 수 있다.
> **사용법:** 작업하며 `- [ ]` → `- [x]`로 **체크박스를 갱신**한다. 각 슬라이스는 "완료 기준(Done when)"을 모두 만족해야 `[x]`.
> **정본 관계:** 기능 정의는 `PRD.md`(FR-*·§), 디자인은 `DESIGN.md`(LF·컴포넌트), 규칙·신뢰 불변식은 `CLAUDE.md`. 이 문서는 **그 문서들을 섹션 ID로 가리키며 순서·검증만** 관리한다(중복 서술 최소화).
> **최종 수정:** 2026-10-07 · 담당 Tech(이용택)

---

## 0. 오리엔테이션 (콜드 스타트 에이전트가 먼저 볼 것)

- **제품 한 줄:** 서울 자유여행 외국인 FIT에게 현재 조건(위치·시간·운영조건)에서 **실제 가능한 문화경험**을 좁혀주는 모바일-퍼스트 웹. 핵심은 다단계 AI Agent + RAG + Long-term Memory.
- **제1 원칙(절대):** **미확인 ≠ 무료 / 예약 불필요 / 이용 가능 보장.** (CLAUDE.md §6 신뢰 불변식 — 모든 슬라이스의 통과 게이트)
- **읽기 순서(통독 금지, 섹션만):** 이 파일 → 해당 슬라이스가 가리키는 `PRD`/`DESIGN` 섹션만. 문서 라우팅은 `CLAUDE.md §0`.
- **스택(확정):** Vanilla HTML/CSS/JS · Python 3.12/FastAPI(`backend/.venv`) · OpenAI(`gpt-4o-mini`)+LangChain · Supabase(Auth·Postgres·pgvector) · Naver Map+Tmap+Google Maps 딥링크 · Google Places(보조). 상세 `CLAUDE.md §2`.
- **역할:** Product=기획, UX/UI=디자인(Figma 정본), **Tech=구현**. 입력/출력·상태·신뢰·MVP 범위·완료기준을 바꿔야 할 때만 Product 재조율(`PRD.md §11`).

### 현재 상태 (Current Status) — ⚠️ 작업 시작·종료 때 갱신할 것
- [x] **사전 준비 완료**: 문서(PRD/CLAUDE/DESIGN/tokens.css) · `backend/.venv`(3.12, 의존성 OK) · `.env` 전 키 **라이브 스모크 Green** · Supabase(Google·Anonymous·pgvector) 활성 · Figma MCP 연결 · GitHub repo/Projects.
- [x] **Phase 0 — Walking Skeleton** (branch `phase0-walking-skeleton`): 프론트(:5500)→백(:8000)→프론트 관통 로컬 검증 Green. `GET /health`·`POST /api/recommend` 스텁(계약 고정)·CORS·공통 봉투(Envelope)·trace·ruff/black 통과. ⚠️ 조기 배포(Render/Vercel)는 **미완** — Phase 1 중 수행.
- [x] **Phase 1 — A 즉시 추천** (branch `phase1-a-immediate-recommend`) — A1~A6 완료(입력→조회→정규화→판정→지도/도보→Reason·LLM→선택). 날씨·배포는 보류.
  - [x] A1 입력 구조화(LF-02) — 필수입력 스키마·가용시간 경계검증(domain+8 pytest)·입력오류 분리(ValidationFailure 422)·LF-02 모바일 입력 UI·결과 뷰 라우팅·모바일 디바이스 프레임(a-bly). 자연어 note는 캡처까지(구조화는 A5 LLM 투입 시). UI 다듬기(버튼 인터랙션 포함).
  - [x] A2 조회+정규화 — TourAPI EngService2 실연동(sources/tourapi·domain/normalize·curation·agent/orchestrator). 실 후보 반환·신뢰 게이트·cat3 큐레이션.
  - [x] A3 판정+3상태 — domain/timing·status. 영업시간·휴무·행사기간 판정으로 fits/check 산정, Hard 충돌 제외+대체. 54 pytest. (날씨 Context는 이후)
  - [x] A4 지도/이동 — Tmap 도보 거리/시간/경로(A4a) + Naver 지도 핀/경로 렌더(A4b) + Google Map 딥링크(대중교통).
  - [x] A5 Reason+LLM — note LLM 구조화(LangChain) + Reason Copy 선택 + 예산→alternative + parsed chips. 74 pytest.
  - [x] A6 선택상태 — Select 확정·Current choice 배지·홈 재접근 배너(localStorage). **Phase 1 완료.**
  - [~] **데이터 검색 품질 개선** (2026-10-07~) — check_needed 과다(실측 73%) 완화. 원인·솔루션·로드맵은 **`docs/data-quality.md`** 에서 관리. 1~3단계 완료(원인 집계 → `detailInfo2` 연동 → LLM 운영시간 추출): **check 73%→42%, fits 20%→51%**(공식 데이터만, 환각 검증 완료). 4단계(KOPIS/서울문화포털) 대기.
  - [x] A7 상태 UX 보강 (branch `phase1-a-loading-states`, 2026-10-07) — 조회 대기 **로딩 화면**(shimmer 스켈레톤 + 회전 단계문구 + 펄스 sparkle, Cancel=요청 AbortController 취소) · 조회 플로우를 `app.js startRecommend`로 중앙화(로딩→결과/취소복귀/오류) · **0건** 지도 축소(NAVER 로고 노출 방지)+경고 아이콘/텍스트 · **전용 오류 화면**(Couldn't load, Try again/Edit conditions, 조건 유지) · 바텀시트 Cancel 버튼 제거 + **grip 스와이프-다운 닫기**(백드롭/Esc 유지). headless 렌더/드래그 검증 Green.
  - [x] A8 Soft 랭킹 A안 (2026-10-07) — 결과 표시 순서 **fits→alternative→check_needed**, 같은 등급 내 **관심사 선호↑/비선호↓**(`avoid_interests` LLM 추출), 그다음 거리순. 제외 아님(Soft only). 정본 `backend/app/domain/ranking.py`. **B안(본격 Soft 스코어링)은 Phase 2/3 — `docs/soft-ranking.md` §3 참조(Product 결정 3건 포함).**
- [~] Phase 2 — 로그인·개인화 (branch `phase2-login-personalization`) — **L1 로그인·연속성 완료**(L1a~d, 실로그인 검증). ← **다음: L2 선호 온보딩**(P-09, FR-L3/L4) → L3 My Page. ⚑ **Soft 랭킹 B안**(걷기 선호 + 저장 Preference 반영, `docs/soft-ranking.md` §3)은 L2에서 착수 가능.
- [ ] Phase 3 — RAG · B 문화루트 · ⚑ **관심사·이동 균형 랭킹**(FR-B4) = Soft 랭킹 B안 구현부 · ⚑ **전면 Agentic 추천(2b)**: LLM 조건해석→멀티소스 조회→후보 재투입→LLM 최종 선별. 목표 아키텍처·신뢰 경계는 **`docs/agent-architecture.md`** (사실은 끝까지 코드 소유). 개방형 선호 배제/기피(옵션 3 슬라이스)는 그 전에 선행 가능.
- [ ] Phase 4 — 배포·실사용자 검증·발표

---

## 1. 공통 작업 규칙 (모든 슬라이스에 적용)

### 1.1 전략: 수직 슬라이스(vertical slice)
레이어별(백 전부→프론트 전부) 금지. **기능 하나를 입력→백엔드→판정→API→프론트 렌더까지 끝까지 관통**하고 다음으로. 이유: AI 에이전트 코딩은 "그럴듯하지만 틀린" 코드 위험 → **매 슬라이스 실제 실행 검증**으로 조기 차단.

### 1.2 슬라이스 미시 루프 (매번 반복)
```
① 범위    해당 PRD FR + DESIGN 컴포넌트 "섹션만" 읽기 (CLAUDE §0 라우팅)
② 계약    API 요청/응답 Pydantic 모델 먼저 확정 (contract-first) → 백·프론트 공유
③ 계획    비자명하면 plan 공유·합의
④ 구현    작은 diff 하나. CLAUDE 컨벤션 준수
⑤ 검증    타입체크로 끝내지 말고 "실제로 돌려" 확인 (/verify, /run). 데이터 경로 스모크
⑥ 신뢰게이트  CLAUDE §6 체크리스트 통과 확인
⑦ 커밋    브랜치→의미 단위 커밋(요청 시 PR). Projects 보드·이 파일 체크박스 갱신
⑧ 다음 슬라이스
```

### 1.3 모든 슬라이스 공통 신뢰 게이트 (⑥) — CLAUDE §6 요약
- [ ] 미확인(빈값/모호)을 `free`·`예약 불필요`·`이용 가능`으로 매핑하지 않음
- [ ] 가격·운영시간·예약·좌표를 **LLM 출력에서 받지 않음**(공식 데이터만)
- [ ] 체류/이동시간을 근거 없이 임의 숫자(60/90/20분)로 채우지 않음(계획값=근거+상태표기)
- [ ] Hard 충돌 후보가 정상 추천에 섞이지 않음
- [ ] 강제 채움 없음(A 최대 3~4 / B 2~3, 3개 강제 금지)
- [ ] 개인화가 사실/필수 조건을 덮어쓰지 않음(Request > Trip > Preference)
- [ ] 선택 ≠ 방문(GPS 자동 방문판정·턴바이턴 없음)
- [ ] AI 관여 고지 · 확인/미확인 구분 UI 유지

### 1.4 횡단 습관 (처음부터)
- **`domain/` 단위 테스트를 일찍** — 판정 로직은 결정론적 → 에이전트의 객관적 검증 신호 + PoC 증빙(NFR-08).
- **trace 로깅을 처음부터** — Agent 다단계 동작(조회/판정/분기)을 trace로 남김 → PoC 증빙 자동 축적.
- **작게·자주 검증** — 큰 diff 한 번에 생성 금지.
- 사용자-facing 문자열 **영어 우선**, 내부 용어 노출 금지. 색·토큰은 `frontend/css/tokens.css`의 `var(--...)`만.

---

## 2. Phase 0 — Walking Skeleton (뼈대 + 1줄 관통 + 조기 배포)
> 목적: "빈 폴더 더미"가 아니라 **프론트→백→프론트가 실제로 연결되는 최소 실행본**을 만들고, **배포 배선까지 Day 1에 검증**(과제 필수 배포 리스크 선제거).
> 참조: `CLAUDE.md §3`(디렉터리), `§4`(아키텍처), `DESIGN.md §2`(tokens).

**백엔드 스캐폴딩**
- [x] `backend/app/main.py` — FastAPI 앱 + `GET /health` 200 응답 (lifespan 키 존재 확인)
- [x] `backend/app/config.py` — `pydantic-settings`로 리포 루트 `.env` 로딩(키 존재 검증 `missing_keys`, 값 미출력)
- [x] `backend/app/core/` — `exceptions.py`(KonnectError/SystemError/ValidationFailure, FR-C7)·`trace.py`(trace_id+단계 로깅, NFR-08)
- [x] `backend/app/models/` — `envelope.py`(Generic Envelope)·`recommend.py`(계약: 3상태·provenance·PriceStatus·max 2 reasons/4 candidates)
- [x] `POST /api/recommend` — **하드코딩 후보 1개** 반환(불변식 준수: 가격 미확인→`unknown`+flag, free 추정 안 함)
- [x] CORS 설정(`CORS_ALLOW_ORIGINS`), `uvicorn`로 부팅 확인 (라이브 `/health` 200)

**프론트 스캐폴딩**
- [x] `frontend/index.html` — `css/tokens.css`+`app.css` 연결 + 390 레이아웃 + AI 고지 pill
- [x] `frontend/js/api.js`(+`config.js` `API_BASE`) — 백엔드 호출 래퍼, 봉투 그대로 반환
- [x] `frontend/js/components/result-card.js` — DESIGN §3.1 최소형(상태배지·Reason·Meta·flag·Select 분리 렌더)
- [x] `frontend/js/state.js` — 클라이언트 상태 컨테이너(focus≠select) · `js/pages/home.js` 와이어링
- [x] `python -m http.server 5500` 구동 → 모든 모듈 200, CORS allow-origin 확인

**조기 배포(권장)**
- [ ] 백엔드 Render / 프론트 Vercel(or Supabase 호스팅)에 스켈레톤 배포 → 외부 URL에서 `/health`·카드 확인 ← **미완(외부 서비스, 사용자 확인 후)**
- [ ] 배포 Secret(.env 값) 주입 경로 확인(저장소 커밋 아님)

**Done when:** 로컬·배포 양쪽에서 프론트가 백엔드 `/api/recommend` 스텁을 호출해 Result Card 1개를 렌더한다.

---

## 3. Phase 1 — A 즉시 추천 (LF-02·03) · **비로그인 경로 우선**
> 우선순위: PRD "A 우선 고도화". 각 슬라이스는 백+프론트 함께. 로그인 없이 첫 추천까지(FR-L1).
> 참조: `PRD.md §4.2·§5·§6·§7·§10`, `DESIGN.md §3·§4(01 섹션)`, `reason-copy-dictionary`.

### A1 — 입력 구조화 (LF-02)
- [x] 요청 스키마: 시작위치(StartLocation)·시작시각·종료시각(필수) + 자연어 note 1영역 (`models/recommend.py`)
- [x] 가용시간 경계 검증: 최소 30분·시작일 24:00까지, 시작≥종료 재선택 (`domain/input_validation.py` + 8 pytest). 종료 자동기본값/자동연장 없음(프론트)
- [x] 입력 오류 처리: 미입력(422)/역전/30분미만/경계초과 = 추천 전 오류·제한, ValidationFailure로 시스템예외·0건과 분리 (FR-A3·C7)
- [x] 현재 위치·시각은 변경 가능한 기본값. 위치 권한 거부 시 직접 입력(📍 Use current → 거부 시 수동) (FR-A6)
- [~] 자연어 선택조건 → **구조화는 A5(LLM 투입) 시**. A1은 note 원문 캡처 + example chip까지 (말 안 한 조건 추정 금지 유지)
- [x] 프론트: LF-02 입력 UI(Section header/tag·Quick Select 5·네이티브 Start/Done by·Example Chip). 커스텀 시트/Parsed Chip은 후속
- [x] 횡단: 모바일 디바이스 프레임(a-bly, 데스크톱 중앙 390 고정) · 입력↔결과 뷰 라우팅(`app.js`)
- **Done when:** ✅ 유효 입력이 Request Context로 구조화되고, 오류/제한이 추천 전에 걸러진다. 로컬 라이브+헤드리스 스크린샷 검증 Green.

### A2 — 조회 + 데이터 정규화 (LLM 아직 없음) ✅
- [x] `sources/tourapi.py` — httpx+tenacity 재시도·타임아웃·단기 TTL 캐시. locationBasedList2·detailIntro2·detailCommon2 (EngService2). 키는 로그 비노출(httpx 로거 WARNING)
- [x] `domain/normalize.py` 단일 지점: 가격 `free/paid/unknown/partial`(빈값·모호→unknown, free 추정 금지), 운영시간 실제/미확인, 예약은 표기 안 함(‘예약 불필요’ 매핑 금지). 미확인 flag 표기
- [x] 좌표 한국 range 검증·drop, 공식 homepage URL 보존, firstimage 없으면 null(가짜 이미지 금지)
- [x] 3개 문화타입(76·78·85) 병렬 조회→병합·거리순, cat1=A02 필터+의료관광(A020205*) 제외, 상세 병렬 보강. 한 소스 실패해도 성립(부분 실패 허용)
- [x] 좌표 해석 `domain/locations.py`(제공좌표>Quick Select 5>도심 기본값), 파이프라인 `agent/orchestrator.py`, 라우터 스텁 제거
- [x] 단위 테스트 15개(`test_normalize`: 가격 매핑·제목·좌표·flag). 라이브 end-to-end + 실 UI 렌더 검증(≈0.4s)
- **Done when:** ✅ 입력 좌표로 실제 문화경험 후보(정규화 상태 포함)가 반환. 빈값→긍정 매핑 없음(게이트 통과, 시각 확인). 다음 **A3 판정**.

### A3 — 판정 + 결과 상태 3종 ✅ (일부 이후 보강)
- [x] `domain/timing.py`(운영시간 범위·last admission·요일 휴무·24h 파싱, 계절/복수/문의는 UNCERTAIN) + `domain/status.py`(3상태 산정) (PRD §5.3)
- [x] 내부 판정 순서 → 사용자-facing 상태: **조건 충족(fits: 영업확인+가격확인) / 추가 확인 필요(check: 미확인)**. Hard 충돌(영업외·휴무·마감후)은 제외. `조건 완화 대안(alternative)`은 예산/Soft 조건 필요 → A5(note 파싱) 이후
- [x] 미확인 분리: 영업외·휴무 '확실할 때만' 제외, 애매하면 check(추정 금지). 가격 unknown/partial은 fits 아님 (PRD §6.2·§5.2)
- [ ] 기상청·AirKorea Context + 공식 위험특보 Outdoor 제외 (PRD §6.6) ← **이후 보강(A3 범위에서 분리)**
- [x] `domain/` 단위 테스트 19개(timing 14 + status 6: 휴무요일·영업외·last admission·24h·미확인·가격경계). 오케스트레이터: 상위 8개 보강·판정 후 Hard 제외분을 다음 후보로 대체(강제 채움 아님), trace에 fits/check/excluded 기록
- **Done when:** ✅ 각 후보가 fits/check + 미확인 flag로 분류, Hard 충돌(영업외·휴무)은 정상 추천에서 빠짐(게이트, 라이브 확인: 영업 전 시간대·월요일 휴무 제외+대체). 다음 **A4 지도/이동**.

### A4 — 후보 구성 + 지도/이동 (LF-03) ✅
- [x] 최대 4개 소수 후보, 강제 채움 금지, 0건 명시 안내 (A2/A3에서 성립)
- [x] `sources/tmap.py` — 보행자 거리·예상시간·경로선(백엔드 프록시) + provenance(estimate). 타임아웃/재시도/캐시/graceful
- [x] 지도 Fallback: path 있으면 경로선, 없으면 핀+외부지도, Tmap 실패 시 `Route unavailable`(path/walk 유무로 단계 자동 분기) (PRD §7)
- [x] 임의 직선 금지(Tmap이 준 실제 path만 그림), 거리·시간·경로 독립
- [x] 프론트: `js/map.js` Naver Map 렌더 + Start/번호 핀(선택/비선택) + 포커스 경로선. **인증실패(도메인 미등록)·로드실패 시 지도 숨김**(카드 유지). 카드↔핀 포커스(teal 테두리). 유형아이콘은 Figma 에셋 export 후 보강
- [x] Google Maps 도보 딥링크(Directions external map)
- [x] `/api/config`로 공개 Naver client id 노출
- **Done when:** ✅ 카드로 소수 후보가 도보시간·신뢰수준과 함께 보이고 외부지도 연결. 직선 위조 없음(게이트). 지도 핀/경로는 **NCP 콘솔에 도메인(localhost:5500·배포URL) 등록** 후 표시(현재는 graceful 폴백). 다음 **A5 Reason+LLM**.

### A5 — 설명(Reason) + AI 고지 (LLM 첫 투입) ✅
- [x] **LLM은 note 자연어 구조화에만**(`agent/note_parser.py`, LangChain `with_structured_output`) — '말한 것만' 추출(추정 금지), 사실(가격·시간) 생성 안 함. 실패 graceful. Reason 텍스트는 LLM이 쓰지 않음
- [x] Reason 0~2개(Primary+Secondary), Reason Copy Dictionary 문구만 — **확정 근거+조건+매치룰로 코드가 선택**(`domain/reasons.py`). 관심사/예산(충족시)/시간(OPEN)/최근접
- [x] 0개면 영역 생략(강제 채움 금지), 미확인 근거엔 Fit 금지(가격 미확인→budget reason 없음), 내부 Fit명 비노출(code 내부용)
- [x] 예산 판정(`domain/budget.py`, 일반가 기준·할인가 제외) → 초과 시 **alternative + 'Above your budget'/'Not a free option'**(충족 reason 금지, §5.7)
- [x] Fact/Reason/미확인 분리 렌더 + AI 고지 유지 + **parsed chips(AI 이해 조건) 표시**
- [x] trace: structure(파싱결과)·judge(fits/alt/check)·explain(reason수). 단위 테스트 24개(budget 9·reasons 8·status +7)
- **Done when:** ✅ 각 후보에 근거 있는 Reason 0~2개, Fact 분리 렌더, 근거 없는 Fit 없음(게이트). 라이브(실 LLM+데이터+지도) 확인: 관심사·예산 reason, 예산초과 alternative, 미확인은 무료/충족 주장 안 함. 다음 **A6 선택 상태**.

### A6 — 선택 상태 (LF-09, 비로그인) ✅
- [x] `Select experience`만 선택 확정(핀 탭·스와이프는 포커스 변경) (FR-A8)
- [x] LF-03에 남아 완료 피드백(Toast) + Current choice 배지·Selected 버튼, 자동 이동·추가 저장 버튼 없음
- [x] 현재 선택 유지·재접근: 홈(입력 뷰) 상단 "Current choice" 배너(View/Clear), 재오픈 시 확정 복원 (LF-09 A variant), 선택≠방문 (FR-C6)
- [x] 비로그인 localStorage 영속 — Phase 2에서 계정 연결(익명→Google identity linking)
- **Done when:** ✅ 선택이 확정·유지되고 홈에서 다시 볼 수 있다. GPS 방문판정 없음(게이트). 라이브 확인.

**Phase 1(A 즉시추천) 완료:** A1~A6 전 슬라이스 통과(PRD §10 A 완료기준). 입력→조회→정규화→판정(3상태·Hard제외)→지도/도보→Reason/LLM→선택까지 end-to-end. **보류(의도적):** 날씨·대기질 Context(§6.6), 자유텍스트 정밀 지오코딩, 조기 배포(Render/Vercel — Phase 4).

**Phase 1 완료 기준(PRD §10 A):** Start Anchor·가용시간 반영, Hard 충돌 미표시, 상태·이유·실행조건·미확인 구분, LF-03에서 Select로 확정·완료 피드백.

---

## 4. Phase 2 — 로그인 · 개인화
> 참조: `PRD.md §4.4`, `product/06-ai-tech-boundary.md`(P-01~P-09), Supabase(이미 Google·Anonymous·pgvector ON).

### L1 — 로그인 게이트 + 연속성/마이그레이션 ✅ 완료(2026-10-07)
> **L1a** 백엔드 JWT/JWKS 검증(`core/auth.py`) · **L1b** 프론트 익명 로그인+Bearer 부착(`auth.js`, `/api/config`에 supabase url/pub key) · **L1c** 서버 영속 `user_sessions`+RLS(`db/migrations/0001`, `db/sessions.py`, `api/session.py`)·saveChoice/요청 서버 미러 · **L1d** Google 로그인(홈 "Log in" + 로그인 시트) + Hello 인사/Log out. 모두 실브라우저 로그인까지 검증 Green.
- [x] Supabase Anonymous Sign-in으로 익명 user_id 선발급 → 요청조건·선택 저장 (L1b·L1c)
- [x] 비회원 첫 추천 후 재추천 시 로그인 유도 (FR-L1) — `isLoggedIn()`=비익명, "Find new options"→로그인 시트
- [x] Google 로그인 — 익명이면 `linkIdentity`(user_id 보존, FR-L2), 이미 연결된 계정이면 `signInWithOAuth`로 폴백
- [x] 백엔드 JWT 검증 = **JWKS**, 공유 secret 미사용 (L1a)
- [x] DB RLS: 각 user(익명 포함)는 `auth.uid()` 일치 데이터만 (L1c)
- [x] 임시 상태를 Trip·장기 Preference로 **자동 승격 금지** (FR-L5) — 세션 연속성만 저장, 선호 학습 없음
- **⚠ 운영 노트(cold-start 필독 — Supabase 대시보드 설정 의존):**
  - Google·Anonymous provider **ON**, **Manual linking ON**(안 켜면 linkIdentity가 `manual_linking_disabled`). Redirect URLs에 `http://localhost:5500/**`(+배포 URL).
  - **identity linking 직후 토큰에 `is_anonymous=true`가 남음** → 로드 시 익명 클레임이면 `refreshSession()`으로 클레임 동기화(`auth.js` 구현됨).
  - 같은 Google 계정 재로그인 시 `identity_already_exists` → `signInWithOAuth` 1회 폴백(`auth.js` 구현됨).
  - 로컬 로그인은 **일반 브라우저 탭**에서(임베디드 웹뷰/자동화 브라우저는 Google이 `disallowed_useragent`로 차단).
- **Done when:** ✅ 비회원→로그인 전환 시 동일 요청 재입력 없이 흐름 연속·데이터 계정 보존.

### L2 — P-09 선호 온보딩
- [ ] Google 최초 가입 1회·1화면: 관심사 6개 복수 + `□ Prefer shorter walks`(단일·미선택 허용), 모두 Skip 가능 (FR-L3)
- [ ] 걷기 선호 = Soft ranking only, 숫자 상한/분·km 변환 금지, 저장 선호만으로 M01/M02 Reason 금지 (FR-L4)
- [ ] 기존 회원 반복 노출 금지 (DESIGN P9-1)
- **Done when:** 신규 가입자만 1회 노출, Skip해도 A/B 제한 없음.

### L3 — My Page
- [ ] 확인된 선호 확인·수정·초기화(이후 추천부터 적용) / 현재 여행·최근 선택 진입 / 계정 정보 (FR-L6)
- [ ] 전체 이력·통계·Stamp는 MVP 제외, 추가 입력 Skip 가능
- [ ] 프론트: MP-1~MP-3 (DESIGN 03 섹션)
- **Done when:** 저장된 선호를 사용자가 관리할 수 있고 변경이 이후 추천에 반영된다.

---

## 5. Phase 3 — RAG · B 문화루트

### R1 — RAG (FAQ·여행정보·콘텐츠 Q&A)
> 참조: `PRD.md §6.5·FR-C8`.
- [ ] 지식 문서 청크 → OpenAI Embeddings → Supabase **pgvector** 저장 (`backend/app/rag/`, `vecs`)
- [ ] 질의 유사도 검색 → LLM이 **검색 근거 범위 안에서만** 답변
- [ ] 사실 데이터(가격·운영·예약)는 RAG가 아니라 공식 API 정본 — RAG는 참고지식 한정
- [ ] 근거 없으면 생성 금지 → `추가 확인 필요`·공식 경로. 범위 밖 질문 안내
- [ ] 별도 챗봇 화면 분리 금지 — A·B 자연어 대화 흐름에 통합
- **Done when:** FAQ/콘텐츠 질문에 근거 인용 답변, 근거 없으면 생성 안 함(게이트).

### B1 — B 입력 (LF-04, Conversation-first)
> 참조: `PRD.md §4.3`, `DESIGN.md 02 섹션`.
- [ ] 필수 4값(날짜·출발위치·시작시각·종료경계), 자연어 요청 주경로 → 구조화 → 누락·모호 필수값만 질문 (FR-B1)
- [ ] Guided Chat S1 Start / S2 Clarification / S3 Ready / V1 Direct edit (FR-B2)
- [ ] 제공값 반복질문 금지, 묶음 질문, 모호·충돌값 추정 금지, 미래날짜 GPS 자동 시작점 금지 (FR-B3)
- [ ] Starting point Quick Select 5개는 보조(지역모드/2km Hard Filter 아님)
- [ ] `Show culture route`는 필수 4값 확인 후 활성
- **Done when:** 대화로 4값이 확정되고 compact editable summary로 수정 가능.

### B2 — 루트 구성 (LF-05)
- [ ] 하루 1코스 2~3개 루트 1개, 2·3개 동등, 3개 강제 금지 (FR-B4, B-T06)
- [ ] 실행 가능성·필수조건 먼저 → 관심사·이동 균형 조합
- [ ] 고정형 실행시간 미확인 시 자동 루트 제외, 자율형 계획 체류시간은 근거 있을 때만(`예정`) (B-T01)
- [ ] 방문 순서·시간·확인 비용·예약/참여·미확인 구분, 루트 전체 vs 개별 장소 이유 구분 (FR-B5)
- [ ] 예산: 필수비용 미확인 포함 시 전체 `예산 충족` 금지 → `총비용 추가 확인 필요`
- **Done when:** 신뢰 가능한 2~3개 루트가 순서·시간·비용·미확인 구분으로 구성. 조합 불가 시 개별/실패 전환.

### B3 — 루트 지도·이동 (LF-08)
- [ ] 시작점→장소1→장소2[→장소3] 구간별 이동·시간·거리, 지도 번호↔장소명 대응 (FR-B6, B-T02/B-T03)
- [ ] 루트 전체 이동부담 vs 전체 소요시간 구분, 일부 구간 미확인 명시
- [ ] 경로 Fallback 3단계 동일 적용, 임의 직선 금지
- [ ] 프론트: Route Stop·Walk Segment (DESIGN §3.6)
- **Done when:** 전체 동선이 신뢰수준과 함께 보이고 `Go with this route`로 확정.

### B4 — 수정·재구성·실패 Fallback
- [ ] 조건 수정/장소 제외 시 유효 입력 유지, 제외 장소 재삽입 금지, 영향 실행가능성 재검증 (FR-B7, B-T05)
- [ ] 재구성 실패 시 직전 조건/결과 복귀 최소 경로, 이전 루트를 새 조건 정상결과로 표시 금지
- [ ] 가용시간 부족 원인 구분(`시간 조건 수정`/`가능한 개별 경험 보기`)
- [ ] 과거 Reason을 새 조건 적합성으로 재사용 금지
- **Done when:** 수정/제외 후 전체 재판단, 실패 시 안전 복귀. LF-09 기존 선택과 분리.

### B5 — 루트명·계획시간·현재 선택 (LF-09 B)
- [ ] 확인 지역/주요장소로 짧은 루트명(근거 없는 테마명 금지, 불가 시 `Culture route`) (FR-B8)
- [ ] 계획 방문시간 `예정` 표기, 공식 고정회차와 구분
- **Done when:** B 선택이 LF-09에서 식별·재접근 가능.

### (선택) LF-10 — 방문 후 최소 피드백
- [ ] Product 최종 MVP 포함 결정 시에만. Push/GPS 없음, 재방문 시 가벼운 Trigger. Analytics 분리(선호 자동 승격 금지)

---

## 6. 횡단 관심사 (Phase 전반에서 지속)

- [ ] **테스트:** `domain/` 결정론 로직 단위 테스트 유지(판정·정규화·경계). `pytest` 통과를 커밋 전 확인.
- [ ] **PoC 증빙(NFR-08):** 다단계 Agent(조회→판정→분기→구성→설명)의 trace를 재현 가능하게 축적.
- [ ] **배포 지속:** 슬라이스마다 배포 갱신(Render/Vercel), 외부 URL 상시 동작.
- [ ] **접근성·i18n:** 영어 우선, 긴 Reason 줄바꿈, 터치타깃, 내부용어 비노출 (DESIGN §6).
- [ ] **Naver Map:** 프론트 지도 착수 시 NCP 콘솔 Web 서비스 URL 등록 + `ncpKeyId` 확인.
- [ ] **보안:** 시크릿은 `.env`/배포 Secret만, 커밋 금지. Secret 키는 백엔드 전용.
- [ ] **실사용자 검증(과제 필수):** 발표 전 최소 5명 테스트·피드백 반영 문서화.

---

## 7. 완료 기준 매핑 (PRD §10) — 최종 점검
- [ ] A 정상/Fallback 완료 기준 충족 (PRD §10 A)
- [ ] B 정상/Fallback 완료 기준 충족 (PRD §10 B)
- [ ] 과제 요건: 생성형 AI/Agent 핵심 + 기술요소 3개(Agent·RAG·Memory) + 배포 + 실사용자 5명 + GitHub 기록 + AI 윤리 고지 (PRD §1)

---

## 8. 구현 단계 Tech 후속 (막히면 Product 재조율 전에 여기부터)
- B-T01 자율형 체류시간 산정 근거 / B-T02 구간 충돌 판정 / B-T03 다구간 도보 / B-T04 대화 조건수정 / B-T05 재구성·복구 / B-T06 조합 검증 (PRD §12, `research/tech-validation/..._1004_01.md`)
- **Evidence-based Reopen 원칙:** 정상 루트의 실행가능성 판단 자체가 성립 불가한 제약이 실제로 확인될 때만 근거와 함께 Product에 알린다. 화면/기술 세부 차이만으로 Freeze를 다시 열지 않는다.
