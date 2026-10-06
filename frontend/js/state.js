// 클라이언트 상태 컨테이너. 화면 로직(pages/)과 분리.
export const state = {
  request: null, // 마지막 추천 요청 조건(payload)
  candidates: [], // 현재 후보 목록
  focusedId: null, // 포커스(스와이프/핀 탭) — 선택 확정과 다름
  selectedId: null, // Select experience 로 확정한 현재 선택 (선택 ≠ 방문)
};

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
}
