"use strict";
if (/Win/i.test(navigator.platform || navigator.userAgent)) document.documentElement.classList.add("win");      // Windows 에서는 글꼴 보정 적용
// 키오스크 화면. 서버가 보낸 텍스트는 항상 textContent 로만 넣는다 (HTML 주입 방지).
const IDLE_MS = 45000, FADE_MS = 9000;          // 45초 동안 입력이 없으면 9초에 걸쳐 서서히 처음 화면으로
const $ = (id) => document.getElementById(id);
const state = { lang: "ko", cfg: null, cat: "", busy: false, last: Date.now(), chatStarted: false, ctx: [], prev: "", hist: [], gen: 0 };
const MAX_Q = 300;                                  // 서버가 처리하는 질문 길이 (넘으면 조용히 자르지 않고 알려 준다)

const ui = () => (state.cfg && state.cfg.ui[state.lang]) || {};
const T = (k) => ui()[k] || k;

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}
// **굵게** 와 https:// 주소(바로 누를 수 있는 링크)만 지원하는 아주 작은 서식. 모두 textContent 로만 넣는다.
function rich(parent, text) {
  text.split(/(\*\*[^*]+\*\*|https:\/\/[A-Za-z0-9._~:\/?#@!$&'()*+,;=%-]+)/g).forEach((part) => {
    if (part.startsWith("**") && part.endsWith("**")) parent.appendChild(el("b", null, part.slice(2, -2)));
    else if (/^https:\/\//.test(part)) {
      const a = el("a", "link", part);
      a.href = part; a.target = "_blank"; a.rel = "noopener noreferrer";
      parent.appendChild(a);
    } else if (part) parent.appendChild(document.createTextNode(part));
  });
}
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (r.status === 429) throw new Error("toofast");
  if (!r.ok) throw new Error("http " + r.status);
  return r.json();
}

function applyChrome() {
  const c = state.cfg;
  document.documentElement.lang = state.lang;
  const title = c.title[state.lang];
  $("title").textContent = title;
  document.title = title;
  $("home").textContent = T("home");
  $("lang-label").textContent = T("lang");
  $("welcome").hidden = state.chatStarted;
  $("send").textContent = T("send");
  $("q").placeholder = T("placeholder");
  $("suggest-title").textContent = T("suggest");
  $("welcome-text").textContent = (c.messages && c.messages.greeting && c.messages.greeting[state.lang]) || "";
  $("disclaimer").textContent = T("disclaimer");
  renderCats();
}
function renderCats() {
  const box = $("cats");
  box.replaceChildren();
  const all = el("button", state.cat === "" ? "on" : "", T("all"));
  all.type = "button";
  all.onclick = () => { state.cat = ""; renderCats(); loadSuggestions(); };
  box.appendChild(all);
  state.cfg.cats.filter((c) => !c.hidden).forEach((c) => {
    const b = el("button", state.cat === c.id ? "on" : "", c[state.lang]);
    b.type = "button";
    b.onclick = () => { state.cat = c.id; renderCats(); loadSuggestions(); };
    box.appendChild(b);
  });
}
async function loadSuggestions() {
  const d = await api(`/api/suggest?lang=${state.lang}&cat=${encodeURIComponent(state.cat)}&n=${state.cat ? 14 : 12}`);
  const box = $("suggestions");
  box.replaceChildren();
  d.items.forEach((it) => box.appendChild(cardButton(it, true)));
}
function cardButton(it, big) {
  const b = el("button", null, it.q);
  b.type = "button";
  b.dataset.id = it.id;                              // 언어를 바꿀 때 이 카드의 새 언어 문구로 바꾸기 위해
  b.onclick = () => showCard(it.id, it.q);
  return b;
}

function addQ(text) {
  state.chatStarted = true;
  $("welcome").hidden = true;
  $("chat").appendChild(el("div", "msg-q", text));
}
function badge(status) {
  const lab = state.cfg.statuses[status] || { ko: status, en: status };
  const sp = el("span", "badge " + status, lab[state.lang]);
  sp.dataset.status = status;
  return sp;
}
// 화면 언어를 바꾸면 이미 떠 있는 이어지는 질문 버튼·제목·배지도 새 언어로 바꾼다 (답 본문은 질문한 그대로 둔다)
async function relabel() {
  document.querySelectorAll("#chat .more h3").forEach((h) => { h.textContent = T(h.dataset.key); });
  document.querySelectorAll("#chat .badge[data-status]").forEach((x) => {
    const lab = state.cfg.statuses[x.dataset.status]; if (lab) x.textContent = lab[state.lang];
  });
  const btns = Array.from(document.querySelectorAll("#chat button[data-id]"));
  if (!btns.length) return;
  try {
    const ids = Array.from(new Set(btns.map((b) => b.dataset.id)));
    const d = await api(`/api/labels?lang=${state.lang}&ids=${encodeURIComponent(ids.join(","))}`);
    btns.forEach((b) => { if (d.labels[b.dataset.id]) b.textContent = d.labels[b.dataset.id]; });
  } catch (e) { /* 실패하면 그대로 둔다 */ }
}
function renderAnswer(res) {
  const box = el("div", "msg-a");
  if (res.note) box.appendChild(el("div", "note", res.note));
  const text = el("div", "text");
  rich(text, res.answer || "");
  box.appendChild(text);
  if (res.source_answer) {                       // AI 가 정리한 답이면 카드 원문을 접어서 보여 준다
    const det = el("details", "source");
    det.appendChild(el("summary", null, T("source_toggle")));
    det.appendChild(el("div", "source-text", res.source_answer));
    box.appendChild(det);
  }
  const meta = el("div", "meta");
  const card = res.card;
  if (card) {
    meta.appendChild(badge(card.status));
  }
  if (res.mode === "llm" && res.card) meta.appendChild(el("span", "src", "· " + T("mode_llm")));
  if (meta.childNodes.length) box.appendChild(meta);
  const more = (res.more && res.more.length) ? res.more : (res.kind === "none" || res.kind === "greeting" || res.kind === "empty" || res.kind === "chat") ? (res.suggestions || []) : [];
  if (more.length) {
    const m = el("div", "more");
    const h3 = el("h3", null, res.kind === "none" ? T("suggest") : T("related"));
    h3.dataset.key = res.kind === "none" ? "suggest" : "related";
    m.appendChild(h3);
    const row = el("div", "row");
    more.forEach((it) => row.appendChild(cardButton(it)));
    m.appendChild(row);
    box.appendChild(m);
  }
  $("chat").appendChild(box);
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

function notice(text) {                              // 대화에 짧은 안내 카드를 넣는다 (서버로 보내지 않는다)
  state.chatStarted = true;
  $("welcome").hidden = true;
  const box = el("div", "msg-a");
  box.appendChild(el("div", "text", text));
  $("chat").appendChild(box);
  box.scrollIntoView({ behavior: "instant", block: "end" });
}
async function ask(text) {
  text = (text || "").trim();
  if (!text || state.busy) return false;
  if (text.length > MAX_Q) {                          // 입력란 제한을 우회해 들어온 긴 글도 조용히 잘리지 않게
    notice(T("toolong").replace("{n}", String(MAX_Q)).replace("{len}", String(text.length)));
    return false;
  }
  const gen = state.gen, reqLang = state.lang;
  state.busy = true;
  $("send").disabled = true;
  addQ(text);
  const wait = el("div", "msg-a thinking");
  wait.appendChild(el("span", "dots", T("thinking")));
  $("chat").appendChild(wait);
  wait.scrollIntoView({ behavior: "instant", block: "end" });      // "찾는 중…" 카드가 화면 아래에 잘리지 않게
  try {
    const res = await api("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q: text, lang: state.lang, ctx: state.ctx, prev: state.prev, hist: state.hist }) });
    wait.remove();
    if (gen !== state.gen) return true;               // 기다리는 동안 '처음으로'를 눌렀다면 이전 질문의 답은 새 화면에 넣지 않는다
    renderAnswer(res);
    if (state.lang !== reqLang) relabel();            // 기다리는 동안 언어를 바꿨다면 추천 버튼·제목도 지금 언어로
    if (res.card) { state.ctx = [res.card.id]; state.prev = text; state.hist = []; }      // 카드로 답했으면 잡담 흐름은 끝
    else if (res.kind === "none") { state.ctx = []; state.prev = ""; }      // 답을 못 찾은 뒤의 "그건 왜요?"가 옛 주제로 이어지지 않게
    if (res.kind === "chat" && (res.via === "free_chat" || res.via === "chitchat")) state.hist = state.hist.concat([{ q: text, a: res.answer }]).slice(-3);   // 잡담이 이어질 때 앞 말을 기억   // 이어 묻기("그럼 얼마예요?")를 위해 직전 답의 카드와 질문을 기억
  } catch (e) {
    wait.remove();
    if (gen === state.gen) renderAnswer({ answer: e.message === "toofast" ? T("toofast") : T("error"), kind: "none" });
  } finally {
    if (gen === state.gen) { state.busy = false; $("send").disabled = false; }
    touch();
  }
  return true;
}
async function showCard(id, qtext) {
  if (state.busy) return;
  addQ(qtext);
  try {
    const c = await api(`/api/card?id=${encodeURIComponent(id)}&lang=${state.lang}`);
    renderAnswer({ answer: c.a, card: c, kind: "answer", mode: "cards", more: c.more || [] });
    state.ctx = [c.id]; state.prev = qtext;
  } catch (e) {
    renderAnswer({ answer: T("error"), kind: "none" });
  }
  touch();
}

function home(resetLang) {
  if (resetLang && state.lang !== "ko") { state.lang = "ko"; applyChrome(); }   // 다음 방문객은 항상 한국어로 시작
  state.gen++;                                      // 아직 오는 중인 이전 답은 무시한다
  state.busy = false; $("send").disabled = false;
  $("chat").replaceChildren();
  $("welcome").hidden = false;
  state.chatStarted = false;
  state.ctx = []; state.prev = ""; state.hist = [];
  state.cat = "";
  $("q").value = "";
  $("idle").hidden = true;
  renderCats();
  loadSuggestions();
  window.scrollTo(0, 0);
  document.querySelector("main").scrollTo(0, 0);
}
function touch() { state.last = Date.now(); $("idle").hidden = true; if (state.fading) stopFade(); if (state.buddy) state.buddy.sleeping(false); }
function startFade() { state.fading = true; if (state.buddy) state.buddy.sleeping(true); $("main").classList.remove("fade-restore"); $("main").classList.add("fading"); }
function stopFade() {                       // 키보드·마우스·터치가 있으면 서서히 사라지던 것을 멈추고 원래대로
  state.fading = false;
  const m = $("main");
  m.classList.remove("fading");
  m.classList.add("fade-restore");
  setTimeout(() => m.classList.remove("fade-restore"), 400);
}

async function init() {
  state.buddy = Buddy.create($("buddy"), 44);
  state.cfg = await api("/api/config");
  state.cfg.messages = state.cfg.messages || {};
  applyChrome();
  await loadSuggestions();
  $("lang").onclick = async () => { state.lang = state.lang === "ko" ? "en" : "ko"; applyChrome(); await loadSuggestions(); relabel(); touch(); };
  $("home").onclick = () => { home(); touch(); };
  $("brand").onclick = (ev) => { ev.preventDefault(); home(); touch(); };      // 제목(로고)을 누르면 처음 화면으로
  $("ask").onsubmit = async (ev) => { ev.preventDefault(); const v = $("q").value; $("q").value = ""; const ok = await ask(v); if (ok === false && v.trim()) $("q").value = v; };    // 보내지 못했으면 글을 그대로 남긴다
  ["pointerdown", "pointermove", "mousemove", "mousedown", "click", "keydown", "touchstart", "wheel"].forEach((n) => window.addEventListener(n, touch, { passive: true }));
  let scrollTimer = 0;                   // 스크롤 막대는 스크롤하는 동안만 보인다 (맥처럼)
  $("main").addEventListener("scroll", () => {
    const m = $("main");
    m.classList.add("scrolling");
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(() => m.classList.remove("scrolling"), 900);
  }, { passive: true });
  setInterval(() => {
    if (!state.chatStarted || state.busy) { if (state.fading) stopFade(); return; }
    const idle = Date.now() - state.last;
    if (idle > IDLE_MS + FADE_MS) {         // 끝까지 입력이 없었다 → 처음 화면으로 (새 화면은 부드럽게 나타난다)
      home(true);
      state.fading = false;
      if (state.buddy) state.buddy.sleeping(false);
      const m = $("main");
      m.classList.remove("fading");
      m.classList.add("fade-in");
      setTimeout(() => m.classList.remove("fade-in"), 900);
      state.last = Date.now();
    } else if (idle > IDLE_MS && !state.fading) startFade();
  }, 500);
}
// 탭·창을 닫으면 서버에 알린다 (새로고침이면 곧바로 다시 접속하므로 서버가 끄지 않는다)
const PAGE_ID = Math.random().toString(36).slice(2, 12);
const beacon = (path) => { try { navigator.sendBeacon(path, new Blob([JSON.stringify({ pid: PAGE_ID })], { type: "application/json" })); } catch (e) { /* 무시 */ } };
beacon("/api/hello");
window.addEventListener("pageshow", () => beacon("/api/hello"));       // 뒤로 가기로 돌아왔을 때도 열려 있다고 알린다
window.addEventListener("pagehide", () => beacon("/api/bye"));
init().catch(() => { document.body.textContent = "Server error"; });
