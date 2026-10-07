// P9-1 · 선호 온보딩 (Phase 2 L2 · FR-L3). 첫 Google 가입 직후 1회·1화면.
// 문화 관심사 6개 복수선택 + 'Prefer shorter walks'(단일·미선택 허용). 모두 Skip 가능.
// 입력부(칩+체크)는 components/preference-form 공용 — My Page(MP-2)와 동일 UI.
import { createPreferenceForm } from "../components/preference-form.js";

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

// onSubmit({ interests, prefer_shorter_walks }) · onSkip()
export function renderOnboardingView({ onSubmit, onSkip, name } = {}) {
  const root = el("section", "onboarding");

  const header = el("div", "onboarding-head");
  header.append(
    el(
      "h1",
      "onboarding-title",
      name ? `Welcome, ${name.split(" ")[0]}` : "Welcome",
    ),
    el(
      "p",
      "onboarding-sub",
      "Tell us what you enjoy so we can tailor suggestions. You can change this anytime — or skip for now.",
    ),
  );
  root.append(header);

  const form = createPreferenceForm();
  root.append(form.element);

  // 액션 — Save(선택 저장) / Skip(선호 없이 넘어가기, 둘 다 온보딩 노출은 종료).
  const actions = el("div", "onboarding-actions");
  const save = el("button", "btn-cta", "Save");
  save.type = "button";
  const skip = el("button", "sheet-dismiss", "Skip for now");
  skip.type = "button";

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
