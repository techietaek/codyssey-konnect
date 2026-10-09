// Route Card (LF-05/08) — 하루 1코스를 '따로따로'가 아닌 하나의 코스로.
// 헤드라인·날짜/시간 → WHY THIS ROUTE(루트 상태) → 확인필요 요약 → 범례 →
// 타임라인(Start→구간→스톱, 스톱별 이유·사실·Remove) → 종료 → 총계.
// 체류시간은 주장하지 않는다(B-T01) — 각 스톱 '예정 분'은 표기 안 함.
import { TYPE_GLYPH, aiSignalsToggle } from "./result-card.js";

const STATUS_LABEL = {
  fits: "Fits your conditions",
  check_needed: "Check needed",
  alternative: "Alternative",
};
const ROUTE_STATUS = {
  fits: "Ready to go (route)",
  check_needed: "Still to check (route)",
  alternative: "Alternative route",
};

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}
function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}
function fmtDate(iso) {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function segmentRow(seg) {
  const row = el("div", "route-seg");
  row.append(el("span", "route-seg-rail"));
  const parts = [];
  if (seg.movement?.display) parts.push(`🚶 ${seg.movement.display}`);
  if (seg.movement?.distance_m)
    parts.push(`${(seg.movement.distance_m / 1000).toFixed(seg.movement.distance_m >= 1000 ? 1 : 2)} km`);
  row.append(el("span", "route-seg-text", parts.join(" · ")));
  return row;
}

// 계획 방문시간 배지 — 공식(confirmed)=Official / 유형기준(planned)=Planned.
function visitBadge(prov) {
  const b = el("span", "route-visit-badge", prov === "confirmed" ? "Official" : "Planned");
  b.dataset.prov = prov;
  return b;
}

function stopRow(stop, onRemove) {
  const c = stop.candidate;
  const row = el("div", "route-stop");
  row.dataset.status = c.status;

  const num = el("span", "route-stop-num", String(stop.order));
  const body = el("div", "route-stop-body");

  const titleLine = el("div", "route-stop-title-line");
  titleLine.append(el("span", "route-stop-title", c.title));
  const badge = el("span", "badge badge--sm", STATUS_LABEL[c.status] ?? c.status);
  badge.dataset.status = c.status;
  titleLine.append(
    el("span", "route-stop-glyph", `${TYPE_GLYPH[c.type] ?? TYPE_GLYPH.default}`),
    badge,
  );
  body.append(titleLine);

  // AI 분류 근거 토글 — 제목줄 우측(inline). 누르면 키워드 칩 행이 토글된다(추천 카드와 동일).
  if (c.signals?.length) {
    const { button, row } = aiSignalsToggle(c.signals, { inline: true });
    titleLine.append(button);
    body.append(row);
  }

  // 스톱별 이유(코스 "왜 이 장소") — teal check, 0개면 생략
  if (c.reasons?.length) {
    const rs = el("ul", "route-stop-reasons");
    for (const r of c.reasons.slice(0, 2)) {
      const li = el("li", "reason");
      li.append(el("span", "reason-check", "✓"), el("span", null, r.text));
      rs.append(li);
    }
    body.append(rs);
  }

  // 계획 방문시간 — 공식 spendtime=Official / 유형기준=Planned (B-T01). 도보 미확인이면
  // 절대 window 없이 소요분만. 운영시간(fact)과 별개로 분리 표기.
  if (stop.visit_minutes) {
    const when = el("div", "route-stop-when");
    const label =
      stop.arrival_at && stop.depart_at
        ? `${fmtTime(stop.arrival_at)} – ${fmtTime(stop.depart_at)}`
        : `≈${stop.visit_minutes} min visit`;
    when.append(
      el("span", "route-stop-time", label),
      visitBadge(stop.visit_provenance),
    );
    body.append(when);
  }

  // Fact: 운영시간·가격(미확인 가격은 flag로 분리)
  const meta = el("div", "route-stop-meta");
  if (c.time) meta.append(el("span", "meta-item", c.time.display));
  if (c.price && c.price.status !== "unknown")
    meta.append(el("span", "meta-item", c.price.display));
  if (meta.childNodes.length) body.append(meta);

  if (c.flags?.length) {
    const flags = el("div", "flags");
    for (const f of c.flags) flags.append(el("span", "flag", f.text));
    body.append(flags);
  }

  const actions = el("div", "route-stop-actions");
  for (const link of c.official_links ?? []) {
    const a = el("a", "official-link", `${link.label} ↗`);
    a.href = link.url;
    a.target = "_blank";
    a.rel = "noopener";
    actions.append(a);
  }
  if (onRemove) {
    const rm = el("button", "route-remove", "Remove");
    rm.type = "button";
    rm.addEventListener("click", () => onRemove(c.title));
    actions.append(rm);
  }
  if (actions.childNodes.length) body.append(actions);

  row.append(num, body);
  return row;
}

export function renderRouteCard(route, origin, opts = {}) {
  const { trip, onRemove } = opts;
  const card = el("article", "route-card");

  // ── Head: 날짜/시간 + 헤드라인 + 스톱 요약 ──
  const head = el("div", "route-card-head");
  if (trip?.start_at && trip?.end_at)
    head.append(
      el(
        "p",
        "route-when",
        `${fmtDate(trip.start_at)} · ${fmtTime(trip.start_at)}–${fmtTime(trip.end_at)}`,
      ),
    );
  head.append(el("h2", "route-card-name", route.headline || route.name));
  const stopNames = route.stops.map((s) => s.candidate.title).join(" · ");
  head.append(el("p", "route-stop-summary", stopNames));
  card.append(head);

  // ── WHY THIS ROUTE + 루트 상태 ──
  const why = el("div", "route-why");
  why.append(el("p", "route-why-label", "WHY THIS ROUTE"));
  const whyReason = el("p", "route-why-reason");
  whyReason.append(
    el("span", "reason-check", "✓"),
    el("span", null, "Planned to fit your time window"),
  );
  why.append(whyReason);
  const rstatus = el("span", "route-status", ROUTE_STATUS[route.status] ?? "Culture route");
  rstatus.dataset.status = route.status;
  why.append(rstatus);
  card.append(why);

  // ── 가기 전 확인할 것(집계) ──
  if (route.checks?.length) {
    const check = el("div", "route-check");
    check.append(
      el(
        "p",
        "route-check-title",
        `${route.checks.length} thing${route.checks.length > 1 ? "s" : ""} to check before you go`,
      ),
    );
    const ul = el("ul", "route-check-list");
    for (const c of route.checks) ul.append(el("li", null, c));
    check.append(ul);
    card.append(check);
  }

  // ── 범례 ──
  const legend = el("div", "route-legend");
  for (const [cls, label] of [
    ["lg-official", "Official"],
    ["lg-estimate", "≈ Estimated"],
    ["lg-planned", "Planned"],
    ["lg-check", "needs checking"],
  ])
    legend.append(el("span", `route-legend-item ${cls}`, label));
  card.append(legend);

  // ── 타임라인: Start → (seg) → stop1 … ──
  const timeline = el("div", "route-timeline");
  const startRow = el("div", "route-start");
  startRow.append(el("span", "route-start-dot", "◉"));
  const startText = el("span", "route-start-label", `Start · ${origin?.label ?? "Your start"}`);
  startRow.append(startText);
  if (trip?.start_at)
    startRow.append(el("span", "route-start-time", fmtTime(trip.start_at)));
  timeline.append(startRow);
  route.stops.forEach((stop, i) => {
    if (route.segments?.[i]) timeline.append(segmentRow(route.segments[i]));
    timeline.append(stopRow(stop, onRemove));
  });
  // End — 계획 종료(도보+방문 체인). finish_at 있으면 그 값, 없으면 창 종료.
  const finish = route.finish_at || trip?.end_at || null;
  const endRow = el("div", "route-end");
  endRow.append(el("span", "route-end-flag", "⚑"));
  endRow.append(
    el(
      "span",
      "route-end-label",
      finish
        ? `${route.finish_at ? "Finish about" : "Finish by"} ${fmtTime(finish)}`
        : "End · your plan",
    ),
  );
  timeline.append(endRow);
  card.append(timeline);

  // ── 총계(비용·도보·종료) ──
  const totals = el("div", "route-totals");
  const addTotal = (k, v) => {
    const r = el("div", "route-total-row");
    r.append(el("span", "route-total-k", k), el("span", "route-total-v", v));
    totals.append(r);
  };
  addTotal("Total cost", route.budget_note || "See each stop");
  if (route.total_walk_minutes != null)
    addTotal("Walking", `≈${route.total_walk_minutes} min in total`);
  if (finish)
    addTotal("Finish", `${route.finish_at ? "≈" : "by "}${fmtTime(finish)}`);
  card.append(totals);

  if (route.flags?.length) {
    const flags = el("div", "flags");
    for (const f of route.flags) flags.append(el("span", "flag", f.text));
    card.append(flags);
  }
  // 체류시간 미주장(B-T01) 안내
  if (route.stay_note) card.append(el("p", "route-stay-note", route.stay_note));
  return card;
}
