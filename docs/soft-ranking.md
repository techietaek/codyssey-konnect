# Soft 랭킹 (관심사 선호/비선호) — 설계·로드맵

> **목적:** 사용자의 관심사 선호·비선호를 추천 **순서**에 반영한다.
> **불변(절대):** Soft Preference 는 **우선순위만 조정**한다(PRD §5.3). 개인화가 **사실/가용성을 덮지 않고**(FR-L5·CLAUDE §6.6), 비선호로 **Hard 제외하지 않는다**. 추출은 LLM, **판정·정렬은 코드**.
> **정본:** 정렬 로직 `backend/app/domain/ranking.py`, 상태 판정 `domain/status.py`. 담당 Tech.

---

## 1. 배경 — note 가 바꾸는 것 (현재)

note(Anything else) → `ParsedConditions`(LLM 추출). 추천에 미치는 실제 영향:

| 조건 | 영향 |
|---|---|
| `free_only`·`budget_krw` | 상태(fits/alternative/check) + 예산 Reason |
| `interests`(선호) | Reason 칩 + **표시 순서(A안)** |
| `avoid_interests`(비선호) | **표시 순서(A안)** — 강등만, 제외 아님 |
| `exclude_concepts`(명시 배제) | **배제(옵션3)** — LLM 의미분류로 매칭분 제거+대체, 0건-세이프. 랭킹 아님(`docs/agent-architecture.md`) |
| `indoor_outdoor`·`prefer_shorter_walks` | **현재 무효과** (날씨 Context/개인화 Phase에서 다룸) |

후보 **선발·순서의 1차 기준은 거리**다(현재). Soft 랭킹은 그 위에 얹는다.

---

## 2. A안 — 구현 완료 (2026-10-07, Tech 재량 범위)

같은 **상태 등급 안에서만** 관심사 선호/비선호로 순서를 조정. PRD §5.3 "Soft=우선순위 조정" 범위라 신규 FR 없이 진행.

- `ParsedConditions.avoid_interests` 추가 + `note_parser` 가 "싫다/원치 않음"을 추출(추정 금지, 선호와 중복 금지).
- `domain/ranking.py`: `TYPE_INTERESTS`(유형↔관심사 정본, reasons 와 공유) · `preference_rank`(0 선호 / 1 중립 / 2 비선호; 둘 다 걸리면 선호 우선) · `display_sort_key = (상태등급, 관심사순위)`.
- `orchestrator` 표시 정렬: 거리순 리스트를 `display_sort_key` 로 **안정 정렬** → 등급 우선 → 같은 등급 내 선호↑/비선호↓ → 같은 키 안에서 거리순 유지.
- 프론트: 확인 시트·결과·로딩 요약에 비선호 칩("Not: …") 노출(투명성·교정 가능).
- 테스트 `test_ranking.py`(+5), 전체 98 통과.
- **라이브 검증:** "I love art exhibitions" → fits 그룹 내 exhibition 이 historic 앞으로. 비선호 유형은 같은 등급 뒤로. **제외는 없음.**

### A안 경계(의도적 한계)
- 효과는 **같은 등급 내 순서**로 한정. top-4 **구성(선발)**은 여전히 거리 기준 — 관심사로 멀리 있는 후보를 끌어오지 않는다.
- 저장된 장기 Preference·Trip 미반영(비로그인 단건 note 만).

---

## 3. B안 — Phase 2/3 에서 정식화 (Product 동의 전제, 신규 FR)

A안을 **본격 Soft 스코어링**으로 승격. 저장된 Preference(FR-L3/L4)·Trip 과 정합하며, 후보 **선발·순위 산정**까지 관심사·이동 균형을 반영(FR-B4). A안 코드(`ranking.py`)가 그 토대 — 버리지 않고 확장.

**실행 시점:** **Phase 2(로그인·개인화)** + **Phase 3(B 문화루트)**. A 단독 선구현은 Preference 저장소·Trip 이 없어 반쪽이 되므로 하지 않는다.

### Product 가 못박아야 할 결정 (동의해도 별도 필요)
1. **선발 vs 순서** — 관심사 랭킹이 top-N **구성 자체**를 바꾸나(먼 관심사 장소가 가까운 비관심사 장소를 밀어냄), 아니면 **순서만** 바꾸나? 제품 핵심가치("개인화가 아니라 가능한 것 좁히기", PRD §15)와 충돌 주의.
2. **가중치** — 관심사 vs 거리의 상대 강도(과개인화 방지).
3. **불변식(동의해도 유지)** — 비선호 Hard 제외 금지(§6.6), 사실/가용성 보존(FR-L5), 강제 채움 금지(§6.5), Context 우선순위 Request>Trip>Preference.

### Product 결정 (2026-10-07, 확정)
1. **선발 vs 순서** → **선발까지 영향**. 2. **가중치** → **관심사 우선**(거리는 2차).
3. **불변식** → 유지. 방향: "무작정 가까운 것"이 아니라 **"원하는 콘텐츠 중 가까운 것을 자연스럽게"**.

### 체크리스트
- [x] A안 — 같은 등급 내 선호/비선호 tiebreak (2026-10-07)
- [x] B안-설계 — 결정 3건 확정(위) (2026-10-07)
- [x] **B안-구현 (2026-10-07)** — 표시 키 **(관심사순위 → 상태등급 → 거리)**, 관심사 우선. **선발 반영**: orchestrator 가 조회 풀(반경 1500m 내)을 관심사 우선 안정정렬 후 판정·선발 → 관심사 맞는 후보가 조금 멀어도 들어옴(과개인화는 반경으로 제한). 루트: 가능하면 관심사 매칭 스톱으로 구성, 2개 미만이면 전체 폴백. `domain/ranking`(type_preference_rank·display_sort_key) · `normalize.type_from_contenttype` · `orchestrator`·`route_orchestrator`. 149 pytest. 라이브: "I love art exhibitions" → top-4 전부 exhibition(선발 반영), 비선호·비관심사는 제외 아님(강등). **불변식 유지**: 상태·가격·시간 사실 불변, 비선호 Hard 제외 없음, 강제채움 없음.
- **경계(남음):** 유형 매핑이 조회단계 3유형(76/78/85)이라 hands_on/performance 세분 선발은 제한(상세단계 유형은 반영). 저장 Preference 는 merge 로 반영(Request>Trip>Preference 유지).
