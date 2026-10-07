// 뷰 컨트롤러: 웰컴(W-0) → 홈(LF-01) → 입력(LF-02) → 결과(LF-03) 전환.
// 단일 #view 컨테이너에 주입. 결과는 지도-풀스크린(full-bleed)이라 뷰별로
// .app 패딩을 토글한다.
import { postRecommend, putSession } from "./api.js";
import { ready as authReady } from "./auth.js";
import { renderWelcomeView } from "./pages/welcome.js";
import { renderHomeView } from "./pages/home.js";
import { renderInputView } from "./pages/input.js";
import { renderLoadingView } from "./pages/loading.js";
import { renderErrorView } from "./pages/error.js";
import { renderResultsView } from "./pages/results.js";
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
    renderHomeView({ onStartA: () => showInput(), onViewChoice: showResults }),
    { fullBleed: true },
  );
}

export function showInput(prefill) {
  mount(
    renderInputView({
      prefill,
      onBack: showHome,
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
});
