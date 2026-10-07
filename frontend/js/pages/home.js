// LF-01 · 메인 홈 (M-1 첫 방문 / M-2 현재 선택 있음).
// A 즉시추천 = 활성, B 문화루트·Log in = 디자인 구현하되 비활성(Phase 2).
// 현재 선택이 있으면(A6 localStorage) 재접근 카드 + 미니맵을 상단에 노출.
import { displayName, signInWithGoogle, signOut } from "../auth.js";
import { renderMiniMap } from "../map.js";
import { clearChoice, isLoggedIn, loadChoice } from "../state.js";

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

function fmtTime(iso) {
  // 사용자-facing 문자열은 영어 우선(CLAUDE §5).
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

// "SEOUL · MON, OCT 6 · 3:14 PM"
function nowStamp() {
  const d = new Date();
  const date = d
    .toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
    })
    .toUpperCase();
  return `SEOUL · ${date} · ${fmtTime(d)}`;
}

// 비활성 코어액션 카드(B) — 클릭 불가, 'Coming soon' 배지.
function coreAction({ kicker, title, sub, cta, disabled, onClick }) {
  const card = el("button", "core-action");
  card.type = "button";
  if (disabled) {
    card.classList.add("is-disabled");
    card.disabled = true;
    card.setAttribute("aria-disabled", "true");
  } else {
    card.addEventListener("click", onClick);
  }
  const illo = el("div", "core-illo");
  if (disabled) illo.append(el("span", "soon-badge", "Phase 2"));
  const body = el("div", "core-body");
  body.append(
    el("span", "core-kicker", kicker),
    el("h3", "core-title", title),
    el("p", "core-sub", sub),
  );
  const ctaEl = el("span", "core-cta", cta);
  body.append(ctaEl);
  card.append(illo, body);
  return card;
}

export function renderHomeView({
  onStartA,
  onOpenChat,
  onViewChoice,
  onOpenMyPage,
}) {
  const root = el("section", "home");

  // 소프트 헤더 배경(일러스트 자리) — 토큰 그라디언트.
  root.append(el("div", "home-header-bg"));

  const content = el("div", "home-content");

  // 브랜드 행 (KONNECT · EN · [Account]) — Account 는 로그인(비익명) 시에만(L3 진입점).
  const brand = el("div", "home-brand");
  brand.append(el("span", "home-logo", "KONNECT"));
  const brandRight = el("div", "home-brand-right");
  brandRight.append(el("span", "home-lang", "EN"));
  if (isLoggedIn()) {
    const name = displayName();
    const account = el("button", "home-account");
    account.type = "button";
    account.title = "My Page";
    account.setAttribute("aria-label", "My Page");
    // 아바타 — 이름 첫 글자(없으면 사람 글리프).
    account.textContent = name ? name.trim()[0].toUpperCase() : "👤";
    account.addEventListener("click", () => onOpenMyPage?.());
    brandRight.append(account);
  }
  brand.append(brandRight);
  content.append(brand);

  // 인사
  const greeting = el("div", "home-greeting");
  // 로그인(비익명) 사용자에겐 Google 이름으로 Hello 인사.
  const name = isLoggedIn() ? displayName() : null;
  if (name) {
    greeting.append(el("p", "home-hello", `Hello, ${name.split(" ")[0]} 👋`));
  }
  greeting.append(
    el("p", "home-stamp", nowStamp()),
    el("h1", "home-head", "Find a cultural experience that fits your day."),
  );
  content.append(greeting);

  // M-2 · 현재 선택 재접근 (선택 ≠ 방문)
  const saved = loadChoice();
  const savedCand = saved?.env?.data?.candidates?.find(
    (c) => c.id === saved.candidateId,
  );
  if (savedCand) {
    const choice = el("div", "choice-card");
    const head = el("div", "choice-card-head");
    head.append(
      el("span", "choice-tag", "Your current choice"),
      el("span", "choice-when", "Today"),
    );
    const clear = el("button", "choice-clear", "✕");
    clear.type = "button";
    clear.title = "Clear current choice";
    clear.addEventListener("click", (e) => {
      e.stopPropagation();
      clearChoice();
      choice.remove();
      exploreLabel.textContent = "START HERE";
    });
    head.append(clear);

    const miniEl = el("div", "mini-map");
    const info = el("div", "choice-card-info");
    const texts = el("div", "choice-card-texts");
    texts.append(
      el("span", "choice-card-title", savedCand.title),
      el(
        "span",
        "choice-card-sub",
        `${fmtTime(saved.request.start_at)} session · from ${saved.request.start_location.label}`,
      ),
    );
    const view = el("span", "choice-card-view", "View →");
    info.append(texts, view);

    choice.append(head, miniEl, info);
    choice.addEventListener("click", () =>
      onViewChoice({ request: saved.request, env: saved.env }),
    );
    content.append(choice);

    // 미니맵: 실제 좌표·실제 경로만(임의 직선 금지). 실패 시 패널 숨김.
    renderMiniMap(miniEl, saved.env.data.origin, savedCand).catch(() => {});
  }

  const exploreLabel = el(
    "p",
    "home-explore-label",
    savedCand ? "OR EXPLORE SOMETHING NEW" : "START HERE",
  );
  content.append(exploreLabel);

  // 코어 액션 A / B (동급 2열) — B 비활성
  const actions = el("div", "core-actions");
  actions.append(
    coreAction({
      kicker: "IMMEDIATE RECOMMENDATION",
      title: "Find something cultural to do now",
      sub: "Fits your location and the time you have.",
      cta: "Find experiences",
      disabled: false,
      onClick: onStartA,
    }),
    coreAction({
      kicker: "ASK OR PLAN",
      title: "Chat with KONNECT",
      sub: "Ask travel questions, get ideas, or plan a culture route.",
      cta: "Open chat",
      disabled: false,
      onClick: onOpenChat,
    }),
  );
  content.append(actions);

  // 신뢰 안내 (미확인 분리 고지) — M-1
  const info = el("div", "home-info");
  info.append(el("span", "home-info-icon", "i"));
  const infoText = el("div", "home-info-text");
  infoText.append(
    el("strong", null, "Know what still needs checking"),
    el(
      "span",
      null,
      "We flag information that needs checking instead of filling in the gaps.",
    ),
  );
  info.append(infoText);
  content.append(info);

  // Log in / Log out (화면 최하단, Figma). 로그인(비익명) 상태에 따라 분기. L1d.
  const login = el("div", "home-login");
  if (isLoggedIn()) {
    const logoutBtn = el("button", "home-login-btn", "Log out");
    logoutBtn.type = "button";
    logoutBtn.addEventListener("click", async () => {
      logoutBtn.disabled = true;
      logoutBtn.textContent = "Logging out…";
      try {
        await signOut(); // 성공 시 리로드(로그인 전 상태로)
      } catch (e) {
        logoutBtn.disabled = false;
        logoutBtn.textContent = "Log out";
        console.warn("sign-out failed:", e?.message || e);
      }
    });
    login.append(logoutBtn);
  } else {
    const loginBtn = el("button", "home-login-btn", "Log in");
    loginBtn.type = "button";
    loginBtn.addEventListener("click", async () => {
      loginBtn.disabled = true;
      loginBtn.textContent = "Redirecting…";
      try {
        await signInWithGoogle(); // 성공 시 Google 로 리다이렉트
      } catch (e) {
        loginBtn.disabled = false;
        loginBtn.textContent = "Log in";
        loginBtn.title = "Sign-in is unavailable right now.";
        console.warn("google sign-in failed:", e?.message || e);
      }
    });
    login.append(loginBtn);
  }
  content.append(login);

  root.append(content);
  return root;
}
