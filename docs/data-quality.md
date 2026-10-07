# 데이터 검색 품질 개선 — 조사·솔루션 로그

> **목적:** 추천(A) 결과의 사실 데이터(가격·운영시간) 품질을 올려 과도한 `check_needed`를 줄인다.
> **원칙(불변, CLAUDE §6):** 미확인을 긍정으로 바꾸지 않는다. 사실은 공식 데이터에서만. LLM은 생성이 아니라 **추출/해석**만.
> **정본 관계:** 판정 로직 `backend/app/domain/`, 신뢰 불변식 `CLAUDE.md §6`, 데이터 정책 `PRD.md §6`. 이 문서는 **조사 근거와 개선 순서**를 관리한다.
> **담당:** Tech · **시작:** 2026-10-07

---

## 1. 발견한 문제

추천 결과 대부분이 후보 3~4개 중 **3개가 `check_needed`, 1개만 `fits`** 로 나온다. 사용자 체감 품질이 낮다.

`fits`는 `domain/status.py` 에서 **시간 OPEN + 가격 확정 + 예산 OK** 를 **모두** 만족해야만 부여된다. 하나라도 미확인(UNCERTAIN/UNKNOWN)이면 `check_needed`. 따라서 가격·시간 중 하나라도 비거나 모호하면 바로 `check_needed`로 떨어진다.

**가설:** 판정 로직 문제가 아니라, **단일 소스(TourAPI `detailIntro2`)의 필드 커버리지 부족**이 원인일 것이다.

---

## 2. 실제 조사 결과 (실 TourAPI, 2026-10-07)

도심 5개 시작점(경복궁·인사동·시청·명동·DDP) 기준, 문화타입(76·78·85) 상위 후보 **49개**를 프로덕션과 동일한 함수(`normalize`·`judge_timing`·`judge_budget`·`resolve_status`)로 판정. note 없음(빈 조건 → 예산 OK 고정)으로 **순수 데이터 품질** 관점 측정.

| 지표 | 분포 |
|---|---|
| **최종 상태** | **check_needed 73%** · fits 20% · 제외 6% |
| 가격(price.status) | **unknown 65%** · free 24% · paid 10% |
| 시간(timing) | **uncertain 48%** · open 44% · closed 6% |
| 예산(budget) | ok 100% (빈 조건이므로) |

**`check_needed` 36건 원인 분해:**
- 가격 미확인 때문: **29건** ← 최대 단일 원인
- 시간 미확인 때문: 24건
- 둘 다: 17건 (→ 가격만 12 · 시간만 7)
- 시간 uncertain 세부: `caveat(계절/복수/문의)` 13 · `빈값` 5 · `파싱 실패` 5 · `숙박시간만` 1
- `usefee` 원문 **완전 빈값: 24/49 (49%)**

**해석:**
- 가격 미확인(65%)이 주범이며, 그중 ~75%는 `usefee` 필드가 **아예 비어있음** → 파서로는 못 고침, **다른 소스 필요**.
- 시간 uncertain의 ~75%(18/24)는 **필드는 있으나 자유텍스트**(caveat/파싱실패) → **파서(LLM 포함)로 구제 가능**.

### 2.1 결정적 발견 — `detailInfo2`가 빈 `usefee`를 구제한다

현재 미사용 엔드포인트 `detailInfo2`(반복 구조 행)를 탐침하니, `usefee`가 **빈 후보들**인데 **실제 요금이 들어있었다**(전부 공식 TourAPI 데이터):

```
Ssamzigil          Admission Fees: Free
Museum Kimchikan   Admission Fees: Adults 5,000 won / Teenagers 3,000 won / Children 2,000 won
Tapgol Park        Admission Fees: Free
Bosingak Belfry    Admission Fees: Free
The Sool Gallery   Admission Fees: Free
HIDE AND SEEK      Facility Utilization Fees: Mon-Fri 21,000won / Sat-Sun 26,000won
```

→ `detailInfo2`를 소스로 추가하면 **가격 unknown의 상당수를 free/paid로 확정 전환**할 수 있다(provenance=confirmed, 정책 위반 없음, LLM 불필요). 일부 운영시간 행도 존재.

### 2.2 현재 소스 연동 상태

| 소스 | 상태 |
|---|---|
| TourAPI `locationBasedList2`·`detailIntro2`·`detailCommon2` | ✅ 사용 중 |
| TourAPI **`detailInfo2`** | ❌ 미사용 (← 2.1 발견) |
| Google Places | 보조 `businessStatus`(폐업 신호) 전용 |
| Tmap | 도보 경로 전용 |
| **KOPIS · 서울문화포털** | ❌ 미연동 (키 슬롯·`.env.example`만 존재, 클라이언트 코드 없음) |
| 기상청(KMA) · AirKorea | ❌ 미연동 |

---

## 3. 솔루션 (방법별 평가)

핵심 구분: **"없는 사실을 생성" ❌  vs  "있는 공식 텍스트를 해석/확인을 쉽게" ✅**

| 방법 | 정책 | 효과 | 비고 |
|---|---|---|---|
| **`detailInfo2` 연동** (요금·시간 행 보강) | ✅ 공식 | **가격(주범) + 시간 일부** | 저위험·즉효, LLM 불필요 |
| **LLM normalize** (공식 원문 → 구조화 추출) | ✅ 추출 전용 | 시간 caveat/파싱실패·모호 요금 | temp 0·null 허용·추정 금지·trace |
| KOPIS/서울문화포털 연동 | ✅ 공식 | type 85(축제·공연) 날짜·가격 | **신규 연동**(별도 포털·스키마), 작업량 큼 |
| Places `regularOpeningHours` | ⚠️ 정책 밖 | 시간 보조 | **Product 결정 필요**, 공식 UNCERTAIN일 때만·별도 provenance |
| 가격 미확인 → 공식 링크 1탭 확인 UX | ✅ | check를 "실패"가 아닌 "확인 유도"로 | 병행 |
| Places `price_level`로 가격 채우기 | ❌ 금지 | — | 식당기준 버킷·추정 긍정 변환 |
| LLM/Places로 가격·시간 **생성** | ❌ 금지 | — | 불변식 §6.2 위반 |

---

## 4. 실행 로드맵 (데이터로 재검증된 순서)

- [x] **1단계 — 원인 집계** (2026-10-07): check 73%, 가격 미확인이 주범, `detailInfo2` 구제 가능 확인.
- [x] **2단계 — `detailInfo2` 연동** (2026-10-07) ✅
  - `sources/tourapi.py`: `detail_info(cid, ctype)` 추가(캐시·재시도 동일)
  - `domain/normalize.py`: `enrich_intro()` — `usefee`/`usetime`이 비면 detailInfo2 행("Admission Fees"/"운영시간")에서 보강(빈값→unknown 원칙·기존값 비덮어쓰기 유지)
  - `agent/orchestrator.py`: `_enrich`에서 intro/common과 **병렬**로 detail_info 조회 후 `enrich_intro` 적용
  - `pytest` 5개 추가(총 86 통과), ruff/black 통과
  - **라이브 재측정 (동일 49후보):** price unknown **65%→36%**, free 24%→48%, **fits 20%→30%**, **check_needed 73%→63%**. 공식 데이터만으로 달성(정책 위반 없음).
- [x] **3단계 — LLM normalize 스텝 (운영시간 추출)** (2026-10-07) ✅
  - `domain/timing.py`: `ExtractedHours`(LLM I/O 스키마) + `judge_extracted_hours()`(코드 판정) + `should_retry_hours_with_llm()` 게이트 + `operating_hours_text()`
  - `agent/hours_parser.py`: 공식 운영시간 자유텍스트 → 방문일 기준 구조화 **추출**(temp 0·structured output·추정 금지·graceful)
  - `agent/orchestrator.py`: regex가 "파싱불가/caveat"로 UNCERTAIN일 때만 LLM 재시도. **OPEN 승격만** — LLM 단독 Hard 제외(CLOSED) 없음(보수적, 오추출 방어)
  - `pytest` 9개 추가(총 93 통과), ruff/black 통과
  - **라이브 재측정 (동일 49후보):** check_needed **63%→42%**, **fits 30%→51%**. LLM 18건 호출(게이트된 subset) 중 12건 OPEN 승격
  - **환각 검증:** 승격 사례 전부 공식 텍스트에 근거(계절/요일 구간을 방문일 기준 정확 선택). 예: "March-October 09:00-18:00 / Nov-Feb 09:00-17:00" → 10월 방문 → 09:00-18:00
- [ ] **4단계 — KOPIS/서울문화포털 신규 연동**: type 85 보강 → 이후 Places 영업시간(Product 플래그)

### 누적 개선 (동일 49후보, 공식 데이터만)

| 단계 | check_needed | fits |
|---|---|---|
| baseline (detailIntro2만) | 73% | 20% |
| +detailInfo2 (2단계) | 63% | 30% |
| +LLM hours (3단계) | **42%** | **51%** |

---

## 5. 측정 방법 (재현)

`domain/` 함수를 그대로 import 해 실 TourAPI로 돌리고 price/timing/status 분포를 집계한다(원인 집계 스크립트 방식). 2단계 전후로 동일 좌표·동일 창으로 재측정해 **check_needed 감소**를 확인한다.
