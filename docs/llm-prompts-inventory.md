# LLM Prompts Inventory & Review

> Every place KONNECT sends a prompt to an LLM, the exact instruction text, the model, and a precision review. Use this to audit/tune prompts. Trust rule across all of them: **the LLM routes / extracts / matches / explains — it never generates facts** (price, hours, availability, coordinates); official APIs + `domain/` own facts.
> Models: `orchestrator_model` = `gpt-4o-mini` (aux), `openai_model` = `gpt-4o` (user-facing prose), embeddings = `text-embedding-3-small`.

## Inventory

| # | File · symbol | Model | Role |
|---|---|---|---|
| 1 | `agent/agent_loop.py` `_SYSTEM` | gpt-4o-mini | **Loop router** — pick tool(s) + pass user wording (default path) |
| 2 | `agent/chat_agent.py` `_SYSTEM` | gpt-4o | Single-routing **fallback** (only if `AGENT_LOOP` off) |
| 3 | `agent/tools/schemas.py` docstrings + field descriptions | — | Tool definitions the router (#1/#2) sees |
| 4 | `agent/note_parser.py` `_SYSTEM` + `ParsedConditions` fields | gpt-4o-mini | Free text → structured conditions |
| 5 | `agent/classify.py` `_PROMPT` + `PlaceVerdict` fields | gpt-4o-mini | Indoor/outdoor + qualitative fit (`fits_vibe`) |
| 6 | `agent/exclude_classifier.py` `_SYSTEM` | gpt-4o-mini | Open-ended exclusion semantic match |
| 7 | `agent/hours_parser.py` `_SYSTEM` | gpt-4o-mini | Operating-hours free text → structured |
| 8 | `rag/retrieve.py` `_SYSTEM` | gpt-4o | FAQ answer within retrieved context |
| — | `rag/embed.py` | text-embedding-3-small | RAG retrieval + semantic rerank (not a prompt) |

## Key text (trimmed to the instruction core)

- **#1 Loop router:** "…Use tools — never answer travel facts from your own knowledge. The tools own all facts; you only decide which tools to call and pass the user's own wording. You may call tools across several turns (answer a question AND find experiences). … Location and time come from the app context, never from you."
- **#2 Fallback:** "For any travel intent you MUST call exactly one tool … Pick: plan_culture_route / recommend_experiences / answer_travel_question …" (single-tool; this is why multi-intent needs the loop).
- **#3 Tool schemas:** each tool's docstring says when to use it; `preferences`/`query` fields say "the user's own words"; facts explicitly excluded. (See note in file: location-from-prompt is handled in code, not here — intentional.)
- **#4 note_parser:** "Extract ONLY what the traveler explicitly stated. Do NOT infer/guess. interests(enum) vs avoid_interests(mild) vs exclude_concepts(clear refusal) vs exclude_places(named place) vs keywords(searchable noun) vs open_preferences(vibe adjective). Indoor/outdoor goes ONLY in indoor_outdoor. Never invent prices/times/availability." + 3 worked examples.
- **#5 classify:** "Classify indoor/outdoor/unknown and judge fit — ONLY from name + official description, no outside knowledge. When unsure → unknown / keep fits_vibe true (never exclude on a guess)."
- **#6 exclude:** "Mark candidates that CLEARLY match the unwanted concept — judge by what the place is, not a title keyword ('Alive Museum' is trick-art, not a museum). When unsure, keep. Don't invent facts."
- **#7 hours:** "Extract ONLY what the text states for the visit date. If undeterminable → determinable=false. 24-hour HH:MM. No guessing."
- **#8 RAG:** "Answer using ONLY the context. If not present, say you don't have it — no guessing. Never state prices/hours/reservation details even if asked; defer to the official source."

## Review — strengths

- **Consistent trust framing** everywhere: "only what's stated", "don't invent", "when unsure keep/unknown". Matches the project's first principle.
- All structured via **Pydantic** (`with_structured_output`) + **graceful** failure (empty/None) + `temperature=0`.
- RAG is triple-guarded: similarity gate → grounded-only → explicit no-price rule → refusal fallback.

## Review — weaknesses & fixes applied (2026-10-09)

1. **Two-LLM signal loss (chat).** Chat runs message → [#1 router → `preferences` string] → [#4 note_parser → structured]. If #1 drops a signal (e.g. "indoor") while summarizing, #4 never sees it → conflict re-ask / indoor ranking silently fail. **Fixed:** `domain/text_signals.detect_indoor_outdoor` reads the **raw message** deterministically (handles negation like "no outdoor"); the loop back-fills `indoor_outdoor` when #4 left it null. (Location was already handled this way.)
2. **note_parser bucket confusion.** Six overlapping buckets risk misrouting (observed: "indoor" leaking into `open_preferences`). **Fixed:** explicit rule "indoor/outdoor goes ONLY in indoor_outdoor" + 3 worked examples added to #4.
3. **Schema wording looked contradictory** with prompt-location priority. **Fixed (doc):** comment in `schemas.py` clarifying the LLM is kept out of location on purpose; location-from-prompt is a deterministic code path (`detect_location_in_text`) — the two don't conflict.

## Remaining / optional (not changed)

- **Model split:** fallback (#2) uses gpt-4o while the live path (#1) uses mini; #2 rarely runs now (loop default). Could unify to mini or retire #2.
- **Zero-shot elsewhere:** only #4 has examples now. #5/#6 could get 1 example each if misclassification shows up in eval — weigh against token cost.
- **Determinism ceiling:** back-fill covers indoor/outdoor + location. If other signals (free_only, budget) show loss in testing, extend `text_signals` similarly or run #4 on the raw message instead of `preferences`.
