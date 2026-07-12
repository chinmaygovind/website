/* King of Tokyo - client. Renders from the server's public_view; the server is
   authoritative, so this file only draws state and sends intents. */
(function () {
  const { code: CODE, myPid: MY_PID, roster: ROSTER } = window.KOT;
  const socket = io();

  let state = null;              // latest public_view
  let keep = new Set();          // dice indices the player is keeping
  let lastSeq = -1;

  const $ = (id) => document.getElementById(id);
  const esc = (s) => (s + "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const nameOf = (pid) => (ROSTER[pid] && ROSTER[pid].monster) || pid;
  const colorOf = (pid) => (ROSTER[pid] && ROSTER[pid].color) || "#888";
  const isSpectator = () => !MY_PID || !state || !state.mon[MY_PID];

  const FACE = { "1": "1", "2": "2", "3": "3", heart: "❤", energy: "⚡", claw: "✷", "?": "" };
  const FACE_CLASS = { "1": "num", "2": "num", "3": "num", heart: "heart", energy: "energy", claw: "claw", "?": "blank" };

  // ---- socket wiring -------------------------------------------------------
  socket.on("connect", () => socket.emit("join_game", { code: CODE }));
  socket.on("game_state", (d) => {
    Object.assign(ROSTER, d.roster || {});
    state = d.state;
    if (state.seq !== lastSeq) {
      // Fresh dice roll resets the local keep selection to match the server.
      if (state.phase === "rolling") keep = new Set(state.kept.map((k, i) => (k ? i : -1)).filter((i) => i >= 0));
      lastSeq = state.seq;
    }
    render();
  });
  socket.on("act_error", (d) => toast(d.error || "Not allowed."));

  // ---- ping ----------------------------------------------------------------
  setInterval(() => {
    const t = Date.now();
    socket.emit("cping", {}, () => { $("ping").textContent = (Date.now() - t) + "ms"; });
  }, 4000);

  // ---- actions -------------------------------------------------------------
  const emit = (ev, extra) => socket.emit(ev, Object.assign({ code: CODE }, extra || {}));
  function doRoll() { emit("roll", { keep: [...keep] }); }
  function doResolve() { emit("resolve", {}); }
  function doBuy(i) { emit("buy_card", { index: i }); }
  function doSweep() { emit("sweep_shop", {}); }
  function doEndTurn() { emit("end_turn", {}); }
  function doYield(leave) { emit("yield_tokyo", { leave }); }
  function doCardAction(card, choice) { emit("card_action", { card, choice }); }
  function doLeave() { if (confirm("Leave this game? You'll be knocked out.")) { emit("leave_game", {}); location.href = "/lobbies"; } }

  function toggleKeep(i) {
    if (!isMyRollingTurn() || state.roll_num === 0) return;
    if (keep.has(i)) keep.delete(i); else keep.add(i);
    emit("set_keep", { keep: [...keep] });
    renderDice();
  }

  function isMyTurn() { return state && state.current === MY_PID && !isSpectator(); }
  function isMyRollingTurn() { return isMyTurn() && state.phase === "rolling"; }
  function myYieldTurn() {
    const py = state && state.pending_yield;
    return state && state.phase === "yield" && py && py.queue[0] === MY_PID;
  }

  // ---- rendering -----------------------------------------------------------
  function render() {
    if (!state) return;
    renderBanner();
    renderTokyo();
    renderMonsters();
    renderDice();
    renderActions();
    renderShop();
    renderLog();
    renderOverlay();
  }

  function renderBanner() {
    const b = $("turnBanner");
    if (state.phase === "ended") { b.textContent = "Game over"; b.className = "turn-banner"; return; }
    const cur = nameOf(state.current);
    let phase = state.phase === "rolling" ? "rolling" : state.phase === "buying" ? "shopping" : "Tokyo decision";
    if (myYieldTurn()) { b.textContent = "Stay in Tokyo or yield?"; b.className = "turn-banner mine"; return; }
    b.textContent = isMyTurn() ? `Your turn - ${phase}` : `${cur}'s turn - ${phase}`;
    b.className = "turn-banner" + (isMyTurn() ? " mine" : "");
  }

  function monChip(pid) {
    const m = state.mon[pid];
    if (!m) return "";
    return `<span class="mon-chip" style="--c:${colorOf(pid)}">${esc(nameOf(pid))}</span>`;
  }

  function renderTokyo() {
    const t = state.tokyo;
    $("slot-bay").style.display = state.use_bay ? "" : "none";
    $("city-mon").innerHTML = t.city ? bigMon(t.city) : `<div class="slot-empty">empty</div>`;
    $("bay-mon").innerHTML = t.bay ? bigMon(t.bay) : `<div class="slot-empty">empty</div>`;
  }
  function bigMon(pid) {
    const m = state.mon[pid];
    return `<div class="big-mon" style="--c:${colorOf(pid)}">
      <div class="bm-name">${esc(nameOf(pid))}</div>
      <div class="bm-stats"><span class="hp">❤ ${m.hp}</span> <span class="vp">★ ${m.vp}</span></div>
    </div>`;
  }

  function renderMonsters() {
    const order = state.players;
    $("monsters").innerHTML = order.map((pid) => {
      const m = state.mon[pid];
      const inTokyo = state.tokyo.city === pid ? "city" : state.tokyo.bay === pid ? "bay" : null;
      const cls = ["mon-card"];
      if (!m.alive) cls.push("dead");
      if (state.current === pid && state.phase !== "ended") cls.push("active");
      if (pid === MY_PID) cls.push("me");
      const hpPct = Math.max(0, Math.round(100 * m.hp / m.maxhp));
      const toks = tokenPills(m.tokens);
      const cards = (m.cards || []).map((c) =>
        `<span class="own-card" title="${esc(c.name)}: ${esc(c.text || "")}">${esc(c.name)}</span>`).join("");
      return `<div class="${cls.join(" ")}" style="--c:${colorOf(pid)}">
        <div class="mc-head">
          <span class="mc-dot"></span>
          <span class="mc-name">${esc(nameOf(pid))}</span>
          ${inTokyo ? `<span class="mc-tokyo">${inTokyo === "city" ? "TOKYO" : "BAY"}</span>` : ""}
          ${!m.alive ? '<span class="mc-ko">KO</span>' : ""}
        </div>
        <div class="mc-sub">${esc((ROSTER[pid] && ROSTER[pid].name) || "")}${pid === MY_PID ? " (you)" : ""}</div>
        <div class="mc-hpbar"><div class="mc-hpfill" style="width:${hpPct}%"></div><span class="mc-hptext">❤ ${m.hp}/${m.maxhp}</span></div>
        <div class="mc-stats">
          <span class="stat-vp">★ ${m.vp}</span>
          <span class="stat-en">⚡ ${m.energy}</span>
        </div>
        ${toks ? `<div class="mc-tokens">${toks}</div>` : ""}
        ${cards ? `<div class="mc-cards">${cards}</div>` : ""}
      </div>`;
    }).join("");
  }

  function tokenPills(tokens) {
    const out = [];
    for (const [k, v] of Object.entries(tokens || {})) {
      if (v > 0) out.push(`<span class="tok tok-${k}">${k} ${v}</span>`);
    }
    return out.join("");
  }

  function renderDice() {
    const tray = $("diceTray");
    const dice = state.dice || [];
    if (!dice.length || (state.phase !== "rolling" && state.roll_num === 0)) { tray.innerHTML = ""; return; }
    tray.innerHTML = dice.map((f, i) => {
      const kept = keep.has(i);
      const canClick = isMyRollingTurn() && state.roll_num > 0;
      return `<button class="die ${FACE_CLASS[f] || "blank"} ${kept ? "kept" : ""}" ${canClick ? "" : "disabled"} data-i="${i}">
        <span class="die-face">${FACE[f] || ""}</span>
      </button>`;
    }).join("");
    tray.querySelectorAll(".die").forEach((el) => el.onclick = () => toggleKeep(+el.dataset.i));
  }

  function renderActions() {
    const row = $("actionRow");
    let html = "";
    if (state.phase === "ended") {
      html = `<button class="btn" onclick="location.href='/lobbies'">Back to lobbies</button>`;
    } else if (myYieldTurn()) {
      html = `<button class="btn danger" data-a="yield-leave">Yield Tokyo</button>
              <button class="btn" data-a="yield-stay">Stay &amp; take it</button>`;
    } else if (isSpectator()) {
      html = `<span class="spectate">Spectating - ${esc(nameOf(state.current))}'s turn</span>`;
    } else if (state.current !== MY_PID) {
      html = `<span class="spectate">Waiting for ${esc(nameOf(state.current))}…</span>
              <button class="btn ghost sm" data-a="leave">Leave</button>`;
    } else if (state.phase === "rolling") {
      const first = state.roll_num === 0;
      const canRoll = first || state.rolls_left > 0;
      const rollLabel = first ? "Roll dice" : `Reroll (${state.rolls_left} left)`;
      html = `<button class="btn big ${canRoll ? "" : "hidden"}" data-a="roll">${rollLabel}</button>`;
      if (!first) html += `<button class="btn secondary" data-a="resolve">Done - resolve</button>`;
      html += cardActionButtons();
    } else if (state.phase === "buying") {
      html = `<button class="btn big" data-a="end">End turn</button>`;
      html += cardActionButtons();
    }
    row.innerHTML = html;
    row.querySelectorAll("[data-a]").forEach((el) => el.onclick = () => {
      const a = el.dataset.a;
      if (a === "roll") doRoll();
      else if (a === "resolve") doResolve();
      else if (a === "end") doEndTurn();
      else if (a === "yield-leave") doYield(true);
      else if (a === "yield-stay") doYield(false);
      else if (a === "leave") doLeave();
      else if (a.startsWith("card:")) fireCard(a.slice(5));
    });
  }

  // Gather any choice an actionable card needs, then send it.
  function fireCard(id) {
    let choice = null;
    if (id === "herd_culler") {
      const i = askDie("Set which die to a 1?"); if (i == null) return; choice = { index: i };
    } else if (id === "plot_twist" || id === "stretchy") {
      const i = askDie("Change which die?"); if (i == null) return;
      const f = askFace(); if (!f) return; choice = { index: i, face: f };
    }
    doCardAction(id, choice);
  }
  function askDie(msg) {
    const n = state.dice.length;
    const v = prompt(msg + " (1-" + n + ")"); if (v == null) return null;
    const i = parseInt(v, 10) - 1; return (i >= 0 && i < n) ? i : null;
  }
  function askFace() {
    let v = prompt("New face: 1, 2, 3, heart, energy, claw"); if (!v) return null;
    v = v.trim().toLowerCase();
    return ["1", "2", "3", "heart", "energy", "claw"].includes(v) ? v : null;
  }

  // Cards that grant an active ability the player can fire on their turn.
  function cardActionButtons() {
    if (!isMyTurn()) return "";
    const mine = (state.mon[MY_PID] && state.mon[MY_PID].cards) || [];
    const btns = [];
    for (const c of mine) {
      const a = ACTIONABLE[c.id];
      if (a && a.when(state)) btns.push(`<button class="btn card-act" data-a="card:${c.id}">${esc(a.label)}</button>`);
    }
    return btns.join("");
  }

  // Client-side hints for which Keep cards expose a manual action. The server
  // re-validates everything; these just decide when to show the button.
  const ACTIONABLE = {
    herd_culler: { label: "Herd Culler: set a die to 1", when: (s) => s.phase === "rolling" && s.roll_num > 0 },
    plot_twist: { label: "Plot Twist: set a die", when: (s) => s.phase === "rolling" && s.roll_num > 0 },
    stretchy: { label: "Stretchy: change a die (2⚡)", when: (s) => s.phase === "rolling" && s.roll_num > 0 && s.mon[MY_PID].energy >= 2 },
    telepath: { label: "Telepath: +1 reroll (1⚡)", when: (s) => s.phase === "rolling" && s.mon[MY_PID].energy >= 1 },
    smoke_cloud: { label: "Smoke Cloud: +1 reroll", when: (s) => s.phase === "rolling" },
    rapid_healing: { label: "Rapid Healing: heal 1 (2⚡)", when: (s) => (s.mon[MY_PID].energy >= 2 && s.mon[MY_PID].hp < s.mon[MY_PID].maxhp) },
    wings: { label: "Wings: negate damage (2⚡)", when: (s) => s.mon[MY_PID].energy >= 2 },
  };

  function renderShop() {
    const shop = $("shop");
    if (state.phase === "ended") { shop.innerHTML = ""; return; }
    const canBuy = isMyTurn() && state.phase === "buying";
    const myEnergy = (state.mon[MY_PID] && state.mon[MY_PID].energy) || 0;
    const cards = (state.shop || []).map((c, i) => {
      if (!c) return `<div class="card empty">sold out</div>`;
      const afford = myEnergy >= c.cost;
      const cls = ["card", c.type === "keep" ? "keep" : "discard"];
      if (canBuy && afford) cls.push("buyable");
      return `<div class="${cls.join(" ")}" ${canBuy && afford ? `data-buy="${i}"` : ""}>
        <div class="card-top"><span class="card-name">${esc(c.name)}</span><span class="card-cost">${c.cost}⚡</span></div>
        <div class="card-type">${c.type === "keep" ? "Keep" : "Discard"}</div>
        <div class="card-text">${esc(c.text || "")}</div>
      </div>`;
    }).join("");
    const sweep = canBuy
      ? `<button class="btn secondary sweep" ${myEnergy >= 2 ? "" : "disabled"} data-sweep="1">Sweep (2⚡)</button>`
      : "";
    shop.innerHTML = `<div class="shop-head">Power cards <span class="deck-left">${state.deck_left} left in deck</span></div>
      <div class="shop-cards">${cards}</div>${sweep}`;
    shop.querySelectorAll("[data-buy]").forEach((el) => el.onclick = () => doBuy(+el.dataset.buy));
    const sw = shop.querySelector("[data-sweep]"); if (sw) sw.onclick = doSweep;
  }

  function renderLog() {
    const feed = $("logFeed");
    const items = (state.log || []).slice().reverse();
    feed.innerHTML = items.map((l) =>
      `<div class="log-line log-${l.kind || "sys"}">${l.pid ? `<b style="color:${colorOf(l.pid)}">${esc(nameOf(l.pid))}</b> ` : ""}${esc(stripName(l))}</div>`
    ).join("");
  }
  // The server log text already contains the monster name; the pid bold prefix
  // would double it, so strip a leading "<name> " when we render the prefix.
  function stripName(l) {
    if (!l.pid) return l.text;
    const n = nameOf(l.pid);
    return l.text.startsWith(n + " ") ? l.text.slice(n.length + 1) : l.text;
  }

  function renderOverlay() {
    const ov = $("overlay");
    if (state.phase !== "ended") { ov.style.display = "none"; return; }
    const st = state.standings || [];
    const rows = st.map((s) => `<div class="fin-row ${s.place === 1 ? "win" : ""}">
      <span class="fin-place">#${s.place}</span>
      <span class="fin-name" style="color:${colorOf(s.pid)}">${esc(nameOf(s.pid))}</span>
      <span class="fin-vp">★ ${s.vp}</span>
    </div>`).join("");
    const champ = state.winner ? nameOf(state.winner) : "Nobody";
    $("overlayCard").innerHTML = `<div class="crown">👑</div>
      <h2>${esc(champ)} rules Tokyo!</h2>
      <div class="finals">${rows}</div>
      <button class="btn big" onclick="location.href='/lobbies'">Back to lobbies</button>`;
    ov.style.display = "flex";
  }

  // ---- misc UI -------------------------------------------------------------
  let toastT;
  function toast(msg) {
    const t = $("toast"); t.textContent = msg; t.classList.add("show");
    clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("show"), 2200);
  }
  $("logToggle").onclick = () => $("logPanel").classList.toggle("open");
  $("logClose").onclick = () => $("logPanel").classList.remove("open");

  // Keyboard: R roll, Space resolve/end, 1-6 toggle dice.
  document.addEventListener("keydown", (e) => {
    if (!state || e.target.tagName === "INPUT") return;
    if (e.key === "r" || e.key === "R") { if (isMyRollingTurn() && (state.roll_num === 0 || state.rolls_left > 0)) doRoll(); }
    else if (e.code === "Space") {
      e.preventDefault();
      if (isMyRollingTurn() && state.roll_num > 0) doResolve();
      else if (isMyTurn() && state.phase === "buying") doEndTurn();
    } else if (/^[1-6]$/.test(e.key)) { toggleKeep(+e.key - 1); }
  });
})();
