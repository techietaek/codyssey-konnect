// 조건 요약 pill — "장소 · 시작–종료" + (있으면) 이해한 조건 한 줄.
// 로딩 화면 상단에서 "무엇을 조건으로 찾는 중인지"를 보여준다(투명 공개).
const INTEREST_LABEL = {
  traditional_culture: "Traditional culture",
  palaces_historic: "Palaces & historic",
  hands_on: "Hands-on",
  art_exhibitions: "Art & exhibitions",
  live_performances: "Live performances",
  festivals_events: "Festivals & events",
};

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

// 이해한 조건을 사람이 읽을 라벨 배열로(결과 뷰 conditionChips 와 동일 규칙).
function conditionLabels(cond) {
  if (!cond) return [];
  const labels = (cond.interests ?? []).map((i) => INTEREST_LABEL[i] ?? i);
  for (const i of cond.avoid_interests ?? [])
    labels.push(`Not: ${INTEREST_LABEL[i] ?? i}`);
  if (cond.free_only) labels.push("Free only");
  if (cond.budget_krw) labels.push(`Under ₩${cond.budget_krw.toLocaleString()}`);
  if (cond.indoor_outdoor)
    labels.push(cond.indoor_outdoor === "indoor" ? "Indoor" : "Outdoor");
  if (cond.prefer_shorter_walks) labels.push("Less walking");
  return labels;
}

export function renderConditionSummary(request, conditions) {
  const box = document.createElement("div");
  box.className = "cond-summary";

  const where = document.createElement("p");
  where.className = "cond-summary-where";
  where.textContent = `${request.start_location.label} · ${fmtTime(
    request.start_at,
  )}–${fmtTime(request.end_at)}`;
  box.append(where);

  const labels = conditionLabels(conditions);
  if (labels.length) {
    const cond = document.createElement("p");
    cond.className = "cond-summary-cond";
    cond.textContent = labels.join(" · ");
    box.append(cond);
  }
  return box;
}
