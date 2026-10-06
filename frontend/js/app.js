// 뷰 컨트롤러: 웰컴(W-0) → 홈(LF-01) → 입력(LF-02) → 결과(LF-03) 전환.
// 단일 #view 컨테이너에 주입. 결과는 지도-풀스크린(full-bleed)이라 뷰별로
// .app 패딩을 토글한다.
import { renderWelcomeView } from "./pages/welcome.js";
import { renderHomeView } from "./pages/home.js";
import { renderInputView } from "./pages/input.js";
import { renderResultsView } from "./pages/results.js";

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
      onResults: showResults,
      onViewChoice: showResults,
    }),
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
if (seen) showHome();
else showWelcome();
