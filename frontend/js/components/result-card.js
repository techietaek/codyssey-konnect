// Result Card v2 (DESIGN §3.1) — 최소형.
// Fact · Reason · 미확인을 '시각적으로 분리' 렌더하는 것이 1차 목표(신뢰 UX).
// 상태 배지는 후보당 1개, Reason 0~2개, 미확인은 별도 flag 칩.

const STATUS_LABEL = {
  fits: "Fits your conditions",
  check_needed: "Check needed",
  alternative: "Alternative",
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

export function renderResultCard(c) {
  const card = el("article", "card");
  card.dataset.status = c.status;

  // 1. Head: 상태 배지 + 제목
  const head = el("div", "card-head");
  const badge = el("span", "badge", STATUS_LABEL[c.status] ?? c.status);
  badge.dataset.status = c.status;
  head.append(badge, el("h2", "card-title", c.title));
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
  if (c.price && c.price.status !== "unknown") {
    meta.append(el("span", "meta-item", c.price.display));
  }
  if (c.movement) {
    const m = el("span", "meta-item", c.movement.display);
    if (c.movement.provenance === "estimate") m.classList.add("is-estimate");
    meta.append(m);
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
  const select = el("button", "btn-select", "Select experience");
  select.dataset.status = c.status;
  select.dataset.id = c.id;
  actions.append(links, select);
  card.append(actions);

  return card;
}
