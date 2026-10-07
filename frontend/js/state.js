// 클라이언트 상태 컨테이너. 화면 로직(pages/)과 분리.
import { putSession } from "./api.js";
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
