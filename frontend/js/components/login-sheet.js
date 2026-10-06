// LF-06 · 로그인 유도 바텀시트 (FR-L1). 비회원이 'Find new options'을 누를 때.
// 디자인은 구현하되 'Continue with Google'은 비활성 — 실제 Supabase Auth(OAuth)는
// Phase 2. 현재 결과/선택은 그대로 유지된다는 점을 문구로 안내.
function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

export function showLoginSheet({ onEditInstead } = {}) {
  document.querySelector(".sheet-scrim")?.remove();

  const scrim = el("div", "sheet-scrim");
  const sheet = el("div", "sheet");
  sheet.setAttribute("role", "dialog");
  sheet.setAttribute("aria-modal", "true");

  sheet.append(
    el("div", "sheet-grip"),
    el("h2", "sheet-title", "Sign in to find new options"),
    el(
      "p",
      "sheet-sub",
      "New recommendations need a Google sign-in. Your current results and choice stay as they are.",
    ),
  );

  const google = el("button", "btn-google", "Continue with Google");
  google.type = "button";
  google.disabled = true;
  google.setAttribute("aria-disabled", "true");
  google.title = "Coming in a later phase";
  const soon = el("span", "sheet-soon", "Available in a later phase");
  sheet.append(google, soon);

  const not = el("button", "sheet-dismiss", "Not now");
  not.type = "button";
  sheet.append(not);

  function close() {
    scrim.classList.remove("is-open");
    setTimeout(() => scrim.remove(), 220);
  }
  not.addEventListener("click", close);
  scrim.addEventListener("click", (e) => {
    if (e.target === scrim) close();
  });
  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key === "Escape") close();
    },
    { once: true },
  );

  scrim.append(sheet);
  // device-frame 안에 담아 데스크톱 목업 밖으로 넘치지 않게(모바일은 화면 전체).
  (document.querySelector(".device-frame") || document.body).append(scrim);
  // 다음 프레임에 open 클래스 → 슬라이드업 트랜지션
  requestAnimationFrame(() => scrim.classList.add("is-open"));

  return { close };
}
