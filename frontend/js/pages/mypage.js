// MP-1~3 · My Page (Phase 2 L3 · FR-L6). 최소범위:
//  - 계정 정보(Google 이름·이메일)
//  - 현재 선택 최소 진입점(선택 ≠ 방문)
//  - 확인된 선호 확인·수정(MP-2)·초기화(MP-3) → 변경은 **이후 추천부터** 적용
// 전체 이력·방문 통계·취향 분석·Stamp 는 MVP 제외. 선호 저장은 PUT /api/preferences.
import { displayName, userEmail } from "../auth.js";
import { getPreferences, putPreferences } from "../api.js";
import {
  createPreferenceForm,
  INTERESTS,
} from "../components/preference-form.js";
import { openSheet, el as sheetEl } from "../components/sheet.js";
import { loadChoice } from "../state.js";

const LABEL = Object.fromEntries(INTERESTS); // code → 표시 라벨

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

// renderMyPageView({ onBack, onViewChoice }) — prefs 는 비동기 로드 후 채운다.
export function renderMyPageView({ onBack, onViewChoice } = {}) {
  const root = el("section", "mypage");

  // 헤더 — 뒤로 + 타이틀
  const header = el("div", "mypage-head");
  const back = el("button", "mypage-back", "← Back");
  back.type = "button";
  back.addEventListener("click", () => onBack?.());
  header.append(back, el("h1", "mypage-title", "My Page"));
  root.append(header);

  const body = el("div", "mypage-body");
  root.append(body);

  let prefs = null; // { interests, prefer_shorter_walks, needs_onboarding }
  let mode = "view"; // view | edit

  function section(title) {
    const s = el("div", "mypage-section");
    s.append(el("h2", "mypage-section-title", title));
    return s;
  }

  function renderAccount() {
    const s = section("Account");
    const name = displayName();
    const email = userEmail();
    s.append(el("p", "mypage-account-name", name || "Signed in"));
    if (email) s.append(el("p", "mypage-account-email", email));
    return s;
  }

  function renderCurrentChoice() {
    const saved = loadChoice();
    const cand = saved?.env?.data?.candidates?.find(
      (c) => c.id === saved.candidateId,
    );
    if (!cand) return null;
    const s = section("Current choice");
    const card = el("button", "mypage-choice");
    card.type = "button";
    const texts = el("div", "mypage-choice-texts");
    texts.append(
      el("span", "mypage-choice-title", cand.title),
      el(
        "span",
        "mypage-choice-sub",
        `${fmtTime(saved.request.start_at)} session · from ${saved.request.start_location.label}`,
      ),
    );
    card.append(texts, el("span", "mypage-choice-view", "View →"));
    card.addEventListener("click", () =>
      onViewChoice?.({ request: saved.request, env: saved.env }),
    );
    s.append(card);
    return s;
  }

  // 선호 표시(읽기) — 저장된 관심사 라벨 + 걷기 선호. 없으면 안내.
  function renderPreferencesView() {
    const s = section("Preferences");
    const list = prefs?.interests ?? [];
    if (list.length) {
      const chips = el("div", "mypage-pref-chips");
      for (const code of list)
        chips.append(el("span", "parsed-chip", LABEL[code] || code));
      s.append(chips);
    } else {
      s.append(el("p", "mypage-pref-empty", "No interests saved yet."));
    }
    s.append(
      el(
        "p",
        "mypage-pref-walk",
        prefs?.prefer_shorter_walks
          ? "Prefers shorter walks"
          : "No walking preference set",
      ),
    );

    const actions = el("div", "mypage-pref-actions");
    const edit = el("button", "btn-cta", "Edit preferences");
    edit.type = "button";
    edit.addEventListener("click", () => {
      mode = "edit";
      render();
    });
    actions.append(edit);

    if (list.length || prefs?.prefer_shorter_walks) {
      const reset = el("button", "sheet-dismiss", "Reset preferences");
      reset.type = "button";
      reset.addEventListener("click", confirmReset);
      actions.append(reset);
    }
    s.append(actions);
    // 변경은 이후 추천부터 적용됨을 조용히 고지(현재 결과 소급 변경 없음).
    s.append(
      el(
        "p",
        "mypage-pref-note",
        "Changes apply to your next recommendations.",
      ),
    );
    return s;
  }

  // MP-2 · 선호 수정 — 공용 preference-form prefill + Save/Cancel.
  function renderPreferencesEdit() {
    const s = section("Edit preferences");
    const form = createPreferenceForm({
      interests: prefs?.interests ?? [],
      preferShorterWalks: !!prefs?.prefer_shorter_walks,
    });
    s.append(form.element);

    const actions = el("div", "mypage-pref-actions");
    const save = el("button", "btn-cta", "Save");
    save.type = "button";
    save.addEventListener("click", async () => {
      save.disabled = true;
      save.textContent = "Saving…";
      const env = await putPreferences(form.getValues()).catch(() => null);
      if (env?.ok && env.data) prefs = env.data;
      mode = "view";
      render();
    });
    const cancel = el("button", "sheet-dismiss", "Cancel");
    cancel.type = "button";
    cancel.addEventListener("click", () => {
      mode = "view";
      render();
    });
    actions.append(save, cancel);
    s.append(actions);
    return s;
  }

  // MP-3 · 초기화 확인 시트 → 빈 PUT(관심사 [], 걷기 null).
  function confirmReset() {
    openSheet((close) => {
      const c = sheetEl("div", "reset-confirm");
      c.append(
        sheetEl("h2", "sheet-title", "Reset preferences?"),
        sheetEl(
          "p",
          "sheet-sub",
          "This clears your saved interests and walking preference. It won't change your current recommendations.",
        ),
      );
      const confirm = sheetEl("button", "btn-cta", "Reset");
      confirm.type = "button";
      confirm.addEventListener("click", async () => {
        confirm.disabled = true;
        confirm.textContent = "Resetting…";
        const env = await putPreferences({
          interests: [],
          prefer_shorter_walks: null,
        }).catch(() => null);
        if (env?.ok && env.data) prefs = env.data;
        close();
        mode = "view";
        render();
      });
      const keep = sheetEl("button", "sheet-dismiss", "Keep them");
      keep.type = "button";
      keep.addEventListener("click", close);
      c.append(confirm, keep);
      return c;
    });
  }

  function render() {
    body.replaceChildren();
    body.append(renderAccount());
    const choice = renderCurrentChoice();
    if (choice) body.append(choice);
    body.append(mode === "edit" ? renderPreferencesEdit() : renderPreferencesView());
  }

  // 초기: 스켈레톤 → 선호 로드 후 채움.
  body.append(renderAccount(), el("p", "mypage-loading", "Loading…"));
  getPreferences()
    .then((env) => {
      prefs = env?.ok ? env.data : { interests: [], prefer_shorter_walks: null };
    })
    .catch(() => {
      prefs = { interests: [], prefer_shorter_walks: null };
    })
    .finally(render);

  return root;
}
