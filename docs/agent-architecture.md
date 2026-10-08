# 추천 아키텍처 — Agentic 방향 & 선호 필터링 정밀도

> **목적:** 개방형 선호(예: "박물관 싫어")를 제대로 반영하기 위한 추천 엔진의 **목표 아키텍처(2b, Agentic)**와 거기까지의 **단계적 경로**, 그리고 반드시 지켜야 할 **신뢰 경계**를 기록한다.
> **상태:** 설계 메모(미구현). 결정·착수 시 이 문서를 갱신.
> **관련:** `docs/soft-ranking.md`(선호 랭킹 A안/B안), `docs/data-quality.md`(소스 보강), `CLAUDE.md §4·§6`, `PRD.md §5·§6`.
> **담당:** Tech · **작성:** 2026-10-07

---

## 1. 문제 — 선호 필터링의 정밀도 한계

"박물관을 싫어한다"고 해도 박물관이 추천되고, 심지어 `fits`로 뜬다. 원인:

1. **관심사 enum이 6개뿐** — "museum"은 enum에 없어 LLM이 `art_exhibitions`로 뭉개 매핑.
2. **공식 분류가 사용자 개념과 불일치** — TourAPI `contenttypeid`(76/78/85)·`cat3` 모두 "박물관"을 깨끗이 못 집음.
3. **A안(Soft 랭킹)은 등급 내 순서만** 바꿈 — 상태(fits)는 사실이라 개인화로 안 바뀌고, 제외도 안 함(§6.6).

### 실측 근거 (2026-10-07, Insadong)
`cat3`가 박물관을 세 코드로 흩뿌리고, 같은 코드에 비박물관이 섞인다 → **공식 taxonomy로는 개념 분류 불가**:
```
Museum Kimchikan   cat3=A02040800
Kyung-In Museum    cat3=A02060500
Seoul Craft Museum cat3=A02060100
Alive Museum       cat3=A02060100  ← 실제론 트릭아트(박물관 아님)
Sool Gallery       cat3=A02060300  ← 같은 코드에 한식공간·인권기록관 혼재
```

---

## 2. 옵션 평가

| 옵션 | 내용 | 평가 |
|---|---|---|
| **1. enum 다양화** | 관심사/카테고리 enum 세분화 | ❌ **source 한계.** 공식 분류가 개념과 안 맞아 박물관이 흩어지고 오분류 잔존. 관심사 6개는 Product 정의라 임의 확장도 불가. (title 키워드 매칭은 저렴하나 brittle.) |
| **2a. LLM 의미분류(후보 텍스트)** | 이미 가져온 후보의 title·overview·category를 LLM이 보고 "배제/기피 개념 매칭?" structured 태그 반환 | ✅ **지금 가능한 올바른 답.** 공식 데이터를 *해석*만, 사실 생성 없음. enum 없이 개방형 개념 처리. |
| **2b. LLM 검색 오케스트레이션** | LLM이 조건 해석→API 쿼리 구성→후보 재투입→최종 판단 | ⭐ **목표 아키텍처(아래 §3).** 강력하나 비결정성·비용·지연·PoC/trace 난이도↑, KOPIS·서울 미연동. |
| **3. 2a + 코드 판정·가드레일** | 사실은 코드, 개방형 선호 배제/강등만 LLM 의미분류 + 0건-세이프 + 확인시트 되돌리기 | ✅ **현 단계 권장 슬라이스.** 2b로 가는 디딤돌. |

---

## 3. 목표 아키텍처 (2b, Agentic) — 채택 방향

사용자가 합의한 목표 파이프라인:

```
[1] 사용자 입력(자연어)
      → [2] LLM 해석: 조건을 구조화(의도·선호·배제·제약)
      → [3] 구조화 정보로 필요한 API 호출: TourAPI(+detailInfo2) · KOPIS · 서울문화포털 …
      → [4] 후보군 + 각 후보의 설명/공식 텍스트(가격·시간·분류·overview)를 LLM에 전달
      → [5] LLM 최종 판단: 선호·배제·맥락으로 후보 선별/정렬 → 사용자에게 전달
```

### 신뢰 경계 (★ 2b에서도 절대 불변 — 미래의 우리를 위한 못)

목표가 "LLM 최종 판단"이어도, **사실은 끝까지 코드가 소유**한다:

- **[2] 구조화·[5] 최종 판단에서 LLM이 하는 일 = 의미/선호 매칭 + 선별 + 랭킹.** 가격·영업시간·휴무·예약·좌표·`fits`/`check` 같은 **사실·가용성은 LLM이 결정하지 않는다**(§6.2).
- **[4]로 넘기는 후보는 이미 코드가 판정한 fact 객체**(status·price·timing = 공식 데이터 기반). LLM은 그 위에서 **고르고 정렬**만.
- **[5] 출력의 표시 사실값은 LLM 산문이 아니라 코드 fact 객체에서** 렌더(LLM이 가격/시간을 다시 쓰지 못함). LLM은 "어떤 후보를, 어떤 순서로"만 돌려주고 코드가 fact와 재결합.
- **배제(exclude)는 명시적 사용자 지시에 한함**(PRD §5.3 "사용자가 명확히 지정한 제약") + **0건 세이프 폴백**(비면 강등+안내) + **확인 시트에서 되돌리기**.
- **trace 필수** — [2]~[5] 각 단계의 조회·판정·분기를 남겨 PoC/디버깅(NFR-08) 유지.

### 왜 단계적으로 가나 (리스크)
- 비결정성(재현·테스트 어려움), 비용·지연(요청당 다중 LLM 호출), **KOPIS·서울문화포털 미연동**(먼저 소스 연동 필요), PoC 증빙 난이도.
- → 전면 2b는 **Phase 3**(RAG·B 루트의 자연어 통합과 함께)로. 그 전에 사실-판정 코드와 소스를 탄탄히.

---

## 4. 단계적 경로

- [x] **옵션 3 (완료, 2026-10-07):** 개방형 배제를 LLM 의미분류로 처리(사실은 코드, 0건-세이프, 확인시트 되돌리기). `exclude_concepts`(개방형 명시 배제, enum 밖 포함) vs `avoid_interests`(enum 약한 기피) 분리.
  - **백엔드:** `models.ParsedConditions.exclude_concepts`·`RecommendData.notices` · `note_parser`(강·약 구분 프롬프트) · `agent/exclude_classifier.py`(후보 이름+overview 의미분류, structured·temp0·graceful) · `domain/exclusion.py`(선별·0건-세이프, 순수함수) · `orchestrator` [filter] 단계+trace(`exclude_filter`/`exclude_safe_fallback`). `test_exclusion.py`(+5), 125 pytest Green.
  - **프론트:** `confirm-sheet`(Without 칩 ✕ 되돌리기) · `results`/`condition-summary`(Without 칩) · `results` notices 배너(check amber).
  - **라이브 검증(Insadong):** "no museums" → Museum Kimchikan 외 2건 배제+대체(reorder 아님), exclude 비면 0건-세이프 유지+안내. 헤드리스 렌더/✕ 되돌리기 Green.
  - **경계(의도):** 선발이 아닌 '거리순 유효 후보 중 제거+대체'. 저장 Preference·Trip 미반영(단건 note). avoid(약한 기피)는 기존 A안 tiebreak 유지.
- [ ] **4단계(데이터):** KOPIS·서울문화포털 연동 — 2b의 [3] 멀티소스 전제 (`docs/data-quality.md` 4단계).
- [ ] **Phase 3(전면 2b):** LLM 검색 오케스트레이션 + 최종 판단. 위 신뢰 경계·trace 유지. RAG·B 자연어 흐름과 통합.
- [ ] **결정 필요(Product):** 선발 vs 순서 영향 범위 / 배제 정책 / 관심사 taxonomy 확장 여부(§soft-ranking B안과 공유).

---

## 5. 현재 코드와의 접점 (착수 시 재사용)
- `agent/orchestrator.py` — [3][4] 조회·조립 파이프라인 골격.
- `agent/note_parser.py`·`hours_parser.py` — [2] LLM 구조화/추출 패턴(structured output·temp 0·graceful·trace)의 선례.
- `domain/*`(status·timing·budget·normalize·ranking) — **[5] 이후에도 사실 판정의 정본**(LLM이 대체하지 않음).
- `sources/*` — [3] 멀티소스 클라이언트(TourAPI 완비, KOPIS·서울 신규 필요).

---

## 6. 전체 Agentic 설계 (챗 전체 · 2026-10-08 승인)

> **승인 범위:** 챗 전체(A 즉시추천 · B 문화루트 · FAQ)를 **하나의 agentic 루프**로. 오케스트레이션 LLM은 **상위 모델 허용**(gpt-4o-mini의 tool-calling 변동성 회피). 사실 판정 tool은 그대로 결정론 코드.
> **한 줄 목표:** "LLM을 통해 사용자의 조건·요청에 맞는 **최적의 문화 콘텐츠**를 제공한다." → 코드=가용성(참여 가능?) / **LLM=적합성(이 사용자에게 최적?) 선별**.

### 6.0 핵심 원칙 (불변 — 바꾸려면 Product 재조율)
1. **코드=사실/가용성, LLM=해석/선별.** 가격·운영시간·휴무·회차·좌표·예약은 **소스 공식 데이터 → 코드 정규화·판정**이 소유. LLM은 그 **fact 객체를 읽고** 어떤 소스를 조회할지·무엇이 적합한지·어떤 순서로 보여줄지만 결정. LLM은 사실을 **생성/뒤집지 않는다**.
2. **참여 가능한 것만 선별 입력.** LLM 최종 선별에는 **코드가 이미 가용성 판정(fits/check, Hard 제외)한 후보만** 들어간다. 가용성≠적합성.
3. **미확인≠긍정.** 멀티소스 어디서 와도 빈값/모호는 `unknown`(무료·예약불필요·이용가능으로 매핑 금지).
4. **표시 사실값은 코드 fact 객체에서 렌더** — LLM 산문이 가격/시간을 다시 쓰지 못함. LLM은 "어떤 후보를 어떤 순서로"만 반환, 코드가 fact와 재결합.
5. **루프 상한·graceful·trace.** 무한루프 방지(max steps), 한 tool/소스 실패가 전체를 막지 않음, 모든 step trace(NFR-08).

### 6.1 Agentic 루프 (while-loop tool-calling)
```
messages = [SYSTEM, *history, user(자연어)]
for step in range(MAX_STEPS):          # 상한(예: 6) — 무한루프·비용 방어
    ai = orchestrator_llm.bind_tools(TOOLS).invoke(messages)   # 상위 모델
    trace.step("agent_turn", step, tools=[c.name for c in ai.tool_calls])
    if not ai.tool_calls:              # 더 쓸 tool 없음 → 종료
        return finalize(messages, ai)  # 최종 응답(선별된 fact 후보 + 설명)
    results = await gather(run_tool(c) for c in ai.tool_calls)  # 병렬 실행
    messages += [ai, *tool_results]    # 결과를 다시 LLM에 투입(ReAct)
# 상한 도달 → 지금까지의 best 후보로 graceful 종료
```
- **종료 조건:** LLM이 tool_call 없이 최종 답을 낼 때(= "더 쓸 도구 없음"). 사용자 요청 충족.
- **표시:** 최종 후보 id·순서는 LLM, **사실값은 코드가 보관한 Candidate에서 렌더**(id로 재결합).
- LangChain 수동 루프(LangGraph 금지, CLAUDE §2). tool-runner 패턴.

### 6.2 멀티소스 어댑터 (사실 정규화 — LLM 아님)
소스별 클라이언트 + `domain/normalize_{source}` → **공통 `Candidate`**(단일 지점). 이종 스키마·시간모델·지오를 코드가 흡수:

| 소스 | 질의 | 시간 모델 → 판정 | 지오 |
|---|---|---|---|
| **TourAPI**(76/78/85) | 위치기반(lat/lng+반경) | 일 운영시간·휴무 → `domain/timing` | 네이티브 좌표 |
| **서울문화포털**(행사) | 구·날짜 | **행사기간**(오늘 ∈ 기간? +시간) → 기간 판정 | LAT/LOT → 거리 후필터 |

> **KOPIS 제외(2026-10-08, §6.10).** 레이트 제한(10/s·공유IP)·지오 부적합·커버리지 중복으로 멀티소스에서 뺀다. 멀티소스 = TourAPI + 서울문화포털.

- 둘 다 **동일 3상태(fits/check/Hard제외)로 수렴** → 하위 선별·루트 로직은 소스 불문.
- **병합·dedup**(제목+좌표 근접), **부분실패 허용**.
- **언어:** TourAPI=영문, 서울=국문 → 제목 그대로(장소명). LLM 번역은 옵션.
- `Candidate`에 최소 추가: `source`(출처 배지). (`schedule` 고정행사 필드는 KOPIS 전용이라 제외와 함께 폐기 — 서울 행사는 기간만 판정.)

### 6.3 툴 계약 (초안 — 사실/의미 소유 명시)
| tool | 입력 | 하는 일 | 소유 |
|---|---|---|---|
| `structure_request` | user NL, history | 조건 구조화(관심사·배제·시간창·실내외·예산·요청유형) | **LLM** 해석 |
| `search_experiences` | area/coords, when, intent, source?("auto") | 의도별 소스 선택·병렬 조회 → 정규화 Candidate 풀 | **코드**(공식) |
| `classify_places` | [cand.text] | per-place 실내/외·카테고리 의미태그(park→outdoor, museum→indoor) | **LLM** 해석 |
| `check_availability` | cands, time window | 운영/휴무/회차/기간·폐업 → fits/check/Hard제외 | **코드**(공식) |
| `check_budget` | cands, budget | 예산 상태(일반가 기준) | **코드** |
| `walk_route` | origin, stops | Tmap 도보 거리/시간/경로 | **코드** |
| `answer_knowledge` | query | RAG 근거내 답변(FAQ) | 코드검색+LLM답(근거내) |
| `plan_day_route` | feasible cands, window | 하루 동선 조립(fit_count·스케줄) | **코드** |
| `finalize` | selected ids, order, reasons | 최종 선별 확정(사실은 코드 fact 재결합) | **LLM** 선택 |

- **FAQ·추천·루트가 한 툴셋**: LLM이 요청에 따라 조합(FAQ면 answer_knowledge, 지금 추천이면 search+classify+check+finalize, 하루면 +plan_day_route).
- 각 tool: structured I/O(Pydantic), graceful, trace. 사실 tool은 결정론 → **단위테스트 유지**.

### 6.4 신뢰 경계 매핑
- **가용성(참여 가능?)** = `search_experiences`+`check_availability` (코드·공식). LLM 선별 입력엔 이 통과분만.
- **적합성(이 사용자에게 최적?)** = `classify_places`+`finalize` (LLM). 단 **참여 가능 후보 내에서만** 고르고, 표시 사실은 코드 fact로 렌더.
- 그래서 "indoor only"·"not outdoor"·"조용한 곳" 같은 **개방형 적합성**은 LLM이 per-place로 처리(유형 휴리스틱 탈피 → 앞서 본 Tapgol/Kimchikan 오분류 해소).

### 6.5 trace · 테스트
- **trace:** `agent_turn`(step·선택tool), 각 tool 입·출력 요약, 종료사유. PoC 증빙(NFR-08) 자동 축적.
- **테스트:** 사실 tool(normalize·timing·budget·route·fit_count)은 결정론 → 단위테스트 유지·확장. 루프/LLM선별은 비결정 → trace 스냅샷 + 소수 e2e 스모크(게이트: 미확인 긍정매핑 없음·닫힌 곳 제외·사실 렌더).

### 6.6 점진 롤아웃 (안전하게)
1. **멀티소스 어댑터** 먼저: 서울문화포털 클라이언트 + 정규화 + 병합/dedup(기존 추천 파이프라인에 투입, agentic 아직 아님). 사실 레이어 탄탄히. (KOPIS는 제외 — §6.10.)
2. **툴 래핑**: 기존 `orchestrator`·`domain/`·`rag/`를 위 tool 계약으로 노출(얇은 어댑터).
3. **Agentic 루프**: `agent/agent_loop.py`(while-loop) + 상위 모델 + `/api/chat` 교체(기존 단일 라우팅 → 루프). trace·max_steps.
4. **classify_places(실내/외·적합성)** + finalize 선별을 루프에 투입 → 3대 품질 이슈 해소.
5. 검증·튜닝(프롬프트·상한·비용/지연 측정) → 기존 결정론 경로는 fallback으로 유지.

### 6.7 결정 대기 (Product/Tech)
- **오케스트레이션 모델**: 상위 모델 허용됨 → 구체 모델/비용 상한(예: gpt-4o vs gpt-4o-mini 혼용 — 라우팅=상위, 보조추출=mini).
- ~~**KOPIS 지오**~~: **해소** — KOPIS 제외로 종결(§6.10).
- **"only/not" = 제외 강도**: 명시 배제어는 Hard 제외(정확 판정 전제), 약한 선호는 Soft — 경계 copy 확정.
- **언어**: 서울 국문 제목 그대로 vs LLM 번역(비용).
- **응답 지연 허용치**: 루프 다중 LLM+멀티소스 → 목표 p50/p95(로딩 UX와 함께).

### 6.8 현재 코드 재사용
- `orchestrator`·`route_orchestrator` → `search_experiences`·`check_availability`·`plan_day_route` tool로 분해/노출.
- `domain/{normalize,timing,budget,status,route,ranking,exclusion}` → 사실 tool 내부(정본 유지).
- `agent/{note_parser,hours_parser,exclude_classifier}` → `structure_request`·`classify_places`의 선례/부품.
- `rag/retrieve` → `answer_knowledge` tool.
- `sources/{tourapi,tmap,gplaces,kma,airkorea}` 재사용 + `sources/seoulculture` 신규. (KOPIS 제외 — §6.10.)

### 6.9 피드백 반영 (2026-10-08 승인)
- **(a) 끝난 콘텐츠 Hard 제외** — 날짜형(행사기간)은 **종료일 지남/미개막**이면 제외. `check_availability`에 날짜형 종료 판정 추가(TourAPI 85 `eventenddate`·서울 `END_DATE`). 가용성=코드. (KOPIS `prfpdto`는 제외 — §6.10.)
- **(b) 모델 전부 gpt-4o** — `.env`·Render의 `OPENAI_MODEL=gpt-4o`(임베딩은 별개 유지). 비용↑(루프).
- ~~**(c) KOPIS 공연장 좌표 매번 조회**~~ — **폐기**(KOPIS 제외, §6.10).
- **(d) 영어 전용 + 표시 정형화** — 결과에 한국어 금지. `normalize_content_display` tool(LLM: 공식 원문 → **영문·정형 표시**). 단 **번역/정형은 '표시'만, 가격/시간 status·열림판정은 코드**(없는 값 생성 금지). TourAPI 지저분 텍스트(`[F1,F5:…]`·`16:00 session`)도 이 tool이 정형.
- **(e) Reason → 근거기반 카테고리 라벨** — 긴 문장("open when you can visit") 폐기, 짧은 색상 칩으로: `Free`·`Paid/Budget`·`Indoor`·`Outdoor`·`Fits time`·`Your interest`. **각 라벨은 사실 근거 있을 때만**(free=확인무료, time=확인열림, interest=말한 관심사, in/out=classify). 색은 tokens.css/DESIGN 정합으로 확정.
- **(f) 응답 지연 → 로딩 UX** — 루프 단계별 진행 문구.

### 6.10 결정 기록 — KOPIS 제외 (2026-10-08)

**결정:** 멀티소스에서 **KOPIS(공연예술통합전산망)를 제외**한다. 추천 파이프라인은 **TourAPI + 서울문화포털** 2소스로 간다. (어댑터/판정 코드는 구현·테스트까지 갔으나 **연결하지 않고 제거** — 1b 서울문화포털·캐싱 제거는 유지.)

**근거:**
1. **레이트 제한이 아키텍처와 충돌.** KOPIS는 **초당 10회 초과 시 서비스 중지**(IP 단위 페널티). 공연은 목록에 좌표·`mt10id`가 없어 **추천 1회당 ≈21호출**(목록 1 + 상세 N + 공연시설 좌표 N)이 강제된다. 배포(Render)는 **단일 IP를 전 사용자 공유** → 동시 사용자 몇 명만으로 합산 한도를 초과해 **IP 전체 중지** 위험. 라이브에서 facility 배치 400(스로틀) 간헐 재현 확인.
2. **커버리지 중복.** 공연·콘서트·뮤지컬은 **서울문화포털**(CODENAME 공연 계열)과 **TourAPI type 85**(축제/공연/행사)가 이미 포함. KOPIS 없이도 공연이 사라지지 않음.
3. **지오 부적합.** KOPIS는 위치 쿼리 파라미터가 없어 서울 전역 샘플→거리 후필터라 "지금 여기서 가능한" 핵심가치와 맞물림이 약함(공연은 목적지·티켓형).
4. **투자 대비 신뢰도.** 유일한 XML 소스 + 3단계 호출 + 전용 레이트 리미터 + 회차(`dtguidance`) 파싱(보수 판정상 대부분 check_needed) — 최다 코드로 최저 신뢰.

**영향·후속:**
- §6.2 멀티소스 표에서 KOPIS 행 삭제, §6.6-1은 서울문화포털만, §6.7 "KOPIS 지오" 결정항목 해소(제외로 종결), §6.9(a)의 날짜형 종료 판정은 TourAPI 85·서울 `END_DATE` 기준으로 유지(KOPIS `prfpdto` 제외), §6.9(c) KOPIS 좌표 조회 항목 폐기.
- **1d 병합/dedup**은 TourAPI + 서울문화포털 2소스 기준.
- `.env`의 `KOPIS_API_KEY` 슬롯은 남겨둬도 무방(미사용). 향후 공연 특화 요구가 생기면 **공연 의도일 때만 조회**(agentic 소스선택)로 재검토 가능 — 단 레이트/공유IP 문제 해결이 전제.
