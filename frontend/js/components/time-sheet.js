// LF-02 · 시간 바텀시트 (Figma). 빠른 칩(Now/+30/+1hr 등) + 휠 피커(시·분·AM/PM)
// + "You have Xh Ym" 요약. 종료는 시작 이후만 선택 가능.
import { el, openSheet } from "./sheet.js";

const ITEM_H = 40;
const HOURS = Array.from({ length: 12 }, (_, i) => i + 1); // 1..12
const MINUTES = Array.from({ length: 12 }, (_, i) => i * 5); // 0,5,..55
const MERIDIEM = ["AM", "PM"];

function round5(date) {
  const d = new Date(date);
  d.setSeconds(0, 0);
  d.setMinutes(Math.round(d.getMinutes() / 5) * 5); // 60 → 다음 시로 롤오버
  return d;
}
function to12(date) {
  const h = date.getHours();
  return { h12: h % 12 || 12, min: date.getMinutes(), ap: h >= 12 ? "PM" : "AM" };
}
function toLocalInput(date) {
  const off = date.getTimezoneOffset();
  return new Date(date.getTime() - off * 60000).toISOString().slice(0, 16);
}
function fmtTime(date) {
  return date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}
function fmtDur(min) {
  if (min <= 0) return "0 min";
  const h = Math.floor(min / 60);
  const m = min % 60;
  return [h ? `${h} hr` : "", m ? `${m} min` : ""].filter(Boolean).join(" ");
}

// 스냅 휠 컬럼. getIndex()=현재 중앙 인덱스. onChange=스크롤 정착 시 콜백.
function wheelColumn(items, selectedIndex, format, onChange) {
  const col = el("div", "wheel-col");
  const pad = () => el("div", "wheel-pad");
  col.append(pad());
  items.forEach((v) => col.append(el("div", "wheel-item", format(v))));
  col.append(pad());

  const getIndex = () =>
    Math.max(0, Math.min(items.length - 1, Math.round(col.scrollTop / ITEM_H)));
  const setIndex = (i) => {
    col.scrollTop = i * ITEM_H;
  };
  let raf = 0;
  col.addEventListener("scroll", () => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      for (let i = 0; i < items.length; i++)
        col.children[i + 1].classList.toggle("is-active", i === getIndex());
      onChange?.();
    });
  });
  // 초기 위치(레이아웃 후)
  requestAnimationFrame(() => {
    setIndex(selectedIndex);
    for (let i = 0; i < items.length; i++)
      col.children[i + 1].classList.toggle("is-active", i === selectedIndex);
  });
  return { col, getIndex, setIndex };
}

export function openTimeSheet({ kind, startValue, endValue, onDone }) {
  const isStart = kind === "start";
  const now = round5(new Date());
  const startDate = startValue ? round5(new Date(startValue)) : now;
  const baseDate = isStart ? startDate : startDate; // 같은 날 기준
  const initial = isStart
    ? startDate
    : endValue
      ? round5(new Date(endValue))
      : round5(new Date(startDate.getTime() + 2 * 3600000));

  return openSheet((close) => {
    const root = el("div", "time-sheet");

    const head = el("div", "sheet-head");
    head.append(el("h2", "sheet-title", isStart ? "Start" : "Done by"));
    const cancel = el("button", "sheet-cancel", "Cancel");
    cancel.type = "button";
    cancel.addEventListener("click", close);
    head.append(cancel);
    root.append(head);

    // 빠른 칩
    const quick = el("div", "time-quick");
    const quickDefs = isStart
      ? [
          { label: "Now", date: () => round5(new Date()) },
          { label: "In 30 min", date: () => round5(new Date(Date.now() + 30 * 60000)) },
          { label: "In 1 hr", date: () => round5(new Date(Date.now() + 60 * 60000)) },
        ]
      : [
          { label: "In 1 hr", date: () => new Date(startDate.getTime() + 3600000) },
          { label: "In 2 hr", date: () => new Date(startDate.getTime() + 2 * 3600000) },
          { label: "In 3 hr", date: () => new Date(startDate.getTime() + 3 * 3600000) },
        ];

    // 휠
    const init12 = to12(initial);
    const wheel = el("div", "time-wheel");
    wheel.append(el("div", "wheel-center"));
    const hCol = wheelColumn(HOURS, init12.h12 - 1, (v) => String(v), () => refresh());
    const mCol = wheelColumn(MINUTES, MINUTES.indexOf(init12.min), (v) => String(v).padStart(2, "0"), () => refresh());
    const apCol = wheelColumn(MERIDIEM, init12.ap === "PM" ? 1 : 0, (v) => v, () => refresh());
    wheel.append(hCol.col, mCol.col, apCol.col);

    const summary = el("p", "time-summary");
    const note = el("p", "time-note");
    if (isStart) note.textContent = "Earlier times are unavailable — this is for right now.";

    const doneBtn = el("button", "btn-cta", "Done");
    doneBtn.type = "button";

    function currentDate() {
      const h12 = HOURS[hCol.getIndex()];
      const min = MINUTES[mCol.getIndex()];
      const ap = MERIDIEM[apCol.getIndex()];
      const h24 = ap === "PM" ? (h12 % 12) + 12 : h12 % 12;
      const d = new Date(baseDate);
      d.setHours(h24, min, 0, 0);
      // 종료는 '시작일 자정까지'만 유효(FR-A2, 자정 넘김 금지) → 같은 날로 둔다.
      // 자정 자체(다음날 00:00)는 '그날 끝'으로 허용.
      if (!isStart && h24 === 0 && min === 0) d.setDate(d.getDate() + 1);
      return d;
    }
    function refresh() {
      const d = currentDate();
      // 빠른 칩 활성 표시
      for (const b of quick.children) {
        const target = round5(b._date());
        b.classList.toggle("is-active", target.getTime() === d.getTime());
      }
      if (isStart) {
        if (endValue) {
          const end = new Date(endValue);
          const dur = Math.round((end - d) / 60000);
          summary.textContent = `Done by ${fmtTime(end)} · You have ${fmtDur(dur)}`;
          summary.classList.toggle("is-warn", dur <= 0);
        } else {
          summary.textContent = "";
        }
        doneBtn.disabled = false;
      } else {
        const dur = Math.round((d - startDate) / 60000);
        summary.textContent = dur > 0 ? `You have ${fmtDur(dur)}` : "End must be after your start time";
        summary.classList.toggle("is-warn", dur <= 0);
        doneBtn.disabled = dur <= 0;
      }
    }

    function setWheelsTo(date) {
      const t = to12(round5(date));
      hCol.setIndex(t.h12 - 1);
      mCol.setIndex(MINUTES.indexOf(t.min));
      apCol.setIndex(t.ap === "PM" ? 1 : 0);
      requestAnimationFrame(refresh);
    }

    for (const def of quickDefs) {
      const b = el("button", "chip", def.label);
      b.type = "button";
      b._date = def.date;
      b.addEventListener("click", () => setWheelsTo(def.date()));
      quick.append(b);
    }

    doneBtn.addEventListener("click", () => {
      onDone(toLocalInput(currentDate()));
      close();
    });

    root.append(quick, wheel, summary);
    if (isStart) root.append(note);
    root.append(doneBtn);
    requestAnimationFrame(refresh);
    return root;
  });
}
