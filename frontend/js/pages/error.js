// LF-03(오류) — 추천 조회 실패(네트워크/시스템 예외) 전용 화면.
// 0건(정상 결과)과 구분되는 "불러오지 못함" 상태. 조건은 유지되고 재시도 가능.
import { renderConditionSummary } from "../components/condition-summary.js";

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

const WARN_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="28" height="28" aria-hidden="true"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>';

export function renderErrorView({ request, conditions, onRetry, onEdit, onBack }) {
  const root = el("section", "results-view error-view");

  // ── 상단: 뒤로 + 타이틀 + 조건 요약 ──
  const top = el("div", "results-top");
  const topRow = el("div", "results-top-row");
  const back = el("button", "icon-back", "←");
  back.type = "button";
  back.setAttribute("aria-label", "Back");
  back.addEventListener("click", () => onBack?.());
  topRow.append(back, el("h1", "loading-title", "Immediate recommendation"));
  top.append(topRow);
  top.append(renderConditionSummary(request, conditions));
  root.append(top);

  // ── 중앙: 경고 아이콘 + 제목 + 설명 ──
  const center = el("div", "error-center");
  const icon = el("div", "error-icon");
  icon.innerHTML = WARN_SVG;
  center.append(
    icon,
    el("h2", "error-title", "Couldn't load experiences"),
    el(
      "p",
      "error-sub",
      "Check your connection and try again. Your conditions are kept.",
    ),
  );
  root.append(center);

  // ── 액션: Try again(primary) + Edit conditions ──
  const actions = el("div", "error-actions");
  const retry = el("button", "btn-cta error-retry", "Try again");
  retry.type = "button";
  retry.addEventListener("click", () => onRetry?.());
  const edit = el("button", "error-edit", "Edit conditions");
  edit.type = "button";
  edit.addEventListener("click", () => onEdit?.());
  actions.append(retry, edit);
  root.append(actions);

  return root;
}
