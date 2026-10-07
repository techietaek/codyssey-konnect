// Supabase Auth (Phase 2 L1b) — 익명 세션 선발급 + 세션 JWT 제공.
// 백엔드는 이 JWT 를 검증만 한다(provider-agnostic). Google 로그인/연결은 L1d.
// 공개 설정(url·publishable key)은 /api/config 에서 받는다(비밀키 아님).
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { API_BASE } from "./config.js";

let _client = null;
let _ready = null;
let _signedIn = false; // 비익명(정식 로그인) 여부 — FR-L1 게이팅용 동기 플래그

async function init() {
  const cfg = await (await fetch(`${API_BASE}/api/config`)).json();
  if (!cfg.supabase_url || !cfg.supabase_publishable_key) return null;
  _client = createClient(cfg.supabase_url, cfg.supabase_publishable_key, {
    auth: { persistSession: true, autoRefreshToken: true },
  });

  _client.auth.onAuthStateChange((_event, session) => {
    _signedIn = !!session?.user && session.user.is_anonymous !== true;
  });

  // 세션이 없으면 익명으로 선발급(요청 조건·선택을 user_id 로 저장하기 위함, L1c)
  const {
    data: { session },
  } = await _client.auth.getSession();
  if (!session) {
    await _client.auth.signInAnonymously();
  } else {
    _signedIn = session.user?.is_anonymous !== true;
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
