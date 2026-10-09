// 뷰 컨트롤러: 웰컴(W-0) → 홈(LF-01) → 입력(LF-02) → 결과(LF-03) 전환.
// 단일 #view 컨테이너에 주입. 결과는 지도-풀스크린(full-bleed)이라 뷰별로
// .app 패딩을 토글한다.
import { postRecommend, putSession, getPreferences, putPreferences } from "./api.js";
import { ready as authReady, onAuthChange, isSignedIn, displayName } from "./auth.js";
import { renderWelcomeView } from "./pages/welcome.js";
import { renderHomeView } from "./pages/home.js";
import { renderInputView } from "./pages/input.js";
import { renderLoadingView } from "./pages/loading.js";
import { renderErrorView } from "./pages/error.js";
import { renderResultsView } from "./pages/results.js";
import { renderChatView } from "./pages/chat.js";
import { renderOnboardingView } from "./pages/onboarding.js";
import { renderMyPageView } from "./pages/mypage.js";
import { setResults } from "./state.js";

const viewEl = document.getElementById("view");
const WELCOME_KEY = "konnect.seenWelcome";

// fullBleed=true → 지도가 프레임을 꽉 채우는 결과 뷰(패딩 제거).
function mount(node, { fullBleed = false } = {}) {
  viewEl.classList.toggle("app--bleed", fullBleed);
  viewEl.replaceChildren(node);
  viewEl.scrollTop = 0;
}

export function showWelcome() {
  mount(renderWelcomeView({ onStart: markSeenAndHome }), { fullBleed: true });
}

export function showHome() {
  mount(
    renderHomeView({
      onStartA: () => showInput(),
      onOpenChat: showChat,
      onViewChoice: showResults,
      onOpenMyPage: showMyPage,
    }),
    { fullBleed: true },
  );
}

// AG-4 단일 챗봇 — FAQ(RAG)·즉시추천·문화루트를 하나의 대화 흐름으로.
export function showChat() {
  mount(renderChatView({ onBack: showHome }), { fullBleed: true });
}

// My Page (L3) — 로그인 사용자만 진입(홈 Account). 뒤로=홈, 선택 보기=결과.
export function showMyPage() {
  mount(renderMyPageView({ onBack: showHome, onViewChoice: showResults }));
}

export function showInput(prefill) {
  mount(
    renderInputView({
      prefill,
      onBack: showHome,
      onHome: showHome,
      onRecommend: startRecommend,
    }),
  );
}

// 공통 조회 플로우: 로딩(shimmer) → 성공(결과) / 취소(입력) / 실패(오류 화면).
export function startRecommend(payload) {
  const controller = new AbortController();
  let done = false;

  mount(
    renderLoadingView({
      request: payload,
      conditions: payload.conditions ?? null,
      onCancel: () => {
        if (done) return;
        done = true;
        controller.abort();
        showInput(payload); // 입력값 유지한 채 복귀
      },
    }),
    { fullBleed: true },
  );

  postRecommend(payload, controller.signal)
    .then((env) => {
      if (done) return; // 취소됨
      done = true;
      if (!env.ok) {
        showError(payload); // 시스템 예외 → 전용 오류 화면
        return;
      }
      setResults(payload, env.data.candidates);
      // 현재 요청조건을 서버에 영속(선택 전에도 연속성 — L1c/FR-L2). 실패 무영향.
      putSession({ last_request: payload }).catch(() => {});
      showResults({ request: payload, env });
    })
    .catch(() => {
      if (done) return; // Cancel 로 인한 AbortError
      done = true;
      showError(payload); // 네트워크 실패 → 전용 오류 화면
    });
}

// 전용 오류 화면 — 조건 유지, Try again / Edit conditions.
export function showError(request) {
  mount(
    renderErrorView({
      request,
      conditions: request.conditions ?? null,
      onRetry: () => startRecommend(request),
      onEdit: () => showInput(request),
      onBack: () => showInput(request),
    }),
    { fullBleed: true },
  );
}

export function showResults({ request, env }) {
  mount(
    renderResultsView({
      request,
      env,
      onBack: showHome,
      onEdit: () => showInput(request),
    }),
    { fullBleed: true },
  );
}

// P9-1 선호 온보딩 — 정식 가입 후 '처음 한 번'만. needs_onboarding 은 서버가 판정
// (onboarded_at 부재). Save·Skip 둘 다 PUT 으로 노출을 종료시켜 재노출을 막는다.
let onboardingChecked = false; // 로드당 1회만 서버 확인(중복 onAuthChange 방어)

export function showOnboarding() {
  const finish = (fields) =>
    putPreferences(fields)
      .catch(() => {}) // 저장 실패해도 흐름을 막지 않음(graceful)
      .finally(showHome);
  mount(
    renderOnboardingView({
      name: displayName(),
      onSubmit: finish,
      onSkip: () => finish({ interests: [], prefer_shorter_walks: null }),
    }),
  );
}

async function maybeShowOnboarding() {
  if (onboardingChecked || !isSignedIn()) return;
  onboardingChecked = true;
  try {
    const env = await getPreferences();
    if (env.ok && env.data?.needs_onboarding) showOnboarding();
  } catch {
    /* 확인 실패 시 조용히 건너뜀(온보딩은 1회 Should) */
  }
}

function markSeenAndHome() {
  try {
    localStorage.setItem(WELCOME_KEY, "1");
  } catch {
    /* 저장 불가여도 진행 */
  }
  showHome();
}

// 첫 실행이면 웰컴(W-0), 이후엔 홈(LF-01)으로 진입.
let seen = false;
try {
  seen = localStorage.getItem(WELCOME_KEY) === "1";
} catch {
  /* noop */
}

// 세션(익명/정식) 준비 후 첫 화면을 그린다 → 홈의 로그인 상태(Hello·Log out)가
// 첫 페인트에 반영된다. auth 실패해도 화면은 그린다(비인증 진행).
authReady().finally(() => {
  if (seen) showHome();
  else showWelcome();
  // 가입 직후 복귀면(정식 로그인) 1회 온보딩. 홈 위에 덮어씀.
  maybeShowOnboarding();
});

// 로그인/로그아웃/OAuth 복귀로 세션이 바뀌면, 홈이 떠 있을 때 재렌더(Hello·Log out 반영).
onAuthChange(() => {
  if (document.querySelector(".home")) showHome();
  // 익명→Google 승격 직후 첫 로그인이면 온보딩(1회). 결과/선택 화면 위에는 띄우지 않음.
  if (document.querySelector(".home") || document.querySelector(".welcome"))
    maybeShowOnboarding();
  // 온보딩이 떠 있는데 이름이 뒤늦게(getUser 보강) 잡히면 greeting 갱신(레이스 보정).
  const title = document.querySelector(".onboarding-title");
  const name = displayName();
  if (title && name) title.textContent = `Welcome, ${name.split(" ")[0]}`;
});
