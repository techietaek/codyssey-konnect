// Supabase Auth (Phase 2 L1b) — 익명 세션 선발급 + 세션 JWT 제공.
// 백엔드는 이 JWT 를 검증만 한다(provider-agnostic). Google 로그인/연결은 L1d.
// 공개 설정(url·publishable key)은 /api/config 에서 받는다(비밀키 아님).
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { API_BASE } from "./config.js";

let _client = null;
let _ready = null;
let _signedIn = false; // 비익명(정식 로그인) 여부 — FR-L1 게이팅용 동기 플래그
let _displayName = null; // 정식 로그인 시 표시 이름(Google) — 동기 캐시
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

function _applySession(session) {
  const u = session?.user;
  _signedIn = !!u && u.is_anonymous !== true;
  _displayName = _signedIn ? _nameFrom(u) : null;
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

  _client.auth.onAuthStateChange((_event, session) => {
    _applySession(session);
    _listeners.forEach((l) => {
      try {
        l();
      } catch {
        /* 구독자 오류가 auth 를 막지 않게 */
      }
    });
  });

  // OAuth 복귀 에러 처리: 이 Google 계정이 이미 다른(이전) user 에 연결된 경우
  // (identity_already_exists). 링크 대신 기존 계정으로 **로그인**(signInWithOAuth)으로
  // 1회 폴백(루프 방지 플래그). 그 외/재시도 후에는 URL 에러 파라미터만 정리.
  const _params = new URLSearchParams(
    window.location.search.slice(1) + "&" + window.location.hash.slice(1),
  );
  const _alreadyLinked = _params.get("error_code") === "identity_already_exists";
  if (_alreadyLinked && !sessionStorage.getItem("konnect.oauthRetry")) {
    sessionStorage.setItem("konnect.oauthRetry", "1");
    await _client.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin + window.location.pathname },
    });
    return _client; // Google 로 리다이렉트됨(기존 계정 로그인)
  }
  sessionStorage.removeItem("konnect.oauthRetry");
  if (_params.has("error_code")) {
    // 에러 파라미터가 남지 않게 URL 정리(새로고침 시 재트리거 방지)
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
    await _client.auth.signInAnonymously();
    const { data } = await _client.auth.getSession();
    _applySession(data.session);
  } else {
    // identity linking 직후엔 기존 토큰에 is_anonymous=true 클레임이 남아있다.
    // 익명 클레임이면 서버에서 토큰을 refresh → 링크됐으면 새 토큰은 is_anonymous=false
    // (+ Google user_metadata). 진짜 익명이면 그대로 익명.
    let current = session;
    if (current?.user?.is_anonymous === true) {
      const { data } = await _client.auth.refreshSession();
      if (data?.session) current = data.session;
    }
    _applySession(current);
    // 세션 user 객체가 identities/metadata 를 덜 담고 있으면 이름이 비는 경우가 있다.
    // 로그인 상태인데 이름이 없으면 getUser() 로 완전한 user 를 한 번 더 받아 보강
    // → 잡히면 구독자 통지로 홈/온보딩 greeting 갱신(graceful, 실패 무영향).
    if (_signedIn && !_displayName) {
      try {
        const { data } = await _client.auth.getUser();
        const name = data?.user ? _nameFrom(data.user) : null;
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
  const redirectTo = window.location.href;
  const {
    data: { session },
  } = await _client.auth.getSession();
  const opts = { provider: "google", options: { redirectTo } };
  const { error } = session?.user?.is_anonymous
    ? await _client.auth.linkIdentity(opts)
    : await _client.auth.signInWithOAuth(opts);
  if (error) throw error;
}

export function supabase() {
  return _client;
}
