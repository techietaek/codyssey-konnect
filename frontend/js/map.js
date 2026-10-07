// Naver Maps 렌더 (LF-03, DESIGN §3.4) — 지도 풀스크린 + 부드러운 포커스 모션.
// - 출발점(Start) 핀 + 후보 번호/유형 핀(선택 시 CSS 트랜지션으로 확대)
// - 포커스 전환 시: 지도 카메라 pan(부드럽게) + 경로선 프로그레시브 draw.
//   임의 직선 금지 — 실제 Tmap path 가 있을 때만 그린다(PRD §7).
// - SDK 로드 실패(도메인 미등록 등) 시 지도 컨테이너를 숨긴다(카드는 그대로).
import { API_BASE } from "./config.js";
import { TYPE_GLYPH } from "./components/result-card.js";

const TEAL = "#007385";
const reduceMotion = window.matchMedia(
  "(prefers-reduced-motion: reduce)",
).matches;

let _loader = null;

async function loadNaver() {
  if (window.naver?.maps) return true;
  if (_loader) return _loader;
  _loader = (async () => {
    const cfg = await (await fetch(`${API_BASE}/api/config`)).json();
    const id = cfg.naver_map_client_id;
    if (!id) return false;
    await new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${encodeURIComponent(id)}`;
      s.onload = resolve;
      s.onerror = reject;
      document.head.append(s);
    });
    return !!window.naver?.maps;
  })().catch(() => false);
  return _loader;
}

function startPinHTML() {
  return '<div class="start-pin"></div>';
}

// 번호+유형 핀. 선택 상태/걷기 라벨은 포커스 때 DOM 클래스/텍스트로 갱신.
function numPinHTML(glyph, n) {
  return (
    '<div class="map-pin">' +
    `<div class="map-pin-body"><span class="map-pin-glyph">${glyph}</span></div>` +
    `<span class="map-pin-num">${n}</span>` +
    '<span class="map-pin-walk"></span>' +
    "</div>"
  );
}

function midpoint(maps, a, b) {
  return new maps.LatLng((a.lat + b.lat) / 2, (a.lng + b.lng) / 2);
}

// 지도 렌더. 성공 시 { focus(id), onPinClick(cb) } 컨트롤러, 실패 시 null.
export async function renderMap(container, origin, candidates) {
  const ok = await loadNaver();
  if (!ok || !origin?.lat || !origin?.lng) {
    container.remove(); // 지도 불가 → 숨김(카드·딥링크는 유지)
    return null;
  }
  window.navermap_authFailure = () => container.remove();
  const { maps } = window.naver;
  const map = new maps.Map(container, {
    center: new maps.LatLng(origin.lat, origin.lng),
    zoom: 15,
    scaleControl: false,
    mapDataControl: false,
    logoControlOptions: { position: maps.Position.BOTTOM_RIGHT },
  });

  new maps.Marker({
    position: new maps.LatLng(origin.lat, origin.lng),
    map,
    icon: { content: startPinHTML(), anchor: new maps.Point(9, 9) },
    zIndex: 50,
  });

  const bounds = new maps.LatLngBounds(
    new maps.LatLng(origin.lat, origin.lng),
    new maps.LatLng(origin.lat, origin.lng),
  );
  const entries = {};
  let pinClickCb = null;
  candidates.forEach((c, i) => {
    if (c.lat == null || c.lng == null) return;
    const pos = new maps.LatLng(c.lat, c.lng);
    const glyph = TYPE_GLYPH[c.type] ?? TYPE_GLYPH.default;
    const marker = new maps.Marker({
      position: pos,
      map,
      icon: { content: numPinHTML(glyph, i + 1), anchor: new maps.Point(16, 16) },
    });
    maps.Event.addListener(marker, "click", () => pinClickCb && pinClickCb(c.id));
    entries[c.id] = { marker, index: i, cand: c };
    bounds.extend(pos);
  });

  // 초기: 출발점+모든 핀을 지도 박스 안에 프레이밍(여백 확보).
  if (candidates.length)
    map.fitBounds(bounds, { top: 56, right: 48, bottom: 56, left: 48 });

  let routeLine = null;
  let routeAnim = 0;

  function drawRoute(cand) {
    cancelAnimationFrame(routeAnim);
    if (routeLine) {
      routeLine.setMap(null);
      routeLine = null;
    }
    const path = cand?.movement?.path;
    if (!path?.length) return; // 경로 데이터 없음 → 그리지 않음(직선 위조 금지)
    const latlngs = path.map(([la, ln]) => new maps.LatLng(la, ln));
    const style = {
      map,
      strokeColor: TEAL,
      strokeWeight: 5,
      strokeOpacity: 0.9,
      strokeLineCap: "round",
      strokeLineJoin: "round",
    };
    if (reduceMotion || latlngs.length < 3) {
      routeLine = new maps.Polyline({ ...style, path: latlngs });
      return;
    }
    // 프로그레시브 draw — 출발점에서 핀까지 선이 '이어지듯' 그려진다.
    routeLine = new maps.Polyline({ ...style, path: [latlngs[0]] });
    const DURATION = 450;
    const t0 = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - t0) / DURATION);
      const n = Math.max(2, Math.ceil(t * latlngs.length));
      routeLine.setPath(latlngs.slice(0, n));
      if (t < 1) routeAnim = requestAnimationFrame(tick);
    };
    routeAnim = requestAnimationFrame(tick);
  }

  function focus(id) {
    const target = entries[id];
    for (const [cid, e] of Object.entries(entries)) {
      const sel = cid === id;
      const node = e.marker.getElement()?.querySelector(".map-pin");
      if (node) {
        node.classList.toggle("is-sel", sel);
        const walk = node.querySelector(".map-pin-walk");
        if (walk) walk.textContent = sel ? (e.cand.movement?.walk_minutes ? `≈${e.cand.movement.walk_minutes} min walk` : "") : "";
      }
      e.marker.setZIndex(sel ? 100 : 10);
    }
    drawRoute(target?.cand);
    // 카메라: 출발점↔포커스 핀 중점으로 부드럽게 이동(둘 다 화면에 유지).
    if (target?.cand?.lat != null && !reduceMotion) {
      map.panTo(midpoint(maps, origin, target.cand), {
        duration: 600,
        easing: "easeOutCubic",
      });
    }
  }

  return {
    focus,
    onPinClick(cb) {
      pinClickCb = cb;
    },
  };
}

// 루트 지도(B3·LF-08) — 출발점 + 순번 스톱 핀 + 구간 경로선(실제 Tmap path 이어붙임).
// 임의 직선 금지 — 측정된 구간 path 만 그린다. 실패/미등록 시 컨테이너 숨김(카드는 유지).
export async function renderRouteMap(container, origin, route) {
  const ok = await loadNaver();
  if (!ok || !origin?.lat || !origin?.lng) {
    container.remove();
    return null;
  }
  window.navermap_authFailure = () => container.remove();
  const { maps } = window.naver;
  const map = new maps.Map(container, {
    center: new maps.LatLng(origin.lat, origin.lng),
    zoom: 15,
    scaleControl: false,
    mapDataControl: false,
    logoControlOptions: { position: maps.Position.BOTTOM_RIGHT },
  });
  new maps.Marker({
    position: new maps.LatLng(origin.lat, origin.lng),
    map,
    icon: { content: startPinHTML(), anchor: new maps.Point(9, 9) },
    zIndex: 50,
  });
  const bounds = new maps.LatLngBounds(
    new maps.LatLng(origin.lat, origin.lng),
    new maps.LatLng(origin.lat, origin.lng),
  );
  (route.stops ?? []).forEach((s, i) => {
    const c = s.candidate;
    if (c?.lat == null || c?.lng == null) return;
    const pos = new maps.LatLng(c.lat, c.lng);
    new maps.Marker({
      position: pos,
      map,
      icon: {
        content: numPinHTML(TYPE_GLYPH[c.type] ?? TYPE_GLYPH.default, i + 1),
        anchor: new maps.Point(16, 16),
      },
    });
    bounds.extend(pos);
  });
  // 구간 path 를 순서대로 이어붙여 전체 동선 1선으로(측정된 구간만).
  const latlngs = [];
  for (const seg of route.segments ?? []) {
    const p = seg.movement?.path;
    if (p?.length) for (const [la, ln] of p) latlngs.push(new maps.LatLng(la, ln));
  }
  if (latlngs.length) {
    new maps.Polyline({
      map,
      path: latlngs,
      strokeColor: TEAL,
      strokeWeight: 5,
      strokeOpacity: 0.9,
      strokeLineCap: "round",
      strokeLineJoin: "round",
    });
  }
  map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
  return { map };
}

// 미니맵(홈 현재선택 카드) — 비상호작용, 출발점+단일 핀+실제 경로만. 실패 시 숨김.
export async function renderMiniMap(container, origin, candidate) {
  const ok = await loadNaver();
  if (!ok || !origin?.lat || !origin?.lng || candidate?.lat == null) {
    container.remove();
    return null;
  }
  window.navermap_authFailure = () => container.remove();
  const { maps } = window.naver;
  const map = new maps.Map(container, {
    center: new maps.LatLng(candidate.lat, candidate.lng),
    zoom: 14,
    draggable: false,
    pinchZoom: false,
    scrollWheel: false,
    keyboardShortcuts: false,
    disableDoubleTapZoom: true,
    disableDoubleClickZoom: true,
    scaleControl: false,
    mapDataControl: false,
    logoControl: false,
  });
  new maps.Marker({
    position: new maps.LatLng(origin.lat, origin.lng),
    map,
    icon: { content: startPinHTML(), anchor: new maps.Point(9, 9) },
    zIndex: 50,
  });
  const glyph = TYPE_GLYPH[candidate.type] ?? TYPE_GLYPH.default;
  new maps.Marker({
    position: new maps.LatLng(candidate.lat, candidate.lng),
    map,
    icon: { content: numPinHTML(glyph, 1), anchor: new maps.Point(16, 16) },
    zIndex: 100,
  });
  const path = candidate.movement?.path;
  if (path?.length) {
    new maps.Polyline({
      map,
      path: path.map(([la, ln]) => new maps.LatLng(la, ln)),
      strokeColor: TEAL,
      strokeWeight: 4,
      strokeOpacity: 0.9,
      strokeLineCap: "round",
      strokeLineJoin: "round",
    });
  }
  const bounds = new maps.LatLngBounds(
    new maps.LatLng(origin.lat, origin.lng),
    new maps.LatLng(candidate.lat, candidate.lng),
  );
  map.fitBounds(bounds, { top: 20, right: 24, bottom: 20, left: 24 });
  // 선택 핀 강조
  requestAnimationFrame(() => {
    const el = container.querySelector(".map-pin");
    if (el) el.classList.add("is-sel");
  });
  return { map };
}
