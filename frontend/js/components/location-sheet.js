// LF-02 · "Start from" 바텀시트 (Figma). 검색 + 현재 위치 + 대표 시작점.
// 선택은 '어디서 출발'만 정함 — 추천을 그 지역으로 한정하지 않는다(footer 고지).
import { el, openSheet } from "./sheet.js";

const POPULAR = [
  "Gyeongbokgung Palace",
  "Anguk · Insadong",
  "City Hall · Deoksugung",
  "Myeongdong",
  "DDP",
];

const SEARCH_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="18" height="18"><circle cx="11" cy="11" r="7"/><path d="m20 20-3-3"/></svg>';

export function openLocationSheet({ currentLabel, onPick }) {
  return openSheet((close) => {
    const root = el("div", "loc-sheet");

    // head: 타이틀 + Cancel
    const head = el("div", "sheet-head");
    head.append(el("h2", "sheet-title", "Start from"));
    const cancel = el("button", "sheet-cancel", "Cancel");
    cancel.type = "button";
    cancel.addEventListener("click", close);
    head.append(cancel);
    root.append(head);

    // 검색
    const search = el("div", "loc-search");
    const sIcon = el("span", "loc-search-icon");
    sIcon.innerHTML = SEARCH_SVG;
    const sInput = el("input", "loc-search-input");
    sInput.type = "text";
    sInput.placeholder = "Search a place or station";
    search.append(sIcon, sInput);
    root.append(search);

    // 현재 위치 옵션
    const curSelected = currentLabel === "Current location";
    const curCard = el("button", "loc-current");
    curCard.type = "button";
    if (curSelected) curCard.classList.add("is-selected");
    const radio = el("span", "loc-radio");
    const curText = el("div", "loc-current-text");
    curText.append(
      el("span", "loc-current-title", "Current location"),
      el("span", "loc-current-sub", "Uses your device location"),
    );
    curCard.append(radio, curText);
    if (curSelected) curCard.append(el("span", "loc-check", "✓"));
    curCard.addEventListener("click", () => {
      if (!navigator.geolocation) {
        onPick("Current location", null);
        return close();
      }
      curCard.classList.add("is-locating");
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          onPick("Current location", {
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
          });
          close();
        },
        () => {
          onPick("Current location", null);
          close();
        },
      );
    });
    root.append(curCard);

    // 대표 시작점
    root.append(el("p", "loc-section-label", "POPULAR STARTING POINTS"));
    const chips = el("div", "loc-chips");
    const chipEls = [];
    for (const name of POPULAR) {
      const chip = el("button", "chip", name);
      chip.type = "button";
      chip.addEventListener("click", () => {
        onPick(name, null);
        close();
      });
      chips.append(chip);
      chipEls.push({ chip, name });
    }
    root.append(chips);

    // 검색: 대표 시작점 필터 + Enter 시 자유 입력 커밋
    sInput.addEventListener("input", () => {
      const q = sInput.value.trim().toLowerCase();
      for (const { chip, name } of chipEls)
        chip.hidden = q && !name.toLowerCase().includes(q);
    });
    sInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const v = sInput.value.trim();
        if (v) {
          onPick(v, null);
          close();
        }
      }
    });

    root.append(
      el(
        "p",
        "loc-footer",
        "Picking a spot just sets where you start — suggestions aren't limited to that area.",
      ),
    );
    return root;
  });
}
