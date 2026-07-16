/* King of Tokyo - client. Renders from the server's public_view; the server is
   authoritative, so this file only draws state and sends intents. */
(function () {
  const { code: CODE, myPid: MY_PID, roster: ROSTER } = window.KOT;
  const socket = io();

  let state = null;              // latest public_view
  let keep = new Set();          // dice indices the player is keeping
  let lastSeq = -1;
  let pendingRollAnim = false;   // set only by this client's own roll/reroll click

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

  // Font Awesome icons for heart/energy so they render identically on iPhone
  // and desktop, instead of platform-inconsistent emoji glyphs. Claw stays
  // the original "✷" mark - preferred over both later icon attempts.
  const FACE = {
    "1": "1", "2": "2", "3": "3",
    heart: '<i class="fa-solid fa-heart"></i>',
    energy: '<i class="fa-solid fa-bolt"></i>',
    claw: "✷",
    "?": "",
  };
  const FACE_CLASS = { "1": "num", "2": "num", "3": "num", heart: "heart", energy: "energy", claw: "claw", "?": "blank" };

  // ---- sound effects: short synthesized stings, no samples ------------------
  const SOUND_SRC = {
    roll: "/static/sounds/roll.wav", card: "/static/sounds/card.wav",
    attack: "/static/sounds/attack.wav", ko: "/static/sounds/ko.wav", turn: "/static/sounds/turn.wav",
  };
  const soundPool = {};
  for (const k in SOUND_SRC) { const a = new Audio(SOUND_SRC[k]); a.preload = "auto"; soundPool[k] = a; }
  let muted = localStorage.getItem("kot_muted") === "1";
  function playSound(name) {
    if (muted || !soundPool[name]) return;
    const el = soundPool[name].cloneNode();
    el.volume = 0.55;
    el.play().catch(() => {});
  }
  function setMuted(v) {
    muted = v;
    localStorage.setItem("kot_muted", v ? "1" : "0");
    const btn = $("muteBtn");
    if (btn) btn.textContent = v ? "🔇" : "🔊";
  }

  // New log lines drive attack/ko/buy stings (and It Has a Child's revive
  // burst on whichever monster's card just came back); a turn change into
  // MY_PID pings.
  let lastLogId = null;
  let prevCurrent = null;
  const LOG_SOUND = { attack: "attack", ko: "ko", buy: "card", revive: "turn" };
  function soundForLog(log) {
    if (lastLogId == null) {
      lastLogId = log.length ? log[log.length - 1].id : 0;
      return;
    }
    const played = new Set();
    for (const l of log) {
      if (l.id <= lastLogId) continue;
      const snd = LOG_SOUND[l.kind];
      if (snd && !played.has(snd)) { playSound(snd); played.add(snd); }
      if (l.kind === "revive" && l.pid) spawnReviveAnim(l.pid);
    }
    if (log.length) lastLogId = Math.max(lastLogId, log[log.length - 1].id);
  }
  function soundForTurn(newState) {
    if (prevCurrent != null && newState.current !== prevCurrent && newState.current === MY_PID
        && newState.phase !== "ended" && !isSpectator()) {
      playSound("turn");
    }
    prevCurrent = newState.current;
  }

  // A ping the moment it becomes this player's call to stay in Tokyo or
  // leave - easy to miss on mobile since it's tucked behind the Dice tab.
  let prevMyYield = false;
  function soundForYield() {
    const nowYield = myYieldTurn();
    if (nowYield && !prevMyYield) playSound("turn");
    prevMyYield = nowYield;
  }

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
      </div>
      <div class="card-type">${c.type === "keep" ? "Keep" : "Discard"}</div>
      <div class="card-text">${esc(c.text || "")}</div>
      <span class="card-cost">${c.cost}⚡</span>
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
    pop.innerHTML = cardFaceHtml(card) + `<button class="card-popup-close" aria-label="Close">✕</button>`;
    pop.querySelector(".card-popup-close").onclick = () => { clearTimeout(popupHideT); pop.classList.remove("show"); };
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

  // It Has a Child: a one-shot gold burst on the reborn monster's card plus a
  // rising "Reborn!" label, on top of whatever hp/vp floats also fire for the
  // same change.
  function spawnReviveAnim(pid) {
    const card = document.querySelector(`.mon-card[data-pid="${pid}"]`);
    if (!card) return;
    card.classList.remove("revive-burst");
    void card.offsetWidth;
    card.classList.add("revive-burst");
    card.addEventListener("animationend", () => card.classList.remove("revive-burst"), { once: true });
    const span = document.createElement("span");
    span.className = "revive-label";
    span.textContent = "🥚 Reborn!";
    card.appendChild(span);
    setTimeout(() => span.remove(), 1800);
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
    soundForLog(state.log || []);
    soundForTurn(state);
    soundForYield();
  });
  socket.on("act_error", (d) => toast(d.error || "Not allowed."));

  // ---- actions -------------------------------------------------------------
  const emit = (ev, extra) => socket.emit(ev, Object.assign({ code: CODE }, extra || {}));
  function doRoll() { playSound("roll"); pendingRollAnim = true; emit("roll", { keep: [...keep] }); }
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
    renderMobileYieldBadge();
    renderOpportunistPicker();
  }

  // A small "!" badge on the mobile Dice tab while it's this player's call
  // to stay in Tokyo or leave - easy to miss since the decision buttons live
  // behind that tab, not on the always-visible Board view.
  function renderMobileYieldBadge() {
    const icon = $("diceTabIcon");
    if (!icon) return;
    let badge = document.getElementById("yieldBadge");
    if (myYieldTurn()) {
      if (!badge) {
        badge = document.createElement("span");
        badge.id = "yieldBadge";
        badge.className = "mobile-yield-badge";
        badge.textContent = "!";
        icon.appendChild(badge);
      }
    } else if (badge) {
      badge.remove();
    }
  }

  function renderBanner() {
    const b = $("turnBanner");
    if (state.phase === "ended") { b.textContent = "Game over"; b.className = "turn-banner"; return; }
    if (myYieldTurn()) { b.textContent = "Stay in Tokyo or yield?"; b.className = "turn-banner mine"; return; }
    // During a yield decision, state.current is still the attacker - the
    // monster actually being waited on is whoever's first in the queue.
    if (state.phase === "yield" && state.pending_yield && state.pending_yield.queue.length) {
      const decider = state.pending_yield.queue[0];
      b.textContent = `Waiting for ${nameOf(decider)} to stay or leave Tokyo…`;
      b.className = "turn-banner";
      return;
    }
    // Same idea as yield above: the roll is frozen on a Psychic Probe
    // decision, and state.current is still the roller, not the decider.
    if (state.phase === "probe_window" && state.pending_probe && state.pending_probe.queue.length) {
      const decider = state.pending_probe.queue[0];
      b.textContent = `Waiting for ${nameOf(decider)} to psychically probe or pass…`;
      b.className = "turn-banner";
      return;
    }
    const cur = `${emojiOf(state.current)} ${nameOf(state.current)}`;
    const phase = state.phase === "rolling" ? "rolling" : "shopping";
    b.textContent = isMyTurn() ? `Your turn - ${phase}` : `${cur}'s turn - ${phase}`;
    b.className = "turn-banner" + (isMyTurn() ? " mine" : "");
  }

  // Full monster card: stats on the left, that monster's owned power cards as
  // a vertical list on the right. Shared by the Tokyo slot and the Outskirts
  // grid so a monster only ever appears in one place.
  function monCardHtml(pid) {
    const m = state.mon[pid];
    if (!m) return "";
    const cards = m.cards || [];
    const cls = ["mon-card"];
    if (!m.alive) cls.push("dead");
    if (state.current === pid && state.phase !== "ended") cls.push("active");
    if (pid === MY_PID) cls.push("me");
    if (!cards.length) cls.push("no-cards");
    const hpPct = Math.max(0, Math.round(100 * m.hp / m.maxhp));
    const toks = tokenPills(m.tokens);
    const cardList = cards.length
      ? cards.map((c) => `<div class="mc-cardrow" data-cid="${esc(c.id)}">${c.emoji || "🎴"} ${esc(c.name)}${cardRowSuffix(c, pid)}</div>`).join("")
      : `<div class="mc-cardlist-empty">—</div>`;
    // The Tokyo/Bay badge lives on the slot label now, not the card itself,
    // since an occupant only ever renders inside that slot (never duplicated
    // in the Outskirts grid), so the badge would just repeat the slot label.
    return `<div class="${cls.join(" ")}" style="--c:${colorOf(pid)}" data-pid="${pid}">
      <div class="mc-left">
        <div class="mc-avatar">${emojiOf(pid)}</div>
        <div class="mc-head">
          <span class="mc-name">${esc(nameOf(pid))}</span>
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

  // A short parenthetical on a card row for the handful of cards with extra
  // live state worth showing at a glance (Mimic's target, Made in a Lab's
  // peek, Monster Batteries' remaining charge). The server broadcasts the
  // same state to everyone, so a Made in a Lab peek is technically visible to
  // any client that goes looking - but it's only meant to be seen by its
  // owner, so we only ever render it for MY_PID's own row, never when looking
  // at someone else's monster card. Battery charge isn't secret, so it always
  // shows for everyone.
  function cardRowSuffix(c, ownerPid) {
    if (c.mimic_target) {
      const t = c.mimic_target;
      let extra = "";
      if (t.battery_left != null) extra = `, ${t.battery_left}⚡ left`;
      else if (t.smoke_left != null) extra = `, ${t.smoke_left} left`;
      else if (t.used != null) extra = t.used ? ", used" : ", ready";
      else if (t.wings_active) extra = ", shielded";
      return ` <span class="mc-card-note">(${esc(t.name)}${extra})</span>`;
    }
    if (c.lab_peek && ownerPid === MY_PID) return ` <span class="mc-card-note">(${esc(c.lab_peek.name)}, ${c.lab_peek.cost}⚡)</span>`;
    if (c.battery_left != null) return ` <span class="mc-card-note">(${c.battery_left}⚡ left)</span>`;
    if (c.wings_active) return ` <span class="mc-card-note">(shielded)</span>`;
    return "";
  }

  function renderTokyo() {
    const t = state.tokyo;
    $("slot-bay").style.display = state.use_bay ? "" : "none";
    // lets CSS size City/Bay differently (each solo vs. a matched medium
    // size when both are stacked/side-by-side together) without JS doing layout math
    $("tokyo").classList.toggle("both-active", !!state.use_bay);
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

  const REEL_KEYS = ["1", "2", "3", "heart", "energy", "claw"];
  const randomFaceKey = () => REEL_KEYS[Math.floor(Math.random() * REEL_KEYS.length)];
  const dieFaceHtml = (f) => `<span class="die-face">${FACE[f] || ""}</span>`;

  let lastAnimatedRollNum = -1;
  // Generic "arm this button, then click one of your own dice to fire the
  // ability on it" mode, built for Background Dweller ([3]s only) and reused
  // for Herd Culler (any die) - any future one-die-picking ability just adds
  // an entry here instead of growing its own prompt() or its own copy of this
  // targeting machinery.
  const DIE_TARGET = {
    background_dweller: { filter: (f) => f === "3" },
    herd_culler: { filter: () => true },
    // These two also let you choose the NEW face, not just which die - once
    // a die's picked, fireDieTarget opens a small face-picker instead of
    // firing straight away.
    plot_twist: { filter: () => true, needsFace: true },
    stretchy: { filter: () => true, needsFace: true },
  };
  let dieTargetCard = null;          // card id currently armed, or null
  let pendingDieAnim = null;         // {index, prevFace} - a fired action awaiting its server-confirmed face
  let lastShownCamoId = 0;           // highest Camouflage camo_roll.id already played out
  let camoRollAnim = null;           // {dice, reels} - a Camouflage roll currently animating
  let probeTargetArmed = false;      // Psychic Probe eagerly armed via its own button mid-roll
  function renderDice() {
    const tray = $("diceTray");
    const dice = state.dice || [];
    if (!dice.length || (state.phase !== "rolling" && state.phase !== "probe_window" && state.roll_num === 0)) { tray.innerHTML = ""; dieTargetCard = null; return; }
    // Only animate when THIS client just clicked roll/reroll (pendingRollAnim) -
    // never on page load, reconnect, or just opening the mobile Dice tab, which
    // would otherwise replay a stale animation for a roll that already happened.
    const rollChanged = state.roll_num !== lastAnimatedRollNum;
    const freshRoll = pendingRollAnim && rollChanged;
    if (rollChanged) {
      lastAnimatedRollNum = state.roll_num;
      pendingRollAnim = false;
      // A fresh roll always exits die-targeting mode - the armed ability has
      // to be re-armed against the new dice.
      dieTargetCard = null;
      pendingDieAnim = null;
    }
    if (!isMyRollingTurn()) dieTargetCard = null;
    if (!canEagerProbe()) probeTargetArmed = false;
    // Psychic Probe targets someone ELSE's dice tray (there's only ever one
    // tray shown, whoever's turn it is), so it's armed either by its own
    // button mid-roll, or automatically the moment it's your forced decision
    // in the probe window - either way, every die becomes a valid target.
    const probeArmed = probeTargetArmed || myProbeWindowTurn();
    const targetFilter = probeArmed ? () => true : (dieTargetCard && DIE_TARGET[dieTargetCard].filter);
    // A targeted die-changing ability only gets its reel animation once the
    // server's actual new face lands (never on the optimistic re-render right
    // after the click, which still shows the old face).
    let animIdx = null;
    if (pendingDieAnim) {
      const { index, prevFace } = pendingDieAnim;
      if (dice[index] !== prevFace) { animIdx = index; pendingDieAnim = null; }
    }
    tray.innerHTML = dice.map((f, i) => {
      const kept = keep.has(i);
      const canClick = isMyRollingTurn() && state.roll_num > 0;
      const targetable = !!targetFilter && targetFilter(f);
      // Only dice actually being rerolled get the reel animation - kept dice
      // stay put, except a targeted reroll always gets one.
      const isRolling = (freshRoll && !kept) || i === animIdx;
      let inner;
      if (isRolling) {
        const reel = [randomFaceKey(), randomFaceKey(), randomFaceKey(), randomFaceKey(), f];
        inner = `<div class="die-face-viewport"><div class="die-reel" style="animation-delay:${i * 45}ms">${reel.map(dieFaceHtml).join("")}</div></div>`;
      } else {
        inner = dieFaceHtml(f);
      }
      // While targeting, only matching dice stay clickable - everything else
      // (including the normal keep-toggle) is inert until targeting mode ends.
      const clickable = targetFilter ? targetable : canClick;
      return `<button class="die ${FACE_CLASS[f] || "blank"} ${kept ? "kept" : ""} ${isRolling ? "rolling" : ""} ${targetable ? "die-target" : ""}"
        ${clickable ? "" : "disabled"} data-i="${i}">${inner}</button>`;
    }).join("");
    tray.querySelectorAll(".die").forEach((el) => {
      const i = +el.dataset.i;
      el.onclick = probeArmed
        ? () => fireProbeDie(i)
        : targetFilter
          ? (targetFilter(dice[i]) ? () => fireDieTarget(dieTargetCard, i) : null)
          : () => toggleKeep(i);
    });
    // Once a die's reel animation genuinely finishes, collapse its multi-row
    // reel back down to a single plain face. The CSS leaves the reel parked
    // on the right (real) row via the animation's end state either way, but
    // without this the multi-row DOM lingers indefinitely - swapping it out
    // for one clean node removes any doubt about what's actually showing.
    tray.querySelectorAll(".die.rolling .die-reel").forEach((reel) => {
      reel.addEventListener("animationend", () => {
        const viewport = reel.parentElement;
        const dieEl = viewport && viewport.parentElement;
        if (!dieEl || !dieEl.isConnected) return;
        const idx = +dieEl.dataset.i;
        viewport.outerHTML = dieFaceHtml(state.dice[idx]);
        dieEl.classList.remove("rolling");
      }, { once: true });
    });
  }

  function renderActions() {
    const row = $("actionRow");
    let html = "";
    if (state.phase === "ended") {
      html = `<button class="btn" onclick="location.href='/lobbies'">Back to lobbies</button>`;
    } else if (myYieldTurn()) {
      html = `<button class="btn danger" data-a="yield-leave">Leave Tokyo</button>
              <button class="btn" data-a="yield-stay">Stay in Tokyo</button>`;
    } else if (state.phase === "yield" && state.pending_yield && state.pending_yield.queue.length) {
      const decider = state.pending_yield.queue[0];
      html = `<span class="spectate">Waiting for ${dispName(decider)} to stay or leave Tokyo…</span>`;
    } else if (myProbeWindowTurn()) {
      html = `<span class="spectate">🔮 Click one of ${dispName(state.current)}'s dice to reroll it, or pass.</span>
              <button class="btn secondary" data-a="probe-pass">Pass</button>`;
    } else if (state.phase === "probe_window" && state.pending_probe && state.pending_probe.queue.length) {
      const decider = state.pending_probe.queue[0];
      html = `<span class="spectate">Waiting for ${dispName(decider)} to psychically probe or pass…</span>`;
    } else if (isSpectator()) {
      html = `<span class="spectate">Spectating - ${dispName(state.current)}'s turn</span>`;
    } else if (state.current !== MY_PID) {
      html = `<span class="spectate">Waiting for ${dispName(state.current)}…</span>`;
    } else if (state.phase === "rolling") {
      const first = state.roll_num === 0;
      const canRoll = first || state.rolls_left > 0;
      // Always "Roll" - before the first roll, rolls_left already counts the
      // rerolls that follow it, so +1 to also count this upcoming roll itself.
      const rollsRemaining = first ? state.rolls_left + 1 : state.rolls_left;
      const rollLabel = `<span class="roll-btn-label">Roll</span><span class="roll-btn-sub">${rollsRemaining} left</span>`;
      // Done is always rendered (just disabled before the first roll) so its
      // appearance never changes the roll-stack's height and shifts the UI.
      html = `<div class="roll-stack">
        <button class="btn big ${canRoll ? "" : "hidden"}" data-a="roll">${rollLabel}</button>
        <button class="btn big secondary" data-a="resolve" ${first ? "disabled" : ""}>Done</button>
      </div>`;
      html += cardActionButtons();
    } else if (state.phase === "buying") {
      html = `<button class="btn big" data-a="end">End turn</button>`;
      html += cardActionButtons();
    }
    // Psychic Probe, Opportunist and a pending Camouflage roll all react
    // outside of whoever's turn it is, so they're not gated by isMyTurn()
    // like the rest of cardActionButtons() - append them regardless of
    // which branch above fired.
    html += psychicProbeButton() + opportunistButton() + camoRollButton();
    row.innerHTML = html;
    row.querySelectorAll("[data-a]").forEach((el) => el.onclick = () => {
      const a = el.dataset.a;
      if (a === "roll") doRoll();
      else if (a === "resolve") doResolve();
      else if (a === "end") doEndTurn();
      else if (a === "yield-leave") doYield(true);
      else if (a === "yield-stay") doYield(false);
      // Background Dweller / Herd Culler (or Mimic copying either) arm die-
      // targeting mode on the dice tray instead of firing straight away.
      else if (a.startsWith("card:") && DIE_TARGET[a.slice(5)]) toggleDieTargetMode(a.slice(5));
      else if (a === "camo-roll") fireCamoRoll();
      else if (a === "opportunist-open") openOpportunistPicker();
      else if (a === "probe-arm") toggleProbeTarget();
      else if (a === "probe-pass") passProbe();
      else if (a.startsWith("card:")) fireCard(a.slice(5));
    });
  }

  function ownsOrMimics(cardId) {
    const mine = (state.mon[MY_PID] && state.mon[MY_PID].cards) || [];
    return mine.some((c) => c.id === cardId || (c.id === "mimic" && c.mimic_target && c.mimic_target.id === cardId));
  }

  // Psychic Probe: fireable any time someone else is mid-roll, once per
  // roller per turn - not gated by isMyTurn() at all. On top of that eager
  // use, the server also opens a forced last-chance window the instant the
  // roller clicks Done (so racing to Done can't rob a slower prober of the
  // window entirely) - myProbeWindowTurn() covers that separate moment.
  function canEagerProbe() {
    if (isSpectator() || state.phase !== "rolling" || state.roll_num <= 0) return false;
    if (state.current === MY_PID || !ownsOrMimics("psychic_probe")) return false;
    const probedBy = (state.mon[state.current] && state.mon[state.current].probed_by) || [];
    return !probedBy.includes(MY_PID);
  }
  function myProbeWindowTurn() {
    return !!(state && state.phase === "probe_window" && state.pending_probe && state.pending_probe.queue[0] === MY_PID);
  }
  function psychicProbeButton() {
    if (!canEagerProbe()) return "";
    const extra = probeTargetArmed ? " active" : "";
    return `<button class="btn card-act${extra}" data-a="probe-arm">🔮 Probe ${dispName(state.current)}'s die</button>`;
  }
  function toggleProbeTarget() {
    if (!canEagerProbe()) return;
    probeTargetArmed = !probeTargetArmed;
    renderDice();
    renderActions();
  }
  function fireProbeDie(i) {
    probeTargetArmed = false;
    pendingDieAnim = { index: i, prevFace: state.dice[i] };
    doCardAction("psychic_probe", { index: i });
    renderDice();
    renderActions();
  }
  function passProbe() {
    if (!myProbeWindowTurn()) return;
    doCardAction("psychic_probe", { pass: true });
  }

  // Opportunist: a shop slot refilling (one purchase, or all 3 at once from a
  // Sweep) opens a window on each freshly-revealed card, for as long as it
  // sits unclaimed - regardless of whose turn it is. Rather than one button
  // per card, this opens a popup listing everything currently snipeable so
  // the player can buy any number of them, then dismiss it with Done.
  function liveOpportunistWindow() {
    if (!state) return [];
    return (state.opportunist_window || []).filter((e) => {
      const c = state.shop[e.index];
      return c && c.id === e.cid;
    });
  }
  function opportunistButton() {
    if (isSpectator() || state.phase !== "buying" || !ownsOrMimics("opportunist")) return "";
    const win = liveOpportunistWindow();
    if (!win.length) return "";
    return `<button class="btn card-act" data-a="opportunist-open">🕵️ Buy card (${win.length})</button>`;
  }

  // Camouflage: the mitigation already happened server-side the instant
  // damage landed, but its owner still gets a button to roll-and-reveal it
  // themselves, with a small reel per point of damage and a floating pop for
  // each [heart] that shrugs off a point - fireable regardless of whose turn
  // it is, since damage can land on anyone at any time.
  function camoRollButton() {
    if (camoRollAnim) return camoRollWidgetHtml();
    if (isSpectator()) return "";
    const mine = state.mon[MY_PID];
    const cr = mine && mine.camo_roll;
    if (!cr || cr.id <= lastShownCamoId) return "";
    return `<button class="btn card-act danger" data-a="camo-roll">🦎 Roll Camouflage (${cr.blocked})</button>`;
  }

  function camoRollWidgetHtml() {
    const { dice, reels } = camoRollAnim;
    const diceHtml = dice.map((f, i) => {
      const frames = reels[i].concat([f]);
      return `<span class="die mini rolling ${FACE_CLASS[f] || "blank"}">
        <span class="die-face-viewport"><span class="die-reel" style="animation-delay:${i * 45}ms">${frames.map(dieFaceHtml).join("")}</span></span>
      </span>`;
    }).join("");
    return `<div class="camo-roll"><span class="camo-roll-label">🦎 Rolling camouflage…</span><div class="camo-roll-dice">${diceHtml}</div></div>`;
  }

  function fireCamoRoll() {
    const mine = state.mon[MY_PID];
    const cr = mine && mine.camo_roll;
    if (!cr || camoRollAnim || cr.id <= lastShownCamoId) return;
    lastShownCamoId = cr.id;
    doCardAction("camouflage", null);
    // Freeze the reel's random mid-spin frames once, up front - renderActions()
    // can re-run several times while this plays (e.g. another player acting),
    // and re-rolling those frames on every re-render would look like flicker
    // instead of one clean spin.
    camoRollAnim = { dice: cr.dice, reels: cr.dice.map(() => [randomFaceKey(), randomFaceKey(), randomFaceKey(), randomFaceKey()]) };
    renderActions();
    const n = cr.dice.length;
    cr.dice.forEach((f, i) => {
      if (f === "heart") setTimeout(spawnCamoBlockedPop, i * 45 + 520);
    });
    setTimeout(() => { camoRollAnim = null; renderActions(); }, (n - 1) * 45 + 520 + 700);
  }

  function spawnCamoBlockedPop() {
    const card = document.querySelector(`.mon-card[data-pid="${MY_PID}"]`);
    const anchor = card && card.querySelector(".mc-hpbar");
    if (!anchor) return;
    const cardR = card.getBoundingClientRect();
    const anchorR = anchor.getBoundingClientRect();
    const span = document.createElement("span");
    span.className = "stat-float saved";
    span.textContent = "❤ blocked!";
    span.style.left = (anchorR.left - cardR.left + anchorR.width / 2) + "px";
    span.style.top = (anchorR.top - cardR.top) + "px";
    card.appendChild(span);
    setTimeout(() => span.remove(), 1300);
  }

  // Gather any choice an actionable card needs, then send it.
  function fireCard(id) {
    let choice = null;
    if (id === "metamorph") {
      const mine = (state.mon[MY_PID].cards || []);
      if (!mine.length) return;
      openCardPicker({
        title: "Discard which card for its energy back?",
        options: mine.map((c) => ({ card: c })),
        onConfirm: (cid) => doCardAction("metamorph", { card: cid }),
      });
      return;
    } else if (id === "mimic") {
      const options = [];
      for (const p of state.players) {
        if (p === MY_PID) continue;
        for (const oc of (state.mon[p].cards || [])) {
          // Only Mimic itself can't be copied - it has no power of its own.
          // Plot Twist / Smoke Cloud / Monster Batteries are one-time-charge
          // cards, but the mimicker gets their own independent charge pool
          // (server-side), so they're copyable like everything else.
          if (oc.id === "mimic") continue;
          options.push({ pid: p, card: oc });
        }
      }
      if (!options.length) { toast("No copyable cards in play yet."); return; }
      openCardPicker({
        title: "Copy which card?",
        options,
        onConfirm: (cid) => doCardAction("mimic", { card: cid }),
      });
      return;
    } else if (id === "made_in_a_lab") {
      const c = (state.mon[MY_PID].cards || []).find((x) => x.id === "made_in_a_lab");
      choice = { action: (c && c.lab_peek) ? "buy" : "peek" };
    } else if (id === "parasitic_tentacles") {
      const options = [];
      for (const p of state.players) {
        if (p === MY_PID || !state.mon[p].alive) continue;
        for (const oc of (state.mon[p].cards || [])) options.push({ pid: p, card: oc });
      }
      if (!options.length) { toast("No monster has a card to take."); return; }
      openCardPicker({
        title: "Take which card?",
        options,
        onConfirm: (cid, pid) => doCardAction("parasitic_tentacles", { pid, card: cid }),
      });
      return;
    } else if (id === "healing_ray") {
      const others = state.players.filter((p) => p !== MY_PID && state.mon[p].alive);
      if (!others.length) { toast("No other monster to aim at."); return; }
      openPlayerPicker({
        title: "Aim the healing ray",
        candidates: others,
        confirmLabel: "🩹 Heal Ray",
        onConfirm: (target) => doCardAction("healing_ray", { pid: target }),
      });
      return;
    } else if (id === "monster_batteries") {
      const maxE = state.mon[MY_PID].energy;
      openAmountPicker({
        title: "Choose how much ⚡ to store in Monster Batteries",
        min: 0,
        max: maxE,
        initial: maxE,
        confirmLabel: "OK",
        onConfirm: (amount) => doCardAction("monster_batteries", { amount }),
      });
      return;
    }
    doCardAction(id, choice);
  }

  // Background Dweller / Herd Culler: clicking the button arms that card's
  // die-targeting mode (renderDice() draws the violet hover box and wires the
  // click); clicking a matching die fires the ability and disarms it again.
  function toggleDieTargetMode(card) {
    if (!isMyRollingTurn() || state.roll_num === 0) return;
    dieTargetCard = dieTargetCard === card ? null : card;
    renderDice();
    renderActions();
  }
  function fireDieTarget(card, i) {
    dieTargetCard = null;
    if (DIE_TARGET[card].needsFace) {
      renderDice();
      renderActions();
      openFacePicker({
        title: `${card === "stretchy" ? "Stretchy" : "Plot Twist"}: change this die to…`,
        onConfirm: (face) => {
          pendingDieAnim = { index: i, prevFace: state.dice[i] };
          doCardAction(card, { index: i, face });
          renderDice();
        },
      });
      return;
    }
    pendingDieAnim = { index: i, prevFace: state.dice[i] };
    doCardAction(card, { index: i });
    renderDice();
    renderActions();
  }
  // Generic "click a monster's icon to target it" popup, built for Healing
  // Ray but deliberately not hardcoded to it - any future ability (or Mimic
  // copying one of these) that needs to pick another monster reuses this
  // instead of growing its own prompt()/modal.
  //   openPlayerPicker({ title, candidates: [pid...], confirmLabel, onConfirm(pid) })
  let pickerState = null;
  function openPlayerPicker(opts) {
    pickerState = { title: opts.title, candidates: opts.candidates, confirmLabel: opts.confirmLabel, onConfirm: opts.onConfirm, selected: null };
    renderPicker();
    $("pickerModal").style.display = "flex";
  }
  function closePlayerPicker() {
    $("pickerModal").style.display = "none";
    pickerState = null;
  }
  function renderPicker() {
    if (!pickerState) return;
    const { title, candidates, confirmLabel, selected } = pickerState;
    const m = selected ? state.mon[selected] : null;
    $("pickerBox").innerHTML = `
      <div class="picker-head">
        <span class="picker-title">${esc(title)}</span>
        <button class="picker-close" id="pickerCloseBtn">✕</button>
      </div>
      <div class="picker-grid">${candidates.map((pid) => `
        <div class="picker-chip${selected === pid ? " selected" : ""}" data-pid="${pid}" style="--c:${colorOf(pid)}">
          <div class="picker-avatar">${emojiOf(pid)}</div>
          <div class="picker-name">${esc(nameOf(pid))}</div>
        </div>`).join("")}
      </div>
      <div class="picker-stats">${m
        ? `<span class="picker-stat">❤ ${m.hp}/${m.maxhp}</span><span class="picker-stat">⚡ ${m.energy}</span>`
        : `<span class="picker-hint">Pick a monster above</span>`}</div>
      <button class="btn card-act picker-confirm" id="pickerConfirmBtn" ${selected ? "" : "disabled"}>${esc(confirmLabel)}</button>
    `;
    $("pickerBox").querySelectorAll(".picker-chip").forEach((el) => el.onclick = () => {
      pickerState.selected = el.dataset.pid;
      renderPicker();
    });
    $("pickerCloseBtn").onclick = closePlayerPicker;
    if (selected) {
      $("pickerConfirmBtn").onclick = () => {
        const target = pickerState.selected;
        const onConfirm = pickerState.onConfirm;
        closePlayerPicker();
        onConfirm(target);
      };
    }
  }

  // Generic "pick a number between min and max" popup, built for Monster
  // Batteries' store-energy choice but not hardcoded to it, same spirit as
  // openPlayerPicker above. Shares the same modal container - only one of the
  // two is ever open at a time.
  //   openAmountPicker({ title, min, max, initial, confirmLabel, onConfirm(n) })
  let amountPickerState = null;
  function openAmountPicker(opts) {
    amountPickerState = { title: opts.title, min: opts.min, max: opts.max,
      value: opts.initial, confirmLabel: opts.confirmLabel, onConfirm: opts.onConfirm };
    renderAmountPicker();
    $("pickerModal").style.display = "flex";
  }
  function closeAmountPicker() {
    $("pickerModal").style.display = "none";
    amountPickerState = null;
  }
  function renderAmountPicker() {
    if (!amountPickerState) return;
    const { title, min, max, value, confirmLabel } = amountPickerState;
    $("pickerBox").innerHTML = `
      <div class="picker-head">
        <span class="picker-title">${esc(title)}</span>
        <button class="picker-close" id="pickerCloseBtn">✕</button>
      </div>
      <div class="amount-stepper">
        <button class="amount-btn" id="amtMinus" ${value <= min ? "disabled" : ""}>−</button>
        <span class="amount-value"><i class="fa-solid fa-bolt"></i> ${value}</span>
        <button class="amount-btn" id="amtPlus" ${value >= max ? "disabled" : ""}>+</button>
      </div>
      <button class="btn card-act picker-confirm" id="pickerConfirmBtn">${esc(confirmLabel)}</button>
    `;
    $("pickerCloseBtn").onclick = closeAmountPicker;
    $("amtMinus").onclick = () => { amountPickerState.value = Math.max(min, amountPickerState.value - 1); renderAmountPicker(); };
    $("amtPlus").onclick = () => { amountPickerState.value = Math.min(max, amountPickerState.value + 1); renderAmountPicker(); };
    $("pickerConfirmBtn").onclick = () => {
      const n = amountPickerState.value;
      const onConfirm = amountPickerState.onConfirm;
      closeAmountPicker();
      onConfirm(n);
    };
  }

  // Plot Twist / Stretchy: after a die's picked on the tray (dieTargetCard's
  // arm-then-click flow), this is the second step - a grid of the 6 faces to
  // change it to, styled like real dice. Shares the same picker-modal/box.
  //   openFacePicker({ title, onConfirm(face) })
  let facePickerState = null;
  function openFacePicker(opts) {
    facePickerState = { title: opts.title, onConfirm: opts.onConfirm };
    renderFacePicker();
    $("pickerModal").style.display = "flex";
  }
  function closeFacePicker() {
    $("pickerModal").style.display = "none";
    facePickerState = null;
  }
  function renderFacePicker() {
    if (!facePickerState) return;
    const { title } = facePickerState;
    $("pickerBox").innerHTML = `
      <div class="picker-head">
        <span class="picker-title">${esc(title)}</span>
        <button class="picker-close" id="pickerCloseBtn">✕</button>
      </div>
      <div class="face-grid">${REEL_KEYS.map((f) => `
        <button class="die ${FACE_CLASS[f] || "blank"}" data-f="${f}">${dieFaceHtml(f)}</button>`).join("")}
      </div>
    `;
    $("pickerCloseBtn").onclick = closeFacePicker;
    $("pickerBox").querySelectorAll(".face-grid .die").forEach((el) => el.onclick = () => {
      const f = el.dataset.f;
      const onConfirm = facePickerState.onConfirm;
      closeFacePicker();
      onConfirm(f);
    });
  }

  // Generic "pick one card from a list, fires the instant you click it"
  // popup - built for Metamorph / Mimic / Parasitic Tentacles' card-choice
  // prompts. Shares the same picker-modal/box as the pickers above.
  //   openCardPicker({ title, options: [{card, pid?}], onConfirm(cid, pid) })
  let cardPickerState = null;
  function openCardPicker(opts) {
    cardPickerState = { title: opts.title, options: opts.options, onConfirm: opts.onConfirm };
    renderCardPicker();
    $("pickerModal").style.display = "flex";
  }
  function closeCardPicker() {
    $("pickerModal").style.display = "none";
    cardPickerState = null;
  }
  function renderCardPicker() {
    if (!cardPickerState) return;
    const { title, options } = cardPickerState;
    const rows = options.map((o, i) => `
      <div class="card-pick-row" data-i="${i}">
        ${cardFaceHtml(o.card)}
        ${o.pid ? `<span class="card-pick-owner">${esc(nameOf(o.pid))}</span>` : ""}
      </div>`).join("");
    $("pickerBox").innerHTML = `
      <div class="picker-head">
        <span class="picker-title">${esc(title)}</span>
        <button class="picker-close" id="pickerCloseBtn">✕</button>
      </div>
      <div class="opp-list">${rows}</div>
    `;
    $("pickerCloseBtn").onclick = closeCardPicker;
    $("pickerBox").querySelectorAll(".card-pick-row").forEach((el) => el.onclick = () => {
      const o = options[+el.dataset.i];
      const onConfirm = cardPickerState.onConfirm;
      closeCardPicker();
      onConfirm(o.card.id, o.pid);
    });
  }

  // Opportunist's own popup: not a "pick one and confirm" like the two
  // pickers above, but a list of every currently snipeable card with its own
  // Buy button, plus a Done button to close whenever the player's finished.
  // Refreshed on every render() so a card someone else buys out from under
  // you (or a fresh Sweep) updates live while it's open.
  let opportunistPickerOpen = false;
  function openOpportunistPicker() {
    opportunistPickerOpen = true;
    renderOpportunistPicker();
    $("pickerModal").style.display = "flex";
  }
  function closeOpportunistPicker() {
    opportunistPickerOpen = false;
    $("pickerModal").style.display = "none";
  }
  function renderOpportunistPicker() {
    if (!opportunistPickerOpen) return;
    const win = liveOpportunistWindow();
    if (!win.length) { closeOpportunistPicker(); return; }
    const myEnergy = (state.mon[MY_PID] && state.mon[MY_PID].energy) || 0;
    const rows = win.map((e) => {
      const c = state.shop[e.index];
      const afford = myEnergy >= c.cost;
      return `<div class="opp-row">${cardFaceHtml(c)}
        <button class="btn card-act opp-buy" data-idx="${e.index}" ${afford ? "" : "disabled"}>Buy ${c.cost}⚡</button>
      </div>`;
    }).join("");
    $("pickerBox").innerHTML = `
      <div class="picker-head">
        <span class="picker-title">Opportunist</span>
        <button class="picker-close" id="pickerCloseBtn">✕</button>
      </div>
      <div class="opp-list">${rows}</div>
      <button class="btn secondary picker-confirm" id="oppDoneBtn">Done</button>
    `;
    $("pickerCloseBtn").onclick = closeOpportunistPicker;
    $("oppDoneBtn").onclick = closeOpportunistPicker;
    $("pickerBox").querySelectorAll(".opp-buy").forEach((el) => el.onclick = () => {
      doCardAction("opportunist", { index: +el.dataset.idx });
    });
  }

  // Cards that grant an active ability the player can fire on their turn.
  // ``label`` can be a plain string, or a (state, card) => string for cards
  // whose button text depends on some extra state (Mimic, Made in a Lab).
  function cardActionButtons() {
    if (!isMyTurn()) return "";
    const mine = (state.mon[MY_PID] && state.mon[MY_PID].cards) || [];
    const btns = [];
    const addBtn = (id, a, c) => {
      const label = typeof a.label === "function" ? a.label(state, c) : a.label;
      // A die-targeting ability stays visually "pressed" while its targeting
      // mode is armed, same card-act color as every other ability button.
      const extra = dieTargetCard === id ? " active" : "";
      btns.push(`<button class="btn card-act${extra}" data-a="card:${id}">${esc(label)}</button>`);
    };
    for (const c of mine) {
      const a = ACTIONABLE[c.id];
      if (a && a.when(state, c)) addBtn(c.id, a, c);
      // Mimic also surfaces whatever manual ability it's currently copying.
      if (c.id === "mimic" && c.mimic_target) {
        const ma = ACTIONABLE[c.mimic_target.id];
        if (ma && ma.when(state, c)) {
          const mimicLabel = typeof ma.label === "function" ? ma.label(state, c) : ma.label;
          addBtn(c.mimic_target.id, { label: `🎭 ${mimicLabel}` }, c);
        }
      }
    }
    return btns.join("");
  }

  // Client-side hints for which Keep cards expose a manual action. The server
  // re-validates everything; these just decide when to show the button.
  const ACTIONABLE = {
    herd_culler: { label: "Herd Culler: set a die to 1", when: (s) => s.phase === "rolling" && s.roll_num > 0 },
    plot_twist: {
      label: "Plot Twist: set a die",
      // A real copy always has one shot; a mimicked copy has its own
      // independent one-time use, spent once you've fired it (mimic_target.used).
      when: (s, c) => s.phase === "rolling" && s.roll_num > 0
        && (c.id === "mimic" ? !(c.mimic_target && c.mimic_target.used) : true),
    },
    stretchy: { label: "Stretchy: change a die (2⚡)", when: (s) => s.phase === "rolling" && s.roll_num > 0 && s.mon[MY_PID].energy >= 2 },
    telepath: { label: "Telepath: +1 reroll (1⚡)", when: (s) => s.phase === "rolling" && s.mon[MY_PID].energy >= 1 },
    smoke_cloud: {
      label: "Smoke Cloud: +1 reroll",
      // A real copy just discards itself once its 3 charges run out, so no
      // charge check is needed for it; a mimicked copy sticks around, so its
      // own independent pool (mimic_target.smoke_left) has to be checked.
      when: (s, c) => s.phase === "rolling"
        && (c.id === "mimic" ? (c.mimic_target && c.mimic_target.smoke_left > 0) : true),
    },
    rapid_healing: { label: "Rapid Healing: heal 1 (2⚡)", when: (s) => (s.mon[MY_PID].energy >= 2 && s.mon[MY_PID].hp < s.mon[MY_PID].maxhp) },
    wings: {
      label: "Wings: negate damage (2⚡)",
      // A real copy just checks energy - once already up, re-arming would
      // silently no-op server-side, so hide it. A mimicked copy has its own
      // independent shield state (mimic_target.wings_active) to check instead.
      when: (s, c) => s.mon[MY_PID].energy >= 2
        && !(c.id === "mimic" ? (c.mimic_target && c.mimic_target.wings_active) : c.wings_active),
    },
    background_dweller: { label: "Reroll 3", when: (s) => s.phase === "rolling" && s.roll_num > 0 && (s.dice || []).includes("3") },
    metamorph: { label: "Metamorph: discard a card for ⚡", when: (s) => s.phase === "buying" && (s.mon[MY_PID].cards || []).length > 0 },
    monster_batteries: {
      label: "🔌 Monster Batteries: store energy",
      when: (s, c) => s.phase === "buying"
        && (c.id === "mimic" ? (c.mimic_target && c.mimic_target.battery_left == null) : c.battery_left == null),
    },
    mimic: {
      label: (s, c) => c.mimic_target ? `Mimic: copying ${c.mimic_target.name} (change 1⚡)` : "Mimic: choose a card to copy",
      // "At the start of your turn" - only before you've rolled, same window
      // the server enforces, so the button never sits there doing nothing.
      when: (s) => s.phase === "rolling" && s.roll_num === 0,
    },
    made_in_a_lab: {
      label: (s, c) => c.lab_peek ? `Buy peeked ${c.lab_peek.name} (${c.lab_peek.cost}⚡)` : "Made in a Lab: peek at the deck",
      when: (s) => s.phase === "buying",
    },
    parasitic_tentacles: {
      label: "Parasitic Tentacles: take a card from another monster",
      when: (s) => s.phase === "buying" && s.players.some((p) => p !== MY_PID && s.mon[p].alive && (s.mon[p].cards || []).length),
    },
    healing_ray: {
      label: "🩹 Healing Ray: aim at a monster",
      when: (s) => s.phase === "rolling" && s.roll_num > 0 && (s.dice || []).includes("heart"),
    },
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
    // Always render the sweep button (just disabled when unusable) so the
    // shop's height never changes depending on whose turn it is. It lives up
    // top next to the deck widget, not in its own row below the cards.
    const sweep = `<button class="btn secondary sweep" ${canBuy && myEnergy >= 2 ? "" : "disabled"} data-sweep="1">Sweep 2⚡</button>`;
    shop.innerHTML = `<div class="shop-head"><span class="shop-title">Power cards</span>
      <div class="shop-head-right">${sweep}${deckWidgetHtml(state.deck_left)}</div></div>
      <div class="shop-cards">${cards}</div>`;
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
  $("muteBtn").onclick = () => setMuted(!muted);
  setMuted(muted);
  // Open by default on desktop (where the board reserves space for it), but
  // start closed on mobile - it's a fixed overlay there and would otherwise
  // cover most of the "Board" tab's screen.
  if (window.innerWidth > 760) $("logPanel").classList.add("open");

  // ---- mobile tab bar: board / dice / deck ----------------------------------
  // Board is always visible; Dice and Deck slide the .controls bar up as a
  // sheet showing just that half. Tapping the active tab (or the board
  // itself) closes the sheet back to the board view.
  (function initMobileTabs() {
    const tabs = document.querySelectorAll(".mobile-tab");
    const controls = $("controls");
    const board = $("board");
    if (!tabs.length || !controls) return;
    let active = "board";
    function setTab(panel) {
      active = (panel !== "board" && panel === active) ? "board" : panel;
      tabs.forEach((t) => t.classList.toggle("active", t.dataset.panel === active));
      controls.classList.remove("panel-dice", "panel-deck", "mobile-open");
      if (active === "dice") controls.classList.add("mobile-open", "panel-dice");
      else if (active === "deck") controls.classList.add("mobile-open", "panel-deck");
    }
    tabs.forEach((t) => t.onclick = () => setTab(t.dataset.panel));
    board.addEventListener("click", () => { if (window.innerWidth <= 760) setTab("board"); });
  })();

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
