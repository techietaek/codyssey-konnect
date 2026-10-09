// Result Card v3 (LF-03 카드 캐러셀) — Fact · Reason · 미확인을 시각 분리(신뢰 UX).
// 상태 배지 후보당 1개, Reason 0~2개, 미확인은 별도 flag 칩. 썸네일에 번호 배지.

const STATUS_LABEL = {
  fits: "Fits your conditions",
  check_needed: "Check needed",
  alternative: "Alternative",
};

// 문화경험 유형 글리프(썸네일·핀 공용). 모양 바뀌어도 key 고정(DESIGN §3.4).
export const TYPE_GLYPH = {
  historic_visit: "🏛",
  exhibition: "🖼",
  performance: "🎭",
  hands_on: "✋",
  festival_event: "🎉",
  default: "📍",
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

// Google Maps 길찾기 딥링크 (외부 상세 길찾기, DESIGN §3.4).
// 대중교통 모드 — 구글맵은 한국에서 도보 경로를 제공하지 않는다(도보는 내부 Tmap).
function directionsUrl(origin, c) {
  if (!origin?.lat || !origin?.lng || c.lat == null || c.lng == null) return null;
  return (
    "https://www.google.com/maps/dir/?api=1" +
    `&origin=${origin.lat},${origin.lng}&destination=${c.lat},${c.lng}&travelmode=transit`
  );
}

export function renderResultCard(c, origin, index = 0) {
  const card = el("article", "card");
  card.dataset.status = c.status;

  // 1. Head: 썸네일(번호 배지) + 상태 배지 + 제목
  const head = el("div", "card-head");
  const thumb = el("div", "card-thumb");
  if (c.image_url) thumb.style.backgroundImage = `url("${c.image_url}")`;
  else thumb.append(el("span", "card-thumb-glyph", TYPE_GLYPH[c.type] ?? TYPE_GLYPH.default));
  thumb.append(el("span", "card-num", String(index + 1)));
  const headText = el("div", "card-head-text");
  const badge = el("span", "badge", STATUS_LABEL[c.status] ?? c.status);
  badge.dataset.status = c.status;
  headText.append(badge, el("h2", "card-title", c.title));
  head.append(thumb, headText);
  card.append(head);

  // 2. Reasons (0~2) — teal check. 0개면 영역 생략.
  if (c.reasons?.length) {
    const reasons = el("ul", "reasons");
    for (const r of c.reasons.slice(0, 2)) {
      const li = el("li", "reason");
      li.append(el("span", "reason-check", "✓"), el("span", null, r.text));
      reasons.append(li);
    }
    card.append(reasons);
  }

  // 3. Meta (Fact) — 시간·가격·이동. provenance 를 문구로 구분.
  const meta = el("div", "meta");
  if (c.time) meta.append(el("span", "meta-item", c.time.display));
  if (c.price && c.price.status !== "unknown")
    meta.append(el("span", "meta-item", c.price.display));
  if (c.movement) {
    const m = el("span", "meta-item", c.movement.display);
    if (c.movement.provenance === "estimate") m.classList.add("is-estimate");
    meta.append(m);
  }
  // 반경 확대로 편입된 후보 — 출발점 직선거리 라벨(조금 떨어진 곳임을 투명하게).
  if (c.from_widened_search && c.distance_m != null) {
    const d =
      c.distance_m >= 1000
        ? `${(c.distance_m / 1000).toFixed(1)} km`
        : `${c.distance_m} m`;
    meta.append(el("span", "meta-item is-widened", `📍 ${d} away`));
  }
  if (meta.childNodes.length) card.append(meta);

  // 4. 미확인 flags — 앰버 칩. 미확인을 무료/가능으로 바꾸지 않는다.
  if (c.flags?.length) {
    const flags = el("div", "flags");
    for (const f of c.flags) flags.append(el("span", "flag", f.text));
    card.append(flags);
  }

  // 5. Actions: 공식 링크 + Select experience (선택 ≠ 방문)
  const actions = el("div", "actions");
  const links = el("div", "links");
  for (const link of c.official_links ?? []) {
    const a = el("a", "official-link", `${link.label} ↗`);
    a.href = link.url;
    a.target = "_blank";
    a.rel = "noopener";
    links.append(a);
  }
  // 외부 지도 길찾기 (경로 provenance와 무관하게 항상 제공 — Fallback의 공통 출구)
  const dir = directionsUrl(origin, c);
  if (dir) {
    const a = el("a", "official-link", "Google Map ↗");
    a.href = dir;
    a.target = "_blank";
    a.rel = "noopener";
    links.append(a);
  }
  const select = el("button", "btn-select", "Select experience");
  select.dataset.status = c.status;
  select.dataset.id = c.id;
  actions.append(links, select);
  card.append(actions);

  return card;
}
