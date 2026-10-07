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
    sheet.style.transform = ""; // 인라인 드래그 변형 제거 → CSS 로 아래로 슬라이드
    scrim.classList.remove("is-open");
    document.removeEventListener("keydown", onKey);
    setTimeout(() => scrim.remove(), 220);
    onClose?.();
  }

  // grip(그랩 바) — 터치 영역을 넓힌 zone 안에 둔다. 아래로 끌면 닫힘.
  const gripZone = document.createElement("div");
  gripZone.className = "sheet-grip-zone";
  const grip = document.createElement("div");
  grip.className = "sheet-grip";
  gripZone.append(grip);
  sheet.append(gripZone, build(close));

  // ── grip 스와이프-다운 → 닫기 (iOS 스타일) ──
  let dragging = false;
  let startY = 0;
  let dragY = 0;
  const onPointerMove = (e) => {
    if (!dragging) return;
    dragY = Math.max(0, e.clientY - startY); // 위로는 당겨지지 않음
    sheet.style.transform = `translateY(${dragY}px)`;
  };
  const onPointerUp = () => {
    if (!dragging) return;
    dragging = false;
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    sheet.style.transition = ""; // 트랜지션 복원
    // 충분히 내렸으면 닫고, 아니면 제자리로 스냅.
    const threshold = Math.min(120, sheet.offsetHeight * 0.25);
    if (dragY > threshold) close();
    else sheet.style.transform = "translateY(0)";
  };
  gripZone.addEventListener("pointerdown", (e) => {
    dragging = true;
    startY = e.clientY;
    dragY = 0;
    sheet.style.transition = "none"; // 드래그 중엔 즉시 추종
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  });

  scrim.addEventListener("click", (e) => {
    if (e.target === scrim) close();
  });
  const onKey = (e) => {
    if (e.key === "Escape") close();
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
