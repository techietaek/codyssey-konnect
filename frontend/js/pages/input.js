// LF-02 — 즉시 추천(A) 입력. Figma 정본(274:2272 + 인터랙션) 정확 반영.
// Field Row(탭→바텀시트) · 시간 휠 시트 · 예시 칩 · note 포커스 시 Where&when 접힘 ·
// 제출 시 "Here's what we understood" 확인 시트(4a). FR-A1·A2·A4·A5·A6.
import { postParse } from "../api.js";
import { openConfirmSheet } from "../components/confirm-sheet.js";
import { openLocationSheet } from "../components/location-sheet.js";
import { openTimeSheet } from "../components/time-sheet.js";

// FR-A4 예시 칩 (Figma 문구)
const EXAMPLE_CONDITIONS = [
  "Indoor only",
  "Free or cheap",
  "Less walking",
  "Traditional culture",
  "Live performances",
  "I have plans later",
];

const ICONS = {
  pin: '<path d="M21 10c0 7-9 12-9 12s-9-5-9-12a9 9 0 0 1 18 0Z"/><circle cx="12" cy="10" r="3"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  flag: '<path d="M5 22V4M5 4h12l-2.5 4L17 12H5"/>',
  sparkle: '<path d="M12 3l1.7 4.8L18.5 9.5l-4.8 1.7L12 16l-1.7-4.8L5.5 9.5l4.8-1.7z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.8h.01"/>',
  chevron: '<path d="M15 5l-7 7 7 7"/>',
};

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

function icon(name, className = "fr-icon") {
  const s = el("span", className);
  s.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="20" height="20">${ICONS[name]}</svg>`;
  return s;
}

function localNowValue() {
  const d = new Date();
  d.setSeconds(0, 0);
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 16);
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}
function fmtValue(iso, isStart) {
  const d = new Date(iso);
  const today = new Date();
  if (isStart && Math.abs(d - today) < 150000) return `Now · ${fmtTime(iso)}`;
  if (d.toDateString() === today.toDateString()) return fmtTime(iso);
  return `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })} · ${fmtTime(iso)}`;
}
function durText(startIso, endIso) {
  const min = Math.round((new Date(endIso) - new Date(startIso)) / 60000);
  if (min <= 0) return "";
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `You have ${[h ? `${h} hr` : "", m ? `${m} min` : ""].filter(Boolean).join(" ")}`;
}

export function renderInputView({ prefill, onBack, onRecommend }) {
  const root = el("section", "view input-view");

  // 상태값
  let geoCoords = prefill?.start_location?.lat != null
    ? { lat: prefill.start_location.lat, lng: prefill.start_location.lng }
    : null;
  let locationLabel = prefill?.start_location?.label ?? "Current location";
  let startValue = prefill?.start_at?.slice(0, 16) ?? localNowValue();
  let endValue = prefill?.end_at?.slice(0, 16) ?? "";

  // ── Nav: chevron + 타이틀 ──
  const nav = el("div", "input-nav");
  const back = el("button", "nav-back");
  back.type = "button";
  back.setAttribute("aria-label", "Back");
  back.append(icon("chevron", "nav-back-icon"));
  if (onBack) back.addEventListener("click", onBack);
  nav.append(back, el("span", "nav-title", "Immediate recommendation"));
  root.append(nav);

  // ── 접힘 pill (note 편집 중 Where&when 대체) ──
  const collapsePill = el("div", "cond-pill cond-pill--collapse");
  const collapseText = el("span", "cond-text");
  const collapseEdit = el("button", "cond-edit", "Edit");
  collapseEdit.type = "button";
  collapsePill.append(icon("pin", "cond-pill-icon"), collapseText, collapseEdit);

  // ── Heading ──
  const header = el("header", "input-head");
  header.append(
    el("h1", "input-title", "What fits your time now?"),
    el("p", "input-sub", "We'll find up to 4 cultural experiences nearby."),
  );

  const form = el("form", "form");

  // ── Where & when (required) ──
  const whereSec = el("div", "section where-section");
  const whereHead = el("div", "section-head");
  whereHead.append(
    el("h2", null, "Where & when"),
    el("span", "tag tag--required", "Required"),
  );
  whereSec.append(whereHead);

  // Field Row 공통 생성기 (탭 → onOpen)
  function fieldRow(iconName, label, onOpen) {
    const row = el("div", "field-row");
    row.append(icon(iconName));
    const text = el("div", "fr-text");
    const lbl = el("span", "fr-label", label);
    const val = el("span", "fr-value");
    text.append(lbl, val);
    const action = el("button", "fr-action", "Change");
    action.type = "button";
    row.append(text, action);
    const open = () => onOpen();
    text.addEventListener("click", open);
    action.addEventListener("click", open);
    return { row, val, action };
  }

  // Start from
  const loc = fieldRow("pin", "Start from", () =>
    openLocationSheet({
      currentLabel: locationLabel,
      onPick: (label, coords) => {
        locationLabel = label;
        geoCoords = coords;
        refreshLoc();
        loc.row.classList.remove("is-error");
        validate();
      },
    }),
  );
  function refreshLoc() {
    loc.val.textContent = locationLabel;
  }
  refreshLoc();

  // Start
  const start = fieldRow("clock", "Start", () =>
    openTimeSheet({
      kind: "start",
      startValue,
      endValue,
      onDone: (v) => {
        startValue = v;
        refreshStart();
        refreshHint();
        validate();
      },
    }),
  );
  function refreshStart() {
    start.val.textContent = fmtValue(startValue, true);
    start.action.textContent = "Change";
  }
  refreshStart();

  // Done by
  const end = fieldRow("flag", "Done by", () =>
    openTimeSheet({
      kind: "end",
      startValue,
      endValue,
      onDone: (v) => {
        endValue = v;
        end.row.classList.remove("is-error");
        refreshEnd();
        validate();
      },
    }),
  );
  function refreshEnd() {
    if (endValue) {
      end.val.textContent = fmtValue(endValue, false);
      end.val.classList.remove("is-empty");
      end.action.textContent = "Change";
    } else {
      end.val.textContent = "Choose an end time";
      end.val.classList.add("is-empty");
      end.action.textContent = "Set";
    }
    refreshHint();
  }

  // 시간 안내: 종료 선택 시 "You have Xh Ym"(teal), 미선택 시 amber 안내
  const timeHint = el("p", "field-hint-amber", "Pick when you need to be done");
  function refreshHint() {
    if (endValue) {
      timeHint.textContent = durText(startValue, endValue);
      timeHint.className = "field-duration";
    } else {
      timeHint.textContent = "Pick when you need to be done";
      timeHint.className = "field-hint-amber";
    }
  }
  refreshEnd();

  whereSec.append(loc.row, start.row, end.row, timeHint);
  form.append(whereSec);

  // ── Anything else (optional) ──
  const elseSec = el("div", "section");
  const elseHead = el("div", "section-head");
  elseHead.append(
    el("h2", null, "Anything else?"),
    el("span", "tag tag--optional", "Optional"),
  );
  elseSec.append(elseHead);

  const nlCard = el("div", "nl-input");
  const noteInput = el("textarea", "nl-textarea");
  noteInput.placeholder =
    'In your own words — e.g. "Indoors please, under ₩20,000. Dinner at 7 in Myeongdong."';
  if (prefill?.note) noteInput.value = prefill.note;
  const nlFooter = el("div", "nl-footer");
  nlFooter.append(
    icon("sparkle", "nl-sparkle"),
    el("span", null, "We'll turn this into conditions you can check"),
  );
  nlCard.append(noteInput, nlFooter);
  elseSec.append(nlCard);

  const examples = el("div", "chips");
  for (const phrase of EXAMPLE_CONDITIONS) {
    const chip = el("button", "chip", `+ ${phrase}`);
    chip.type = "button";
    chip.setAttribute("aria-pressed", "false");
    chip.addEventListener("click", () => {
      const on = chip.getAttribute("aria-pressed") === "true";
      const parts = noteInput.value.split(",").map((s) => s.trim()).filter(Boolean);
      if (on) {
        chip.setAttribute("aria-pressed", "false");
        chip.textContent = `+ ${phrase}`;
        noteInput.value = parts
          .filter((p) => p.toLowerCase() !== phrase.toLowerCase())
          .join(", ");
      } else {
        chip.setAttribute("aria-pressed", "true");
        chip.textContent = `✓ ${phrase}`;
        if (!parts.some((p) => p.toLowerCase() === phrase.toLowerCase()))
          parts.push(phrase);
        noteInput.value = parts.join(", ");
      }
    });
    examples.append(chip);
  }
  elseSec.append(examples);

  const otherPlans = el("button", "other-plans-link", "+ Other plans today? (optional)");
  otherPlans.type = "button";
  otherPlans.addEventListener("click", () => noteInput.focus());
  elseSec.append(otherPlans);

  // ── note 편집 중 Where&when → 접힘 pill ──
  function updateCollapse() {
    collapseText.textContent = `${locationLabel} · ${fmtTime(startValue)}${endValue ? `–${fmtTime(endValue)}` : ""}`;
  }
  noteInput.addEventListener("focus", () => {
    updateCollapse();
    root.classList.add("note-editing");
  });
  collapseEdit.addEventListener("click", () => {
    root.classList.remove("note-editing");
    noteInput.blur();
  });

  // ── 오류 + Bottom bar ──
  const errorBox = el("div", "form-error");
  errorBox.hidden = true;
  form.append(elseSec, errorBox);

  const ctaWrap = el("div", "cta");
  const cta = el("button", "btn-cta", "Find experiences");
  cta.type = "submit";
  ctaWrap.append(cta);
  const about = el("p", "about-info");
  about.append(icon("info", "about-icon"), el("span", null, "About the information"));
  ctaWrap.append(about);
  form.append(ctaWrap);

  function validate() {
    const ok = !!locationLabel.trim() && !!startValue && !!endValue;
    cta.disabled = !ok;
    return ok;
  }

  function basePayload() {
    const start_location = { label: locationLabel.trim() };
    if (geoCoords) Object.assign(start_location, geoCoords);
    return {
      start_location,
      start_at: `${startValue}:00`,
      end_at: `${endValue}:00`,
      note: noteInput.value.trim() || null,
    };
  }

  // 조회(로딩→성공/오류)는 app.js 의 공통 플로우가 담당. 입력 뷰는 payload 만 넘긴다.
  function runRecommend(conditions) {
    const payload = basePayload();
    if (conditions) payload.conditions = conditions;
    onRecommend(payload);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.hidden = true;
    if (!validate()) {
      if (!endValue) end.row.classList.add("is-error");
      return;
    }
    const note = noteInput.value.trim();
    // note 없으면 확인할 게 없으니 바로 추천. 있으면 '이해한 조건' 확인 시트.
    if (!note) return runRecommend(null);

    cta.disabled = true;
    cta.textContent = "Reading…";
    let conditions = null;
    try {
      const env = await postParse(note);
      conditions = env.ok ? env.data : {};
    } catch {
      conditions = {};
    } finally {
      cta.textContent = "Find experiences";
      validate();
    }
    openConfirmSheet({
      request: basePayload(),
      conditions,
      onShow: (edited) => runRecommend(edited),
      onEdit: () => noteInput.focus(),
    });
  });

  root.append(collapsePill, header, form);
  validate();
  return root;
}
