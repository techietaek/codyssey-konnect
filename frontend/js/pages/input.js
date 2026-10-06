// LF-02 — 즉시 추천(A) 입력. FR-A1·A2·A4·A5·A6.
// 필수: 시작 위치·시작 시각·종료 시각. 자연어 선택조건은 1영역(구조화는 이후 LLM).
// 종료는 자동 기본값 없음(FR-A2). 경계 검증은 백엔드 domain/ 이 정본, 여기선 보조.
import { postRecommend } from "../api.js";
import { clearChoice, loadChoice, setResults } from "../state.js";

// FR-A5 대표 시작점 5개 (지역 전용 모드/Hard Filter 아님 — 보조 Quick Select)
const QUICK_STARTS = [
  "Gyeongbokgung Palace",
  "Anguk · Insadong",
  "City Hall · Deoksugung",
  "Myeongdong",
  "DDP",
];

// FR-A4 예시 칩: 탭하면 자연어 입력에 문구를 추가/제거(말 안 한 조건은 추정 금지).
const EXAMPLE_CONDITIONS = [
  "Indoor",
  "Free only",
  "Under ₩20,000",
  "Within 1 km",
  "Quiet place",
];

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

// 로컬 now → datetime-local 값("YYYY-MM-DDTHH:MM")
function localNowValue() {
  const d = new Date();
  d.setSeconds(0, 0);
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 16);
}

export function renderInputView({ prefill, onResults, onViewChoice }) {
  const root = el("section", "view input-view");

  const header = el("header", "app-header");
  header.append(
    el("h1", null, "KONNECT"),
    el("p", null, "What can you actually do in Seoul right now?"),
  );
  root.append(header);

  // 현재 선택 재접근 (A6, LF-09 A variant). 선택 ≠ 방문.
  const saved = loadChoice();
  const savedCand = saved?.env?.data?.candidates?.find(
    (c) => c.id === saved.candidateId,
  );
  if (savedCand && onViewChoice) {
    const banner = el("div", "choice-banner");
    const info = el("div", "choice-info");
    info.append(
      el("span", "choice-label", "Current choice"),
      el("span", "choice-title", savedCand.title),
    );
    const view = el("button", "choice-view", "View");
    view.type = "button";
    view.addEventListener("click", () =>
      onViewChoice({ request: saved.request, env: saved.env }),
    );
    const clear = el("button", "choice-clear", "✕");
    clear.type = "button";
    clear.title = "Clear current choice";
    clear.addEventListener("click", () => {
      clearChoice();
      banner.remove();
    });
    banner.append(info, view, clear);
    root.append(banner);
  }

  const form = el("form", "form");

  // ── Where & when (required) ──
  const whereSec = el("div", "section");
  const whereHead = el("div", "section-head");
  whereHead.append(el("h2", null, "Where & when"), el("span", "tag tag--required", "required"));
  whereSec.append(whereHead);

  // 시작 위치 + 현재 위치 버튼(FR-A6: 필요 시점에만 권한 요청, 선요청 금지)
  let geoCoords = null; // {lat,lng} — 현재위치 사용 시에만
  const locField = el("div", "field");
  locField.append(el("label", null, "Start from"));
  const locRow = el("div", "loc-row");
  const locInput = el("input");
  locInput.type = "text";
  locInput.placeholder = "e.g. Chungmuro, Seoul";
  locInput.value = prefill?.start_location?.label ?? "Current location";
  const geoBtn = el("button", "btn-geo", "📍 Use current");
  geoBtn.type = "button";
  geoBtn.addEventListener("click", () => {
    if (!navigator.geolocation) {
      locInput.focus();
      return;
    }
    geoBtn.textContent = "…";
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        geoCoords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        locInput.value = "Current location";
        geoBtn.textContent = "📍 Pinned";
      },
      () => {
        // 거부/실패 → 직접 입력으로 폴백
        geoBtn.textContent = "📍 Use current";
        locInput.value = "";
        locInput.focus();
      },
    );
  });
  // 사용자가 직접 수정하면 좌표는 무효화(라벨과 좌표 불일치 방지)
  locInput.addEventListener("input", () => {
    geoCoords = null;
    if (geoBtn.textContent === "📍 Pinned") geoBtn.textContent = "📍 Use current";
  });
  locRow.append(locInput, geoBtn);
  locField.append(locRow);
  whereSec.append(locField);

  // Quick Select 대표 시작점
  const quick = el("div", "chips");
  for (const name of QUICK_STARTS) {
    const chip = el("button", "chip", name);
    chip.type = "button";
    chip.addEventListener("click", () => {
      locInput.value = name;
      geoCoords = null;
    });
    quick.append(chip);
  }
  whereSec.append(quick);

  // 시작/종료 시각 (네이티브 피커). 시작=now 기본값, 종료=비움(자동 기본값 금지).
  const timeRow = el("div", "time-row");
  const startField = el("div", "field");
  startField.append(el("label", null, "Start"));
  const startInput = el("input");
  startInput.type = "datetime-local";
  startInput.value = prefill?.start_at?.slice(0, 16) ?? localNowValue();
  startField.append(startInput);

  const endField = el("div", "field");
  endField.append(el("label", null, "Done by"));
  const endInput = el("input");
  endInput.type = "datetime-local";
  if (prefill?.end_at) endInput.value = prefill.end_at.slice(0, 16);
  endField.append(endInput);

  timeRow.append(startField, endField);
  whereSec.append(timeRow);
  form.append(whereSec);

  // ── Anything else (optional) ──
  const elseSec = el("div", "section");
  const elseHead = el("div", "section-head");
  elseHead.append(el("h2", null, "Anything else"), el("span", "tag tag--optional", "optional"));
  elseSec.append(elseHead);

  const noteField = el("div", "field");
  const noteInput = el("textarea");
  noteInput.placeholder = "Interests, budget, how far you'll walk… in your own words.";
  if (prefill?.note) noteInput.value = prefill.note;
  noteField.append(noteInput);
  elseSec.append(noteField);

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
        noteInput.value = parts.filter((p) => p.toLowerCase() !== phrase.toLowerCase()).join(", ");
      } else {
        chip.setAttribute("aria-pressed", "true");
        chip.textContent = `✓ ${phrase}`;
        if (!parts.some((p) => p.toLowerCase() === phrase.toLowerCase())) parts.push(phrase);
        noteInput.value = parts.join(", ");
      }
    });
    examples.append(chip);
  }
  elseSec.append(examples);
  form.append(elseSec);

  // ── 오류 + CTA ──
  const errorBox = el("div", "form-error");
  errorBox.hidden = true;
  form.append(errorBox);

  const ctaWrap = el("div", "cta");
  const cta = el("button", "btn-cta", "Find experiences");
  cta.type = "submit";
  ctaWrap.append(cta);
  form.append(ctaWrap);

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.hidden = false;
    errorBox.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.hidden = true;

    const label = locInput.value.trim();
    if (!label) return showError("Please enter where you'll start from.");
    if (!startInput.value) return showError("Please choose a start time.");
    // 종료 자동 기본값 없음 → 사용자가 반드시 선택 (FR-A2)
    if (!endInput.value) return showError("Please choose an end time (we don't assume one).");

    const start_location = { label };
    if (geoCoords) Object.assign(start_location, geoCoords);
    const payload = {
      start_location,
      start_at: `${startInput.value}:00`,
      end_at: `${endInput.value}:00`,
      note: noteInput.value.trim() || null,
    };

    cta.disabled = true;
    cta.textContent = "Finding…";
    try {
      const env = await postRecommend(payload);
      if (!env.ok) {
        // 입력오류(검증)·시스템예외 모두 봉투 error 로 옴 → 추천 전 인라인 표시
        showError(env.error?.message ?? "Please check your input and try again.");
        return;
      }
      setResults(payload, env.data.candidates);
      onResults({ request: payload, env });
    } catch {
      showError("Could not reach the server. Please try again.");
    } finally {
      cta.disabled = false;
      cta.textContent = "Find experiences";
    }
  });

  root.append(form);
  return root;
}
