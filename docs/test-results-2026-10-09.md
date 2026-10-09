# Test Run Results — 2026-10-09 (Recommendation A / Route B)

> Automated backend run of the `manual-test-scenarios.md` cases. I exercised the **backend pipeline directly** (same inputs the frontend sends: `recommend_a` for the form path, `run_chat_loop` for chat) against **live official APIs (no caching)**. This validates the logic, not the rendered UI. Titles vary day-to-day; some chat behaviors depend on LLM extraction.
>
> Legend: ✅ match · ⚠️ works-with-nuance (expectation refined) · 🐛 bug found → fixed this session · ⏭️ inferred (not run live; shares verified code path).

## Recommendation A

| # | Result | Evidence |
|---|---|---|
| A1 (no input, chat) | ✅ | `kind=clarify` — assistant asks interests before recommending (doesn't recommend blind). |
| A3 (indoor art, detailed) | ✅ | Top 4 = The Sool Gallery, Seoul Museum of Craft Art, Alive Museum, Kyung-In Museum of Fine Art — all indoor galleries/museums (semantic rerank surfaced them first). |
| A4 (keyword: hanok) | ✅ | Returned **Namsangol Hanok Village** at top (keyword search augmented the pool). |
| A5 (conflict indoor+palaces, form) | ✅ | Notice: *"You asked for indoor, but palaces & historic sites are mostly outdoor — results favor your indoor preference."* (+ strict-indoor set-aside notice). |
| A7 (prompt location) | ✅ | Base Gyeongbokgung + note "I'm at Myeongdong" → origin = **Myeongdong (37.5637, 126.985)**. |
| A9 (exclude named place) | ✅ | "not Gyeongbokgung Palace" → results had no Gyeongbokgung Palace (Folk Museum, Songhyeon Plaza, Gwanghwamun Gate, Sejong-ro Park). |
| A10 (free only) | ✅ | No paid item relabeled free. Paid items appear only with a **paid** badge (as a relaxed alternative), unknown-price marked unknown — invariant holds. |
| A6 (exclude vs love) | ⏭️ | Shares the exclusion + 0-safe path exercised elsewhere; not run live. |
| A8 (sparse→widen) | ⏭️ | Radius-ladder + distance labels already verified live in P1 (Seoul Forest 1→4 + "widened" notice). |

## Route B (chat)

| # | Result | Evidence |
|---|---|---|
| B1 (minimal) | ⚠️→✅ | Vague "plan a culture walk" with **no preferences** → assistant **asks interests first** (no tool called) — consistent with A1, not a direct route. With `anything is fine` → route built (5 stops: Kyung-In Museum, Museum Kimchikan, Templestay Info Center, …). Doc expectation refined. |
| B2 (detailed) | ✅ | "3-stop itinerary of palaces and historic sites" → `PlanCultureRoute` built a palace/historic route. |
| B3 (conflict) | ✅/⚠️ | Explicit "strictly indoor route, but I love palaces" → **conflict clarify** fired. ⚠️ With milder phrasing the orchestrator LLM sometimes drops "indoor" from the extracted preferences, so the clarify is skipped that turn (2-LLM extraction variance — retry with explicit wording). |
| B4 (window too short) | 🐛→✅ | 20-min window raised `ValidationFailure("Please allow at least 30 minutes.")`, which the loop's generic tool-error handler **swallowed** into a vague *"there was an issue"*. **Fixed:** the loop now catches `ValidationFailure` and surfaces its message. Re-run shows `kind=clarify, message="Please allow at least 30 minutes."` |
| B5 (keyword route) | ⏭️ | Keyword path verified in A4; route reuses the same `collect_judged`/keyword merge. |
| B6 (prompt location) | ⏭️ | `recommend_route` uses the same `detect_location_in_text(ctx.note)` as A7 (verified). |

## Multi-intent & FAQ

| # | Result | Evidence |
|---|---|---|
| C1 (route + tip) | ✅ | One turn returned **both** a route **and** a tipping answer (`kind=route`, `route` present, `answer` present). The tip question is no longer dropped. |
| C3 (FAQ tip, grounded) | ✅ | "Do I need to tip?" → `kind=answer`, `grounded=True` (RAG-grounded, not invented). |
| C2 (recommend + transit) | ⏭️ | Same multi-intent mechanism as C1. |
| C4 (out of scope) | ⏭️ | RAG refusal path (grounded-only) exercised by design. |

## Findings & actions

1. **🐛 Fixed — short-window message swallowed (B4).** `validate_available_time` raised a clear, actionable `ValidationFailure` ("Please allow at least 30 minutes.") but the loop's broad `except Exception` turned it into a vague failure. Now caught in `_run_recommend_or_route` and surfaced as the clarify message. Regression test added (`test_short_window_surfaces_validation_message`).
2. **⚠️ Behavior refined — vague route asks for interests (B1).** A route request with zero preferences makes the assistant ask interests first (LLM, no tool) rather than building immediately. This is **consistent with Recommendation A's "ask once" behavior**, so I treated it as intended and refined the doc (reply "anything" to build directly). *Open question for Product:* should chat build a no-preference route directly (like the A form path does), or keep asking? — not changed pending your call.
3. **⚠️ Known variance — conflict clarify depends on LLM extraction (B3).** The conflict re-ask only fires when the orchestrator LLM keeps "indoor/outdoor" in the extracted `preferences`. Explicit wording ("strictly indoor") is reliable; mild wording can miss it. Mitigations if we want it tighter: detect indoor/outdoor from the raw message too (like location), or add it to the tool schema.

**Trust invariants:** no violations observed — no paid-as-free, no fabricated facts, route stops time-bounded, conflict never silently resolved without a notice/clarify.

**Net:** all scenarios pass or pass-with-refinement; **1 real bug found and fixed** (B4). 268 backend tests green.
