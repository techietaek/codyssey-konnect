// LF-03 — 즉시 추천(A) 결과. 지도 + 현재 조건 pill + AI 고지 + 후보 카드.
// (Reason 설명은 A5 슬라이스에서 보강.)
import { renderResultCard } from "../components/result-card.js";
import { renderMap } from "../map.js";
import { state } from "../state.js";

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

function fmtTime(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function showToast(text) {
  document.querySelector(".toast")?.remove();
  const toast = el("div", "toast", text);
  document.body.append(toast);
  setTimeout(() => toast.remove(), 2200);
}

export function renderResultsView({ request, env, onEdit }) {
  const root = el("section");
  const data = env.data;

  // 현재 조건 pill (출발점 · 시간대) + Edit 진입
  const cond = el("div", "conditions");
  const label = `${request.start_location.label} · ${fmtTime(request.start_at)}–${fmtTime(request.end_at)}`;
  cond.append(el("span", null, label));
  const editBtn = el("button", null, "Edit");
  editBtn.type = "button";
  editBtn.addEventListener("click", onEdit);
  cond.append(editBtn);
  root.append(cond);

  // 지도 (후보 있을 때만). 로드 실패 시 map.js가 컨테이너를 제거(카드는 유지).
  let mapCtrl = null;
  if (data.candidates.length) {
    const mapEl = el("div", "map");
    root.append(mapEl);
    renderMap(mapEl, data.origin, data.candidates)
      .then((ctrl) => {
        mapCtrl = ctrl;
        if (ctrl) {
          ctrl.onPinClick(focusCard);
          focusCard(data.candidates[0].id); // 첫 후보 포커스 동기화
        }
      })
      .catch(() => {});
  }

  // AI 관여 고지 (NFR-05) — 제거 금지
  root.append(el("div", "ai-notice", data.ai_notice));

  const list = el("div", "results");
  if (!data.candidates.length) {
    // 0건은 몰래 완화하지 않고 명시적으로 안내 (FR-A3 · §5.5)
    list.append(el("p", "empty-msg", "No experiences fit these conditions. Try adjusting your time or start point."));
  } else {
    for (const c of data.candidates) {
      const card = renderResultCard(c, data.origin);
      card.dataset.id = c.id;
      list.append(card);
    }
  }
  root.append(list);

  // 카드 포커스(지도 핀 강조 + 경로선) — 스와이프/탭에 해당(선택 확정 아님)
  function focusCard(id) {
    state.focusedId = id;
    for (const card of list.querySelectorAll(".card")) {
      card.classList.toggle("is-focused", card.dataset.id === id);
    }
    mapCtrl?.focus(id);
  }

  list.addEventListener("click", (e) => {
    // Select experience → 현재 선택 확정(선택 ≠ 방문). 자동 이동 없음.
    const btn = e.target.closest(".btn-select");
    if (btn) {
      state.selectedId = btn.dataset.id;
      showToast("Current choice set");
      return;
    }
    // 링크 클릭은 그대로, 그 외 카드 영역 탭 → 포커스
    if (e.target.closest("a")) return;
    const card = e.target.closest(".card");
    if (card?.dataset.id) focusCard(card.dataset.id);
  });

  root.append(el("p", "status-line", `trace ${env.trace_id} · ${data.candidates.length} candidate(s)`));
  return root;
}
