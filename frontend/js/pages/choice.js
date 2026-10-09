// LF-09 · 선택 상세 (저장 전/후). 10/8 멘토링 "저장 동작 명확하게".
//  - 저장 전(9-1a/b/c): 제목 "Your pick", "Not saved yet", 버튼 "Save choice".
//  - 저장 후(9-1·9-1s): 제목 "Your current choice", 버튼 "See on map", toast.
// 선택 ≠ 방문(booking 아님) 고지를 양쪽 모두 유지. 저장 전엔 current choice로 안 보인다.
import { saveChoice } from "../state.js";

const STATUS_LABEL = {
  fits: "Fits your conditions",
  check_needed: "Partly confirmed",
  alternative: "Alternative",
};

const CHEVRON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="20" height="20" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>';
const HOME =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="20" height="20" aria-hidden="true"><path d="M3 11l9-8 9 8"/><path d="M5 9.5V21h5v-6h4v6h5V9.5"/></svg>';

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

function tripStamp(startIso, endIso) {
  const d = new Date(startIso);
  const today = new Date();
  const dayLabel =
    d.toDateString() === today.toDateString()
      ? "TODAY"
      : d.toLocaleDateString("en-US", { weekday: "short" }).toUpperCase();
  const date = d
    .toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })
    .toUpperCase();
  return `${dayLabel} · ${date} · ${fmtTime(startIso)}–${fmtTime(endIso)}`;
}

// 저장 toast — 제목 + 보조(선택 ≠ 방문 고지). device-frame 안에서 뜨게.
function showSaveToast() {
  document.querySelector(".toast")?.remove();
  const toast = el("div", "toast toast--rich");
  toast.append(el("span", "toast-check", "✓"));
  const t = el("div", "toast-text");
  t.append(
    el("strong", null, "Saved as your current choice"),
    el("span", null, "Not a booking — check official details before you go."),
  );
  toast.append(t);
  (document.querySelector(".device-frame") || document.body).append(toast);
  setTimeout(() => toast.remove(), 2800);
}

function factRow(label, value) {
  const row = el("div", "choice-fact");
  row.append(el("span", "choice-fact-k", label));
  if (value && value.chip) {
    const v = el("span", "choice-fact-v");
    v.append(el("span", "choice-fact-chip", value.chip));
    row.append(v);
  } else {
    row.append(el("span", "choice-fact-v", value || "—"));
  }
  return row;
}

export function renderChoiceView({
  candidate,
  request,
  env,
  saved = false,
  onBack,
  onHome,
  onSeeMap,
  onFindOther,
  onBackToResults,
}) {
  const root = el("section", "view choice-view");
  const origin = env?.data?.origin;
  let isSaved = saved;

  function render() {
    root.replaceChildren();

    // Nav: Back(좌) · 제목 · Home(우)
    const nav = el("div", "input-nav");
    const back = el("button", "nav-back");
    back.type = "button";
    back.setAttribute("aria-label", "Back");
    back.innerHTML = CHEVRON;
    back.addEventListener("click", () => onBack?.());
    const home = el("button", "nav-home");
    home.type = "button";
    home.setAttribute("aria-label", "Home");
    home.innerHTML = HOME;
    home.addEventListener("click", () => onHome?.());
    nav.append(
      back,
      el("span", "nav-title", isSaved ? "Your current choice" : "Your pick"),
      home,
    );
    root.append(nav);

    const body = el("div", "choice-body");

    body.append(el("p", "choice-stamp", tripStamp(request.start_at, request.end_at)));
    body.append(el("h1", "choice-title", candidate.title));

    const badge = el("span", "badge", STATUS_LABEL[candidate.status] ?? candidate.status);
    badge.dataset.status = candidate.status;
    body.append(badge);

    if (candidate.reasons?.length) {
      const reasons = el("ul", "reasons");
      for (const r of candidate.reasons.slice(0, 2)) {
        const li = el("li", "reason");
        li.append(el("span", "reason-check", "✓"), el("span", null, r.text));
        reasons.append(li);
      }
      body.append(reasons);
    }

    // Fact 표 — Time(세션+소요) · Price · Getting there · Opening hours.
    const facts = el("div", "choice-facts");
    const timeVal =
      `${fmtTime(request.start_at)} session` +
      (candidate.visit_minutes ? ` · ${candidate.visit_minutes} min` : "");
    facts.append(factRow("Time", timeVal));
    facts.append(factRow("Price", candidate.price?.display || "Price needs checking"));
    if (candidate.movement?.display) {
      facts.append(
        factRow(
          "Getting there",
          origin?.label
            ? `${candidate.movement.display} from ${origin.label}`
            : candidate.movement.display,
        ),
      );
    }
    facts.append(
      factRow(
        "Opening hours",
        candidate.time?.display
          ? candidate.time.display
          : { chip: "Check opening hours" },
      ),
    );
    body.append(facts);

    // 선택 ≠ 방문 고지 (저장 전/후 문구 구분).
    body.append(
      el(
        "p",
        "choice-note",
        isSaved
          ? "This is your saved choice — not a booking or visit record. Check official details before you go."
          : "Not saved yet. Save it to keep it as your current choice. Saving isn't a booking.",
      ),
    );

    // 버튼 — 저장 전: Save choice / Official details / Back to results.
    //        저장 후: See on map / Official details / Find other options.
    const actions = el("div", "choice-actions");
    if (isSaved) {
      const map = el("button", "btn-cta", "See on map");
      map.type = "button";
      map.addEventListener("click", () => onSeeMap?.());
      actions.append(map);
    } else {
      const save = el("button", "btn-cta", "Save choice");
      save.type = "button";
      save.addEventListener("click", () => {
        saveChoice(request, env, candidate.id); // 이제서야 저장(그 전엔 current choice 아님)
        isSaved = true;
        render();
        showSaveToast();
      });
      actions.append(save);
    }

    const off = candidate.official_links?.[0];
    const offBtn = el("button", "btn-outline-pill", "Official details ↗");
    offBtn.type = "button";
    if (off) offBtn.addEventListener("click", () => window.open(off.url, "_blank", "noopener"));
    else offBtn.disabled = true;
    actions.append(offBtn);

    const third = el(
      "button",
      "btn-outline-pill",
      isSaved ? "Find other options" : "Back to results",
    );
    third.type = "button";
    third.addEventListener("click", () =>
      isSaved ? onFindOther?.() : onBackToResults?.(),
    );
    actions.append(third);

    body.append(actions);
    root.append(body);
  }

  render();
  return root;
}
