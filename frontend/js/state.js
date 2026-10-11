// 클라이언트 상태 컨테이너. 화면 로직(pages/)과 분리.
import { getSession, postRoute, putSession } from "./api.js";
import { isSignedIn } from "./auth.js";

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
  const at = Date.now();
  try {
    localStorage.setItem(
      CHOICE_KEY,
      JSON.stringify({ request, env, candidateId, at }),
    );
  } catch {
    /* 저장 불가(시크릿 모드 등)여도 현 세션 선택은 유지 */
  }
  // 서버(계정)에도 영속 — 로그아웃·재로그인·기기 변경에도 '내가 고른 결과'가 유지되게(FR-L2).
  // 사용자가 고른 그 후보 1개 + origin 을 저장(참조+표시 스냅샷). 이는 '현재 선택' 상태 저장
  // (§4.4)이지 외부 API 응답 캐시가 아니다 — 추천 질의에 재사용하거나 타인에게 제공하지 않는다.
  const candidate = (env?.data?.candidates || []).find((c) => c.id === candidateId);
  putSession({
    last_request: request,
    current_choice: { candidateId, at, candidate, origin: env?.data?.origin, request },
  }).catch(() => {});
}

export function loadChoice() {
  try {
    return JSON.parse(localStorage.getItem(CHOICE_KEY) || "null");
  } catch {
    return null;
  }
}

// 서버(DB)에 저장된 현재 선택을 로컬로 복원 — 재로그인·기기 변경 시 '내가 고른 결과' 재현.
// 로그인 사용자만. 성공 시 localStorage 를 DB 스냅샷으로 채워 home/mypage(loadChoice)가 렌더.
export async function restoreChoiceFromServer() {
  if (!isSignedIn()) return false;
  if (loadChoice()) return true; // 로컬에 이미 있으면 덮어쓰지 않음(토큰 갱신 시 clobber 방지)
  try {
    const env = await getSession();
    const cc = env?.ok ? env.data?.current_choice : null;
    if (!cc?.candidate || !cc?.candidateId) return false;
    state.selectedId = cc.candidateId;
    const local = {
      request: cc.request,
      candidateId: cc.candidateId,
      at: cc.at,
      env: { data: { candidates: [cc.candidate], origin: cc.origin } },
    };
    try {
      localStorage.setItem(CHOICE_KEY, JSON.stringify(local));
    } catch {
      /* noop */
    }
    return true;
  } catch {
    return false;
  }
}

// 로그아웃 시 로컬 뷰만 비운다(DB 는 유지 → 재로그인하면 복원). 서버 삭제는 명시적 ✕ 때만.
export function clearLocalChoice() {
  state.selectedId = null;
  try {
    localStorage.removeItem(CHOICE_KEY);
  } catch {
    /* noop */
  }
}

export function clearChoice() {
  state.selectedId = null;
  try {
    localStorage.removeItem(CHOICE_KEY);
  } catch {
    /* noop */
  }
  putSession({ current_choice: null }).catch(() => {}); // 명시적 삭제 → 서버도 비움
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

// 저장된 ref → 라이브 재조립(사실·경로선 신선). 시간창은 **저장 당시 시계시간을 오늘 날짜로**
// 쓴다 — 시간 판정은 '지금'이 아니라 '창 대비 운영시간'이라, 지금이 몇 시든 저장한 방문 시간대
// (예: 14:00–18:00) 기준으로 판정돼 루트가 유지된다(now 기준 창은 심야엔 전부 closed 가 됨).
// pin_titles 로 저장 스톱을 고정 복원하고, 못 찾은 스톱은 조용히 빠진다. 실패/빈결과는 null.
export async function rebuildSavedRoute(ref) {
  if (!ref?.stops?.length) return null;
  const sh = String(ref.start_hm || "10:00");
  let eh = String(ref.end_hm || "18:00");
  // 종료가 시작 이하(비정상)면 안전하게 시작+4시간으로.
  if (eh <= sh) {
    const [h, m] = sh.split(":").map(Number);
    const e = new Date();
    e.setHours(h + 4, m, 0, 0);
    eh = `${String(e.getHours()).padStart(2, "0")}:${String(e.getMinutes()).padStart(2, "0")}`;
  }
  const d = new Date();
  const ymd = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  try {
    const env = await postRoute({
      start_location: ref.origin || { label: "Current location" },
      start_at: `${ymd}T${sh}:00`,
      end_at: `${ymd}T${eh}:00`,
      pin_titles: ref.stops,
    });
    return env?.ok ? (env.data ?? null) : null;
  } catch {
    return null;
  }
}
