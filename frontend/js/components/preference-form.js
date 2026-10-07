// 선호 입력 공용 컴포넌트 (L2 온보딩 P9-1 · L3 My Page MP-2 공용).
// 관심사 6개 복수선택 + 'Prefer shorter walks'(단일·미선택 허용). 제목/액션은
// 화면마다 달라 포함하지 않는다 — 이 컴포넌트는 입력부(칩+체크)와 값 수집만.
// 신뢰: 걷기 선호는 Soft 신호(수치 상한 아님, FR-L4). 미선택=null 유지(긍정 기본값 금지).
export const INTERESTS = [
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

// createPreferenceForm({ interests?, preferShorterWalks? })
//   → { element, getValues }  // getValues(): { interests, prefer_shorter_walks }
// interests: 초기 선택 코드 배열(MP-2 수정 시 prefill). preferShorterWalks: 초기 체크.
export function createPreferenceForm({
  interests = [],
  preferShorterWalks = false,
} = {}) {
  const root = el("div", "pref-form");
  const selected = new Set(interests);

  root.append(el("h2", "onboarding-label", "What are you into?"));
  const chips = el("div", "onboarding-chips");
  for (const [code, label] of INTERESTS) {
    const chip = el("button", "chip", label);
    chip.type = "button";
    const on = selected.has(code);
    chip.setAttribute("aria-pressed", String(on));
    chip.addEventListener("click", () => {
      const now = selected.has(code);
      if (now) selected.delete(code);
      else selected.add(code);
      chip.setAttribute("aria-pressed", String(!now));
    });
    chips.append(chip);
  }
  root.append(chips);

  // 걷기 선호(단일·미선택 허용). 체크 없음=선호 없음(null).
  const walkRow = el("label", "onboarding-walk");
  const walkBox = el("input");
  walkBox.type = "checkbox";
  walkBox.checked = !!preferShorterWalks;
  walkRow.append(walkBox, el("span", null, "Prefer shorter walks"));
  root.append(walkRow);

  function getValues() {
    return {
      interests: [...selected],
      prefer_shorter_walks: walkBox.checked ? true : null,
    };
  }

  return { element: root, getValues };
}
