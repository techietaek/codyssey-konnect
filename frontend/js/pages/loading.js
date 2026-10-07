// LF-03(로딩) — 즉시 추천(A) 조회 대기 화면.
// 실제로 조회가 "걸리고 있음"을 shimmer 스켈레톤 + 회전 문구 + 펄스 sparkle 로 전달.
// 조회 단계(운영시간·가격·도보 확인)를 그대로 노출해 신뢰감을 준다(과장/가짜 진행률 없음).
import { renderConditionSummary } from "../components/condition-summary.js";

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

const SPARKLE_SVG =
  '<svg viewBox="0 0 24 24" fill="currentColor" width="26" height="26" aria-hidden="true"><path d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9z"/><path d="M18.5 14l.8 2.4 2.4.8-2.4.8-.8 2.4-.8-2.4-2.4-.8 2.4-.8z" opacity=".7"/></svg>';

// 조회 단계 문구 — 실제 파이프라인 단계(fetch→judge→route)를 순서대로 보여준다.
const STEP_MESSAGES = [
  "Checking opening hours, prices and walking time…",
  "Confirming today's hours and closures…",
  "Measuring walking distance from your start…",
  "Filtering out anything that doesn't fit…",
];

function skeletonCard() {
  const card = el("div", "skeleton-card");
  const media = el("div", "skeleton skeleton-media");
  const lines = el("div", "skeleton-lines");
  lines.append(
    el("div", "skeleton skeleton-line w-90"),
    el("div", "skeleton skeleton-line w-80"),
    el("div", "skeleton skeleton-line w-55"),
  );
  card.append(media, lines);
  return card;
}

export function renderLoadingView({ request, conditions, onCancel }) {
  const root = el("section", "results-view loading-view");

  const reduceMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)",
  ).matches;

  // ── 상단: 뒤로 + 타이틀 + 조건 요약 pill ──
  const top = el("div", "results-top");
  const topRow = el("div", "results-top-row");
  const back = el("button", "icon-back", "←");
  back.type = "button";
  back.setAttribute("aria-label", "Back");
  back.addEventListener("click", () => onCancel?.());
  topRow.append(back, el("h1", "loading-title", "Immediate recommendation"));
  top.append(topRow);
  top.append(renderConditionSummary(request, conditions));
  root.append(top);

  // ── 중앙: 펄스 sparkle + 헤드라인 + 회전 문구 ──
  const center = el("div", "loading-center");
  const spark = el("div", "loading-spark");
  spark.innerHTML = SPARKLE_SVG;
  const headline = el("h2", "loading-headline", "Finding experiences that fit");
  const sub = el("p", "loading-sub", STEP_MESSAGES[0]);
  sub.setAttribute("aria-live", "polite");
  center.append(spark, headline, sub);
  root.append(center);

  // ── 스켈레톤 카드(shimmer) ──
  const list = el("div", "skeleton-list");
  list.setAttribute("aria-hidden", "true");
  list.append(skeletonCard(), skeletonCard(), skeletonCard());
  root.append(list);

  // ── Cancel ──
  const cancelRow = el("div", "loading-cancel-row");
  const cancelBtn = el("button", "loading-cancel", "Cancel");
  cancelBtn.type = "button";
  cancelBtn.addEventListener("click", () => onCancel?.());
  cancelRow.append(cancelBtn);
  root.append(cancelRow);

  // 회전 문구 — reduce-motion 이면 고정(첫 문구만). 뷰가 사라지면 자동 정리.
  if (!reduceMotion) {
    let i = 0;
    const timer = setInterval(() => {
      i = (i + 1) % STEP_MESSAGES.length;
      sub.textContent = STEP_MESSAGES[i];
    }, 1800);
    // 뷰가 DOM 에서 제거되면 타이머 정리(결과/입력 전환 시).
    const observer = new MutationObserver(() => {
      if (!root.isConnected) {
        clearInterval(timer);
        observer.disconnect();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  return root;
}
