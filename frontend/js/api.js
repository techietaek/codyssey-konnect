// 백엔드 호출 래퍼. 모든 응답은 공통 봉투(Envelope) { ok, trace_id, data, error }.
import { API_BASE } from "./config.js";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  // 봉투를 그대로 반환 — 시스템 예외(ok=false)와 정상 결과(0건 등)를 호출부가 구분한다.
  return res.json();
}

export function getHealth() {
  return request("/health");
}

export function postRecommend(payload, signal) {
  return request("/api/recommend", {
    method: "POST",
    body: JSON.stringify(payload),
    signal, // 로딩 화면 Cancel 시 요청 취소(AbortController)
  });
}

// 확인 시트용 — note 를 '이해한 조건'으로만 구조화(추천 조회 없음).
export function postParse(note) {
  return request("/api/parse", {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}
