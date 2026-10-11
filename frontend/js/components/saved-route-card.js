// 저장된 B 문화루트 재접근 카드(home · My Page 공용).
// 라이브 재조립된 RouteData 를 '표시'만 한다 — 사실은 재조회가 정본(스냅샷 아님).
// 선택 ≠ 방문(예약 아님). 탭하면 대화 화면으로 이동해 전체 루트를 본다.

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

export function renderSavedRouteCard(routeData, { onClear, onView } = {}) {
  const r = (routeData?.routes || [])[0];
  if (!r) return null;

  const card = el("div", "choice-card route-choice-card");
  const head = el("div", "choice-card-head");
  head.append(
    el("span", "choice-tag", "Your current route"),
    el("span", "choice-when", "Refreshed"),
  );
  if (onClear) {
    const x = el("button", "choice-clear", "✕");
    x.type = "button";
    x.title = "Clear saved route";
    x.addEventListener("click", (e) => {
      e.stopPropagation();
      onClear();
      card.remove();
    });
    head.append(x);
  }

  const info = el("div", "choice-card-info");
  const texts = el("div", "choice-card-texts");
  const stops = (r.stops || []).map((s) => s.candidate.title).join(" → ");
  texts.append(
    el("span", "choice-card-title", r.headline || r.name || "Culture route"),
    el("span", "choice-card-sub", stops),
  );
  const view = el("span", "choice-card-view", "View →");
  info.append(texts, view);

  card.append(head, info);
  if (onView) card.addEventListener("click", onView);
  return card;
}
