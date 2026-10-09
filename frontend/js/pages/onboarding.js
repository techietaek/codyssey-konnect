// P9-2 · 선호 온보딩 (Phase 2 L2 · FR-L3). 첫 Google 가입 직후 1회·1화면.
// 관심사 6개 복수선택 + 자유입력("Anything else?"). Save and continue 를 누르면
// 자유입력을 해석(reading)하고 **확인 모달**로 이름·이메일 + 해석 결과("Also")를 보여준 뒤
// 저장한다(사용자 요청). 인라인 해석은 하지 않는다(autoParse=false).
import { displayName, userEmail } from "../auth.js";
import { createPreferenceForm } from "../components/preference-form.js";
import { openSheet, el as sheetEl } from "../components/sheet.js";

const SPARKLE =
  '<svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18" aria-hidden="true"><path d="M12 3l1.7 4.8L18.5 9.5l-4.8 1.7L12 16l-1.7-4.8L5.5 9.5l4.8-1.7z"/></svg>';

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text != null) n.textContent = text;
  return n;
}

// onSubmit({ interests, prefer_shorter_walks, open_preferences }) · onSkip()
export function renderOnboardingView({ onSubmit, onSkip } = {}) {
  const root = el("section", "onboarding");

  root.append(el("p", "onboarding-kicker", "Welcome to KONNECT"));
  const header = el("div", "onboarding-head");
  header.append(
    el("h1", "onboarding-title", "What do you enjoy?"),
    el(
      "p",
      "onboarding-sub",
      "Optional. We'll use this for future suggestions. Your current search stays as it is.",
    ),
  );
  root.append(header);

  const form = createPreferenceForm({ autoParse: false });
  root.append(form.element);

  root.append(
    el("p", "onboarding-foot", "You can change or reset this anytime in My Page."),
  );

  const actions = el("div", "onboarding-actions");
  const save = el("button", "btn-cta", "Save and continue");
  save.type = "button";
  const skip = el("button", "sheet-dismiss", "Skip for now");
  skip.type = "button";
  save.addEventListener("click", openConfirm);
  skip.addEventListener("click", () => {
    skip.disabled = true;
    onSkip?.();
  });
  actions.append(save, skip);
  root.append(actions);

  // Save → 확인 모달: reading → 이름/이메일 + 관심사 + Also → "이게 맞나요?" → 저장.
  function openConfirm() {
    openSheet((close) => {
      const c = sheetEl("div", "onb-confirm");
      const titleRow = sheetEl("div", "confirm-title-row");
      const spark = sheetEl("span", "confirm-spark");
      spark.innerHTML = SPARKLE;
      titleRow.append(spark, sheetEl("h2", "sheet-title", "Does this look right?"));
      c.append(titleRow);

      // 계정(이 계정으로 가입)
      const name = displayName();
      const email = userEmail();
      const acct = sheetEl("div", "onb-confirm-acct");
      acct.append(
        sheetEl("div", "mypage-avatar", name ? name.trim()[0].toUpperCase() : "👤"),
      );
      const acctText = sheetEl("div", "onb-confirm-acct-text");
      acctText.append(sheetEl("span", "mypage-account-name", name || "Signed in"));
      if (email) acctText.append(sheetEl("span", "mypage-account-sub", email));
      acct.append(acctText);
      c.append(acct);

      const results = sheetEl("div", "onb-confirm-results");
      c.append(results);

      const saveBtn = sheetEl("button", "btn-cta", "Save and continue");
      saveBtn.type = "button";
      saveBtn.disabled = true;
      saveBtn.addEventListener("click", () => {
        close();
        save.disabled = true;
        onSubmit?.(form.getValues());
      });
      const editBtn = sheetEl("button", "sheet-dismiss", "Edit");
      editBtn.type = "button";
      editBtn.addEventListener("click", close);
      c.append(saveBtn, editBtn);

      // reading → 해석 → 결과 채움.
      results.append(
        (() => {
          const r = sheetEl("p", "pref-status");
          r.append(sheetEl("span", "pref-spinner"), sheetEl("span", null, "Reading your note…"));
          return r;
        })(),
      );
      (async () => {
        if (form.hasNote()) await form.runParse();
        fillResults(results);
        saveBtn.disabled = false;
      })();

      return c;
    });
  }

  function fillResults(container) {
    container.replaceChildren();
    const v = form.getValues();
    if (v.interests.length) {
      container.append(el("p", "onb-confirm-label", "Your interests"));
      const chips = el("div", "mypage-pref-chips");
      for (const code of v.interests)
        chips.append(el("span", "parsed-chip", INTEREST_LABEL[code] || code));
      container.append(chips);
    }
    const extras = [...v.open_preferences];
    if (v.prefer_shorter_walks) extras.push("Shorter walks");
    if (extras.length) {
      container.append(el("p", "onb-confirm-label", "Also"));
      const chips = el("div", "mypage-pref-chips");
      for (const p of extras) chips.append(el("span", "parsed-chip", p));
      container.append(chips);
    }
    if (!v.interests.length && !extras.length) {
      container.append(
        el(
          "p",
          "pref-status",
          "Nothing to save yet — you can skip, or go back and add something.",
        ),
      );
    }
  }

  return root;
}

const INTEREST_LABEL = {
  traditional_culture: "Traditional culture",
  palaces_historic: "Palaces & historic",
  hands_on: "Hands-on",
  art_exhibitions: "Art & exhibitions",
  live_performances: "Live performances",
  festivals_events: "Festivals & events",
};
