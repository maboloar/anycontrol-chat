"use strict";
// 안내 챗봇의 웹캠 캐릭터. AnyControl 앱(CameraBuddy.tsx)과 같은 11×12 픽셀 웹캠이다:
// 머리만 두리번거리고, 가끔 깜박이고, 녹화 불빛이 깜박이며, 누르면 통통 뛰고 눈을 두 번 깜박인다. 오래 입력이 없으면 졸린다.
const Buddy = (() => {
  const PALETTE = { B: "#6ea8fe", S: "#3f5f9e", K: "#1b1f27", W: "#ffffff", R: "#ff4d6d" };
  const BODY = ["...BBBBB...", "..BBBBBRB..", ".BBBKKKBBB.", ".BBKWKKKBB.", ".BBKKKKKBB.", ".BBKKKKKBB.", ".BBBKKKBBB.", "..BBBBBBB..", "...BBBBB...", ".....S.....", "....SSS....", "..SSSSSSS.."];
  const STAND_FROM = 9;                                           // 이 줄부터 받침 (머리만 움직인다)
  const BLINK = { 2: ".BBBBBBBBB.", 3: ".BBBBBBBBB.", 5: ".BBBBBBBBB.", 6: ".BBBBBBBBB." };   // 셔터가 닫히듯 렌즈가 한 줄만 남는다
  const NS = "http://www.w3.org/2000/svg";
  const W = BODY[0].length, H = BODY.length;
  const mk = (tag, attrs) => { const n = document.createElementNS(NS, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); return n; };

  function create(button, size) {
    const svg = mk("svg", { class: "buddy", viewBox: `-1 0 ${W + 2} ${H}`, width: size, height: (size * H) / (W + 2), "shape-rendering": "crispEdges", "aria-hidden": "true" });
    const head = mk("g", { class: "buddy-head" }), stand = mk("g", {});
    const zzz = mk("g", { class: "buddy-zzz" });
    [[W - 1, 2.5], [W + 0.2, 1], [W + 1.4, -0.5]].forEach(([x, y]) => { const t = mk("text", { x, y }); t.textContent = "z"; zzz.appendChild(t); });
    svg.append(head, stand, zzz);
    button.appendChild(svg);
    const st = { blink: false, sleeping: false, timers: [] };

    function render() {
      head.replaceChildren(); stand.replaceChildren();
      const closed = st.blink || st.sleeping;
      BODY.forEach((row, y) => {
        [...((closed && BLINK[y]) || row)].forEach((ch, x) => {
          if (ch === ".") return;
          const r = mk("rect", { x, y, width: 1.02, height: 1.02, fill: PALETTE[ch] });
          if (ch === "R") r.setAttribute("class", "buddy-rec");
          (y < STAND_FROM ? head : stand).appendChild(r);
        });
      });
    }
    function loop() {                                              // 3~8초마다 혼자 깜박인다
      st.timers.push(setTimeout(() => {
        st.blink = true; render();
        setTimeout(() => { st.blink = false; render(); loop(); }, 150);
      }, 3000 + Math.random() * 5000));
    }
    function react() {                                             // 누르면: 통통 뛰며 두리번거리고 눈을 두 번 깜박인다
      button.classList.remove("playing");
      requestAnimationFrame(() => {
        button.classList.add("playing");
        setTimeout(() => button.classList.remove("playing"), 1300);
      });
      [0, 160, 320, 480].forEach((d, i) => setTimeout(() => { st.blink = i % 2 === 0; render(); }, d));
    }
    function sleeping(on) { if (st.sleeping !== on) { st.sleeping = on; svg.classList.toggle("sleeping", on); render(); } }
    button.addEventListener("click", react);
    render(); loop();
    return { react, sleeping };
  }
  return { create };
})();
