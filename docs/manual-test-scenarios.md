# KONNECT — Manual Test Scenarios (Recommendation A / Route B)

> Hand-run test script for the two core flows. Questions are written as a **foreign traveler** would type them (English). Each row lists the **setup**, the **expected behavior**, and **what to verify** (trust invariants).
> Behavior reflects the current build (agentic loop default ON, semantic rerank, adaptive radius, keyword search, conflict handling, prompt-location priority).

## How to run

- **Recommendation A** can be exercised two ways:
  - **Input form (LF-01):** type the question into the free-text **note** field → review the "what we understood" confirm sheet → Show.
  - **Chat:** type it as a message. The assistant picks the `recommend_experiences` path.
- **Route B** is exercised in **chat** only (type an itinerary/route request → `plan_culture_route`).
- **Location:** open the "Start from" sheet and pick a **Jongno-gu / Jung-gu** preset (now coordinate-backed): Gyeongbokgung, Gwanghwamun Square, Anguk·Insadong, Bukchon Hanok Village, Jonggak, Jongmyo Shrine, City Hall, Deoksugung, Myeongdong, Namsangol Hanok Village, Dongdaemun·DDP.
- **Time window (suggested):** start ≈ **1:00 PM**, end ≈ **6:00 PM** (a real ~5h afternoon so operating-hours/closing checks are meaningful). Use a date that is **today or near-future**.

> Note on variability: results come from **live official APIs with no caching**, so exact titles change day to day and some checks (e.g. a conflict re-ask) depend on the LLM capturing both signals — if a re-ask doesn't fire, retry with the wording made explicit.

---

## A — Recommendation A (individual experiences)

| # | Category | Question (type this) | Setup | Expected behavior | Verify |
|---|---|---|---|---|---|
| A1 | No input | *(form: leave note empty)* / chat: `What can I do around here?` | Gyeongbokgung | **Chat:** first a short **follow-up asking your interests** (palaces / art / hands-on / performances / festivals, or "anything"). **Form:** runs directly → up to **4** nearby cultural spots, nearest-first. | Chat asks once before recommending (no prefs yet). ≤4 cards. Each card has a status badge. |
| A2 | Sparse / vague | `anything cultural nearby, I'm not picky` | Insadong | Up to 4 nearby spots in distance order; no strong reranking. | ≤4 cards; sensible nearby mix (palace/museum/historic). |
| A3 | Detailed (aligned) | `I love art galleries and museums, I'd prefer indoor, and free if possible` | Anguk · Insadong | Galleries/museums surface **first** (semantic rerank). Confirm sheet shows understood chips: interests = art & exhibitions, indoor, free-only. Free/unknown-price items favored. | Top results are galleries/museums (not palaces). Chips match the note. Paid-only items not claimed as free. |
| A4 | Keyword-specific | `I want to see a hanok village or traditional houses` | Myeongdong | **Keyword search** augments the pool → a **hanok village** (e.g. Namsangol Hanok Village) appears near the top. | A hanok result shows up even though it isn't the nearest generic POI. |
| A5 | Conflict (indoor + outdoor interest) | `indoor only, but I really love palaces and historic sites` | Gyeongbokgung | **Chat:** a **re-ask** — "You asked for indoor, but palaces & historic sites are mostly outdoor — indoor only, the outdoor sights, or a mix?" **Form:** runs + shows a **notice** "…results favor your indoor preference." | The conflict is surfaced (question in chat, notice in form) — palaces are **not silently dropped without explanation**. |
| A6 | Conflict (exclude vs. love) | `show me temples, but skip anything religious` | Anguk · Insadong | Exclusion is applied; if it would empty the list, a **0-result-safe notice** explains nearby alternatives are shown instead. | No crash/empty with no message. If excluded, a notice appears; nothing religious that was explicitly excluded is force-shown. |
| A7 | Location in prompt | `suggest some museums — I'm actually over at Myeongdong now` | **Base = Gyeongbokgung** | The **prompt location wins**: origin pin + walking distances are computed from **Myeongdong**, not Gyeongbokgung. | Map origin = Myeongdong; distances/times are from Myeongdong. |
| A8 | Sparse area → widen | `any cultural spots near me` | Dongdaemun · DDP (or a quieter edge) | If fewer than ~2 viable nearby, the search **widens** → a notice "Few options were nearby, so we widened the search area to find more." Widened cards show a **"📍 X km away"** distance label. | Notice appears only when sparse; widened cards are labeled with distance; nearby cards are not. |
| A9 | Exclude a named place | `palaces and historic sites near me, but not Gyeongbokgung Palace` | Gyeongbokgung | Gyeongbokgung Palace is **removed** from results; other historic sites remain. | The named place is absent from the cards. |
| A10 | Budget | `free experiences only` | City Hall | Only free / unconfirmed-price items (never a paid item relabeled free). May return fewer than 4. | No paid item shown as "Free". Unconfirmed price is marked, not assumed free. |

---

## B — Route B (one day culture route — chat only)

| # | Category | Question (type this) | Setup | Expected behavior | Verify |
|---|---|---|---|---|---|
| B1 | Sparse / minimal | `plan me a culture walk this afternoon` | Insadong, 1–6 PM | **One route** of **2+ stops** in walking order (time-bounded, not padded). Each leg shows a **≈ min walk**; stops show visit times (official = confirmed, otherwise planned/estimate). | ≥2 stops; walking times present; no forced 3rd stop if time doesn't allow. |
| B2 | Detailed (aligned) | `a half-day route focused on palaces and traditional architecture` | Gyeongbokgung | Route of historic/palace stops (interest-first), within the window. | Stops skew to palaces/historic; order is walkable. |
| B3 | Conflict | `an indoor route, but I love temples and palaces` | Gyeongbokgung | **Re-ask** (same conflict prompt as A5) rather than silently building an indoor-only route. | Conflict surfaced before/with the route; palaces not silently dropped. |
| B4 | Too little time | `plan a walking route for me` | Myeongdong, **start 5:30 PM, end 6:00 PM** | **Unmet** message — "…don't fit your time window as one walking route — try a longer window or see individual experiences." | No route is forced into an impossible window; a clear fallback message appears. |
| B5 | Keyword route | `a route with a hanok village and some traditional crafts` | Bukchon Hanok Village | Keyword search feeds candidates; route includes a hanok/traditional stop if walkable. | Hanok/traditional stop present; route still walkable within window. |
| B6 | Location in prompt | `make me an afternoon route — I'm starting from City Hall` | **Base = Gyeongbokgung** | Route origin = **City Hall** (prompt wins); first leg starts there. | Origin/first stop anchored at City Hall. |

---

## C — Multi-intent & FAQ (chat)

| # | Category | Question (type this) | Setup | Expected behavior | Verify |
|---|---|---|---|---|---|
| C1 | Multi-intent (route + FAQ) | `Plan me an afternoon culture route near me, and do I need to tip?` | Insadong | **Both** are returned in one turn: a **route** *and* a **tipping answer** (tipping is not customary in Korea). | The tip question is **not dropped**; you see the route and the answer together. |
| C2 | Multi-intent (recommend + FAQ) | `What can I see nearby, and how does the T-money card work?` | Myeongdong | Recommendations **and** a transit/T-money answer together. | Both intents answered. |
| C3 | FAQ only (grounded) | `Do I need to tip at restaurants in Seoul?` | any | A short grounded answer (no tipping culture). If the knowledge base lacks it → "needs checking / official source," not a guess. | Answer is grounded or explicitly defers — never invented. |
| C4 | FAQ only (out of scope) | `What's the wifi password at this cafe?` | any | Politely cannot answer / asks to clarify; does **not** fabricate. | No fabricated facts. |

---

## Trust invariants — should NEVER happen (check across all tests)

- Unconfirmed/empty **price never shown as "Free"** (unknown is marked, not assumed).
- No **prices, hours, availability, or coordinates invented** by the assistant — only official data; unconfirmed details are labeled.
- **Closed-today / ended events** never appear in normal recommendations or routes.
- **Recommendation A ≤ 4 cards**; **Route B stops are time-bounded** (never padded to hit a number).
- **"Select" ≠ visited** — selecting an experience never implies check-in / GPS tracking.
- **Walking lines** on the map are real Tmap paths; if unavailable it says "Route unavailable" (no fake straight line).
- Every result set carries the **AI-assisted notice**; confirmed vs. unconfirmed is visually separated.
- Personalization/interests only **re-order or widen discovery** — they never override a hard fact or availability.

---

## Quick coverage matrix

| Category | A | B | C |
|---|---|---|---|
| No / minimal input | A1, A2 | B1 | — |
| Detailed | A3 | B2 | — |
| Keyword-specific | A4 | B5 | — |
| Conflict (indoor↔outdoor) | A5 | B3 | — |
| Exclude / budget | A6, A9, A10 | — | — |
| Prompt location priority | A7 | B6 | — |
| Sparse → radius widen | A8 | (shared pipeline) | — |
| Time infeasible | — | B4 | — |
| Multi-intent / FAQ | — | — | C1–C4 |
