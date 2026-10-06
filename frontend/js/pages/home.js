// Phase 0 홈 페이지 로직: 스텁 추천을 호출해 Result Card 1개 렌더.
// 이후 A1 슬라이스에서 실제 LF-02 입력 UI → 조건 구조화로 대체한다.
import { postRecommend } from "../api.js";
import { setResults, state } from "../state.js";
import { renderResultCard } from "../components/result-card.js";

const resultsEl = document.getElementById("results");
const statusEl = document.getElementById("status-line");

function showToast(text) {
  const prev = document.querySelector(".toast");
  if (prev) prev.remove();
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = text;
  document.body.append(toast);
  setTimeout(() => toast.remove(), 2200);
}

function render() {
  resultsEl.replaceChildren();
  for (const c of state.candidates) {
    resultsEl.append(renderResultCard(c));
  }
}

async function load() {
  // Phase 0: 고정 조건으로 스텁 호출 (실제 입력 UI는 A1에서)
  const req = {
    start_location: "Chungmuro",
    start_time: "15:20",
    end_time: "18:30",
    note: "palaces, under 20000 won",
  };
  statusEl.textContent = "Loading…";
  try {
    const env = await postRecommend(req);
    if (!env.ok) {
      statusEl.textContent = `System error (${env.error?.code ?? "unknown"}). Please try again.`;
      return;
    }
    setResults(req, env.data.candidates);
    render();
    statusEl.textContent = `trace ${env.trace_id} · ${state.candidates.length} candidate(s)`;
  } catch (e) {
    statusEl.textContent = "Could not reach the server. Is the backend running on :8000?";
  }
}

// Select experience → 현재 선택 확정(선택 ≠ 방문). 자동 이동 없음.
resultsEl.addEventListener("click", (e) => {
  const btn = e.target.closest(".btn-select");
  if (!btn) return;
  state.selectedId = btn.dataset.id;
  showToast("Current choice set");
});

load();
