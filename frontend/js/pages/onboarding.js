// P9-1 · 선호 온보딩 (Phase 2 L2 · FR-L3). 첫 Google 가입 직후 1회·1화면.
// 문화 관심사 6개 복수선택 + 'Prefer shorter walks'(단일·미선택 허용). 모두 Skip 가능.
// 신뢰: 걷기 선호는 Soft 신호일 뿐(수치 상한 아님) — Copy 로도 수치/제한을 암시하지 않는다.
const INTERESTS = [
  ["traditional_culture", "Traditional culture"],
  ["palaces_historic", "Palaces & historic"],
  ["hands_on", "Hands-on"],
  ["art_exhibitions", "Art & exhibitions"],
  ["live_performances", "Live performances"],
  ["festivals_events", "Festivals & events"],
];

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

  // 관심사(복수) — chip 토글. 선택 상태는 aria-pressed 로.
  root.append(el("h2", "onboarding-label", "What are you into?"));
  const chips = el("div", "onboarding-chips");
  const selected = new Set();
  for (const [code, label] of INTERESTS) {
    const chip = el("button", "chip", label);
    chip.type = "button";
    chip.setAttribute("aria-pressed", "false");
    chip.addEventListener("click", () => {
      const on = selected.has(code);
      if (on) selected.delete(code);
      else selected.add(code);
      chip.setAttribute("aria-pressed", String(!on));
    });
    chips.append(chip);
  }
  root.append(chips);

  // 걷기 선호(단일·미선택 허용). 체크 없음=선호 없음(null) — 기본값을 긍정/부정으로 두지 않음.
  const walkRow = el("label", "onboarding-walk");
  const walkBox = el("input");
  walkBox.type = "checkbox";
  walkRow.append(walkBox, el("span", null, "Prefer shorter walks"));
  root.append(walkRow);

  // 액션 — Save(선택 저장) / Skip(선호 없이 넘어가기, 둘 다 온보딩 노출은 종료).
  const actions = el("div", "onboarding-actions");
  const save = el("button", "btn-cta", "Save");
  save.type = "button";
  const skip = el("button", "sheet-dismiss", "Skip for now");
  skip.type = "button";

  save.addEventListener("click", () => {
    save.disabled = true;
    onSubmit?.({
      interests: [...selected],
      prefer_shorter_walks: walkBox.checked ? true : null,
    });
  });
  skip.addEventListener("click", () => {
    skip.disabled = true;
    onSkip?.();
  });

  actions.append(save, skip);
  root.append(actions);
  return root;
}
