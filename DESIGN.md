# DESIGN.md — KONNECT 디자인 시스템 / UI 구현 기준

> **역할:** UX/UI Figma를 개발(Vanilla HTML/CSS/JS)로 옮길 때 따르는 **디자인 토큰·컴포넌트·화면·상태 시각 규칙**.
> **정본:** 화면 구조·상태·필수 정보·Product 주석은 `planning/product/05-ux-handoff.md` + `reason-copy-dictionary.md`, 시각 디테일(색·타이포·간격·컴포넌트)은 **UX/UI Figma**가 정본.
> **Figma:** `Konnect-Design` · fileKey `YQCE7JXtvy0fP1pLTwnS7k` · 메인 페이지 `전체 흐름` (node `115:37`) — [열기](https://www.figma.com/design/YQCE7JXtvy0fP1pLTwnS7k/Konnect-Design?node-id=115-37&m=dev)
> **작성 기준일:** 2026-10-05 · 값은 Figma에서 직접 추출(변수 미사용 → raw style 기준).
> **범위 경계:** 토큰·컴포넌트 스펙·수치는 구현 기준이되, 최종 Interaction·Visual은 Figma 최신본을 우선한다. 충돌·갱신 시 Figma 기준으로 본 문서를 갱신한다.

---

## 1. 디자인 원칙 (신뢰 UX)

KONNECT의 UI는 "예쁘게 보여주기"가 아니라 **확인된 사실 / 계산·계획 / 미확인을 시각적으로 구분**하는 것이 1차 목표다(제1 원칙: 미확인 ≠ 무료/예약 불필요/이용 가능).

1. **3가지 결과 상태를 색으로 구분한다** — Fits(초록) / Check needed(앰버) / Alternative(인디고). 내부 용어(`Hard Constraint`, `추천 제외`, 내부 Fit명)는 화면에 노출하지 않는다.
2. **Fact · Reason · 미확인을 분리 렌더한다** — 상태 배지 / 추천 이유(0~2개, teal check) / 시간·가격·이동 Fact / 미확인 Flag(앰버 칩)를 각각 다른 영역·스타일로.
3. **provenance를 표기한다** — `confirmed`, `≈`(estimate/추정), `예정`(계획값)을 문구/기호로 구분. 임의 직선 경로·추정치를 사실처럼 그리지 않는다.
4. **AI 관여를 고지한다** — 결과 상단 `AI-assisted results · unconfirmed details marked` 고지를 제거하지 않는다.
5. **Mobile-first · 영어 우선** — 기준 프레임 **390px 폭**. 영문 UI, KR은 Reference.
6. **선택 ≠ 방문** — `Select experience`/`Go with this route`는 현재 선택 확정이지 방문·예약 완료가 아니다.

---

## 2. 디자인 토큰

> **값 정본은 `frontend/css/tokens.css`** (CSS Custom Properties). 이 섹션은 그 값의 의미·용도를 설명하는 참조다 — 코드에서는 하드코딩하지 말고 `var(--token)`을 쓴다. 값이 바뀌면 `tokens.css`를 먼저 고치고 이 표를 맞춘다.
> Figma에 변수(variables)는 정의돼 있지 않아 실제 스타일에서 역추출했다.

### 2.1 색상 (Color)

**Brand / Primary**
| 토큰 | 값 | 용도 |
|---|---|---|
| `--c-primary` | `#007385` | 브랜드 teal. 버튼·선택 테두리·핀·배지·링크·지도 경로선 |
| `--c-primary-ink` | `#1f6670` | teal 텍스트(추천 이유·walk time·보조) |
| `--c-primary-tint` | `#e3f1f3` | teal 연한 배경(선택된 칩, 비강조 버튼 bg) |
| `--c-primary-tint-2` | `#dff3e7` | (Fits 배지 bg와 유사한 연초록 계열) |

**Text / Surface / Border**
| 토큰 | 값 | 용도 |
|---|---|---|
| `--c-text` | `#1a2429` | 기본 텍스트·제목·Fact |
| `--c-text-muted` | `#6b787d` | 보조·placeholder·비활성 |
| `--c-surface` | `#ffffff` | 카드·시트·칩 배경 |
| `--c-bg` | `#f4f6f7` | 페이지 배경(지도·여백 톤, 근사치) |
| `--c-border` | `#dfe4e6` | 기본 테두리(칩·입력·구분선) |
| `--c-ink-pin` | `#2a2f45` | 지도 Start 핀(다크 ink, 근사치) |

**상태 시맨틱 (결과 상태 배지)**
| 상태 | 배지 bg | 배지 text | 의미(사용자-facing) |
|---|---|---|---|
| Fits | `#dff3e7` | `#2e7d4f` | `Fits your conditions` (조건 충족) |
| Check needed | `#fdf0d0` | `#a8660a` | `Check needed` (추가 확인 필요) |
| Alternative | `#e6e8f2` | `#454773` | `Alternative` (조건 완화 대안) |

**미확인 Flag 칩** (예: `Walk time needs checking`, `Price needs checking`, `Booking needs checking`, `Relaxed condition · Above your budget`)
| 토큰 | 값 |
|---|---|
| flag bg | `#fbf1de` |
| flag text | `#9a5b00` |

> 색 사용 규칙: **상태 배지는 후보당 1개(주 상태)**, 미확인 flag는 별도 영역에 복수 가능. Alternative tint(`#e6e8f2`)는 AI-notice 등 중립 안내 pill에도 사용.

### 2.2 타이포그래피 (Typography)

- **Font family:** `Inter` (웹폰트) → fallback `-apple-system, "Segoe UI", Roboto, sans-serif`. 한글 Reference 필요 시 `Pretendard` 등 fallback 추가(EN 우선).
- **Weight:** Bold 700 / Semibold 600 / Medium 500.

| 역할 | size / line-height | weight |
|---|---|---|
| 카드 제목 (experience title) | 16 / 1.25 | 700 |
| 결과 타이틀 (`3 experiences near…`) | ~16–17 | 700 |
| Meta (시간·가격·이동) | 13 / 1.25 | 600(Fact) · 500(≈추정) |
| 추천 이유 (reason) | 12 | 500 |
| 상태 배지 / flag / 보조 | 11 | 600 |
| 버튼 라벨 | 12 | 700 |
| 공식 링크 (`View official details ↗`) | 12 | 600 |
| 지도 핀 번호 | 10 | 700 |

### 2.3 간격 · 반경 · 그림자 · 레이아웃

**Radius**
| 토큰 | 값 | 용도 |
|---|---|---|
| `--r-card` | `18px` | 결과 카드·바텀시트 |
| `--r-md` | `14px` | 카드 내 이미지 |
| `--r-badge` | `10px` | 상태 배지 |
| `--r-flag` | `8px` | 미확인 flag 칩 |
| `--r-pill` | `20px` | 버튼(pill) |
| `--r-full` | `999px` | 예시 칩·태그·No 배지 |

**Shadow**
| 토큰 | 값 |
|---|---|
| `--shadow-card` | `0 4px 8px rgba(13,38,46,0.10)` |
| `--shadow-card-focus` | `0 4px 8px rgba(13,38,46,0.18)` |
| `--shadow-pin` | `0 2px 3px rgba(0,0,0,0.20)` |

**Spacing (카드 기준 추출)**
- 카드: padding `14`, 내부 섹션 gap `10`
- Head gap `12` · Info gap `4` · Reasons gap `3` · Reason(icon12 + gap5) · Flags gap `6` · Actions gap `8`
- 버튼 padding `9/14` · 배지 `3/8` · flag `4/8` · 예시칩 `8/12(gap4)`
- 공통 스텝 추천: `2 · 3 · 4 · 6 · 8 · 10 · 12 · 14 · 20`

**Layout**
- 기준 프레임: **390 × 844 (모바일)**. 카드 폭 `330`(좌우 여백 포함).
- 지도 핀(그림자)·바텀시트·바텀바 CTA는 safe-area 고려.

---

## 3. 핵심 컴포넌트 스펙

> Figma Components 섹션: `입력`(Field Row, Example Chip, Parsed Chip) · `결과 카드·핀`(Map Pin, Result Card v2) · `문화경험 유형 아이콘`(Experience Type Icon) · `B 입력`(Chat Message, Day Row, Day Chip, Route Stop, Walk Segment).

### 3.1 Result Card v2 (node `218:391`) — 결과/루트 카드
A 결과·B 루트 공통 카드. **24개 상태 조합** = `State(Fits/Check/Alternative) × Focus(Yes/No) × Route(Yes/No) × Confirmed(Yes/No)`.

구조(위→아래):
1. **Head** — 이미지(72px, 공식 이미지 있을 때만·`rounded 14`) + 번호 배지(좌상단, Focus 시 teal/흰숫자, 비focus 시 흰/teal숫자) · **State badge**(§2.1) + **제목**(16/700).
2. **Reasons (0–2)** — teal check(12px) + 이유 텍스트(12/500, `--c-primary-ink`). Reason Copy Dictionary v1.0 문구만, 후보당 0~2개.
3. **Meta (official · estimate)** — 시간·가격·이동. Fact는 600, 추정은 `≈`+500. 예: `16:00 session · Free · confirmed` · `≈12 min walk`.
4. **Unconfirmed flags** — 앰버 flag 칩 복수(§2.1). `Check`/`Alternative`에서 주로 노출.
5. **Actions** — 좌: `View official details ↗` / `Check booking or entry ↗`(teal, 복수 가능) · 우: **Select experience** 버튼.

상태별 시각:
- **Focus=Yes:** `border 2px #007385` + `--shadow-card-focus`. (둘러보는 중 — 스와이프·핀 탭)
- **Focus=No:** 테두리 없음 + `--shadow-card`.
- **Select 버튼:** `Fits` = teal bg / 흰 텍스트. `Check`/`Alternative` = `#e3f1f3` bg / teal 텍스트(비강조).
- **Confirmed=Yes:** 현재 선택 확정 상태(Current choice 배지 유지). 다시 스와이프해도 Confirmed 유지.

### 3.2 상태/정보 서브 요소
| 요소 | 스펙 |
|---|---|
| State badge | `radius 10`, `pad 3/8`, 11/600. 색은 §2.1 상태 시맨틱 |
| Reason row | check svg 12px + 12/500 `#1f6670`. 최대 2개 |
| Unconfirmed flag | `#fbf1de`/`#9a5b00`, `radius 8`, `pad 4/8`, 11/600 |
| Official link | `View official details ↗` 등, teal 12/600. 같은 URL 중복 CTA 금지 |

### 3.3 입력 컴포넌트
- **Example Chip** (`218:346`) — 자연어 입력창 아래 예시 칩. Default: 흰 bg/`#dfe4e6` 테두리/`+`/muted 텍스트. Added: `#e3f1f3` bg/teal 테두리/`✓`/teal 텍스트. `radius 999`, `pad 8/12`, 12/500~600.
- **Parsed Chip** (`218:353`) — AI가 자연어에서 구조화한 조건 칩(예: `+ Indoor · Under ₩20,000`). teal 계열, 수정 가능.
- **Field Row** (`218:327`) — 필수 입력 행(Where & when 등).
- **Conditions chip** (결과 상단) — 흰 pill `Chungmuro · 3:20–6:30 PM` + teal `Edit`. 출발점/시간 재설정 진입.
- **Section header + tag** — `Where & when (required)` / `Anything else (optional)` 섹션 헤더에 `required`/`optional` 태그.

### 3.4 지도 컴포넌트
- **Map Pin** (`218:382`) — 지도는 **Naver Map** 위 오버레이.
  - 비선택: 흰 bg, `2px #007385`, `radius 15`, `30px`, 가운데 = **유형 아이콘**, 우상단 번호 배지(teal).
  - 선택: teal bg, `3px` 흰 테두리, `radius 20`, `40px`, 흰 유형 아이콘, 우상단 흰 번호 배지.
  - B 루트 핀은 번호 핀 사용. Start 핀 = 다크 ink 원.
- **Experience Type Icon** (`218:3878`) — D-06 유형 아이콘. **개발 키 고정:** `hands_on` / `performance` / `exhibition` / `historic_visit` / `festival_event` / `default`(유형 미상). export 이름 `icon-type-{key}`. 모양이 바뀌어도 키는 고정.
- **Walk time 라벨** — teal pill `≈12 min walk`. **경로/거리/시간 provenance 3단계**(PRD §7): 경로선+시간/거리 → 핀+시간/거리+외부지도 → 핀+외부지도(`Route unavailable`). 임의 직선 금지.
- **외부 길찾기** — `Directions (external map)` = Google Maps 딥링크.

### 3.5 버튼 · 피드백
| 컴포넌트 | 스펙 |
|---|---|
| Primary 버튼(`Select experience`) | teal bg / 흰 텍스트 / `radius 20` / `pad 9/14` / 12/700 |
| Secondary 버튼(`Edit conditions`,`Find new options`) | 흰 bg / `#dfe4e6` 테두리 / teal 텍스트 / pill |
| CTA (Bottom bar, `Get started`,`See my route`) | 큰 teal pill. Disabled 상태 별도 |
| AI notice | 중립 pill(`#e6e8f2` 계열) + muted 텍스트 `AI-assisted results · unconfirmed details marked` |
| Toast (`current choice set`) | 아이콘 + 텍스트, 선택 확정 완료 피드백(LF-03 내 유지) |
| Page dots | 캐러셀 인디케이터, 활성 teal |
| Carousel | 결과 카드 가로 스와이프(포커스 변경) |

### 3.6 B(문화루트) 전용 컴포넌트
- **Chat Message** (`218:2513`) — Conversation-first 대화 버블(User ↔ KONNECT).
- **Day Row / Day Chip** (`218:2524`/`218:2550`) — 날짜 선택.
- **Route Stop** (`218:2563`) — 루트 내 장소(순서 번호·유형·시간·비용).
- **Walk Segment** (`218:2616`) — 구간 이동(도보 시간/거리, 미확인 구간 구분).

---

## 4. 화면 카탈로그 (Figma `전체 흐름` 기준)

> 섹션 = Figma section. LF 번호는 `05-ux-handoff` 매핑. 화면 분할·전환은 UX 재량, 번호는 요구 연결용.

### 00 · 메인 (LF-01) — section `222:1418`
- `W-0` 웰컴(첫 실행·선택) / `M-1` 처음 방문(비로그인) / `M-2` 재방문·현재 선택 있음(A 장소+미니 지도) / `M-3` 로그인·현재 루트 있음(B+미니 지도)·My Page 진입.

### 01 · A 즉시 추천 (LF-02·03) — section `222:1420`
- **입력(LF-02):** `2-0` 위치 권한 / `2-1` 기본(현재 위치·시각 기본값) / `2-2` 자연어 입력 중 / `2-3` 이해한 조건 확인·수정(모호값만) / `2-3b` 조건 못 찾음(그래도 진행) / `2-4` 위치 없음→직접 검색·종료시각 오류 / `2-5` 로딩 / `2-5b` 실패 / `2-6` 끝나는 시각(Done by) / `2-7` 시작 시각(Start) / `2-8` 출발점 변경(Start from).
- **결과+지도(LF-03):** `1-1~1-3` 포커스 스와이프 / `1-4` 후보 1개·이유 0개 / `1-5` 경로 데이터 없음 / `1-6` 최종 0건(LF-03-V1) / `1-7` Select→확정 toast / `1-8` 재스와이프·선택 유지.
- **로그인 흐름:** `L-1` 로그인 유도(overlay 시트·Continue with Google / Not now·Kept context) / `L-2` 로그인 후 같은 조건 새 추천 중 / `L-3` 새 추천 결과(흐름 유지).

### 02 · B 문화루트 (LF-04·05·08) — section `222:2093`
- **조건 설정(LF-04, Conversation-first):** `3-1` 첫 화면(안내+예시) / `3-2` 조건 채움+모호값만 질문 / `3-3` 조건 완성→`See my route` 활성 / `3-4` 로딩 / `3-5` 필수값 여러 개→묶음 질문 / `3-6` 반복 모호→직접 고르기 / `3-6b`·`3-7` 날짜 선택 시트 / `3-8` 미래 날짜→출발점 지정 / `3-9` 생성 실패.
- **결과(LF-05):** `5-1` 루트(3곳) / `5-2` 장소 빼기 확인 / `5-3` 재구성(2곳·총비용 확인 필요·Undo) / `5-4` 구성 실패→개별 제안 / `5-5` 시간 부족(구분) / `5-6` 재구성 실패→이전 루트 복귀.
- **지도·이동(LF-08):** `8-1` 루트 지도(구간 이동·확정 전) / `8-2` Go with this route→확정 / `8-3` 일부 구간 미확인(선 없음·외부 지도) / `8-1b`·`8-2b`·`8-2c` 재구성 루트 지도·확정·미확인 유지.

### 03 · 공통 (LF-06·09 · 가입 · My Page · 기존 일정) — section `222:2276`
- **현재 선택(LF-09):** `9-1` A 장소 / `9-2` B 루트 / `9-3` 새 선택이 기존 선택 교체(확인).
- **상세(LF-06):** `6-1` A 상세·Fits / `6-2` A 상세·Check needed(미확인 구체·출처 펼침) / `6-3` B 루트에서 진입(루트로 돌아가기).
- **온보딩(P-09):** `P9-1` 첫 Google 가입 직후 선호 설정(1회·Skip 가능).
- **My Page:** `MP-1` 계정·현재 선택·선호 / `MP-2` 선호 수정 / `MP-3` 선호 초기화 확인.
- **기존 일정(Context):** `E-1` 다음 고정 일정 간편 입력(시트) / `E-2` 전체 일정 펼침→AI 정리→모호값만 확인.

> `개발 참고 ·` 로 시작하는 프레임(A 입력·B 입력·B 결과 지도·유형 아이콘)은 Product/Tech 주석용 참고 보드다.

---

## 5. 상태 · 신뢰 시각 규칙 (구현 체크리스트)

1. **3 상태 배지**는 후보당 1개(주 상태). Fits/Check/Alternative 색을 §2.1대로.
2. **추천 이유 0~2개** — Reason Copy Dictionary v1.0 문구만. 0개면 이유 영역 생략(중립 안내는 Reason 아님). 내부 Fit명 노출 금지.
3. **미확인은 flag 칩**으로 구체 표기(`~ needs checking`). 미확인을 무료/예약 불필요/가능으로 바꾸지 않는다.
4. **provenance** — `confirmed`(확인) / `≈`(추정) / `예정`(계획값) / 미확인 구분. 계획 체류시간은 `예정`.
5. **경로 Fallback 3단계** — 임의 직선·추정 경로를 실제처럼 그리지 않는다(`Route unavailable` 상태 포함).
6. **AI 고지·선택≠방문** UI를 제거하지 않는다.
7. **조건 완화 대안**은 차이를 명시(`Above your budget` 등)하고 해당 조건에 충족 Reason을 붙이지 않는다.

---

## 6. 접근성 · 반응형 · i18n

- **반응형:** 390px 기준, 상대 단위·flex/grid. 지도·카드·바텀시트는 뷰포트 하단 safe-area 고려. 가로 스크롤 영역(예시 칩)만 가로 스크롤.
- **대비:** 상태 배지/flag는 bg-text 대비 확보(WCAG AA 지향). teal `#007385` on 흰 OK.
- **터치 타깃:** 버튼·핀·칩 최소 탭 영역 확보(핀 비선택 30px은 히트영역 확대 권장).
- **i18n:** 영어 우선. 긴 문구(추천 이유 최장 영문 ~51자) 줄바꿈·카드 높이 변동 대응. 내부 용어 비노출.
- **폰트 로딩:** Inter 웹폰트 self-host 또는 CSP 허용 호스트. FOUT 대비 system fallback.

---

## 7. 에셋

- **문화경험 유형 아이콘** — export 키 고정: `icon-type-hands_on` / `-performance` / `-exhibition` / `-historic_visit` / `-festival_event` / `-default`. SVG, 24px 기준(지도 핀 내 16~20px).
- **아이콘(check 등)** · **일러스트(Hero, Welcome, 로그인 시트)** 는 Figma export로 받아 `frontend/assets/`에 둔다. Figma MCP asset URL은 7일 만료 → 받아서 로컬 보관.
- **대표 이미지:** 공식 소스 우선(§PRD 6.7). 없으면 placeholder, Google Places는 보조 Fallback(정식 키).

---

## 8. 열린 항목 / 경계

- Figma에 **디자인 변수(토큰) 미정의** → 본 문서의 토큰을 코드 CSS 변수로 1차 구축하고, Figma에 변수가 추가되면 동기화.
- 페이지 배경(`--c-bg`)·Start 핀 ink 색은 스크린샷 기반 **근사치** → Figma 최신본으로 확정.
- 화면 수·분할·전환·최종 Microcopy·Visual 고도화는 **UX/UI(희영님)** 결정. 데이터 상태·경로 provenance·추천 이유 생성/억제는 **Tech** 구현.
- 본 문서와 Figma가 다르면 **Figma 최신본 우선**, 입력/출력·상태·신뢰·완료기준에 영향 주는 변경은 Product 재조율.
