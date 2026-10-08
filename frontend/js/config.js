// 프론트 런타임 설정 — 백엔드 API 베이스.
// 로컬(localhost)은 로컬 백엔드, 그 외(배포)는 PROD_API(Render URL)를 쓴다.
// 필요 시 window.KONNECT_API_BASE 로 강제 덮어쓸 수 있다(빌드 없이).
const PROD_API = "https://REPLACE-WITH-RENDER-URL.onrender.com"; // ← Render 백엔드 URL로 교체
const LOCAL_HOSTS = ["localhost", "127.0.0.1"];

export const API_BASE =
  window.KONNECT_API_BASE ||
  (LOCAL_HOSTS.includes(location.hostname) ? "http://localhost:8000" : "https://codyssey-konnect.onrender.com");
