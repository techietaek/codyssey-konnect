// 선호 입력 공용 컴포넌트 (L2 온보딩 P9-2 · L3 My Page MP-2 공용).
// 관심사 6개 복수선택 + "Anything else?" 자유입력 → AI 해석(postParse, LLM 구조화).
// 신뢰: 개방형 선호·걷기 선호는 Soft 신호만. 해석 실패는 graceful(기존 상태 유지).
//
// autoParse(기본 true, My Page): 입력창 blur 시 바로 해석 + "We'll remember" 인라인 칩.
// autoParse=false(온보딩): 인라인 해석 안 함 — 호출부가 Save 시 runParse() 후 모달로 확인.
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

// createPreferenceForm({ interests?, preferShorterWalks?, openPreferences?, autoParse? })
//   → { element, getValues, runParse, hasNote, isBusy, onBusyChange }
//   getValues(): { interests, prefer_shorter_walks, open_preferences }
//   runParse(): 자유입력을 해석해 상태에 병합(async, 반환 = 뭔가 추가됐는지).
// 걷기 선호 tri-state 라벨: true=덜 걷기, false=걷기 좋아함, null=미언급(라벨 없음).
function walkLabel(w) {
  return w === true ? "Shorter walks" : w === false ? "Happy to walk" : null;
}

export function createPreferenceForm({
  interests = [],
  preferShorterWalks = null,
  openPreferences = [],
  autoParse = true,
} = {}) {
  const root = el("div", "pref-form");
  const selected = new Set(interests);
  // tri-state 보존: true/false/null 그대로(불리언 강제 금지 — false=걷기 좋아함을 잃지 않게).
  let walks =
    preferShorterWalks === true || preferShorterWalks === false
      ? preferShorterWalks
      : null;
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
  ta.addEventListener("input", () => {
    counter.textContent = `${ta.value.length}/300`;
  });

  // ── 인라인 "We'll remember"·상태(autoParse 모드에서만) ──
  let remember = null;
  let rememberChips = null;
  let status = null;
  function setStatus(kind) {
    if (!status) return;
    status.replaceChildren();
    status.hidden = kind === "none";
    if (kind === "reading")
      status.append(el("span", "pref-spinner"), el("span", null, "Reading your note…"));
    else if (kind === "empty")
      status.append(
        el("span", null, "We couldn't pick anything out. You can edit it or skip."),
      );
    else if (kind === "hint")
      status.append(
        el(
          "span",
          null,
          "Write it in your own words. We'll show you what we understood before saving.",
        ),
      );
  }
  function renderRemember() {
    if (!rememberChips) return;
    rememberChips.replaceChildren();
    const items = [];
    const wl = walkLabel(walks);
    if (wl) items.push({ text: wl, remove: () => (walks = null) });
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

  if (autoParse) {
    status = el("p", "pref-status");
    root.append(status);
    remember = el("div", "remember");
    rememberChips = el("div", "remember-chips");
    remember.append(
      el("p", "remember-label", "We'll remember"),
      rememberChips,
      el("p", "remember-hint", "Remove anything that isn't right, or edit your note."),
    );
    root.append(remember);
    renderRemember();
    setStatus(walks !== null || opens.length ? "none" : "hint");
    ta.addEventListener("blur", () => runParse());
  }

  // 자유입력 해석. 같은 텍스트는 재해석 안 함(중복 LLM 호출 방지). 노트가 바뀌면
  // **이전 해석이 더한 것만** 되돌린 뒤 다시 해석한다(누적 방지) — base 선호(My Page
  // prefill)와 수동 × 편집은 보존. 실패·결과없음도 진행 막지 않음.
  let lastParsedText = "";
  let parseOpens = []; // 가장 최근 해석이 더한 개방형 선호
  let parseSetWalks = false; // 가장 최근 해석이 새로 켠 걷기 선호
  async function runParse() {
    const text = ta.value.trim();
    if (text === lastParsedText) return false; // 변화 없음(둘 다 빈 값 포함)
    lastParsedText = text;
    // 직전 해석 기여분 되돌리기(노트 바뀌면 교체, 누적 X).
    opens = opens.filter((p) => !parseOpens.includes(p));
    if (parseSetWalks) walks = null;
    parseOpens = [];
    parseSetWalks = false;
    if (!text) {
      renderRemember();
      setStatus(walks !== null || opens.length ? "none" : "hint");
      return false;
    }
    setBusy(true);
    setStatus("reading");
    let added = false;
    try {
      const env = await postParse(text);
      const c = env?.ok ? env.data : null;
      if (c) {
        for (const code of c.interests || []) {
          if (!selected.has(code)) {
            selected.add(code);
            chipEls.get(code)?.setAttribute("aria-pressed", "true");
            added = true;
          }
        }
        // tri-state: 해석이 걷기 선호(싫음 true / 좋아함 false)를 주고, 아직 미설정이면 반영.
        if (
          (c.prefer_shorter_walks === true || c.prefer_shorter_walks === false) &&
          walks === null
        ) {
          walks = c.prefer_shorter_walks;
          parseSetWalks = true;
          added = true;
        }
        const add = [...(c.open_preferences || [])];
        if (c.indoor_outdoor)
          add.push(c.indoor_outdoor === "indoor" ? "Indoor" : "Outdoor");
        for (const p of add)
          if (p && !opens.some((x) => x.toLowerCase() === p.toLowerCase())) {
            opens.push(p);
            parseOpens.push(p);
            added = true;
          }
        renderRemember();
      }
    } catch {
      /* 실패도 '결과 없음'으로(진행 막지 않음) */
    } finally {
      setBusy(false);
      setStatus(walks !== null || opens.length ? "none" : "empty");
    }
    return added;
  }

  function getValues() {
    return {
      interests: [...selected],
      prefer_shorter_walks: walks, // tri-state: true / false / null 그대로
      open_preferences: opens,
    };
  }

  // 확인 모달의 "Also" 칩 × 제거용(걷기 또는 개방형 선호 하나 제거).
  function removeExtra(text) {
    if (text === "Shorter walks" || text === "Happy to walk") walks = null;
    else opens = opens.filter((p) => p !== text);
    renderRemember();
  }

  return {
    element: root,
    getValues,
    runParse,
    removeExtra,
    hasNote: () => !!ta.value.trim(),
    isBusy: () => busy,
    onBusyChange: (f) => busyListeners.push(f),
  };
}
