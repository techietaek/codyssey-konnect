// 선호 저장 확인 모달 (온보딩 Save · My Page Edit 공용).
// Save 를 누르면: "Reading your note…" → runParse → 계정(옵션)·관심사·Also 확인 →
// onConfirm(form.getValues()). Also 칩은 ×로 제거 가능(틀린 해석 교정). 원문은 저장 안 함.
import { openSheet, el } from "./sheet.js";

const SPARKLE =
  '<svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18" aria-hidden="true"><path d="M12 3l1.7 4.8L18.5 9.5l-4.8 1.7L12 16l-1.7-4.8L5.5 9.5l4.8-1.7z"/></svg>';

const INTEREST_LABEL = {
  traditional_culture: "Traditional culture",
  palaces_historic: "Palaces & historic",
  hands_on: "Hands-on",
  art_exhibitions: "Art & exhibitions",
  live_performances: "Live performances",
  festivals_events: "Festivals & events",
};

// openPrefConfirm({ form, account?, confirmLabel?, onConfirm })
export function openPrefConfirm({
  form,
  account = null,
  confirmLabel = "Save and continue",
  onConfirm,
}) {
  openSheet((close) => {
    const c = el("div", "onb-confirm");

    const titleRow = el("div", "confirm-title-row");
    const spark = el("span", "confirm-spark");
    spark.innerHTML = SPARKLE;
    titleRow.append(spark, el("h2", "sheet-title", "Does this look right?"));
    c.append(titleRow);

    if (account) {
      const acct = el("div", "onb-confirm-acct");
      acct.append(
        el("div", "mypage-avatar", account.name ? account.name.trim()[0].toUpperCase() : "👤"),
      );
      const t = el("div", "onb-confirm-acct-text");
      t.append(el("span", "mypage-account-name", account.name || "Signed in"));
      if (account.email) t.append(el("span", "mypage-account-sub", account.email));
      acct.append(t);
      c.append(acct);
    }

    const results = el("div", "onb-confirm-results");
    c.append(results);

    const saveBtn = el("button", "btn-cta", confirmLabel);
    saveBtn.type = "button";
    saveBtn.disabled = true;
    saveBtn.addEventListener("click", () => {
      close();
      onConfirm?.(form.getValues());
    });
    const editBtn = el("button", "sheet-dismiss", "Edit");
    editBtn.type = "button";
    editBtn.addEventListener("click", close);
    c.append(saveBtn, editBtn);

    // 관심사는 파싱이 필요 없다 → 즉시 렌더(모달이 비어 보이지 않게). "Also"(자유입력 해석)만
    // 비동기로 채운다. parsing=true 면 Also 자리에 스피너, 아니면 최종 칩.
    function fill(parsing) {
      results.replaceChildren();
      const v = form.getValues();
      if (v.interests.length) {
        results.append(el("p", "onb-confirm-label", "Your interests"));
        const chips = el("div", "mypage-pref-chips");
        for (const code of v.interests)
          chips.append(el("span", "parsed-chip", INTEREST_LABEL[code] || code));
        results.append(chips);
      }
      if (parsing) {
        const reading = el("p", "pref-status");
        reading.append(
          el("span", "pref-spinner"),
          el("span", null, "Reading your note…"),
        );
        results.append(reading);
        return;
      }
      const extras = [...v.open_preferences];
      if (v.prefer_shorter_walks === true) extras.push("Shorter walks");
      else if (v.prefer_shorter_walks === false) extras.push("Happy to walk");
      if (extras.length) {
        results.append(el("p", "onb-confirm-label", "Also"));
        const chips = el("div", "remember-chips");
        for (const p of extras) {
          const chip = el("span", "remember-chip");
          chip.append(el("span", null, p));
          const x = el("button", "remember-chip-x", "✕");
          x.type = "button";
          x.setAttribute("aria-label", `Remove ${p}`);
          x.addEventListener("click", () => {
            form.removeExtra(p);
            fill(false);
          });
          chip.append(x);
          chips.append(chip);
        }
        results.append(chips);
      }
      if (!v.interests.length && !extras.length)
        results.append(
          el(
            "p",
            "pref-status",
            "Nothing to save yet — you can skip, or go back and add something.",
          ),
        );
    }

    const hasNote = form.hasNote();
    fill(hasNote); // 즉시: 관심사 노출 + (노트 있으면) Also 스피너
    if (!hasNote) {
      saveBtn.disabled = false; // 파싱할 게 없으면 바로 저장 가능
    } else {
      (async () => {
        await form.runParse();
        fill(false);
        saveBtn.disabled = false;
      })();
    }

    return c;
  });
}
