// 저장된 B 문화루트 재접근 카드(home · My Page 공용).
// 1순위: 라이브 재조립된 RouteData 를 '표시'(사실·경로선 신선). 재조립이 비면(심야·스톱 변동
// 등) 사용자가 저장해 둔 스톱 제목(ref) 으로 폴백 렌더 — '내가 저장한 루트'는 항상 보이게 한다
// (ref 는 사용자 자신의 선택 참조이지 외부 API 사실이 아니다). 선택 ≠ 방문.

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

// renderSavedRouteCard(routeData, ref, { onClear, onView })
// routeData: 라이브 재조립 결과(없거나 빈 루트일 수 있음). ref: 저장된 참조(stops 제목 등).
export function renderSavedRouteCard(routeData, ref, { onClear, onView } = {}) {
  const r = (routeData?.routes || [])[0];
  const liveStops = r ? r.stops.map((s) => s.candidate.title) : [];
  const refStops = Array.isArray(ref?.stops) ? ref.stops : [];
  const stopNames = liveStops.length ? liveStops : refStops;
  if (!stopNames.length) return null; // 보여줄 게 아무것도 없음

  const card = el("div", "choice-card route-choice-card");
  const head = el("div", "choice-card-head");
  head.append(
    el("span", "choice-tag", "Your current route"),
    el("span", "choice-when", r ? "Refreshed" : "Saved"),
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
  const title = r
    ? r.headline || r.name || "Culture route"
    : `${stopNames.length}-stop culture route`;
  texts.append(
    el("span", "choice-card-title", title),
    el("span", "choice-card-sub", stopNames.join(" → ")),
  );
  const view = el("span", "choice-card-view", "View →");
  info.append(texts, view);

  card.append(head, info);
  if (onView) card.addEventListener("click", onView);
  return card;
}
