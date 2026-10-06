// 클라이언트 상태 컨테이너(골격). 화면 로직(pages/)과 분리.
// Phase 0 에서는 최소 필드만. 요청조건·현재선택은 이후 슬라이스에서 확장.
export const state = {
  request: null,       // 마지막 추천 요청 조건
  candidates: [],      // 현재 후보 목록
  focusedId: null,     // 포커스(스와이프/핀 탭) — 선택 확정과 다름
  selectedId: null,    // Select experience 로 확정한 현재 선택 (선택 ≠ 방문)
};

export function setResults(req, candidates) {
  state.request = req;
  state.candidates = candidates;
  state.focusedId = candidates[0]?.id ?? null;
}
