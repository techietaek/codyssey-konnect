// 뷰 컨트롤러: 입력(LF-02) ↔ 결과(LF-03) 전환. 단일 #view 컨테이너에 주입.
import { renderInputView } from "./pages/input.js";
import { renderResultsView } from "./pages/results.js";

const viewEl = document.getElementById("view");

function mount(node) {
  viewEl.replaceChildren(node);
  viewEl.scrollTop = 0;
}

export function showInput(prefill) {
  mount(renderInputView({ prefill, onResults: showResults, onViewChoice: showResults }));
}

export function showResults({ request, env }) {
  mount(renderResultsView({ request, env, onEdit: () => showInput(request) }));
}

showInput();
