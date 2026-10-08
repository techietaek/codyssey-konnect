// AG-4 · 단일 챗봇 — FAQ(RAG) · 즉시추천 · 문화루트를 하나의 대화 흐름으로.
// 자연어 → /api/chat(LLM tool-calling) → kind 별 렌더(answer/recommendation/route/clarify).
// 사실은 백엔드 코드 소유 — 여기서는 받은 fact 객체를 신뢰 분리해 '표시'만 한다.
import { postChat } from "../api.js";
import { openLocationSheet } from "../components/location-sheet.js";
import { openTimeSheet } from "../components/time-sheet.js";
import { renderResultCard } from "../components/result-card.js";
import { renderRouteCard } from "../components/route-card.js";
import { renderMap, renderRouteMap } from "../map.js";

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

function localValue(d) {
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 16);
}
function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

const SUGGESTIONS = [
  "Do I need to tip in Seoul?",
  "What can I do near me?",
  "Plan me a culture route for this afternoon",
];

// 에이전트가 생각하는 동안 보여줄 단계별 진행 문구(§6.9f). 실제 파이프라인 흐름을 반영하되
// 서버가 단계 이벤트를 스트리밍하진 않으므로 타이머로 순차 표시(끝 문구에서 멈춤).
const PROGRESS = [
  "Understanding your request…",
  "Searching official sources near you…",
  "Checking what's open and the details…",
  "Finding the best matches…",
  "Putting your results together…",
];
const PROGRESS_INTERVAL_MS = 1800;

export function renderChatView({ onBack }) {
  const root = el("section", "view chat");

  // ── Trip 맥락(추천·루트 tool 이 쓰는 사실). 기본 = 현재 위치·지금~+4h. 편집 가능. ──
  // 기본 종료 = 시작 + 4h, 단 '시작일 24:00까지'(백엔드 경계검증) → 같은 날 23:59로 clamp.
  function endForStart(startIso) {
    const s = new Date(startIso);
    const plus4 = new Date(s.getTime() + 4 * 3600 * 1000);
    const endOfDay = new Date(s);
    endOfDay.setHours(23, 59, 0, 0);
    return localValue(plus4 < endOfDay ? plus4 : endOfDay);
  }

  const now = new Date();
  now.setSeconds(0, 0);
  let locationLabel = "Current location";
  let geoCoords = null;
  let startValue = localValue(now);
  let endValue = endForStart(startValue);

  function tripContext() {
    const start_location = { label: locationLabel };
    if (geoCoords) Object.assign(start_location, geoCoords);
    return {
      start_location,
      start_at: `${startValue}:00`,
      end_at: `${endValue}:00`,
    };
  }

  // ── Header: 뒤로 + 타이틀 + 편집 가능한 Trip 칩(위치·시간) ──
  const header = el("div", "chat-header");
  const back = el("button", "icon-back", "←");
  back.type = "button";
  back.setAttribute("aria-label", "Back");
  if (onBack) back.addEventListener("click", onBack);
  const titleWrap = el("div", "chat-title-wrap");
  titleWrap.append(el("span", "chat-title", "KONNECT chat"));
  header.append(back, titleWrap);
  root.append(header);

  const tripBar = el("div", "chat-trip");
  const locChip = el("button", "trip-chip");
  locChip.type = "button";
  const startChip = el("button", "trip-chip");
  startChip.type = "button";
  const endChip = el("button", "trip-chip");
  endChip.type = "button";
  function refreshTrip() {
    locChip.textContent = `📍 ${locationLabel}`;
    startChip.textContent = `🕑 ${fmtTime(startValue)}`;
    endChip.textContent = `🏁 by ${fmtTime(endValue)}`;
  }
  locChip.addEventListener("click", () =>
    openLocationSheet({
      currentLabel: locationLabel,
      onPick: (label, coords) => {
        locationLabel = label;
        geoCoords = coords;
        refreshTrip();
      },
    }),
  );
  startChip.addEventListener("click", () =>
    openTimeSheet({
      kind: "start",
      startValue,
      endValue,
      onDone: (v) => {
        startValue = v;
        if (new Date(`${endValue}:00`) <= new Date(`${v}:00`))
          endValue = endForStart(v); // 종료가 시작 이하가 되면 재설정
        refreshTrip();
      },
    }),
  );
  endChip.addEventListener("click", () =>
    openTimeSheet({
      kind: "end",
      startValue,
      endValue,
      onDone: (v) => {
        endValue = v;
        refreshTrip();
      },
    }),
  );
  // "Plan a day" — 특정 시각까지가 아니라 오늘 전체(시작일 저녁까지)로 루트. 길이는 시간창이 정함.
  const planDayBtn = el("button", "chat-planday", "Plan a day");
  planDayBtn.type = "button";
  planDayBtn.addEventListener("click", () => {
    const d = new Date(`${startValue}:00`);
    d.setHours(21, 0, 0, 0); // 문화장소 운영 끝물까지 — 실제 길이는 백엔드 시간창 트림
    endValue = localValue(d);
    refreshTrip();
    send("Plan a culture route for the rest of today");
  });
  refreshTrip();
  tripBar.append(locChip, startChip, endChip, planDayBtn);
  root.append(tripBar);

  // AI 관여 고지(1회, NFR-05)
  root.append(
    el(
      "p",
      "chat-ai-notice",
      "AI-assisted · facts come from official sources, unconfirmed details are marked.",
    ),
  );

  // ── 대화 로그 ──
  const log = el("div", "chat-log");
  root.append(log);

  function scrollDown() {
    log.scrollTop = log.scrollHeight;
  }

  function bubble(side, node) {
    const row = el("div", `chat-row chat-row--${side}`);
    const b = el("div", `chat-bubble chat-bubble--${side}`);
    if (typeof node === "string") b.textContent = node;
    else b.append(node);
    row.append(b);
    log.append(row);
    scrollDown();
    return row;
  }

  // 넓은 결과(카드·루트)는 버블 밖 전체폭 블록으로
  function assistantBlock(node) {
    const row = el("div", "chat-row chat-row--assistant");
    const block = el("div", "chat-block");
    block.append(node);
    row.append(block);
    log.append(row);
    scrollDown();
  }

  function renderAnswer(ans) {
    const wrap = el("div");
    wrap.append(el("p", "chat-answer-text", ans.answer));
    if (ans.citations?.length) {
      const cites = el("div", "chat-cites");
      cites.append(el("span", "chat-cites-label", "Sources:"));
      for (const c of ans.citations)
        cites.append(el("span", "chat-cite", c.source));
      wrap.append(cites);
    }
    bubble("assistant", wrap);
  }

  // 환경 주의(PRD §6.6) — 악천후/대기질 나쁨일 때만. Context일 뿐, 운영 사실 아님.
  function envNotice(env) {
    if (!env?.adverse || !env.advisory) return;
    const n = el("div", "chat-weather");
    const glyph =
      env.precipitation === "snow"
        ? "❄️"
        : env.precipitation === "none"
          ? "😷"
          : "🌧";
    n.append(el("span", "chat-weather-icon", glyph), el("span", null, env.advisory));
    assistantBlock(n);
  }

  function renderRecommendation(data) {
    envNotice(data.environment);
    const cands = data.candidates ?? [];
    if (!cands.length) {
      bubble(
        "assistant",
        "I couldn't find experiences that fit those conditions right now. Try a different time or area.",
      );
      return;
    }
    bubble(
      "assistant",
      `Here ${cands.length > 1 ? "are" : "is"} ${cands.length} you could do near ${data.origin?.label ?? "you"}:`,
    );
    for (const n of data.notices ?? []) bubble("assistant", n);
    // 지도: 출발점 + 후보 핀. 카드보다 먼저.
    const mapEl = el("div", "chat-map");
    assistantBlock(mapEl);
    const list = el("div", "chat-cards");
    const cardById = {};
    cands.forEach((c, i) => {
      const card = renderResultCard(c, data.origin, i);
      card.dataset.id = c.id;
      cardById[c.id] = card;
      list.append(card);
    });
    assistantBlock(list);
    // 지도-카드 포커스 연결(추천 A처럼): 카드/핀 선택 → 그 후보의 Tmap 경로선 표시·전환.
    renderMap(mapEl, data.origin, cands)
      .then((ctrl) => {
        if (!ctrl) return;
        const focus = (id) => {
          for (const [cid, card] of Object.entries(cardById))
            card.classList.toggle("is-focused", cid === id);
          ctrl.focus(id); // 해당 후보의 실제 경로선 draw(없으면 핀만)
        };
        for (const c of cands)
          cardById[c.id].addEventListener("click", () => focus(c.id));
        ctrl.onPinClick(focus);
        focus(cands[0].id); // 초기: 첫 후보 경로 표시
      })
      .catch(() => mapEl.remove());
  }

  function renderRoute(data) {
    envNotice(data.environment);
    const routes = data.routes ?? [];
    if (!routes.length) {
      bubble(
        "assistant",
        data.unmet ||
          "I couldn't build a reliable route right now. Try a longer time window.",
      );
      return;
    }
    bubble("assistant", "Here's a walking culture route for your day:");
    for (const r of routes) {
      const mapEl = el("div", "chat-map");
      assistantBlock(mapEl);
      renderRouteMap(mapEl, data.origin, r).catch(() => mapEl.remove());
      assistantBlock(
        renderRouteCard(r, data.origin, {
          trip: { start_at: `${startValue}:00`, end_at: `${endValue}:00` },
          onRemove: (title) => send(`Remove ${title} from the route`),
        }),
      );
    }
  }

  // 어시스턴트 턴을 짧은 텍스트로 요약(멀티턴 맥락 — LLM 이 후속 교정을 이해하도록).
  function summarize(data) {
    // 멀티의도: 실린 결과를 모두 요약(히스토리 맥락 정확). 없으면 message.
    const parts = [];
    if (data.route) {
      const r = (data.route.routes ?? [])[0];
      parts.push(
        r
          ? `Planned a route "${r.name}": ${r.stops
              .map((s) => s.candidate.title)
              .join(" → ")}`
          : data.route.unmet || "No route available.",
      );
    }
    if (data.recommendation) {
      const t = (data.recommendation.candidates ?? []).map((c) => c.title);
      parts.push(
        t.length
          ? `Suggested experiences: ${t.join(", ")}`
          : "No experiences fit those conditions.",
      );
    }
    if (data.answer && data.answer.answer) parts.push(data.answer.answer);
    return parts.join("\n") || data.message || "";
  }

  function renderResponse(data) {
    // 멀티의도: 실린 결과를 모두 렌더(route→recommendation→answer). 한 종류만 그리지 않는다.
    let rendered = false;
    if (data.route && (data.route.routes ?? []).length) {
      renderRoute(data.route);
      rendered = true;
    }
    if (data.recommendation) {
      renderRecommendation(data.recommendation);
      rendered = true;
    }
    if (data.answer && data.answer.answer) {
      renderAnswer(data.answer);
      rendered = true;
    }
    // 아무 결과도 없으면(clarify/빈 결과) 텍스트 되묻기
    if (!rendered) {
      bubble(
        "assistant",
        data.message || "Could you tell me a bit more about what you'd like?",
      );
    }
  }

  // ── 입력 바 ──
  const inputBar = el("div", "chat-input-bar");
  const ta = el("textarea", "chat-textarea");
  ta.rows = 1;
  ta.placeholder = "Ask a question, or say what you'd like to do…";
  const sendBtn = el("button", "chat-send");
  sendBtn.type = "button";
  sendBtn.setAttribute("aria-label", "Send");
  sendBtn.textContent = "↑";
  inputBar.append(ta, sendBtn);

  // 첫 화면 제안 칩(첫 전송 전까지)
  const suggest = el("div", "chat-suggest");
  for (const s of SUGGESTIONS) {
    const chip = el("button", "chat-suggest-chip", s);
    chip.type = "button";
    chip.addEventListener("click", () => send(s));
    suggest.append(chip);
  }
  log.append(suggest);

  // 응답 대기 중 '진행 문구가 순환하는' 어시스턴트 버블. 끝 문구에서 멈추고, stop() 로 정리.
  function thinkingBubble() {
    const span = el("span", "chat-typing", PROGRESS[0]);
    const node = bubble("assistant", span);
    let i = 0;
    const timer = setInterval(() => {
      i = Math.min(i + 1, PROGRESS.length - 1);
      span.textContent = PROGRESS[i];
    }, PROGRESS_INTERVAL_MS);
    return { node, stop: () => clearInterval(timer) };
  }

  const history = []; // 멀티턴 맥락(AG-3) — 서버는 stateless, 매 턴 함께 전송
  let busy = false;
  async function send(text) {
    const msg = (text ?? ta.value).trim();
    if (!msg || busy) return;
    busy = true;
    suggest.remove();
    ta.value = "";
    ta.style.height = "auto";
    bubble("user", msg);

    const prior = history.slice(); // 이번 사용자 메시지 '이전'까지의 맥락
    history.push({ role: "user", content: msg });

    const thinking = thinkingBubble();
    try {
      const env = await postChat(msg, tripContext(), prior);
      thinking.stop();
      thinking.node.remove();
      if (!env.ok) {
        const m =
          env.error?.message || "Sorry, something went wrong. Please try again.";
        bubble("assistant", m);
        history.push({ role: "assistant", content: m });
      } else {
        renderResponse(env.data);
        history.push({ role: "assistant", content: summarize(env.data) });
      }
    } catch {
      const m = "I couldn't reach the service. Please try again.";
      thinking.stop();
      thinking.node.remove();
      bubble("assistant", m);
      history.push({ role: "assistant", content: m });
    } finally {
      busy = false;
    }
  }

  sendBtn.addEventListener("click", () => send());
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
  ta.addEventListener("input", () => {
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
  });

  root.append(inputBar);
  return root;
}
