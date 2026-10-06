# CLAUDE.md — KONNECT 개발 가이드

> 이 파일은 Claude Code(및 팀)가 KONNECT를 개발할 때 따르는 **기술 기준·컨벤션·작업 규칙**이다.
> 제품 요구는 `PRD.md`, 제품 의미의 정본은 `codyssey-ai-native-final-team/planning` 저장소를 따른다.
> 충돌 시 우선순위: **planning 저장소 최신 Product 기준 > PRD.md > CLAUDE.md > 코드 주석.**

---

## 0. 이 저장소의 문서 사용 규칙 (AI·팀 공통)

**자동 로드되는 건 이 `CLAUDE.md` 하나뿐이다.** `PRD.md`·`DESIGN.md`·planning 문서는 필요할 때만 읽는다. **통독하지 말고 ID·헤딩으로 해당 섹션만 찾아(Grep) 읽어** 토큰을 아낀다.

**개발 착수·진행 시 먼저 볼 것:** `agent-flow.md` — 권장 개발 순서(Phase 0~4)와 **슬라이스별 체크리스트**. "지금 어디까지 됐고 다음에 뭘, 어떻게 검증하며"를 이 파일로 이어간다(체크박스 갱신).

**문서 라우팅 — 무엇을 할 때 무엇을 읽나**
| 작업 | 먼저 볼 곳 (해당 ID/섹션만) |
|---|---|
| 기능 요구·동작·완료기준 | `PRD.md` §4(FR-*), §10 |
| AI·Agent 동작·신뢰 판정 | `PRD.md` §5 + 본 파일 §4·§6 |
| 데이터 소스·정규화·가격/예약 | `PRD.md` §6 |
| 지도·경로 | `PRD.md` §7 + 본 파일 §4.3 |
| UI 값(색·타이포·간격) | `frontend/css/tokens.css` (값 정본) |
| 디자인 규칙·컴포넌트·화면 스펙 | `DESIGN.md` §2~§5 (해당 컴포넌트/LF만) |
| 제품 "의미"가 모호·충돌 | planning `product/*` (해당 주제 문서만) |

**정본 위치(Canonical source) — 중복 서술이 보이면 아래를 기준으로 판단·갱신**
| 주제 | 정본 |
|---|---|
| 신뢰·안전 불변식 | 본 파일 §6 |
| 기능 요구·완료기준·데이터/지도 규칙 | `PRD.md` |
| 디자인 **값**(색·px·반경 등) | `frontend/css/tokens.css` (코드가 정본, `DESIGN.md`는 설명) |
| 디자인 **규칙**·컴포넌트·화면 | `DESIGN.md` |
| 제품 의미·정책 | planning `product/*` · Google Docs 기준서 |

- 다른 문서의 서술이 정본과 어긋나면 **정본을 따르고 해당 문서를 갱신**한다. 자기완결성을 위해 요약 서술은 남기되, 세부는 정본을 가리킨다.

---

## 1. 프로젝트 한 줄 요약

서울 자유여행 외국인 FIT에게, 현재 조건(위치·시간·운영조건)에서 **실제 가능한 문화경험**을 좁혀주는 모바일-퍼스트 웹 서비스. 핵심은 공식 데이터 조회·사실 판정·미확인 분리·근거 설명을 수행하는 **다단계 AI Agent**이며, FAQ·여행정보·콘텐츠 Q&A는 **RAG**로, 로그인 사용자 맥락은 **Long-term Memory**로 보강한다.

**제1 원칙(코드 전반에 관철):** **미확인 ≠ 무료 / 예약 불필요 / 이용 가능 보장.** 확인되지 않은 정보를 추정으로 메우는 코드를 작성하지 않는다.

---

## 2. 기술 스택 (확정)

| 레이어 | 기술 | 비고 |
|---|---|---|
| **Frontend** | **순수 HTML / CSS / JavaScript** (프레임워크·빌드 프레임워크 없음) | React/Vue 등 사용 금지. ES Modules·Fetch API 기반 Vanilla JS. |
| **Backend** | **Python 3.12+ / FastAPI** (venv 가상환경) | REST API. Pydantic 모델로 입출력 검증. |
| **AI / Agent** | **OpenAI API + LangChain** | 다단계 조회→판정→재판단 오케스트레이션은 LangChain(Agent + Tools + Chains)으로 구성. LangGraph는 사용하지 않는다. |
| **RAG / Vector** | **Supabase pgvector + OpenAI Embeddings** | FAQ·여행정보·콘텐츠 Q&A 지식베이스 검색. 별도 벡터DB 추가 없이 Supabase Postgres(pgvector) 사용. |
| **DB / Auth / 상태저장** | **Supabase** (Postgres + pgvector + **Supabase Auth**) | **Supabase Auth가 Google OAuth 처리** → 프론트가 세션 JWT 획득 → FastAPI는 JWT 검증만(provider-agnostic). 사용자·선호·현재 선택·세션 상태 저장. |
| **지도 렌더링** | **Naver Maps SDK** (프론트) | 핀·지도 표시. |
| **경로(도보) 표시·계산** | **Tmap API** (백엔드 프록시) | 구간별 도보 경로선·거리·시간. |
| **외부 길찾기 딥링크** | **Google Maps URL** | 외국인 사용자 상세 길찾기 연결. |
| **외부 데이터** | TourAPI(EngService2) · 서울문화포털 문화행사 API · KOPIS · 기상청 · AirKorea | 추천 시점 **직접 조회(경량)** + 단기 캐시. |
| **보조 장소정보** | **Google Places API (New)** (보조 한정) | 좌표·주소·링크 보강. 이미지는 공식 소스 우선·Places는 Fallback. `price_level`·평점·리뷰 판정 사용 금지. 개발=데모 키 / 배포=정식 키(무료 티어), **키만 교체·코드 불변**. 상세 PRD §6.7. |
| **배포** | Frontend: Vercel/Supabase 호스팅 · Backend: Render | 외부 접근 URL 필수. |

**API 키:** 모든 외부 API 키는 보유 중이며 실제 개발 단계에서 전달된다. **절대 저장소에 커밋하지 않는다** — `.env`(gitignore) / 배포 Secret으로만 주입.

---

## 3. 디렉터리 구조 (제안 — 확정 시 갱신)

```
code/
├─ PRD.md
├─ CLAUDE.md
├─ DESIGN.md                 # 디자인 토큰·컴포넌트·화면·상태 시각 규칙 (Figma 기준)
├─ README.md                 # 과제 제출용 (팀원·역할·실행법·결과)
├─ .env.example              # 키 이름만, 값 없음
├─ backend/
│  ├─ app/
│  │  ├─ main.py             # FastAPI 엔트리
│  │  ├─ config.py           # env 로딩 (pydantic-settings)
│  │  ├─ api/                # 라우터 (recommend_a, route_b, auth, mypage, feedback)
│  │  ├─ agent/              # LangChain Agent·체인·프롬프트
│  │  │  ├─ orchestrator.py  # 다단계 파이프라인 (structure→fetch→judge→compose→explain)
│  │  │  ├─ tools/           # LangChain Tools (공식 API 조회·시간/이동 판정 래핑)
│  │  │  ├─ context.py       # Agent 컨텍스트 스키마 (Request/Trip/Preference 포함)
│  │  │  └─ prompts/         # 프롬프트 템플릿
│  │  ├─ sources/            # 외부 API 클라이언트 (tourapi, seoulculture, kopis, kma, airkorea, tmap, gplaces)
│  │  ├─ rag/                # 지식베이스 적재·임베딩·pgvector 검색 (FAQ·여행정보·콘텐츠 Q&A)
│  │  ├─ domain/             # 판정 로직 (constraints, pricing, timing, status, reason)
│  │  ├─ models/             # Pydantic 스키마 (입력/출력/도메인)
│  │  ├─ db/                 # Supabase 클라이언트·쿼리
│  │  └─ core/               # 공통 유틸·예외·로깅/trace
│  ├─ tests/
│  └─ requirements.txt
└─ frontend/
   ├─ index.html
   ├─ css/
   │  └─ tokens.css          # 디자인 토큰(값 정본) — DESIGN.md §2 참조
   ├─ js/
   │  ├─ api.js              # 백엔드 호출 래퍼
   │  ├─ pages/              # LF-01~LF-09 화면 로직
   │  ├─ components/         # 재사용 DOM 컴포넌트 (card, reason-chip, status-badge, map)
   │  └─ state.js            # 클라이언트 상태(현재 요청·선택) 관리
   └─ assets/
```

> 실제 구현 시작 시 이 구조를 확정하고 본 섹션을 갱신한다. 임의로 React 등 프레임워크를 도입하지 않는다.

---

## 4. 아키텍처 핵심

### 4.1 AI Agent (LangChain)
추천의 핵심은 단일 LLM 호출이 아니라 **LangChain 기반 다단계 파이프라인**이다(PRD §5.1). 각 단계는 LangChain의 Agent/Chain + Tools로 연결한다:

```
[structure] 사용자 조건 구조화 (자연어 → Request Context 스키마)
   → [fetch]   필요한 공식 API 조회 (LangChain Tools)
   → [judge]   사실·제약 판정 (운영/가격/시간/이동/충돌) + 미확인 분리
   → [compose] 후보/루트 구성 (Hard 제외 → Soft 균형); 불충족 시 재판단 루프
   → [explain] Reason(0~2개) + 미확인 설명 + 다음 행동
```

- **판정은 코드(`domain/`)로, 설명은 LLM으로.** 명백한 사실·숫자 비교·휴무·시간충돌은 결정론적 코드로 판정하고, LLM은 *확인된 근거를 읽기 쉽게 설명*하는 역할만. LLM이 새 사실·가격·가능성을 만들어내게 하지 않는다. (조회·판정은 가능한 한 Tool/코드로 수행하고 LLM 자유 생성에 의존하지 않는다.)
- **컨텍스트에 Request > Trip > User Preference 우선순위를 명시적으로 모델링**하고, 확인 가능한 사실·필수 조건은 개인화가 덮어쓰지 못하게 분리한다.
- 각 단계의 조회·판정·분기를 **trace로 기록**(PoC·과제 증빙 + 디버깅). LangChain callbacks/LangSmith 등 활용은 Tech 재량.

### 4.2 외부 데이터 (경량 직접 조회)
- `sources/`의 각 클라이언트는 **타임아웃·재시도·단기 캐시**를 기본 내장. 한 소스 실패가 전체 추천 실패로 번지지 않게 한다(`TourAPI + 구조화 공식 API`만으로 기본 추천 성립).
- 응답은 즉시 **데이터 상태로 정규화**(PRD §6.2): 가격 `free/paid/unknown/partial-or-ambiguous`, 예약·참여 확인된 것만, 시간값 `실제/예상/계획/미확인`. 정규화는 `domain/`에서 단일 지점으로.
- 기상청·AirKorea는 **Context**로만 사용(PRD §6.6). 환경정보만으로 행사 취소·휴관 추정 금지.
- **공식 API 우선 원칙.** 모든 사실 데이터는 공식 API가 정본이며, **Google Places는 공식 소스로 부족할 때 좌표·주소·링크·이미지 Fallback 보강에만** 쓴다. `price_level`·평점·리뷰는 판정/랭킹에 사용 금지(PRD §6.7).

### 4.3 지도·이동
- 프론트: Naver Maps SDK로 렌더. 경로선·거리·시간은 백엔드가 **Tmap 프록시**로 계산해 provenance(신뢰 수준)와 함께 내려준다.
- UI는 PRD §7의 **3단계 Fallback**을 provenance 값으로 분기. **임의 직선을 실제 경로처럼 그리지 않는다.** 상세 길찾기는 Google Maps 딥링크.

### 4.4 인증·상태 (Supabase Auth)
- **Supabase Auth가 Google OAuth를 처리**한다. 프론트가 `signInWithOAuth`로 세션 JWT를 받고, FastAPI는 **JWT 검증만** 한다(provider-agnostic — 이후 Kakao 등 추가해도 백엔드 재작업 없음).
- **첫 진입 로그인 강제 금지**, 비회원 첫 추천 결과까지 1회 → 두 번째/재추천 시 로그인 유도(PRD FR-L1).
- **비회원→로그인 데이터 마이그레이션(FR-L2, MVP IN).** 권장 구현: **Supabase Anonymous Sign-in**으로 익명 user_id를 선발급해 요청 조건·선택을 저장 → Google 로그인 시 **identity linking**으로 동일 user_id를 영구 계정으로 승격(데이터 자동 보존). (Anonymous Sign-in은 대시보드에서 토글 ON 필요.)
- **단 임시 상태를 여행 맥락(Trip)·장기 선호(Preference)로 자동 승격하지 않는다.** 확인된 사용자 선호만 저장·재사용, My Page에서 확인·수정·초기화(이후 추천부터 적용).

### 4.5 RAG (FAQ·여행정보·콘텐츠 Q&A)
- 지식 문서를 청크→OpenAI Embeddings→**Supabase pgvector**에 저장, 질의 시 유사도 검색으로 근거를 회수해 LLM이 **검색된 근거 범위 안에서만** 답변(PRD §6.5, FR-C8).
- **사실 데이터(가격·운영시간·예약 등)는 RAG가 아니라 공식 API(`sources/`)가 정본.** RAG는 FAQ·여행정보·콘텐츠 설명 등 참고 지식에 한정하며 실행 가능성 판정 근거로 쓰지 않는다.
- 검색 근거가 없으면 생성하지 않고 `추가 확인 필요`·공식 경로로 연결. 별도 챗봇 화면으로 분리하지 않고 A·B 자연어 대화 흐름에 통합.

---

## 5. 코딩 컨벤션

### 공통
- **언어·주석:** 코드 식별자는 영어, 설명 주석은 한국어 허용(팀 언어). 사용자-facing 문자열은 **영어 우선**.
- **사용자 화면에 내부 용어 노출 금지:** `Hard Constraint`, `추천 제외`, 내부 Fit명(`Time Fit` 등) 같은 내부 용어를 UI에 그대로 쓰지 않는다. 의미를 전달하는 최종 Copy는 design/UX 기준을 따른다.
- **비밀값 하드코딩 금지.** 전부 env.

### Python / FastAPI
- Python 3.12+ (**venv 가상환경**에서 작업), **타입 힌트 필수**, 입출력은 **Pydantic 모델**로 검증.
- 포매터 **ruff + black**, 린트 ruff. 함수·모듈은 단일 책임.
- 외부 호출은 `sources/`에만, 판정 로직은 `domain/`에만. 라우터(`api/`)는 얇게 유지.
- 예외는 `core/`의 공통 예외로 변환해 **시스템 예외(FR-C7)와 정상 결과(0건 등)를 명확히 구분**.

### Frontend (Vanilla JS)
- ES Modules, `fetch` 기반. **빌드 프레임워크/런타임 프레임워크 도입 금지.** 필요한 경량 라이브러리는 추가 전 팀 합의.
- DOM 컴포넌트는 `components/`에 함수 단위로. 상태는 `state.js`에 모으고 화면 로직(`pages/`)과 분리.
- 결과 상태 3종(조건 충족/추가 확인 필요/조건 완화 대안)과 Fact/Reason/미확인을 **시각적으로 분리**해 렌더. 토큰·컴포넌트·상태 시각 규칙은 `DESIGN.md`를 따른다(브랜드 teal `#007385`, Inter, 3상태 색 등).

### Git
- 커밋 메시지는 간결한 명령형. 의미 단위로 커밋. 기본 브랜치에 직접 커밋하지 말고 브랜치 사용.
- `.env`, 키, `__pycache__`, `node_modules`(미사용), 빌드 산출물은 `.gitignore`.
- **커밋·푸시는 사용자가 요청할 때만.**

---

## 6. 신뢰·안전 불변식 (코드로 지켜야 할 것)

리뷰·구현 시 아래를 체크리스트로 쓴다.

1. **미확인을 긍정으로 바꾸지 않는다.** 빈값/모호값을 `free`·`예약 불필요`·`이용 가능`으로 매핑하는 코드가 없는지.
2. **LLM이 사실을 생성하지 않는다.** 가격·운영시간·예약 가능 여부·좌표를 LLM 출력에서 받지 않는다(공식 데이터만).
3. **숫자 임의 생성 금지.** 체류시간·이동시간을 근거 없이 60/90/20분으로 채우지 않는다(계획값은 근거+상태 표기).
4. **Hard 충돌 후보는 정상 추천에 섞이지 않는다.** (휴무·마감·자격 미충족·시간충돌·위험특보 Outdoor.)
5. **강제 채움 금지.** A 후보 수(최대 3~4개)·B 루트(2~3개, 3개 강제 금지)를 숫자 맞추려고 부적합 후보로 채우지 않는다.
6. **개인화가 사실/필수 조건을 덮어쓰지 않는다.** Request > Trip > Preference, 걷기 선호는 Soft signal only(숫자 상한 변환 금지).
7. **선택 ≠ 방문.** GPS 자동 방문판정·턴바이턴 없음.
8. **AI 관여 고지·확인/미확인 구분 UI**를 제거하지 않는다.

---

## 7. 작업 방식 (Claude Code 규칙)

- **먼저 PRD.md와 해당 planning 문서를 확인**하고, 입력/출력·상태·Fallback·신뢰·완료기준에 영향 주는 변경은 임의로 하지 않는다. 필요하면 Product와 재조율하도록 플래그.
- 비자명한 구현 전 접근을 먼저 공유(plan)하고, 다수 파일·아키텍처 결정은 합의 후 진행.
- 구현한 변경은 실제로 **동작을 확인**하고 결과를 사실대로 보고(테스트 실패/스킵을 숨기지 않는다).
- 외부로 나가는 동작(배포, 외부 서비스 전송 등)은 사전 확인 후 진행.
- **개발용 PRD는 Tech가 관리**하며 Product 측 중복 PRD를 만들지 않는다.

---

## 8. 자주 쓰는 명령 (실제 셋업 후 확정)

```bash
# Backend (Python 3.12+ 가상환경)
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload            # 개발 서버

ruff check . && black .                   # 린트·포맷
pytest                                    # 테스트

# Frontend (정적 — 간단 서버)
cd frontend
python -m http.server 5500                # 로컬 확인
```

> 실제 스크립트·명령이 정해지면 이 섹션을 갱신한다.

---

## 9. 참고 문서 (planning 저장소)

- `product/README.md` — 서비스 윤곽·현재 상태·담당자 읽기 경로.
- `product/01-product-baseline.md` — 범위·사용자·핵심가치·시나리오 (D-01~D-06).
- `product/02-input-recommendation-rules.md` — 입력·Hard/Soft·후보 판정·예산·무료 필터 (D-07·D-08·D-10).
- `product/03-data-trust-policy.md` — 데이터 소스·가격/예약·환경·신뢰 (D-09·D-11).
- `product/04-route-time-rules.md` — 기존계획·Start Anchor·시간·문화루트 Fallback (D-12·D-13).
- `product/05-ux-handoff.md` — IA·LF-01~LF-10·정상/Fallback·완료기준.
- `product/06-ai-tech-boundary.md` — AI 동작·PoC 검증·역할 경계·P-09 (D-14·D-15·P-01~P-09).
- `product/reason-copy-dictionary.md` — Reason Copy 17개·생성/억제 조건.
- `decisions/decision-log.md` — D번호·결정 상태 색인.
- `research/` — TourAPI 실측·데이터 품질·Tech 검증 이력(B-T01~B-T06).
- 제품 기준 정본: Google Docs `KONNECT 제품 기획 기준서`.
