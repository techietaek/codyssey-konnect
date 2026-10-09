// P9-2 · 선호 온보딩 (Phase 2 L2 · FR-L3). 첫 Google 가입 직후 1회·1화면.
// 관심사 6개 복수선택 + 자유입력("Anything else?"). Save and continue 를 누르면
// 확인 모달(components/pref-confirm)에서 이름·이메일 + 해석 결과("Also")를 보여준 뒤
// 저장한다. 인라인 해석은 하지 않는다(autoParse=false).
import { displayName, userEmail } from "../auth.js";
import { createPreferenceForm } from "../components/preference-form.js";
import { openPrefConfirm } from "../components/pref-confirm.js";

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

  const form = createPreferenceForm({ autoParse: false });
  root.append(form.element);

  root.append(
    el("p", "onboarding-foot", "You can change or reset this anytime in My Page."),
  );

  const actions = el("div", "onboarding-actions");
  const save = el("button", "btn-cta", "Save and continue");
  save.type = "button";
  const skip = el("button", "sheet-dismiss", "Skip for now");
  skip.type = "button";
  save.addEventListener("click", () =>
    openPrefConfirm({
      form,
      account: { name: displayName(), email: userEmail() },
      onConfirm: (values) => {
        save.disabled = true;
        onSubmit?.(values);
      },
    }),
  );
  skip.addEventListener("click", () => {
    skip.disabled = true;
    onSkip?.();
  });
  actions.append(save, skip);
  root.append(actions);

  return root;
}
