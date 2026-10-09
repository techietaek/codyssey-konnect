// P9-2 · 선호 온보딩 (Phase 2 L2 · FR-L3). 첫 Google 가입 직후 1회·1화면.
// 관심사 6개 복수선택 + 자유입력("Anything else?") → AI 해석 → "We'll remember" 칩.
// 입력부는 components/preference-form 공용(My Page MP-2 와 동일 UI). 모두 Skip 가능.
import { createPreferenceForm } from "../components/preference-form.js";

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

// onSubmit({ interests, prefer_shorter_walks, open_preferences }) · onSkip()
export function renderOnboardingView({ onSubmit, onSkip } = {}) {
  const root = el("section", "onboarding");

  root.append(el("p", "onboarding-kicker", "Welcome to KONNECT"));
  const header = el("div", "onboarding-head");
  header.append(
    el("h1", "onboarding-title", "What do you enjoy?"),
    el(
      "p",
      "onboarding-sub",
      "Optional. We'll use this for future suggestions. Your current search stays as it is.",
    ),
  );
  root.append(header);

  const form = createPreferenceForm();
  root.append(form.element);

  root.append(
    el(
      "p",
      "onboarding-foot",
      "You can change or reset this anytime in My Page.",
    ),
  );

  // 액션 — Save and continue / Skip for now (둘 다 온보딩 노출은 종료).
  const actions = el("div", "onboarding-actions");
  const save = el("button", "btn-cta", "Save and continue");
  save.type = "button";
  const skip = el("button", "sheet-dismiss", "Skip for now");
  skip.type = "button";

  // 해석 중이면 저장 잠시 비활성(P9-2b) — 해석 끝나면 복구.
  form.onBusyChange((busy) => {
    save.disabled = busy;
    save.textContent = busy ? "Reading…" : "Save and continue";
  });

  save.addEventListener("click", () => {
    save.disabled = true;
    onSubmit?.(form.getValues());
  });
  skip.addEventListener("click", () => {
    skip.disabled = true;
    onSkip?.();
  });

  actions.append(save, skip);
  root.append(actions);
  return root;
}
