// 공용 바텀시트 — 스크림 + 슬라이드업 + 백드롭/Esc 닫기.
// build(close) 가 시트 내부 콘텐츠 노드를 반환한다.
export function openSheet(build, { onClose } = {}) {
  document.querySelector(".sheet-scrim")?.remove();

  const scrim = document.createElement("div");
  scrim.className = "sheet-scrim";
  const sheet = document.createElement("div");
  sheet.className = "sheet";
  sheet.setAttribute("role", "dialog");
  sheet.setAttribute("aria-modal", "true");

  let closed = false;
  function close() {
    if (closed) return;
    closed = true;
    scrim.classList.remove("is-open");
    setTimeout(() => scrim.remove(), 220);
    onClose?.();
  }

  const grip = document.createElement("div");
  grip.className = "sheet-grip";
  sheet.append(grip, build(close));

  scrim.addEventListener("click", (e) => {
    if (e.target === scrim) close();
  });
  const onKey = (e) => {
    if (e.key === "Escape") {
      close();
      document.removeEventListener("keydown", onKey);
    }
  };
  document.addEventListener("keydown", onKey);

  scrim.append(sheet);
  // device-frame 안에 담아 데스크톱 목업 밖으로 넘치지 않게(모바일은 화면 전체).
  (document.querySelector(".device-frame") || document.body).append(scrim);
  requestAnimationFrame(() => scrim.classList.add("is-open"));
  return { close };
}

export function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}
