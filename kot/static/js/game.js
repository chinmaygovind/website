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

  const MONSTER_EMOJI = {
    "Gigazaur": "🦖", "The King": "🦍", "Cyber Bunny": "🐰",
    "Kraken": "🐙", "Meka Dragon": "🐉", "Alienoid": "👽",
  };
  const emojiOf = (pid) => MONSTER_EMOJI[nameOf(pid)] || "👹";
  const dispName = (pid) => `${emojiOf(pid)} ${esc(nameOf(pid))}`;

  const FACE = { "1": "1", "2": "2", "3": "3", heart: "❤", energy: "⚡", claw: "✷", "?": "" };
  const FACE_CLASS = { "1": "num", "2": "num", "3": "num", heart: "heart", energy: "energy", claw: "claw", "?": "blank" };

  // Stable hash so a given card always gets the same one of the 4 background
  // looks, while the shop as a whole reads as a varied spread.
  function bgVarOf(key) {
    let h = 0;
    for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0;
    return Math.abs(h) % 4;
  }

  // The full face of a power card: emoji/name/cost, type, description. Used
  // both for shop listings and the hover popup, so they always match.
  function cardFaceHtml(c, opts) {
    opts = opts || {};
    const cls = ["card", c.type === "keep" ? "keep" : "discard", "bgvar-" + bgVarOf(c.id || c.name || "x")];
    if (opts.buyable) cls.push("buyable");
    const attr = opts.buyIndex != null ? ` data-buy="${opts.buyIndex}"` : "";
    return `<div class="${cls.join(" ")}"${attr}>
      <div class="card-top">
        <span class="card-emoji">${c.emoji || "🎴"}</span>
        <span class="card-name">${esc(c.name)}</span>
        <span class="card-cost">${c.cost}⚡</span>
      </div>
      <div class="card-type">${c.type === "keep" ? "Keep" : "Discard"}</div>
      <div class="card-text">${esc(c.text || "")}</div>
    </div>`;
  }

  function deckWidgetHtml(n) {
    return `<div class="deck-widget" title="${n} left in the deck">
      <div class="deck-card d3">👑</div>
      <div class="deck-card d2">👑</div>
      <div class="deck-card d1">👑</div>
      <span class="deck-count">${n}</span>
    </div>`;
  }

  // ---- card hover popup ------------------------------------------------------
  let popupHideT;
  function showCardPopup(anchorEl, card) {
    clearTimeout(popupHideT);
    const pop = $("cardPopup");
    pop.innerHTML = cardFaceHtml(card);
    pop.classList.add("show");
    const r = anchorEl.getBoundingClientRect();
    requestAnimationFrame(() => {
      const pw = pop.offsetWidth || 252;
      const ph = pop.offsetHeight || 180;
      let left = r.right + 10;
      if (left + pw > window.innerWidth - 8) left = r.left - pw - 10;
      left = Math.max(8, left);
      let top = Math.max(8, Math.min(r.top + r.height / 2 - ph / 2, window.innerHeight - ph - 8));
      pop.style.left = left + "px";
      pop.style.top = top + "px";
    });
  }
  function hideCardPopup() {
    popupHideT = setTimeout(() => $("cardPopup").classList.remove("show"), 60);
  }
  function wireCardPopups(container) {
    container.querySelectorAll(".mc-cardrow[data-cid]").forEach((row) => {
      row.addEventListener("mouseenter", () => {
        const wrap = row.closest("[data-pid]");
        if (!wrap) return;
        const card = ((state.mon[wrap.dataset.pid] || {}).cards || []).find((c) => c.id === row.dataset.cid);
        if (card) showCardPopup(row, card);
      });
      row.addEventListener("mouseleave", hideCardPopup);
    });
  }

  // ---- floating status-change indicators -------------------------------------
  let prevMon = null;
  function snapshotMon(mon) {
    const out = {};
    for (const pid of Object.keys(mon || {})) {
      const m = mon[pid];
      out[pid] = { hp: m.hp, vp: m.vp, energy: m.energy };
    }
    return out;
  }
  function animateStatChanges(before, after) {
    if (!before) return;
    for (const pid of Object.keys(after)) {
      const b = before[pid];
      if (!b) continue;
      animateStatDelta(pid, "hp", "❤", b.hp, after[pid].hp);
      animateStatDelta(pid, "vp", "★", b.vp, after[pid].vp);
      animateStatDelta(pid, "energy", "⚡", b.energy, after[pid].energy);
    }
  }
  function animateStatDelta(pid, key, symbol, before, after) {
    const delta = after - before;
    if (!delta) return;
    const card = document.querySelector(`.mon-card[data-pid="${pid}"]`);
    if (!card) return;
    const anchor = key === "hp" ? card.querySelector(".mc-hpbar")
      : key === "vp" ? card.querySelector(".stat-vp") : card.querySelector(".stat-en");
    if (!anchor) return;
    const cardR = card.getBoundingClientRect();
    const anchorR = anchor.getBoundingClientRect();
    const span = document.createElement("span");
    span.className = "stat-float " + (delta > 0 ? "up" : "down");
    span.textContent = (delta > 0 ? "+" : "") + delta + symbol;
    span.style.left = (anchorR.left - cardR.left + anchorR.width / 2) + "px";
    span.style.top = (anchorR.top - cardR.top) + "px";
    card.appendChild(span);
    setTimeout(() => span.remove(), 1300);
    anchor.classList.remove("stat-flash");
    void anchor.offsetWidth;
    anchor.classList.add("stat-flash");
  }

  // ---- socket wiring -------------------------------------------------------
  socket.on("connect", () => socket.emit("join_game", { code: CODE }));
  socket.on("game_state", (d) => {
    Object.assign(ROSTER, d.roster || {});
    const before = prevMon;
    state = d.state;
    if (state.seq !== lastSeq) {
      // Fresh dice roll resets the local keep selection to match the server.
      if (state.phase === "rolling") keep = new Set(state.kept.map((k, i) => (k ? i : -1)).filter((i) => i >= 0));
      lastSeq = state.seq;
    }
    render();
    animateStatChanges(before, state.mon);
    prevMon = snapshotMon(state.mon);
  });
  socket.on("act_error", (d) => toast(d.error || "Not allowed."));

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
    const cur = `${emojiOf(state.current)} ${nameOf(state.current)}`;
    let phase = state.phase === "rolling" ? "rolling" : state.phase === "buying" ? "shopping" : "Tokyo decision";
    if (myYieldTurn()) { b.textContent = "Stay in Tokyo or yield?"; b.className = "turn-banner mine"; return; }
    b.textContent = isMyTurn() ? `Your turn - ${phase}` : `${cur}'s turn - ${phase}`;
    b.className = "turn-banner" + (isMyTurn() ? " mine" : "");
  }

  // Full monster card: stats on the left, that monster's owned power cards as
  // a vertical list on the right. Shared by the Tokyo slot and the Outskirts
  // grid so a monster only ever appears in one place.
  function monCardHtml(pid) {
    const m = state.mon[pid];
    if (!m) return "";
    const cls = ["mon-card"];
    if (!m.alive) cls.push("dead");
    if (state.current === pid && state.phase !== "ended") cls.push("active");
    if (pid === MY_PID) cls.push("me");
    const hpPct = Math.max(0, Math.round(100 * m.hp / m.maxhp));
    const toks = tokenPills(m.tokens);
    const cards = m.cards || [];
    const cardList = cards.length
      ? cards.map((c) => `<div class="mc-cardrow" data-cid="${esc(c.id)}">${c.emoji || "🎴"} ${esc(c.name)}</div>`).join("")
      : `<div class="mc-cardlist-empty">—</div>`;
    // The Tokyo/Bay badge lives on the slot label now, not the card itself,
    // since an occupant only ever renders inside that slot (never duplicated
    // in the Outskirts grid), so the badge would just repeat the slot label.
    return `<div class="${cls.join(" ")}" style="--c:${colorOf(pid)}" data-pid="${pid}">
      <div class="mc-left">
        <div class="mc-head">
          <span class="mc-dot"></span>
          <span class="mc-name">${dispName(pid)}</span>
          ${!m.alive ? '<span class="mc-ko">KO</span>' : ""}
        </div>
        <div class="mc-sub">${esc((ROSTER[pid] && ROSTER[pid].name) || "")}${pid === MY_PID ? " (you)" : ""}</div>
        <div class="mc-hpbar"><div class="mc-hpfill" style="width:${hpPct}%"></div><span class="mc-hptext">❤ ${m.hp}/${m.maxhp}</span></div>
        <div class="mc-stats">
          <span class="stat-vp">★ ${m.vp}</span>
          <span class="stat-en">⚡ ${m.energy}</span>
        </div>
        ${toks ? `<div class="mc-tokens">${toks}</div>` : ""}
      </div>
      <div class="mc-cardlist${cards.length ? "" : " empty"}">${cardList}</div>
    </div>`;
  }

  function renderTokyo() {
    const t = state.tokyo;
    $("slot-bay").style.display = state.use_bay ? "" : "none";
    $("city-mon").innerHTML = t.city ? monCardHtml(t.city) : `<div class="slot-empty">empty</div>`;
    $("bay-mon").innerHTML = t.bay ? monCardHtml(t.bay) : `<div class="slot-empty">empty</div>`;
    wireCardPopups($("city-mon"));
    wireCardPopups($("bay-mon"));
  }

  // Whoever's in Tokyo is drawn inside the Tokyo slot only, not duplicated
  // in the Outskirts grid below.
  function renderMonsters() {
    const tokyoOccupants = new Set([state.tokyo.city, state.tokyo.bay].filter(Boolean));
    const el = $("monsters");
    el.innerHTML = state.players.filter((pid) => !tokyoOccupants.has(pid)).map(monCardHtml).join("");
    wireCardPopups(el);
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
      html = `<span class="spectate">Spectating - ${dispName(state.current)}'s turn</span>`;
    } else if (state.current !== MY_PID) {
      html = `<span class="spectate">Waiting for ${dispName(state.current)}…</span>`;
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
      return cardFaceHtml(c, { buyable: canBuy && afford, buyIndex: canBuy && afford ? i : null });
    }).join("");
    const sweep = canBuy
      ? `<button class="btn secondary sweep" ${myEnergy >= 2 ? "" : "disabled"} data-sweep="1">Sweep (2⚡)</button>`
      : "";
    shop.innerHTML = `<div class="shop-head"><span class="shop-title">Power cards</span>${deckWidgetHtml(state.deck_left)}</div>
      <div class="shop-cards">${cards}</div>${sweep}`;
    shop.querySelectorAll("[data-buy]").forEach((el) => el.onclick = () => doBuy(+el.dataset.buy));
    const sw = shop.querySelector("[data-sweep]"); if (sw) sw.onclick = doSweep;
  }

  function renderLog() {
    const feed = $("logFeed");
    const items = (state.log || []).slice().reverse();
    feed.innerHTML = items.map((l) =>
      `<div class="log-line log-${l.kind || "sys"}">${l.pid ? `<b style="color:${colorOf(l.pid)}">${dispName(l.pid)}</b> ` : ""}${esc(stripName(l))}</div>`
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
      <span class="fin-name" style="color:${colorOf(s.pid)}">${dispName(s.pid)}</span>
      <span class="fin-vp">★ ${s.vp}</span>
    </div>`).join("");
    const champ = state.winner ? dispName(state.winner) : "Nobody";
    $("overlayCard").innerHTML = `<div class="crown">👑</div>
      <h2>${champ} rules Tokyo!</h2>
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
  $("leaveBtn").onclick = doLeave;

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
