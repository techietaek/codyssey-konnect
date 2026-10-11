// 클라이언트 상태 컨테이너. 화면 로직(pages/)과 분리.
import { getSession, postRoute, putSession } from "./api.js";
import { isSignedIn } from "./auth.js";

function _localIso(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:00`;
}

export const state = {
  request: null, // 마지막 추천 요청 조건(payload)
  candidates: [], // 현재 후보 목록
  focusedId: null, // 포커스(스와이프/핀 탭) — 선택 확정과 다름
  selectedId: null, // Select experience 로 확정한 현재 선택 (선택 ≠ 방문)
};

// 정식 로그인(비익명) 여부. 익명 세션은 false → FR-L1(재추천 시 로그인 유도) 유지.
// Google 로그인/연결은 L1d에서 활성화되면 이 값이 true 가 된다.
export function isLoggedIn() {
  return isSignedIn();
}

export function setResults(request, candidates) {
  state.request = request;
  state.candidates = candidates;
  state.focusedId = candidates[0]?.id ?? null;
}

// ── 현재 선택 영속 (A6, 비로그인 — localStorage. Phase 2에서 계정 연결) ──
// 선택 ≠ 방문. GPS 자동 방문판정 없음.
const CHOICE_KEY = "konnect.currentChoice";

export function saveChoice(request, env, candidateId) {
  state.selectedId = candidateId;
  try {
    localStorage.setItem(
      CHOICE_KEY,
      JSON.stringify({ request, env, candidateId, at: Date.now() }),
    );
  } catch {
    /* 저장 불가(시크릿 모드 등)여도 현 세션 선택은 유지 */
  }
  // 서버(계정·익명)에도 미러 — 연속성·마이그레이션(L1d) 대비. 실패해도 UI 무영향.
  // env(후보 전체)는 저장하지 않는다 — 요청·선택 id만(복원 시 재조회가 정본).
  putSession({
    last_request: request,
    current_choice: { candidateId, at: Date.now() },
  }).catch(() => {});
}

export function loadChoice() {
  try {
    return JSON.parse(localStorage.getItem(CHOICE_KEY) || "null");
  } catch {
    return null;
  }
}

export function clearChoice() {
  state.selectedId = null;
  try {
    localStorage.removeItem(CHOICE_KEY);
  } catch {
    /* noop */
  }
  putSession({ current_choice: null }).catch(() => {}); // 서버 미러도 비움
}

// ── 저장된 B 문화루트 (DB 정본 — 로그아웃·기기 변경에도 유지. 참조만 저장, 열 때 라이브 재조립) ──
// ref = { stops:[title...], origin, start_at, end_at, note, conditions }. 사실(가격·경로선)은
// 저장하지 않는다 — 캐싱 금지 규약 준수 + 신선도(home/mypage 가 postRoute 로 매번 재조회).
export async function saveRoute(ref) {
  const env = await putSession({ current_route: { ...ref, at: Date.now() } });
  return env?.ok ?? false;
}

export async function loadRoute() {
  if (!isSignedIn()) return null; // 세션/토큰 없으면 호출 안 함(불필요한 401 방지)
  try {
    const env = await getSession();
    return env?.ok ? (env.data?.current_route ?? null) : null;
  } catch {
    return null; // 세션없음 → 저장 루트 없음(graceful)
  }
}

export async function clearRoute() {
  try {
    await putSession({ current_route: null });
  } catch {
    /* noop */
  }
}

// 저장된 ref → 라이브 재조립(사실·경로선 신선). 시간창은 '지금부터 저장 소요시간'으로 롤 —
// 저장 당시 시계시간을 오늘에 그대로 쓰면 시간대에 따라 전부 closed 로 사라질 수 있어서다.
// pin_titles 로 저장 스톱을 고정 복원하고, 못 찾은 스톱은 조용히 빠진다. 실패/빈결과는 null.
export async function rebuildSavedRoute(ref) {
  if (!ref?.stops?.length) return null;
  const [sh, sm] = String(ref.start_hm || "10:00").split(":").map(Number);
  const [eh, em] = String(ref.end_hm || "18:00").split(":").map(Number);
  let durMin = eh * 60 + em - (sh * 60 + sm);
  if (!(durMin > 0)) durMin = 4 * 60; // 안전 기본 4시간
  const start = new Date();
  start.setSeconds(0, 0);
  const end = new Date(start.getTime() + durMin * 60000);
  try {
    const env = await postRoute({
      start_location: ref.origin || { label: "Current location" },
      start_at: _localIso(start),
      end_at: _localIso(end),
      pin_titles: ref.stops,
    });
    return env?.ok ? (env.data ?? null) : null;
  } catch {
    return null;
  }
}
