# 추천 A·B 동작 분석 + Agent Loop / Tool Calling + 검색 품질 개선

> 작성: 2026-10-09 · 관점: AI-Native 백엔드
> 목적: 추천 A(즉시 추천)와 추천 B(문화루트)가 **지금 어떻게 동작하는지**를 코드 근거로 정리하고,
> 이를 기준으로 **검색(retrieval) 품질의 구조적 한계와 개선책**을 기록하기 위한 베이스 문서.
> 정본 코드: `backend/app/agent/`, `backend/app/domain/`, `backend/app/sources/`.

---

## 0. 한눈에 보기 (TL;DR)

- **Agent Loop는 "의도 라우팅"에서만 agentic하다.** `while` 루프(`agent_loop.py`)는 LLM이 3개 intent tool(`recommend_experiences` / `plan_culture_route` / `answer_travel_question`) 중 무엇을 **언제·몇 개** 부를지만 결정한다. **각 tool 내부(추천 A/B)는 고정된 결정론 파이프라인**이라, "검색이 빈약하면 넓혀서 재검색" 같은 루프가 **없다**.
- **추천 품질을 좌우하는 실제 검색은 `recommend_a` / `recommend_route` 안의 고정 조회**다: **반경 1500m · 거리순 · 상위 8~12개만 상세조회·판정**. 이 컷이 recall(놓치지 않고 찾아오는 능력)의 상한을 사실상 결정한다.
- **선호·관심사·정성 조건은 대부분 "조회 이후 재정렬(Soft rerank)"로만 반영**된다. 검색 쿼리 자체에는 거의 들어가지 않는다 → 좋은 후보가 반경·거리 컷에서 떨어지면 재정렬로도 복구 불가.
- 신뢰 경계(사실=코드, LLM은 생성 금지)는 잘 지켜지고 있고, `trace`로 전 단계가 계측된다 → **오프라인 검색 품질 평가(eval) 기반을 깔기 좋은 상태**다.

---

## 1. 진입 경로 (어디서 A/B가 호출되나)

세 경로 모두 결국 같은 두 함수(`recommend_a`, `recommend_route`)로 수렴한다.

| 경로 | 파일 | A/B 호출 |
|---|---|---|
| **Agentic 챗 루프** (`settings.agent_loop=True`) | `agent/agent_loop.py` | LLM tool 선택 → `_run_recommend_or_route` → `recommend_a` / `recommend_route` |
| **단일 라우팅 챗** (`agent_loop=False`, fallback) | `agent/chat_agent.py` | LLM 단일 tool → `dispatch_tool` → 동일 두 함수 |
| **직접 REST** | `api/recommend.py` `POST /api/recommend`, `api/route.py` `POST /api/route` | 바로 `recommend_a` / `recommend_route` |

`api/chat.py:48` 에서 토글: `chat_fn = run_chat_loop if settings.agent_loop else run_chat`.
즉 **"agentic loop"와 "단일 라우팅"은 라우팅 방식만 다르고, 실제 추천 로직(A/B)은 완전히 동일**하다.

---

## 2. Agent Loop (while loop + tool calling) 동작

`agent/agent_loop.py` · `run_chat_loop()`.

```
[system+history+user(+ctx요약)]  →  for step in range(_MAX_STEPS=6):
   ai = llm.ainvoke(messages)            # 경량 모델(gpt-4o-mini), temperature=0, bind_tools(3종)
   calls = ai.tool_calls
   if not calls:  return _present(...)   # tool 안 부르면 종료(자연어 소개 메시지)
   # 같은 턴의 여러 tool 은 asyncio.gather 로 병렬 실행
   observations = [ _run_tool(name,args,state,trace) for call in calls ]
   messages += ToolMessage(관측요약)      # ← LLM 엔 "요약"만, 사실 전문은 state 에 보관
   if state.clarify: return state.clarify # 필수사실/선호 미비 → 즉시 되묻기
→ _MAX_STEPS 소진 시 모은 결과로 _present
```

핵심 설계 포인트:

- **LLM에게는 사실이 아니라 "관측 요약"만 되돌려준다.** 예: `_run_tool`은 `"Found 3 experiences: A, B, C."`만 반환하고(`agent_loop.py:151`), 실제 `RecommendData`/`RouteData`/`RagAnswer`는 `LoopState`에 적재(`agent_loop.py:80-91`). 최종 렌더는 `_present()`가 `LoopState`의 **코드 결과**에서 수행한다(`agent_loop.py:185-215`). → LLM이 가격·시간·좌표를 지어낼 통로가 없음(신뢰 경계).
- **멀티 인텐트 지원.** "이거 질문 + 추천해줘"를 한 턴에서 여러 tool로 처리하고, `_present`는 route > recommendation > answer 순 primary `kind`만 힌트로 주되 **실린 필드는 모두 프론트에 내려준다**(`agent_loop.py:196-215`).
- **필수 사실(위치·시간) 없으면 추정 금지·되묻기.** `has_trip_context` 체크 후 `_CLARIFY_NEED_TRIP`(`agent_loop.py:115-120`). 추천인데 선호 미지정+미질문이면 `_ASK_PREFS`로 한 번 묻는다(`agent_loop.py:122-133`).
- **Graceful.** LLM 호출 실패 시 모은 결과가 있으면 그걸로 종료, 없으면 fallback(`agent_loop.py:252-260`). tool 실패는 `"Tool X failed; proceed"` 관측으로 루프 비중단(`agent_loop.py:178-181`).
- **상한·계측.** `_MAX_STEPS=6`으로 비용/무한루프 방어, 매 턴 `trace.step("agent_turn", ...)`.

> **중요한 구조적 사실:** 이 루프의 "agency"는 **어떤 상위 의도 tool을 조합할지**에 국한된다. `_MAX_STEPS=6`은 멀티 인텐트를 위한 것이지, **검색 결과를 보고 "부족하니 다시/다르게 검색"하는 루프가 아니다.** 루프가 관측하는 것은 `"Found N experiences"` 같은 개수 요약뿐이고, N이 작아도 LLM이 할 수 있는 건 "다시 같은 tool 호출"밖에 없으며 — 그 tool은 **같은 반경·같은 파라미터로** 동일 결과를 낸다.

---

## 3. Tool Calling 인벤토리

### 3.1 LLM에 **실제로 바인딩된** tool (3종, intent 라우팅용)

`agent/tools/schemas.py` — `bind_tools`로 LLM에 노출되는 Pydantic 스키마. LLM은 **의도 선택 + 사용자 표현(preferences 문자열) 추출**만 하고, 위치·시간·가격 같은 사실은 담지 않는다.

| Tool | 트리거 | 실행 코드 |
|---|---|---|
| `RecommendExperiences(preferences)` | "뭐 할까/주변에 뭐 있어" 등 개별 추천 | → `recommend_a` (추천 A) |
| `PlanCultureRoute(preferences)` | "루트/코스/일정 짜줘" 등 다중 스톱 | → `recommend_route` (추천 B) |
| `AnswerTravelQuestion(query)` | 교통/환전/매너/문화 설명 FAQ | → `answer_knowledge` (RAG) |

`preferences`/`query`는 **사용자 원문 표현**이다. preferences는 이후 `parse_note`(LLM 구조화)로 들어가고, query는 pgvector 검색으로 들어간다.

### 3.2 각 tool 내부가 호출하는 **코드 소유 building block** (LLM 비노출)

추천 A/B 파이프라인이 내부에서 직접 호출하는 함수들. 이것들이 실제 "검색·판정"을 수행한다.

| 함수 | 파일 | 역할 |
|---|---|---|
| `_fetch_pool` | `orchestrator.py:129` | TourAPI + 서울문화포털 **병렬 조회·병합·거리순·dedup** |
| `_fetch_tour_pool` | `orchestrator.py:72` | TourAPI 문화타입(76·78·85) `location_based_list` 조회 + 비문화 blacklist |
| `_fetch_seoul_pool` | `orchestrator.py:104` | 서울문화포털 '그날 열리는' 행사 + 좌표 반경 후필터 |
| `_fetch_and_normalize` | `orchestrator.py:195` | 후보당 상세조회(TourAPI detail×3 + Places×1) → 공통 `Candidate` 정규화 |
| `_judge_record` | `orchestrator.py:255` | 운영/휴무/행사기간/폐업/예산 **결정론 판정** → fits/alternative/check 또는 Hard 제외 |
| `parse_note` | `note_parser.py` | 자연어 preferences → `ParsedConditions`(LLM 구조화, 사실 생성 금지) |
| `classify_places` | `classify.py` | 후보 텍스트 → 실내/외 + 정성선호 적합(`fits_vibe`) (per-candidate LLM 1콜) |
| `classify_excluded` | `exclude_classifier.py` | 개방형 배제 개념 의미 매칭(LLM) |
| `parse_hours` | `hours_parser.py` | 운영시간 자유텍스트 UNCERTAIN→OPEN 재추출(LLM, tour 전용) |
| `get_environment` | `environment.py` | 기상청·AirKorea Context(악천후 Soft 신호, 판정 근거 아님) |
| `assemble_route` / `_build_route` | `route_orchestrator.py` | (B) 스톱 동선 조립 + 구간 도보(Tmap) |

### 3.3 정의돼 있으나 **어디서도 호출되지 않는** tool (설계 의도 ↔ 실제 배선 괴리)

`agent/tools/experiences.py`, `agent/tools/route.py`에 다음이 정의돼 있다:

- `search_experiences(lat,lng,on_date,limit)` — 판정 전 사실 후보 조회
- `check_availability(records,ctx,cond)` — 가용성 판정
- `walk_route(origin,stops,sequential)` — 구간 도보
- `plan_day_route(origin,stops,...)` — 하루 1코스 조립

이들은 docstring상 *"agentic 루프가 조합할 코드 소유 사실 tool"*로 쓰여 있으나, **grep 결과 실제 코드 어디에서도 import·호출되지 않고 LLM에 bind도 되지 않는다.** 즉 "search→check→route를 LLM이 단계적으로 조립"하는 그림은 **아직 배선되지 않았고**, 실제 루프는 상위 intent tool 3종만 쓴다. (추천 A/B는 이 building block이 감싸는 하위 함수 `_fetch_pool`·`_enrich` 등을 **직접** 부른다.)

> 검색 품질 개선의 가장 큰 레버는 바로 이 괴리를 좁히는 것이다 — §6 참고.

---

## 4. 추천 A (즉시 추천) 파이프라인

`agent/orchestrator.py` · `recommend_a()`. 단계는 `trace.step` 라벨과 일치한다.

```
[structure] 좌표 해석 + note 구조화(LLM) + 환경(기상/대기)  ── 모두 병렬
   ↓  저장 선호 Request-우선 병합(note 침묵 시에만 관심사 Soft 채움)
[select]    풀을 (관심사→실내외) 선호로 안정정렬                    ← Soft, 반경 안에서만
   ↓
[enrich]    pool[:8] 만 상세조회+판정 (_enrich = _fetch_and_normalize + _judge_record)
   ↓        · 행사기간 종료/미개막 → Hard 제외
   ↓        · Places businessStatus 폐업 → Hard 제외
   ↓        · 운영/휴무/시간충돌/예산 → fits / alternative / check_needed / Hard 제외
[filter-places]  사용자가 이름 댄 장소 결정론 제거
[classify]  생존 후보에 LLM 1콜: 실내/외 + 정성선호 적합(fits_vibe)
   ↓        · "실내만/실외만"(strict) → 반대로 확신분류된 것만 Hard 제외(unknown 유지)
[filter]    개방형 배제개념 LLM 매칭 → 제거(0건이면 세이프 폴백)
   ↓        최대 _MAX_CANDIDATES=4 유지
[route]     후보별 출발점→후보 도보(Tmap) 병렬 부착 (실패=Route unavailable)
[explain]   확정 근거 기반 Reason 0~2개
[compose]   표시정렬 display_sort_key = (관심사, 실내외, 정성, 날씨, 상태등급) 안정정렬
            → 같은 등급 안에서 거리순 보존
→ RecommendData(candidates≤4, origin, conditions, notices, environment)
```

검색 관련 상수(`orchestrator.py:66-69`):

- `_SEARCH_RADIUS_M = 1500` — **고정 반경**
- `_ENRICH_POOL = 8` — 상세조회·판정 대상 상위 개수
- `_MAX_CANDIDATES = 4` — 최종 노출 상한

**선발의 실제 동작(중요):** `[select]`에서 pool을 선호로 안정정렬한 **뒤** `pool[:8]`을 취한다(`orchestrator.py:385-398`). 따라서 관심사 매칭 후보는 "반경 1500m 안"이면 거리가 조금 멀어도 상위 8개 안으로 끌어올려져 판정에 포함된다. 그러나 **반경 1500m 밖은 애초에 pool에 없으므로 재정렬로도 복구 불가**다. `classify_places`의 정성 적합(`fits_vibe`)과 실내외는 **judge를 통과한 생존 후보에만** 적용되므로, recall이 아니라 **순서/소폭 Hard(strict only)에만** 영향한다.

---

## 5. 추천 B (문화루트) 파이프라인

`agent/route_orchestrator.py` · `recommend_route()`. A의 조회·판정을 재사용한다.

```
[fetch]        _fetch_pool (A와 동일 멀티소스 조회) + 환경  ── 병렬
[enrich]       pool[:_ROUTE_POOL=12] 상세조회+판정(_enrich, A와 동일 코드)
   ↓           valid = Hard 제외 통과 후보
[filter-places] 이름 댄 스톱 결정론 제거
[filter]       개방형 배제개념 LLM 매칭 제거
[io_base]      실내외 불일치 유형 강등(≥2 남으면 그걸로, 아니면 전체 — 0-safe)
[preferred]    관심사 매칭(type_preference_rank==0) 스톱 우선 집합
[assemble]     assemble_route: preferred(≥2) → io_base → feasible 순 단계 폴백으로 동선 조립
   ↓           스톱별 Reason 부착
[build]        _build_route: 구간 도보(Tmap) + 시간창 맞춤(fit_count)
   ↓           · 창에 2스톱도 안 들어가면 None → unmet
   ↓           · 체류시간: 공식 spendtime=confirmed / 유형기준=planned (임의 숫자 금지)
→ RouteData(routes=[route](최대 1코스) or [], unmet 메시지, environment)
```

검색 관련 상수(`route_orchestrator.py:50`): `_ROUTE_POOL = 12`.

신뢰 경계상 주의점(코드 주석과 일치):

- **루트 total은 "도보 이동시간"만 합산** — 체류시간을 창 계산에 넣지 않는다(B-T01, `route_orchestrator.py:6-9`). 도보만으로 창 초과면 불가.
- **강제 3개 채움 금지** — `fit_count`로 창이 허용하는 만큼만, 2개 미만이면 루트 포기하고 unmet(`route_orchestrator.py:120-123, 238-245`).
- **관심사·이동 '균형 랭킹'(FR-B4 Soft B안)은 미구현** — 현재는 단계적 폴백(preferred→io_base→feasible) + 거리 기반 동선(`route_orchestrator.py:9, 218-233`).

---

## 6. 검색 품질의 구조적 한계 (AI-Native 백엔드 관점)

> 아래는 "버그"가 아니라 **현재 아키텍처가 만든 상한**이다. 신뢰 경계(사실=코드, 추정 금지)는 올바르게 지켜지고 있으며, 한계는 대부분 **retrieval 전략**에서 온다.

### L1. 고정 반경 1500m + 거리순 1차 컷이 recall 상한을 결정 ★최우선 — **P1로 완화(희소 시 반경 확대)**
`_SEARCH_RADIUS_M=1500`, `pool[:8]`(A)/`pool[:12]`(B). **선호·관심사·정성 조건을 보기 전에** 공간(반경)과 거리로 후보를 잘라낸다. 관심사가 아무리 명확해도 1501m의 완벽한 후보는 **조회조차 되지 않는다.** 선호 재정렬은 "이미 잘린 풀 안에서 순서만" 바꾸므로 recall을 늘리지 못한다. 외국인 FIT가 "오늘 오후 전시 보고 싶다"처럼 **콘텐츠 중심**으로 생각할 때, 공간 우선 검색은 미스매치가 크다.

### L2. 키워드/의미(semantic) 검색의 부재 — **P2(의미 재정렬) + P4(키워드 조회)로 해소**
TourAPI는 `location_based_list`(좌표+타입)만 사용한다(`orchestrator.py:72-101`). 사용자 note의 관심사·개방형 선호("조용한", "캘리그래피 체험", "로맨틱한")는:
- enum 6종으로 축약 → 유형 랭킹(coarse), 또는
- `classify_places`/`fits_vibe`로 **조회 후 재랭킹**

둘 다 **검색 쿼리에는 반영되지 않는다.** TourAPI `searchKeyword`/`areaBasedList`도, 임베딩 기반 매칭도 쓰지 않는다. 결과적으로 "내용 적합도"는 **반경 안에 우연히 들어온 것 중에서만** 평가된다.

### L3. 정성 선호(fits_vibe)가 selection이 아니라 rerank에만 작용 — **P2로 해소(의미 유사도가 selection 반영)**
`classify_places`는 judge를 통과한 생존 후보(최대 8개 중)에만 돈다(`orchestrator.py:415-422`). "로맨틱한 곳" 요청인데 반경 안 로맨틱 후보가 2개뿐이면 **그 2개가 최대치**다. 정성 선호는 recall에 기여 0.

### L4. "agentic retry/refinement"가 없다 — 적응 없는 단발 검색 — **P1로 부분(코드 반경 ladder; LLM 적응은 P3)**
§2에서 본 대로 루프는 intent 선택만 agentic하다. **후보가 0~1건이어도 반경 확대·시간창 완화·관심사 완화로 자동 재검색하지 않는다.** A는 적게 반환하고, B는 `unmet` 메시지를 낸다. LLM이 관측하는 것은 개수 요약뿐이라 "다시 같은 tool"을 불러도 **동일 파라미터·동일 결과**다. §3.3의 세분 tool(`search_experiences(radius)` 등)이 **배선되지 않아** 파라미터를 바꿔 재검색할 통로 자체가 없다.

### L5. latency/비용이 pool 크기를 억제 → recall과 직접 상충
`_fetch_and_normalize`는 후보당 TourAPI 3콜 + Places 1콜(`orchestrator.py:219-229`). **응답 캐싱 금지**(ToS·신선도) 정책상 매 요청 라이브 조회다. pool을 8로 묶은 건 지연 때문이고, 품질을 위해 pool을 키우면 상세조회 폭증으로 지연이 선형 악화된다. **"넓게 조회"와 "빠르게 응답"이 현재 구조에선 정면 충돌**한다.

### L6. 관심사 enum(6종)과 유형 맵이 거칠다 — **P4로 부분(특정 검색어 keyword 조회; 단 영문 데이터 커버리지 한정)**
`TYPE_INTERESTS`(`ranking.py:25-35`)는 내부 5유형 ↔ 6관심사, 1:1도 아니다. 세밀한 요구("서예 특별전만", "야장시장")는 enum으로 표현 불가 → open_preferences→fits_vibe soft로만 흡수되는데, L3 때문에 recall엔 무력.

### L7. 소스 다양성·좌표 의존
서울문화포털은 **좌표 있는 행사만** + 반경 후필터로 drop(`orchestrator.py:113-125`) — 임의 좌표 생성 금지라 정당하지만 recall 손실. TourAPI 비문화 blacklist(`curation.py`)도 불안정 분류를 보수적으로 다룬다. KOPIS 등 추가 소스는 정책상 제외(공연 커버리지 공백).

**강점(개선의 발판):** 전 단계가 `trace.step`으로 계측된다(pool 크기·소스별 건수·dedup·Hard 제외 사유·classify 결과까지). → **골든 쿼리셋 + trace 수집으로 오프라인 recall/precision eval을 바로 깔 수 있다.** 지금은 "검색이 좋은지"를 측정하는 장치가 없을 뿐, 데이터는 이미 나오고 있다.

---

## 7. 개선책 제안 (우선순위순)

> 원칙: **신뢰 경계 불변**(LLM은 파라미터·의미매칭·설명만, 사실·가용성은 코드/공식데이터). 모든 완화는 `notices`로 투명 고지. 이미 있는 인프라(pgvector 임베딩·trace·0건 세이프 패턴)를 재사용.

### P0. 측정부터: 검색 품질 Eval 하네스 — **구현됨 (2026-10-09)**
개선 전에 **골든 쿼리셋**(출발지·시간·note 조합 + 기대/금지 후보)을 만들고, `trace`를 수집해 **recall@k · constraint 위반율 · Hard 제외율 · 0건율 · p50/p95 지연**을 리포트한다. 이후 모든 변경(P1~P6)을 이 지표로 before/after A/B. (문서 제목의 "검색 품질 개선 기록"의 베이스라인.)

**위치:** `backend/app/eval/`
- `golden_set.json` — 쿼리셋(Product도 편집 가능). 라이브 데이터 드리프트에 견디도록 기대값은 **정확한 후보 id가 아니라 제목 부분문자열 + 구조 불변식**으로 둔다: `expect_title_any`(하나라도 잡히면 recall 성공) / `forbid_title_any`(나오면 위반) / `forbid_empty`.
- `metrics.py` — 순수 집계(네트워크·LLM 무관, 유닛테스트 `tests/test_eval_metrics.py`로 커버). recall@k·위반율·empty·hard_exclude·fits·percentile.
- `runner.py` — 추천 A/B를 **라이브 실행**(캐싱 없음)하고 제목·상태·지연·trace 신호 수집 + 구조 불변식 검사(후보≤4·status 누출 없음·루트 2~3스톱·origin 좌표 등). per-query graceful.
- `run_eval.py` — CLI. `python -m app.eval.run_eval [--mode recommend|route] [--filter <id>] [--concurrency N] [--json out.json]`. OpenAI·TourAPI 키 필요(없으면 경고 후 대부분 error로 집계).

**측정 지표 정의(정직성):** recall@k는 기대가 명시된 쿼리에 한정한 분모로 계산. "precision"은 레이블 부재상 **constraint 위반율**(금지 제목 노출·비면 안 되는데 0건·구조 불변식 위반)로 대체해 제약 준수를 측정한다. 루트(B)는 hard/pref 제외가 trace에서 분리 보고되지 않아 `hard_exclude`를 None으로 둔다(과대보고 방지).

**베이스라인 (2026-10-09, 라이브 스냅샷 — `docs/eval-baseline.json`):**

| 지표 | 값 | 메모 |
|---|---|---|
| recall@k | **100%** (n=3) | 기대 명시 쿼리(경복궁 역사/미술/장소제외)는 전부 적중. 단 모수 3개·중심부 '쉬운' 쿼리라 과신 금지 — §7 P0 후속으로 **난이도 높은 기대값·외곽 쿼리 확충** 필요 |
| empty_rate | **0%** | 9쿼리 모두 결과 반환(중심부 위주라 당연 — 외곽/희소 요구를 넣어야 L1·L6 노출됨) |
| constraint_violation | **0%** | 장소제외·구조 불변식 모두 통과 |
| mean fits_ratio | **47.2%** | 반환 후보 절반만 '조건 충족' — 나머지는 alternative/check_needed |
| mean hard_exclude | **5.4%** | 조회 후 가용성에서 걸러진 비율(추천 모드) — 낮음 |
| latency p50 / **p95** | **4.0s / 25.9s** | ★ **L5 확증.** p95가 26s(ddp-handson·outdoor-strict). 캐싱 없는 멀티소스 + per-candidate 상세조회·LLM 분류가 원인. 지연이 pool 확대를 막는 상충의 실측 증거 |

관찰: **모든 recommend 쿼리가 정확히 4개(상한) 반환** → 현재 중심부에선 recall 상한이 안 보이지만, 지연(p95 26s)과 fits 47%가 당장의 약점. 외곽·희소 요구 쿼리를 추가하면 L1(반경)·L6(희소 유형) recall 공백이 드러날 것.

> eval은 라이브·무캐싱이라 수치가 실행마다 변동한다(특히 지연). 베이스라인은 **스냅샷**이며, P1/P2 적용 후 같은 명령으로 재측정해 상대 비교한다.
>
> **다음 작업(P0 후속):** 골든셋에 **외곽 출발지·희소 요구(체험/공연)·더 엄격한 기대값**을 추가해 recall 모수를 키운다. 그 뒤 **P2(semantic rerank)** 착수.

> ⚠ **발견된 문서 불일치:** `agent/tools/schemas.py`의 `PlanCultureRoute` docstring과 설계 설명은 루트를 "2–3 stops"로 쓰지만, 실제 코드(`domain/route.MAX_DAY_STOPS=8`, "개수 제한 대신 시간창 허용분")는 **최대 8스톱**을 허용한다. eval 불변식을 코드 기준(2~`MAX_DAY_STOPS`)으로 맞췄다. LLM tool 설명 ↔ 코드 정합은 Product와 재조율 대상(§1 라우팅: 동작 영향 가능).

### P1. 적응형 반경 ladder (L1·L4 완화) — **구현됨 (2026-10-09)**
단발 조회를 **희소할 때만 넓히는 단계적 재조회**로. 유효 후보가 `_MIN_VIABLE=2` 미만이면 반경을 `_RADIUS_LADDER=(1500, 3000, 5000)`로 확대 재조회한다. **강제 채움이 아니라 '선택지가 2개도 안 될 때만'** 넓히므로, 밀집 지역은 1단계에서 충족돼 **확장이 트리거되지 않는다(지연 불변)**.

**구현:** `orchestrator.py`
- `_fetch_pool`/`_fetch_tour_pool`에 `radius` 파라미터 추가(기본 1500m).
- `collect_judged(..., first_pool, enrich_pool, min_viable)` — 1단계 풀(호출부가 parse_note·env와 병렬로 이미 조회)로 판정 후, 유효<min_viable면 ladder로 확대. 이미 판정한 아이템은 `_pool_item_key`로 걸러 **재판정하지 않는다**(증분 누적). 반환 (유효결과, Hard 제외 수, 최종 반경).
- `_rerank_and_judge` — P2 의미 재정렬 + 상위 K 판정을 단일 지점으로 모은 공용 헬퍼(A·B·ladder 공유).
- `recommend_a`·`recommend_route` 모두 `collect_judged` 사용. 확대 시 `notices`에 "Few options were nearby, so we widened the search area to find more." (RouteData에 `notices` 필드 신설).
- trace `radius_expand`(radius·viable·hard)·`fetch`에 radius 기록. 단위테스트 `tests/test_radius_ladder.py`(확장/미확장/상한 종료).

**신뢰 경계:** 반경은 검색 파라미터일 뿐 사실이 아니다 — 확대는 아무것도 지어내지 않는다. 확대는 항상 `notices`로 투명 고지. `_MIN_VIABLE`로 멈추므로 가까운 결과가 충분하면 먼 후보로 채우지 않는다(강제 채움 금지 불변).

**거리 라벨링 (확대 후보 투명성):** 확대로 편입된 후보에만 `Candidate.from_widened_search=True` + `Candidate.distance_m`(출발점 직선거리, 공식 `dist` — 확인된 사실)를 실어, 프론트(`result-card.js`)가 "📍 2.3 km away" 칩(muted)으로 표시한다. 1단계(기본 반경) 후보엔 붙지 않아 **'조금 떨어진 결과'가 한눈에 구분**된다. 라이브: 서울숲 → Waterworks(0.7km, 라벨無)·Cheonggyecheon(3.0km)·Seongsu(1.6km)·Park Ryu Sook Gallery(2.3km, 라벨有).

**결과 (라이브 확증):** **서울숲**(37.5444,127.0374) "any cultural" → 1500m 풀 **1개** → 3000m 확대 → 풀 7 → **후보 4개**(Waterworks/Cheonggyecheon/Seongsu Museum, Park Ryu Sook Gallery) + 안내 노출. 이전이면 ~1개로 끝날 외곽 요청이 실결과 4개로. 반면 도심(강동 6개/경복궁권)은 1500m에서 충족 → 확장 안 함. eval 12쿼리 **empty_rate 0%**(외곽 2쿼리 포함) 유지.

**남은 한계:** 상한 5000m. 여전히 **공간(반경)이 1차 필터**이고, 완화는 반경에 한정(시간창·관심사 strictness 완화는 미구현 — 필요 시 ladder에 단계 추가). 진짜 적응은 LLM이 파라미터를 고르는 **P3**에서.

### P2. Semantic rerank를 **selection 전으로** 이동 (L2·L3 해소) — **구현됨 (2026-10-09)**
이미 보유한 **OpenAI Embeddings**(RAG 스택, `rag/embed.py`)를 추천에도 재사용. 상세조회 컷(`pool[:K]`) **전에**, 조회 풀을 사용자 의도와의 의미 유사도로 재정렬해 **어떤 후보를 판정할지**를 거리·enum만이 아니라 관련도로 정한다.

**구현:** `agent/semantic_rank.py`
- `build_intent_text(cond, note)` — note 원문 + 관심사(enum→구절) + open_preferences를 한 의도 문자열로 합성(비선호/배제는 제외 — '원하는 것'만). 신호 없으면 None → 의미랭킹 생략.
- `pool_item_text(it)` — **목록 단계 텍스트**(tour: title+addr1 / seoul: TITLE+CODENAME+PLACE+GUNAME). 상세 overview 전이라 얇지만 선발 관련도엔 유효.
- `semantic_similarities(texts, intent, trace)` — 의도·후보 임베딩 cosine(쿼리·문서 임베딩 병렬 1콜씩). **실패/빈 의도는 전부 0.0 → 기존 거리·enum 순서 보존(graceful).**
- 통합: `orchestrator.recommend_a`·`route_orchestrator.recommend_route`의 `[select]` 블록에서 정렬 키 = **(관심사 enum rank → −의미유사도 → 실내외 → 거리)**. 관심사 enum이 1차(Product: 관심사 우선), 의미 유사도가 enum이 못 잡는 뉘앙스를 2차로.

**신뢰 경계:** 임베딩은 **순서만** 바꾼다 — 사실·가용성·가격·시간 불변. 테스트 `tests/test_semantic_rank.py`(9개, embed 모킹).

**결과 (동일 골든셋 9쿼리, before=`eval-baseline.json` / after=`eval-p2.json`):**
- recall@k·constraint 위반·empty: **변화 없음**(중심부 '쉬운' 쿼리는 before에도 적중 — 느슨한 기대값의 한계).
- **정성 증거(강함):** "quiet art exhibitions, indoor" → 반환 4개가 **전부 미술관/갤러리**(Daelim Museum·Seoul Museum of Craft Art·K.O.N.G·PKM Gallery). "lively festivals and performances" → 국악축제·광화문·세종로공원 등 공연/축제 계열. 거리순이면 섞이던 궁·공원이 **의도에 맞게 선발**됨. trace `semantic_rank`로 18개 재정렬 확인.
- **트레이드오프(정직):** mean fits_ratio **47%→36%**. 갤러리·축제가 궁보다 **운영시간 공식데이터가 불확실**해 check_needed 비중↑. 검색 품질 저하가 아니라 '관련도 우선이 미확인-운영시간 장소를 더 올린' 결과이며, 상태 배지로 투명 표기(신뢰 경계 유지).
- 회귀 가드로 의미 민감 쿼리 `a-gbg-quiet-galleries`(expect gallery/museum/art) 추가 → P2 적용 상태에서 적중(recall n=4).

**남은 한계:** P2는 **반경 1500m 안에서만** 재정렬한다(L1·L5 미해소). "넓게 조회→의미 top-K만 상세조회"의 전반부(반경 확대)는 **P1**에, 반경 밖 recall은 P1+P3에 달림. 또 목록 단계 텍스트가 얇아(overview 없음) 유사도 상한이 낮다(top cosine ~0.3–0.44) — 추후 1차 목록 필드 보강 여지.

### P3. 세분 tool을 실제 배선 — "진짜 agentic retrieval" (L4 구조 해소)
§3.3의 `search_experiences(radius)` / `check_availability` / `plan_day_route`를 LLM 루프에 **실제 노출**하고, 관측에 개수뿐 아니라 "반경·관심사 매칭 수"를 포함시킨다. 그러면 루프가:
```
search(1500) → check → "fits가 1개뿐" 관측 → search(3000) 재시도 → check → compose
```
를 **스스로 조립**한다. LLM은 여전히 **파라미터(반경·완화 여부) 선택만**, 사실은 코드. 단 비용/지연 상한(스텝·반경 상한) 가드 필수. — P1을 코드로 먼저 넣고, 여유 될 때 P3로 승격하는 2단계 접근 권장.

### P4. TourAPI keyword 검색 병용 (L2·L6 보강) — **구현됨 (2026-10-09)**
좌표검색(`location_based`, 타입·근접순 10건)이 놓치는 **특정 주제** 후보를 `searchKeyword2`로 보강해 recall↑. 기존 병합·dedup 경로 재사용.

**구현:**
- `note_parser`: `ParsedConditions.keywords` 신설 — 사용자가 말한 **구체적 검색어**(활동·공예·랜드마크·주제, 영어 명사. 예 'hanok', 'ceramics', 'Bukchon')를 vibe 형용사(open_preferences)·enum과 분리 추출.
- `tourapi.search_keyword(keyword, content_type_id)` — searchKeyword2. 좌표 미입력이라 dist 없음 → 호출부가 mapx/mapy로 haversine·반경 후필터(임의 좌표 금지).
- `orchestrator._fetch_keyword_pool`(용어 상위 3개 × 문화타입 병렬, 비문화 제외·반경 후필터·거리 태깅) + `_augment_with_keywords`(contentid 중복 제외 후 기존 풀에 병합 → `dedup_cross_source` → 거리순). **발견 범위만 확장 — 사실·판정 불변.** recommend_a·recommend_route 모두 cond 확정 후 1단계 풀에 적용. graceful. 테스트 `tests/test_keyword_search.py`(5개).

**결과 (라이브):** 명동 "hanok village or traditional houses" → `keywords=['hanok village']` → 키워드 검색이 **Namsangol Hanok Village** 발견·병합(pool 17→18) → 최상단 fits 노출(coord+type 상위 8건이 놓칠 수 있던 특정 결과). 회귀 가드 골든쿼리 `a-myeongdong-hanok-keyword`(expect 'hanok') 적중, eval 13q recall 유지. `docs/eval-p4.json`.

**한계(정직):** EngService2(영문)는 제목이 고유명사 위주라 **일반 개념어 커버리지가 고르지 않다** — 'hanok'/'museum'/'gallery'/'temple'은 매칭되나 'calligraphy'는 0건(영문 데이터에 해당 제목 없음). 즉 키워드가 **영문 TourAPI 제목에 존재할 때만** 효과. 한국어 소스(서울문화포털) 키워드 검색이나 유의어 확장은 추후 여지.

### P5. classify_places를 selection 신호로 승격 (L3, P2의 경량 대안)
P2가 과하면, 최소한 pool을 키운 뒤 `fits_vibe`/실내외로 **top-K 선발**에 쓰도록 순서를 바꾼다(지금은 생존 후보 rerank에만). LLM 1콜로 정성 선호를 selection에 반영. 단 상세조회 비용(L5)과 함께 설계.

### P6. 관심사 표현력 확장 (L6)
enum을 유지하되 open_preferences를 semantic 매칭(P2)의 1급 입력으로 승격. enum↔유형 맵은 eval(P0)로 오분류 케이스를 찾아 보정.

**권장 로드맵:** `P0(측정) → P2(semantic rerank) + P1(완화 ladder) → P3(agentic 배선) → P4~P6`.
P0는 선행 필수, P2는 보유 인프라로 가장 빠르게 recall을 올리는 레버, P1은 0건·빈약 결과를 즉시 개선한다.

---

## 8. 부록 — 파일·상수 레퍼런스

| 항목 | 위치 |
|---|---|
| Agentic 루프 | `agent/agent_loop.py` (`run_chat_loop`, `_MAX_STEPS=6`, `_LOOP_TOOLS`) |
| 단일 라우팅 fallback | `agent/chat_agent.py` (`run_chat`, `dispatch_tool`) |
| 추천 A | `agent/orchestrator.py` (`recommend_a`); 반경/풀 상수 `:66-69` |
| 추천 B | `agent/route_orchestrator.py` (`recommend_route`, `_ROUTE_POOL=12 :50`) |
| LLM 바인딩 tool 3종 | `agent/tools/schemas.py` |
| 미배선 세분 tool | `agent/tools/experiences.py`, `agent/tools/route.py` |
| note 구조화 | `agent/note_parser.py` |
| per-candidate 분류 | `agent/classify.py` |
| 멀티소스 조회·병합 | `agent/orchestrator.py` `_fetch_pool/_fetch_tour_pool/_fetch_seoul_pool` |
| 판정(가용성) | `agent/orchestrator.py` `_judge_record` + `domain/{operational,timing,budget,status}.py` |
| 랭킹 | `domain/ranking.py` (`display_sort_key`, `type_preference_rank`, `io_rank`) |
| 큐레이션 blacklist | `domain/curation.py` |
| 모델/토글 | `config.py` (`agent_loop`, `orchestrator_model=gpt-4o-mini`, `openai_model=gpt-4o`) |

> 메모: 코드 주석이 참조하는 `docs/agent-architecture.md`(§6.x)는 현재 저장소에 실재하지 않는다(planning 저장소 또는 미작성). 본 문서가 그 공백의 일부(추천/검색 관점)를 대신한다.

---

## 9. 남은 작업 — 다음 세션 백로그 (핸드오프)

> **이 섹션만 읽으면 이어서 작업 가능.** 전체 맥락은 §6(한계 L1~L7)·§7(P0~P6)을 필요한 항목만 Grep.
> **모든 before/after 측정은** `cd backend && python -m app.eval.run_eval --json ../docs/eval-<name>.json` (키 필요·라이브·무캐싱). 순수 지표 로직은 `app/eval/metrics.py`(유닛테스트됨).

### 완료 상태 (2026-10-09, 브랜치 머지됨 → main)
| 작업 | 상태 | 해소한 한계 |
|---|---|---|
| P0 eval 하네스 | ✅ `app/eval/` | 측정 기반 |
| P2 의미 재정렬(selection 전) | ✅ `agent/semantic_rank.py` | L2·L3 |
| P1 적응형 반경 ladder | ✅ `orchestrator.collect_judged`/`_RADIUS_LADDER` | L1·L4(부분) |
| 거리 라벨(확대 후보) | ✅ `Candidate.distance_m/from_widened_search`, `result-card.js` | 투명성 |
| P4 키워드 검색 | ✅ `tourapi.search_keyword`, `orchestrator._fetch_keyword_pool/_augment_with_keywords` | L2·L6(부분) |

### 남은 작업 (우선순위순 — 임팩트/작업량)

**① 응답 속도 (L5) — 미해결·체감 최대·★최우선** (임팩트 高 / 작업량 中)
- 문제: eval p95 **~10–26s**. 원인 = `pool[:_ENRICH_POOL=8]` **전부** 상세조회(후보당 TourAPI 3콜+Places 1콜) + per-candidate LLM. 캐싱은 ToS로 금지([[no-response-caching]]).
- 방향: P2 의미점수(`semantic_similarities`)로 **상위 K개만 상세조회**하도록 `_rerank_and_judge`에서 enrich 대상을 줄이거나, 목록 단계에서 1차 컷 후 상세조회. 지연↔recall 트레이드오프를 eval로 튜닝.
- 착수점: `orchestrator._rerank_and_judge`(상세조회 batch 결정 지점), `_fetch_and_normalize`(후보당 4콜).

**② 한국어 소스·유의어 (L7 + P4 영문 한계) ** (임팩트 中 / 작업량 中)
- 문제: P4가 영문 EngService2라 'calligraphy' 등 0건(§7 P4 한계). 외국인 영어 요구가 한국어 데이터에 안 닿음.
- 방향(택1/병행): (a) 서울문화포털 키워드 검색 추가(한국어 제목 매칭), (b) `keywords`를 유의어/한국어로 확장(예 calligraphy→서예) 후 검색.
- 착수점: `sources/seoulculture.py`, `agent/note_parser.py`(keywords), `orchestrator._fetch_keyword_pool`.

**③ P1 완화 ladder 확장** (임팩트 中 / 작업량 小)
- 지금은 '반경'만 확대. 반경 상한(5000m)에도 결과 부족하면 **시간창·관심사 strictness 완화** 단계 추가(각 단계 `notices` 투명 고지 — 기존 패턴 재사용).
- 착수점: `orchestrator.collect_judged`(ladder 루프), `_RADIUS_LADDER` 근처에 완화 단계 정의.

**④ P2 유사도 신호 강화** (임팩트 中 / 작업량 小)
- 목록 단계 텍스트가 얇아 top cosine ~0.3–0.44(§7 P2 한계). 1차 목록 필드(cat 라벨·요약) 보강 또는 경량 overview로 `pool_item_text` 강화 → selection 정확도↑.
- 착수점: `agent/semantic_rank.py` `pool_item_text`.

**⑤ 골든셋 확충 (P0 후속)** (임팩트 低·측정용 / 작업량 小)
- recall 모수 작음(13쿼리 중 기대값 5). 외곽·희소·까다로운 기대값 쿼리 추가로 개선 민감도↑.
- 착수점: `app/eval/golden_set.json`(Product도 편집 가능).

**⑥ P3 LLM 주도 재검색 — 보류 권장** (임팩트 低(지금) / 작업량 大)
- 미배선 세분 tool(`agent/tools/experiences.py`·`route.py`)을 LLM 루프에 연결. 단 핵심(결과 부족→확대)은 **P1이 이미 코드로** 처리 → 현 시점 한계이득. 시간창/관심사까지 LLM이 고르게 할 가치가 생기면 재검토.

### 공통 불변(모든 작업에서 유지 — [[working-style]] §6)
LLM/임베딩은 **순서·발견·설명만**; 가격·시간·가용성·좌표는 코드·공식데이터 소유. 완화·확대는 항상 `notices` 투명 고지. 강제 채움 금지(유효 후보만). 변경은 eval before/after로 검증 + 테스트.

---

## 10. 챗 동작 수정 (2026-10-09, 멀티인텐트·위치·충돌)

사용자 테스트에서 드러난 챗 UX 3건 수정(추천 로직이 아니라 **챗 라우팅/입력처리** 계층):

1. **멀티 인텐트 — `AGENT_LOOP` 기본 True** (`config.py`). off(단일 라우팅 `run_chat`)는 tool 하나만 불러 "루트 짜줘 **+** 팁 필요해?"의 2번째 의도(FAQ)를 버렸다. 루프는 `_present`가 추천+루트+답변을 **모두** 싣는다(`fed55ee`). 비용: 멀티 인텐트 턴은 단발 대비 ~2배 지연(메모 참고).
2. **프롬프트 위치 우선 (A·B 모두)** — "I am at Myeongdong"처럼 프롬프트에 직접 밝힌 지명을 기본입력(앱 폼/컨텍스트)보다 우선. `domain/locations.detect_location_in_text`(결정론 — `_QUICK_COORDS` 테이블 매칭, 좌표 생성 아님; 미등록 지명은 None→기본입력 폴백). **두 지점에서 적용**: (a) 챗 루프 `_run_recommend_or_route`는 **원본 메시지**에서 감지, (b) `recommend_a`·`recommend_route`는 **`ctx.note`**에서 감지 → **폼 경로의 A/B도** 프롬프트 위치가 우선된다. 정밀 지오코딩은 미구현(테이블 밖은 폴백). **시간(time) 프롬프트 우선은 미구현** — 자유텍스트 시간 파싱은 신뢰경계(§6.3 임의 시간 생성 금지)상 별도 설계 필요(아래 §11).
3. **입력 충돌 처리** — "indoor" + 궁궐/축제(실외) 모순을 조용히 해소하지 않는다.
   - **챗(루프)**: `CLARIFY`로 **되묻기**(`conflict_message`). 이미 물었으면(히스토리 마커) 재질문 안 함. 2-LLM 추출 편차로 orchestrator가 `preferences`에서 "indoor"를 누락하면 그 턴엔 생략될 수 있음. 클래리파이는 같은 턴 tip 답변을 함께 싣지 않음(다음 턴 해소).
   - **폼/즉시추천(`recommend_a`·`recommend_route`)**: 되묻지 않는 경로이므로 **투명 notice**(`conflict_notice`, Option 1)로 "왜 이런 결과인지" 알림. 양쪽 모두 `domain/conflict.io_interest_conflict` 재사용 — 신뢰/투명 기준을 경로 간 일치.

대화 기억(5턴): **DB 불필요** — 프론트가 `history`를 매 턴 전송(서버 stateless), 백엔드 `to_lc_messages`가 최근 10메시지(≈5턴) 사용. 장기 선호만 Supabase. 테스트: `test_conflict.py`·`test_locations.py`·`test_loop_conflict_location.py`.

> fallback `chat_agent.run_chat`(AGENT_LOOP off)에는 위 2·3이 미적용 — 루프가 기본이라 방치. off로 돌리면 degraded.

## 11. 미구현 — 시간(time) 프롬프트 우선 (다음 작업)

위치처럼 **시간도 프롬프트가 기본입력보다 우선**해야 한다는 요구(2026-10-09). 위치는 완료(§10.2)지만 시간은 미착수 — 자유텍스트 시간은 위험·난이도가 더 크다:
- **신뢰경계(§6.3):** 근거 없는 시간값 생성 금지. 시간은 가용성 판정의 핵심 사실이라 LLM이 함부로 설정하면 안 됨.
- **모호성:** "this afternoon"은 구체 시각이 아님(오후=몇 시?). 상대·구어 표현 해석은 판단이 개입.
- **안전한 범위(제안):** 사용자가 **명시적 시각/구간**을 말한 경우만 override — 예 "from 2pm to 6pm", "until 5pm", "I have 3 hours". `note_parser`에 선택적 `start_time`/`end_time`/`duration_minutes` 추출 필드 추가 → **기본입력 날짜 + tz** 로 구체 datetime 합성(결정론), 모호 표현("afternoon")은 무시(override 안 함). 적용 지점: 챗 루프/`recommend_*`의 ctx 구성 전. `validate_available_time`로 경계 검증.
- 착수점: `agent/note_parser.py`(필드), `agent/agent_loop.py` `_run_recommend_or_route`(ctx.start_at/end_at override), `domain/input_validation.py`.
