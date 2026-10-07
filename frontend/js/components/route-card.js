// Route Card (LF-08 핵심) — 하루 1코스(2~3 스톱)를 타임라인으로.
// 시작점 → 구간 도보 → 스톱(순서·유형·상태·가격·미확인) 순으로 신뢰 분리 렌더.
// 체류시간은 주장하지 않는다(B-T01) — stay_note 로 '직접 계획' 안내만.
import { TYPE_GLYPH } from "./result-card.js";

const STATUS_LABEL = {
  fits: "Fits your conditions",
  check_needed: "Check needed",
  alternative: "Alternative",
};

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

// 구간 도보 한 줄(걷는 사람 + ≈N min). 측정 실패 구간은 그대로 노출(직선 위조 금지).
function segmentRow(seg) {
  const row = el("div", "route-seg");
  row.append(el("span", "route-seg-rail"));
  const txt = seg.movement?.display ?? "Route unavailable";
  const m = el("span", "route-seg-text", `🚶 ${txt}`);
  if (seg.movement?.provenance === "estimate") m.classList.add("is-estimate");
  row.append(m);
  return row;
}

function stopRow(stop) {
  const c = stop.candidate;
  const row = el("div", "route-stop");
  row.dataset.status = c.status;

  const num = el("span", "route-stop-num", String(stop.order));
  const body = el("div", "route-stop-body");

  const titleLine = el("div", "route-stop-title-line");
  titleLine.append(
    el("span", "route-stop-glyph", TYPE_GLYPH[c.type] ?? TYPE_GLYPH.default),
    el("span", "route-stop-title", c.title),
  );
  const badge = el("span", "badge badge--sm", STATUS_LABEL[c.status] ?? c.status);
  badge.dataset.status = c.status;
  titleLine.append(badge);
  body.append(titleLine);

  // Fact: 시간·가격(미확인 가격은 표기 안 함 — flag 로 분리)
  const meta = el("div", "route-stop-meta");
  if (c.time) meta.append(el("span", "meta-item", c.time.display));
  if (c.price && c.price.status !== "unknown")
    meta.append(el("span", "meta-item", c.price.display));
  if (meta.childNodes.length) body.append(meta);

  // 미확인 flags(앰버) — 가격/시간 미확인을 가능/무료로 바꾸지 않는다
  if (c.flags?.length) {
    const flags = el("div", "flags");
    for (const f of c.flags) flags.append(el("span", "flag", f.text));
    body.append(flags);
  }

  // 공식 링크(있으면)
  if (c.official_links?.length) {
    const links = el("div", "links");
    for (const link of c.official_links) {
      const a = el("a", "official-link", `${link.label} ↗`);
      a.href = link.url;
      a.target = "_blank";
      a.rel = "noopener";
      links.append(a);
    }
    body.append(links);
  }

  row.append(num, body);
  return row;
}

export function renderRouteCard(route, origin) {
  const card = el("article", "route-card");

  // Head: 루트명 + 전체 메타(총 도보·예산 롤업·체류 안내)
  const head = el("div", "route-card-head");
  head.append(el("h2", "route-card-name", route.name));
  const meta = el("div", "route-card-meta");
  if (route.total_walk_minutes != null)
    meta.append(el("span", "route-pill", `🚶 ${route.total_walk_minutes} min total walk`));
  if (route.budget_note) meta.append(el("span", "route-pill", route.budget_note));
  head.append(meta);
  if (route.stay_note)
    head.append(el("p", "route-stay-note", route.stay_note));
  card.append(head);

  // 타임라인: Start → (seg) → stop1 → (seg) → stop2 ...
  const timeline = el("div", "route-timeline");
  const startRow = el("div", "route-start");
  startRow.append(
    el("span", "route-start-dot", "◉"),
    el("span", "route-start-label", `Start · ${origin?.label ?? "Your start"}`),
  );
  timeline.append(startRow);
  route.stops.forEach((stop, i) => {
    if (route.segments?.[i]) timeline.append(segmentRow(route.segments[i]));
    timeline.append(stopRow(stop));
  });
  card.append(timeline);

  // 루트 레벨 미확인(예: 일부 구간 측정 실패)
  if (route.flags?.length) {
    const flags = el("div", "flags");
    for (const f of route.flags) flags.append(el("span", "flag", f.text));
    card.append(flags);
  }
  return card;
}
