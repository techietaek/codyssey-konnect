// LF-02 · "Here's what we understood" 확인 바텀시트 (Figma, 4a).
// 추천 전, 이해한 조건을 ✕로 제거 가능한 칩으로 확인. Show → 교정된 조건으로 추천.
// (next-plan / travel-time 질문은 4b — 기존 일정 기능이라 이번 범위 밖)
import { el, openSheet } from "./sheet.js";

const SPARKLE =
  '<svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><path d="M12 3l1.7 4.8L18.5 9.5l-4.8 1.7L12 16l-1.7-4.8L5.5 9.5l4.8-1.7z"/></svg>';

const INTEREST_LABEL = {
  traditional_culture: "Traditional culture",
  palaces_historic: "Palaces & historic",
  hands_on: "Hands-on",
  art_exhibitions: "Art & exhibitions",
  live_performances: "Live performances",
  festivals_events: "Festivals & events",
};

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export function openConfirmSheet({ request, conditions, onShow, onEdit }) {
  const edited = JSON.parse(JSON.stringify(conditions || {}));
  edited.interests = edited.interests || [];
  edited.avoid_interests = edited.avoid_interests || [];
  edited.exclude_concepts = edited.exclude_concepts || [];

  return openSheet((close) => {
    const root = el("div", "confirm-sheet");

    const titleRow = el("div", "confirm-title-row");
    const spark = el("span", "confirm-spark");
    spark.innerHTML = SPARKLE;
    titleRow.append(spark, el("h2", "sheet-title", "Here's what we understood"));
    root.append(titleRow);
    root.append(el("p", "sheet-sub", "Tap ✕ to remove anything that's wrong."));

    // WHERE & WHEN
    root.append(el("p", "confirm-label", "WHERE & WHEN"));
    root.append(
      el(
        "p",
        "confirm-where",
        `${request.start_location.label} · ${fmtTime(request.start_at)}–${fmtTime(request.end_at)}`,
      ),
    );

    // FROM WHAT YOU WROTE — 이해한 조건 칩(✕)
    const chips = el("div", "confirm-chips");
    function addChip(text, remove) {
      const chip = el("span", "confirm-chip");
      chip.append(el("span", null, text));
      const x = el("button", "confirm-chip-x", "✕");
      x.type = "button";
      x.setAttribute("aria-label", `Remove ${text}`);
      x.addEventListener("click", () => {
        remove();
        chip.remove();
        if (!chips.children.length) chips.append(emptyNote());
      });
      chip.append(x);
      chips.append(chip);
    }
    function emptyNote() {
      return el("p", "confirm-empty", "No extra conditions — we'll use your time and place.");
    }

    for (const code of edited.interests.slice()) {
      addChip(INTEREST_LABEL[code] || code, () => {
        edited.interests = edited.interests.filter((c) => c !== code);
      });
    }
    for (const code of edited.avoid_interests.slice()) {
      addChip(`Not: ${INTEREST_LABEL[code] || code}`, () => {
        edited.avoid_interests = edited.avoid_interests.filter((c) => c !== code);
      });
    }
    // 개방형 명시 배제 — ✕로 되돌리면 그 조건 없이 다시 추천(사용자 교정 우선).
    // 디자인 10/8: "역사 싫어요" → "Skip: …" 칩으로 표시(이번 요청만, ✕ 해제).
    for (const concept of edited.exclude_concepts.slice()) {
      addChip(`Skip: ${concept}`, () => {
        edited.exclude_concepts = edited.exclude_concepts.filter(
          (c) => c !== concept,
        );
      });
    }
    if (edited.free_only)
      addChip("Free only", () => (edited.free_only = false));
    if (edited.budget_krw)
      addChip(`Under ₩${edited.budget_krw.toLocaleString()} each`, () => (edited.budget_krw = null));
    if (edited.indoor_outdoor)
      addChip(
        edited.indoor_outdoor === "indoor" ? "Indoor only" : "Outdoor only",
        () => (edited.indoor_outdoor = null),
      );
    if (edited.prefer_shorter_walks)
      addChip("Less walking", () => (edited.prefer_shorter_walks = false));

    if (chips.children.length) {
      root.append(el("p", "confirm-label", "FROM WHAT YOU WROTE"));
      root.append(chips);
    }

    const show = el("button", "btn-cta", "Show experiences");
    show.type = "button";
    show.addEventListener("click", () => {
      close();
      onShow(edited);
    });
    root.append(show);

    const edit = el("button", "confirm-edit", "Edit what I wrote");
    edit.type = "button";
    edit.addEventListener("click", () => {
      close();
      onEdit?.();
    });
    root.append(edit);

    return root;
  });
}
