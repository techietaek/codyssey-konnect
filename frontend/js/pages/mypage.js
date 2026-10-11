// MP-1~3 · My Page (Phase 2 L3 · FR-L6). 10/8 MP-1b/2c 디자인 반영.
//  - 계정(아바타 + 이름) · 현재 선택 진입(또는 빈 상태) · 선호 확인/수정/초기화
//  - 하단 Sign out. 선호 변경은 **이후 추천부터** 적용. 저장은 PUT /api/preferences.
import { displayName, signOut } from "../auth.js";
import { getPreferences, putPreferences } from "../api.js";
import { createPreferenceForm, INTERESTS } from "../components/preference-form.js";
import { openPrefConfirm } from "../components/pref-confirm.js";
import { openSheet, el as sheetEl } from "../components/sheet.js";
import { clearRoute, loadChoice, loadRoute, rebuildSavedRoute } from "../state.js";
import { renderSavedRouteCard } from "../components/saved-route-card.js";

const LABEL = Object.fromEntries(INTERESTS); // code → 표시 라벨
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
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

export function renderMyPageView({ onBack, onHome, onViewChoice } = {}) {
  const root = el("section", "mypage");

  // Nav — chevron Back · My Page · Home(우상단).
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
  nav.append(back, el("span", "nav-title", "My Page"), home);
  root.append(nav);

  const body = el("div", "mypage-body");
  root.append(body);

  let prefs = null; // { interests, prefer_shorter_walks, open_preferences }
  let mode = "view"; // view | edit

  // 계정 — 아바타(이니셜) + 이름 + "Signed in with Google".
  function renderAccount() {
    const s = el("div", "mypage-account");
    const name = displayName();
    const avatar = el(
      "div",
      "mypage-avatar",
      name ? name.trim()[0].toUpperCase() : "👤",
    );
    const text = el("div", "mypage-account-text");
    text.append(
      el("span", "mypage-account-name", name || "Signed in"),
      el("span", "mypage-account-sub", "Signed in with Google"),
    );
    s.append(avatar, text);
    return s;
  }

  // 현재 선택 — 있으면 teal 테두리 카드(→ 상세), 없으면 빈 상태(Explore → 홈).
  function renderCurrentChoice() {
    const saved = loadChoice();
    const cand = saved?.env?.data?.candidates?.find(
      (c) => c.id === saved.candidateId,
    );
    const card = el("button", "mypage-cc");
    card.type = "button";
    const texts = el("div", "mypage-cc-texts");
    texts.append(el("span", "mypage-cc-label", "YOUR CURRENT CHOICE"));
    if (cand) {
      card.classList.add("has-choice");
      texts.append(
        el("span", "mypage-cc-title", cand.title),
        el("span", "mypage-cc-sub", `Today · ${fmtTime(saved.request.start_at)} session`),
      );
      card.append(texts, el("span", "mypage-cc-arrow", "→"));
      card.addEventListener("click", () => onViewChoice?.());
    } else {
      texts.append(
        el("span", "mypage-cc-title", "Nothing chosen yet"),
        el("span", "mypage-cc-sub", "Find something to do now or plan a day"),
      );
      card.append(texts, el("span", "mypage-cc-explore", "Explore →"));
      card.addEventListener("click", () => onBack?.());
    }
    return card;
  }

  // 선호 보기 — 관심사 칩 + "Also" 추가선호 + Edit/Add·Reset 링크(MP-1b).
  function renderPreferencesView() {
    const s = el("div", "mypage-prefs");
    const list = prefs?.interests ?? [];
    const extras = [...(prefs?.open_preferences ?? [])];
    if (prefs?.prefer_shorter_walks === true) extras.push("Shorter walks");
    else if (prefs?.prefer_shorter_walks === false) extras.push("Happy to walk");
    const hasAny = list.length || extras.length;

    const head = el("div", "mypage-prefs-head");
    head.append(el("h2", "mypage-prefs-title", "Your preferences"));
    const edit = el("button", "mypage-link", hasAny ? "Edit" : "Add");
    edit.type = "button";
    edit.addEventListener("click", () => {
      mode = "edit";
      render();
    });
    head.append(edit);
    s.append(head);
    s.append(
      el(
        "p",
        "mypage-prefs-sub",
        "Used for future suggestions. Your current request always comes first.",
      ),
    );

    if (list.length) {
      const chips = el("div", "mypage-pref-chips");
      for (const code of list)
        chips.append(el("span", "parsed-chip", LABEL[code] || code));
      s.append(chips);
    }
    if (extras.length) {
      s.append(el("p", "mypage-pref-also", "Also"));
      s.append(el("p", "mypage-pref-also-list", extras.join(" · ")));
    }
    if (!hasAny) s.append(el("p", "mypage-pref-empty", "Nothing saved yet"));

    if (hasAny) {
      const reset = el("button", "mypage-link mypage-link--danger", "Reset preferences");
      reset.type = "button";
      reset.addEventListener("click", confirmReset);
      s.append(reset);
    }
    return s;
  }

  // 선호 수정 — 관심사 + 자유입력(인라인 해석 없음). Save 시 확인 모달에서 해석 결과를
  // 보여주고(Also × 제거 가능) 저장한다(온보딩과 동일 UX, 화면에 인라인 박스를 띄우지 않음).
  function renderPreferencesEdit() {
    const s = el("div", "mypage-prefs");
    s.append(el("h2", "mypage-prefs-title", "Your preferences"));
    const form = createPreferenceForm({
      interests: prefs?.interests ?? [],
      preferShorterWalks: prefs?.prefer_shorter_walks ?? null, // tri-state 보존
      openPreferences: prefs?.open_preferences ?? [],
      autoParse: false,
    });
    s.append(form.element);

    const actions = el("div", "mypage-pref-actions");
    const save = el("button", "btn-cta", "Save");
    save.type = "button";
    save.addEventListener("click", () =>
      openPrefConfirm({
        form,
        confirmLabel: "Save",
        onConfirm: async (values) => {
          const env = await putPreferences(values).catch(() => null);
          if (env?.ok && env.data) prefs = env.data;
          mode = "view";
          render();
        },
      }),
    );
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

  // 초기화 확인 시트 → 빈 PUT(관심사 [] · 걷기 null · 개방형 []).
  function confirmReset() {
    openSheet((close) => {
      const c = sheetEl("div", "reset-confirm");
      c.append(
        sheetEl("h2", "sheet-title", "Reset preferences?"),
        sheetEl(
          "p",
          "sheet-sub",
          "This clears your saved interests and extra preferences. It won't change your current recommendations.",
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
          open_preferences: [],
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

  function renderSignOut() {
    const btn = el("button", "mypage-signout", "Sign out");
    btn.type = "button";
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "Signing out…";
      try {
        await signOut();
      } catch (e) {
        btn.disabled = false;
        btn.textContent = "Sign out";
        console.warn("sign-out failed:", e?.message || e);
      }
    });
    return btn;
  }

  // 저장된 B 문화루트 슬롯 — DB에서 참조 로드 → 라이브 재조립해 표시. 한 번만 네트워크 조회하고
  // 결과(savedRouteData)를 캐시해, render() 가 여러 번 불려도 카드가 사라지지 않게 다시 그린다.
  let routeChecked = false;
  let savedRouteData = null;
  let savedRouteRef = null;
  function renderRouteSlot() {
    const slot = el("div", "mypage-route-slot");
    const paint = () => {
      slot.replaceChildren();
      if (!savedRouteRef) return;
      const card = renderSavedRouteCard(savedRouteData, savedRouteRef, {
        onClear: () => {
          clearRoute();
          savedRouteData = null;
          savedRouteRef = null;
          slot.replaceChildren();
        },
      });
      if (card) slot.append(card);
    };
    if (!routeChecked) {
      routeChecked = true;
      loadRoute().then(async (ref) => {
        savedRouteRef = ref;
        if (ref) savedRouteData = await rebuildSavedRoute(ref);
        paint();
      });
    } else {
      paint();
    }
    return slot;
  }

  function render() {
    body.replaceChildren();
    body.append(renderAccount());
    body.append(renderCurrentChoice());
    body.append(renderRouteSlot());
    body.append(mode === "edit" ? renderPreferencesEdit() : renderPreferencesView());
    body.append(renderSignOut());
  }

  // 초기: 스켈레톤 → 선호 로드 후 채움.
  body.append(renderAccount(), el("p", "mypage-loading", "Loading…"));
  getPreferences()
    .then((env) => {
      prefs = env?.ok
        ? env.data
        : { interests: [], prefer_shorter_walks: null, open_preferences: [] };
    })
    .catch(() => {
      prefs = { interests: [], prefer_shorter_walks: null, open_preferences: [] };
    })
    .finally(render);

  return root;
}
