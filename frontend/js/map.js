// Naver Maps 렌더 (LF-03, DESIGN §3.4).
// - 출발점(Start) 핀 + 후보 번호 핀(선택/비선택)
// - 포커스 후보의 '실제 도보 경로선'만 그린다(Tmap path). 임의 직선 금지(PRD §7).
// - SDK 로드 실패(도메인 미등록 등) 시 지도 컨테이너를 숨기고 카드는 그대로 둔다.
import { API_BASE } from "./config.js";

const TEAL = "#007385";
const INK = "#2a2f45";

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

function startPin() {
  return `<div style="width:14px;height:14px;border-radius:50%;background:${INK};border:2px solid #fff;box-shadow:0 2px 3px rgba(0,0,0,.3)"></div>`;
}

function numPin(n, selected) {
  if (selected) {
    return `<div style="width:30px;height:30px;border-radius:16px;background:${TEAL};border:3px solid #fff;color:#fff;font:700 13px Inter,sans-serif;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 4px rgba(0,0,0,.3)">${n}</div>`;
  }
  return `<div style="width:24px;height:24px;border-radius:12px;background:#fff;border:2px solid ${TEAL};color:${TEAL};font:700 12px Inter,sans-serif;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 3px rgba(0,0,0,.25)">${n}</div>`;
}

// 지도 렌더. 성공 시 { focus(id), onPinClick(cb) } 컨트롤러, 실패 시 null.
export async function renderMap(container, origin, candidates) {
  const ok = await loadNaver();
  if (!ok || !origin?.lat || !origin?.lng) {
    container.remove(); // 지도 불가 → 숨김(카드·딥링크는 유지)
    return null;
  }
  // 인증 실패(도메인 미등록 등) 시 Naver가 컨테이너에 에러를 그리는 대신 숨긴다.
  window.navermap_authFailure = () => container.remove();
  const { maps } = window.naver;
  const map = new maps.Map(container, {
    center: new maps.LatLng(origin.lat, origin.lng),
    zoom: 15,
    scaleControl: false,
    mapDataControl: false,
  });

  new maps.Marker({
    position: new maps.LatLng(origin.lat, origin.lng),
    map,
    icon: { content: startPin(), anchor: new maps.Point(7, 7) },
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
    const marker = new maps.Marker({
      position: pos,
      map,
      icon: { content: numPin(i + 1, false), anchor: new maps.Point(12, 12) },
    });
    maps.Event.addListener(marker, "click", () => pinClickCb && pinClickCb(c.id));
    entries[c.id] = { marker, index: i };
    bounds.extend(pos);
  });
  map.fitBounds(bounds, { top: 48, right: 48, bottom: 48, left: 48 });

  let routeLine = null;
  function focus(id) {
    for (const c of candidates) {
      const e = entries[c.id];
      if (e) {
        const sel = c.id === id;
        e.marker.setIcon({
          content: numPin(e.index + 1, sel),
          anchor: new maps.Point(sel ? 15 : 12, sel ? 15 : 12),
        });
        e.marker.setZIndex(sel ? 100 : 1);
      }
    }
    if (routeLine) {
      routeLine.setMap(null);
      routeLine = null;
    }
    const c = candidates.find((x) => x.id === id);
    const path = c?.movement?.path;
    if (path?.length) {
      routeLine = new maps.Polyline({
        map,
        path: path.map(([la, ln]) => new maps.LatLng(la, ln)),
        strokeColor: TEAL,
        strokeWeight: 5,
        strokeOpacity: 0.9,
      });
    }
  }

  if (candidates[0]) focus(candidates[0].id);
  return {
    focus,
    onPinClick(cb) {
      pinClickCb = cb;
    },
  };
}
