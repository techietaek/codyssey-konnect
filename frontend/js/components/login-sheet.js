// LF-06 · 로그인 유도 바텀시트 (FR-L1). 비회원이 'Find new options'을 누를 때.
// 'Continue with Google' → Supabase OAuth(익명→identity linking, L1d). 현재 결과/
// 선택은 그대로 유지되고, 리다이렉트 후 돌아오면 동일 user_id 로 데이터 보존된다.
import { signInWithGoogle } from "../auth.js";

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
  const hint = el("span", "sheet-soon", "");
  hint.hidden = true;
  google.addEventListener("click", async () => {
    google.disabled = true;
    google.textContent = "Redirecting…";
    try {
      await signInWithGoogle(); // 성공 시 Google 로 리다이렉트(이 페이지를 떠남)
    } catch (e) {
      // 설정 누락(redirect 미허용·manual linking 비활성 등) → 여기서 드러난다.
      google.disabled = false;
      google.textContent = "Continue with Google";
      hint.hidden = false;
      hint.textContent = "Sign-in is unavailable right now. Please try again.";
      console.warn("google sign-in failed:", e?.message || e);
    }
  });
  sheet.append(google, hint);

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
