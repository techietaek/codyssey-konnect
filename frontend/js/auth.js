// Supabase Auth (Phase 2 L1b) — 익명 세션 선발급 + 세션 JWT 제공.
// 백엔드는 이 JWT 를 검증만 한다(provider-agnostic). Google 로그인/연결은 L1d.
// 공개 설정(url·publishable key)은 /api/config 에서 받는다(비밀키 아님).
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { API_BASE } from "./config.js";

let _client = null;
let _ready = null;
let _signedIn = false; // 비익명(정식 로그인) 여부 — FR-L1 게이팅용 동기 플래그
let _displayName = null; // 정식 로그인 시 표시 이름(Google) — 동기 캐시
let _email = null; // 정식 로그인 시 이메일(My Page 계정 표시) — 동기 캐시
const _listeners = new Set(); // 세션 변경 구독자(화면 갱신용)

// Google 표시이름 추출. 익명→Google **링크** 계정은 이름이 user_metadata 가 아니라
// identities[].identity_data 에만 있을 수 있어 둘 다 확인한다.
function _nameFrom(u) {
  const m = u?.user_metadata || {};
  let name = m.full_name || m.name || m.email || null;
  if (!name && Array.isArray(u?.identities)) {
    for (const idn of u.identities) {
      const d = idn?.identity_data || {};
      name = d.full_name || d.name || d.email || null;
      if (name) break;
    }
  }
  return name;
}

function _emailFrom(u) {
  const m = u?.user_metadata || {};
  let email = u?.email || m.email || null;
  if (!email && Array.isArray(u?.identities)) {
    for (const idn of u.identities) {
      email = idn?.identity_data?.email || null;
      if (email) break;
    }
  }
  return email;
}

function _applySession(session) {
  const u = session?.user;
  _signedIn = !!u && u.is_anonymous !== true;
  _displayName = _signedIn ? _nameFrom(u) : null;
  _email = _signedIn ? _emailFrom(u) : null;
}

// 세션 상태가 바뀌면(로그인/로그아웃/OAuth 복귀) 구독자에게 통지 → 화면 재렌더.
export function onAuthChange(cb) {
  _listeners.add(cb);
  return () => _listeners.delete(cb);
}

async function init() {
  const cfg = await (await fetch(`${API_BASE}/api/config`)).json();
  if (!cfg.supabase_url || !cfg.supabase_publishable_key) return null;
  _client = createClient(cfg.supabase_url, cfg.supabase_publishable_key, {
    auth: { persistSession: true, autoRefreshToken: true },
  });

  _client.auth.onAuthStateChange((event, session) => {
    if (event === "SIGNED_OUT") {
      _signedIn = false;
      _displayName = null;
      _email = null;
    } else {
      _applySession(session);
    }
    _listeners.forEach((l) => {
      try {
        l();
      } catch {
        /* 구독자 오류가 auth 를 막지 않게 */
      }
    });
  });

  // 에러 파라미터가 URL 에 남았으면 정리(새로고침 시 재트리거 방지).
  if (/[?#&]error/.test(window.location.search + window.location.hash)) {
    history.replaceState({}, "", window.location.origin + window.location.pathname);
  }

  // OAuth 복귀(해시/쿼리에 토큰·코드)면 세션이 곧 수립되므로 익명 재로그인하지 않는다
  // (익명 세션이 Google 세션을 덮지 않게). detectSessionInUrl 이 처리.
  const returning = /[#&?](access_token|code)=/.test(
    window.location.hash + window.location.search,
  );
  const {
    data: { session },
  } = await _client.auth.getSession();
  if (!session && !returning) {
    // 비로그인: 익명 세션 선발급(백엔드 JWT 연속성). 로그인은 signInWithGoogle(표준 OAuth).
    await _client.auth.signInAnonymously();
    const { data } = await _client.auth.getSession();
    _applySession(data.session);
  } else {
    _applySession(session);
    // 세션 user 객체가 identities/metadata 를 덜 담고 있으면 이름이 비는 경우가 있다.
    // 로그인 상태인데 이름이 없으면 getUser() 로 완전한 user 를 한 번 더 받아 보강
    // → 잡히면 구독자 통지로 홈/온보딩 greeting 갱신(graceful, 실패 무영향).
    if (_signedIn && (!_displayName || !_email)) {
      try {
        const { data } = await _client.auth.getUser();
        const name = data?.user ? _nameFrom(data.user) : null;
        const email = data?.user ? _emailFrom(data.user) : null;
        if (email) _email = email;
        if (name) {
          _displayName = name;
          _listeners.forEach((l) => {
            try {
              l();
            } catch {
              /* 구독자 오류 격리 */
            }
          });
        }
      } catch {
        /* 이름 보강 실패해도 'Welcome' fallback 으로 진행 */
      }
    }
  }
  return _client;
}

// 최초 1회 초기화(실패해도 추천은 비인증으로 진행 — graceful).
export function ready() {
  if (!_ready)
    _ready = init().catch((e) => {
      console.warn("auth init failed:", e?.message || e);
      return null;
    });
  return _ready;
}

export async function getToken() {
  await ready();
  if (!_client) return null;
  const {
    data: { session },
  } = await _client.auth.getSession();
  return session?.access_token ?? null;
}

// 정식 로그인(비익명) 여부 — 동기(캐시). 익명 세션은 false.
export function isSignedIn() {
  return _signedIn;
}

// 정식 로그인 시 표시 이름(Google) — 없으면 null. 동기(캐시).
export function displayName() {
  return _displayName;
}

// 정식 로그인 시 이메일(My Page) — 없으면 null. 동기(캐시).
export function userEmail() {
  return _email;
}

// 로그아웃 → 깨끗이 재부트(홈=로그인 전 상태, 익명 세션 재발급).
export async function signOut() {
  await ready();
  if (_client) await _client.auth.signOut();
  window.location.reload();
}

// Google 로그인 (L1d). 익명 세션이 있으면 **identity linking**으로 동일 user_id 를
// 영구 계정으로 승격(데이터 자동 보존, FR-L2). 아니면 일반 OAuth. 둘 다 Google 로
// 리다이렉트되고, 돌아오면 supabase-js 가 세션을 복원한다(detectSessionInUrl).
export async function signInWithGoogle() {
  await ready();
  if (!_client) throw new Error("Auth is not ready.");
  // 표준 OAuth 로그인(항상). 익명 identity linking 은 쓰지 않는다 — returning user 의
  // identity_already_exists / is_anonymous stale 로 "재로그인이 안 되는" 문제와, 모바일
  // 시크릿창의 저장소 왕복 취약성을 피하기 위함. (대가: FR-L2 비로그인→계정 데이터 자동
  // 이관 미지원. 되살리려면 session.user.is_anonymous 시 linkIdentity 분기를 복원.)
  const { error } = await _client.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: window.location.origin + window.location.pathname },
  });
  if (error) throw error;
}

export function supabase() {
  return _client;
}
