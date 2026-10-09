// 선호 입력 공용 컴포넌트 (L2 온보딩 P9-2 · L3 My Page MP-2 공용).
// 관심사 6개 복수선택 + "Anything else?" 자유입력 → AI 해석(postParse) → "We'll remember"
// 칩(× 제거). 10/8: 걷기 체크박스를 자유입력으로 대체(걷기는 해석 결과로 들어온다).
// 신뢰: 개방형 선호·걷기 선호는 Soft 신호만. 해석 실패는 graceful(기존 상태 유지).
import { postParse } from "../api.js";

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

// createPreferenceForm({ interests?, preferShorterWalks?, openPreferences? })
//   → { element, getValues, isBusy, onBusyChange }
//   getValues(): { interests, prefer_shorter_walks, open_preferences }
export function createPreferenceForm({
  interests = [],
  preferShorterWalks = false,
  openPreferences = [],
} = {}) {
  const root = el("div", "pref-form");
  const selected = new Set(interests);
  // "We'll remember" 의 원천(편집 가능). 걷기 선호 + 개방형 선호.
  let walks = !!preferShorterWalks;
  let opens = [...openPreferences];
  let busy = false;
  const busyListeners = [];
  function setBusy(b) {
    busy = b;
    for (const f of busyListeners) f(b);
  }

  // ── 관심사 ──
  root.append(el("h2", "onboarding-label", "Interests · pick any"));
  const chips = el("div", "onboarding-chips");
  const chipEls = new Map();
  for (const [code, label] of INTERESTS) {
    const chip = el("button", "chip", label);
    chip.type = "button";
    chip.setAttribute("aria-pressed", String(selected.has(code)));
    chip.addEventListener("click", () => {
      const now = selected.has(code);
      if (now) selected.delete(code);
      else selected.add(code);
      chip.setAttribute("aria-pressed", String(!now));
    });
    chipEls.set(code, chip);
    chips.append(chip);
  }
  root.append(chips);

  // ── 자유입력 ──
  root.append(el("h2", "onboarding-label", "Anything else? (optional)"));
  const nlCard = el("div", "nl-input");
  const ta = el("textarea", "nl-textarea");
  ta.maxLength = 300;
  ta.placeholder = "e.g. Shorter walks, quieter places, not too late at night";
  const footer = el("div", "nl-footer2");
  const counter = el("span", "nl-counter", "0/300");
  footer.append(counter);
  nlCard.append(ta, footer);
  root.append(nlCard);

  // ── We'll remember (해석 결과 칩, × 제거) ──
  const remember = el("div", "remember");
  const rememberChips = el("div", "remember-chips");
  remember.append(
    el("p", "remember-label", "We'll remember"),
    rememberChips,
    el("p", "remember-hint", "Remove anything that isn't right, or edit your note."),
  );
  root.append(remember);

  function renderRemember() {
    rememberChips.replaceChildren();
    const items = [];
    if (walks) items.push({ text: "Shorter walks", remove: () => (walks = false) });
    for (const p of opens)
      items.push({ text: p, remove: () => (opens = opens.filter((x) => x !== p)) });
    for (const it of items) {
      const chip = el("span", "remember-chip");
      chip.append(el("span", null, it.text));
      const x = el("button", "remember-chip-x", "✕");
      x.type = "button";
      x.setAttribute("aria-label", `Remove ${it.text}`);
      x.addEventListener("click", () => {
        it.remove();
        renderRemember();
      });
      chip.append(x);
      rememberChips.append(chip);
    }
    remember.hidden = items.length === 0;
  }
  renderRemember();

  // 자유입력 → 디바운스 해석 → remember 병합. (기존 칩 유지 + 새 해석 추가)
  let timer = 0;
  ta.addEventListener("input", () => {
    counter.textContent = `${ta.value.length}/300`;
    clearTimeout(timer);
    const text = ta.value.trim();
    if (!text) return;
    setBusy(true);
    timer = window.setTimeout(async () => {
      try {
        const env = await postParse(text);
        const c = env?.ok ? env.data : null;
        if (c) {
          for (const code of c.interests || []) {
            if (!selected.has(code)) {
              selected.add(code);
              chipEls.get(code)?.setAttribute("aria-pressed", "true");
            }
          }
          if (c.prefer_shorter_walks) walks = true;
          const add = [...(c.open_preferences || [])];
          if (c.indoor_outdoor)
            add.push(c.indoor_outdoor === "indoor" ? "Indoor" : "Outdoor");
          for (const p of add)
            if (p && !opens.some((x) => x.toLowerCase() === p.toLowerCase()))
              opens.push(p);
          renderRemember();
        }
      } catch {
        /* 해석 실패는 조용히 무시(기존 상태 유지) */
      } finally {
        setBusy(false);
      }
    }, 650);
  });

  function getValues() {
    return {
      interests: [...selected],
      prefer_shorter_walks: walks ? true : null,
      open_preferences: opens,
    };
  }

  return {
    element: root,
    getValues,
    isBusy: () => busy,
    onBusyChange: (f) => busyListeners.push(f),
  };
}
