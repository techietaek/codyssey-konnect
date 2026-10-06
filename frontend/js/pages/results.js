// LF-03 — 즉시 추천(A) 결과. 지도 풀스크린 배경 + 상단 플로팅 조건 + 하단 카드 캐러셀.
// 핀/카드 포커스는 지도 카메라·핀·경로선이 부드럽게 이어지도록 애니메이션(map.js).
// Find new options → 비로그인이면 로그인 유도 시트(디자인 구현, OAuth는 Phase 2).
import { renderResultCard } from "../components/result-card.js";
import { showLoginSheet } from "../components/login-sheet.js";
import { renderMap } from "../map.js";
import { isLoggedIn, loadChoice, saveChoice, state } from "../state.js";

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

function fmtTime(iso) {
  // 사용자-facing 문자열은 영어 우선(CLAUDE §5) — 로캘 무관하게 en-US 표기.
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

const INTEREST_LABEL = {
  traditional_culture: "Traditional culture",
  palaces_historic: "Palaces & historic",
  hands_on: "Hands-on",
  art_exhibitions: "Art & exhibitions",
  live_performances: "Live performances",
  festivals_events: "Festivals & events",
};

// AI가 note에서 이해한 조건을 칩으로(DESIGN §3.3 Parsed Chip) — 투명 공개
function conditionChips(cond) {
  if (!cond) return [];
  const labels = (cond.interests ?? []).map((i) => INTEREST_LABEL[i] ?? i);
  if (cond.free_only) labels.push("Free only");
  if (cond.budget_krw) labels.push(`≤ ₩${cond.budget_krw.toLocaleString()}`);
  if (cond.indoor_outdoor)
    labels.push(cond.indoor_outdoor === "indoor" ? "Indoor" : "Outdoor");
  if (cond.prefer_shorter_walks) labels.push("Shorter walks");
  return labels;
}

function showToast(text) {
  document.querySelector(".toast")?.remove();
  const toast = el("div", "toast", text);
  // device-frame 안에 담아 데스크톱 목업 안에서 뜨게(모바일은 화면 하단 중앙).
  (document.querySelector(".device-frame") || document.body).append(toast);
  setTimeout(() => toast.remove(), 2200);
}

const reduceMotion = window.matchMedia(
  "(prefers-reduced-motion: reduce)",
).matches;

export function renderResultsView({ request, env, onBack, onEdit }) {
  const root = el("section", "results-view");
  const data = env.data;
  const cands = data.candidates;

  // ── 상단 바: 뒤로 + 조건 pill (+ 이해한 조건) ──
  const top = el("div", "results-top");
  const back = el("button", "icon-back", "←");
  back.type = "button";
  back.setAttribute("aria-label", "Back");
  if (onBack) back.addEventListener("click", onBack);

  const condPill = el("div", "cond-pill");
  condPill.append(
    el(
      "span",
      "cond-text",
      `${request.start_location.label} · ${fmtTime(request.start_at)}–${fmtTime(request.end_at)}`,
    ),
  );
  const editInline = el("button", "cond-edit", "Edit");
  editInline.type = "button";
  editInline.addEventListener("click", onEdit);
  condPill.append(editInline);
  const topRow = el("div", "results-top-row");
  topRow.append(back, condPill);
  top.append(topRow);

  const chipLabels = conditionChips(data.conditions);
  if (chipLabels.length) {
    const understood = el("div", "understood-pill");
    understood.append(el("span", "understood-label", "+"));
    understood.append(el("span", null, chipLabels.join(" · ")));
    top.append(understood);
  }
  root.append(top);

  // ── 지도 박스 (정해진 박스 안에 꽉 채움 — NAVER 로고가 카드를 가리지 않게) ──
  const mapBox = el("div", "map-box");
  const mapEl = el("div", "map-canvas");
  mapBox.append(mapEl);
  root.append(mapBox);

  // ── 하단 덱: 상태 pill + 캐러셀 + dots + 액션 ──
  const deck = el("div", "results-deck");

  const deckPills = el("div", "deck-pills");
  deckPills.append(el("span", "ai-notice", data.ai_notice));
  if (cands.length) {
    deckPills.append(
      el(
        "span",
        "near-pill",
        `${cands.length} experience${cands.length > 1 ? "s" : ""} near your starting point`,
      ),
    );
  }
  deck.append(deckPills);

  const carousel = el("div", "carousel");
  const dots = el("div", "dots");

  if (!cands.length) {
    // 0건은 몰래 완화하지 않고 명시적으로 안내 (FR-A3 · §5.5)
    const empty = el("div", "empty-card");
    empty.append(
      el("h3", "empty-title", "No experiences fit these conditions"),
      el(
        "p",
        "empty-sub",
        "Try adjusting your time window or start point.",
      ),
    );
    carousel.append(empty);
  } else {
    cands.forEach((c, i) => {
      const card = renderResultCard(c, data.origin, i);
      card.dataset.id = c.id;
      carousel.append(card);
      const dot = el("span", "dot");
      dot.dataset.id = c.id;
      dots.append(dot);
    });
  }
  deck.append(carousel);
  if (cands.length > 1) deck.append(dots);

  const actions = el("div", "deck-actions");
  const editBtn = el("button", "btn-ghost", "Edit conditions");
  editBtn.type = "button";
  editBtn.addEventListener("click", onEdit);
  const findBtn = el("button", "btn-ghost", "Find new options");
  findBtn.type = "button";
  findBtn.addEventListener("click", () => {
    // FR-L1: 두 번째/재추천은 로그인 유도. 비로그인 → 로그인 시트.
    if (!isLoggedIn()) {
      showLoginSheet({ onEditInstead: onEdit });
      return;
    }
    onEdit(); // (로그인 구현 후: 조건 유지 재추천)
  });
  actions.append(editBtn, findBtn);
  deck.append(actions);
  root.append(deck);

  // ── 지도 렌더 + 포커스 동기화 ──
  let mapCtrl = null;
  let programmatic = false;

  function setDots(id) {
    for (const d of dots.children)
      d.classList.toggle("is-active", d.dataset.id === id);
  }

  function focusCard(id, { scroll = false } = {}) {
    if (!id) return;
    state.focusedId = id;
    for (const card of carousel.querySelectorAll(".card"))
      card.classList.toggle("is-focused", card.dataset.id === id);
    setDots(id);
    mapCtrl?.focus(id);
    if (scroll) {
      const card = carousel.querySelector(`.card[data-id="${CSS.escape(id)}"]`);
      if (card) {
        programmatic = true;
        const left =
          card.offsetLeft - (carousel.clientWidth - card.clientWidth) / 2;
        carousel.scrollTo({ left, behavior: reduceMotion ? "auto" : "smooth" });
        clearTimeout(focusCard._t);
        focusCard._t = setTimeout(() => (programmatic = false), 450);
      }
    }
  }

  // 캐러셀 스와이프 → 중앙 카드 감지 → 포커스(지도 동기화)
  let scrollRaf = 0;
  carousel.addEventListener("scroll", () => {
    if (programmatic) return;
    cancelAnimationFrame(scrollRaf);
    scrollRaf = requestAnimationFrame(() => {
      const center = carousel.scrollLeft + carousel.clientWidth / 2;
      let best = null;
      let bestD = Infinity;
      for (const card of carousel.querySelectorAll(".card")) {
        const cc = card.offsetLeft + card.clientWidth / 2;
        const d = Math.abs(cc - center);
        if (d < bestD) {
          bestD = d;
          best = card;
        }
      }
      if (best && best.dataset.id !== state.focusedId)
        focusCard(best.dataset.id);
    });
  });

  if (cands.length) {
    renderMap(mapEl, data.origin, cands)
      .then((ctrl) => {
        mapCtrl = ctrl;
        if (ctrl) {
          ctrl.onPinClick((id) => focusCard(id, { scroll: true }));
          focusCard(cands[0].id); // 첫 후보 포커스 동기화(초기 카메라 포함)
        }
      })
      .catch(() => {});
  } else {
    // 후보 0건: 출발점만 지도에 (핀/경로 없음).
    renderMap(mapEl, data.origin, []).catch(() => {});
  }

  // ── Select experience → 현재 선택 확정 (선택 ≠ 방문) ──
  function markConfirmed(id) {
    for (const card of carousel.querySelectorAll(".card")) {
      const isChoice = card.dataset.id === id;
      card.classList.toggle("is-choice", isChoice);
      card.querySelector(".current-choice")?.remove();
      const selectBtn = card.querySelector(".btn-select");
      if (isChoice) {
        const head = card.querySelector(".card-head");
        head.append(el("span", "current-choice", "✓ Current choice"));
        if (selectBtn) selectBtn.textContent = "Selected";
      } else if (selectBtn) {
        selectBtn.textContent = "Select experience";
      }
    }
  }

  carousel.addEventListener("click", (e) => {
    const btn = e.target.closest(".btn-select");
    if (btn) {
      saveChoice(request, env, btn.dataset.id); // 비로그인 영속
      markConfirmed(btn.dataset.id);
      showToast("Current choice set");
      return;
    }
    if (e.target.closest("a")) return;
    const card = e.target.closest(".card");
    if (card?.dataset.id) focusCard(card.dataset.id, { scroll: true });
  });

  // 재접근 시: 저장된 현재 선택이 이 결과에 있으면 확정 상태로 복원
  const saved = loadChoice();
  if (saved && cands.some((c) => c.id === saved.candidateId))
    markConfirmed(saved.candidateId);

  return root;
}
