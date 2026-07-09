/* Egyptian Rat Screw - table client. Renders the wooden table, the pile, the
   slap feed and standings; sends flip/slap over the socket. The server is the
   authority for every rule. */

const socket = io();
let STATE = null;
let prevPile = 0;
let lastLogT = 0;
let lastFlipSeq = 0;       // gates the fly-in animation so a card never re-animates
let lastBurnSeq = 0;       // gates the burn (lift + slide-under) animation
let lastWinSeq = 0;        // gates the "cards slide to the winner" animation
let lastLogId = 0;         // highest chat entry id seen (for fresh-entry effects)
let slapCooldownUntil = 0; // local echo of the freeze after your wrong slap

// sound effects (unlocked after the first user gesture by browser policy)
const sndFlip = new Audio("/static/sounds/flip.wav");
const sndSlap = new Audio("/static/sounds/slap.wav");
sndFlip.volume = 0.5; sndSlap.volume = 0.85;
function playSafe(a) { try { a.currentTime = 0; a.play().catch(() => {}); } catch (e) {} }

socket.on("connect", () => socket.emit("join_game", { code: GAME_CODE }));
socket.on("game_state", (d) => {
  STATE = d.state;
  if (d.roster) ROSTER = d.roster;
  render();
});

// ---- helpers ----
const RL = { 11: "J", 12: "Q", 13: "K", 14: "A" };
const rankLabel = (r) => RL[r] || ("" + r);
const REASON = { double: "double", sandwich: "sandwich", top_bottom: "top-bottom",
                 ten: "tens", kingqueen: "K-Q" };
const pname = (pid) => (ROSTER[pid] || {}).name || pid;
const pcolor = (pid) => (ROSTER[pid] || {}).color || "#f2c94c";
const esc = (s) => (s + "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function cardFace(card, cls) {
  const red = card.suit === "♥" || card.suit === "♦";
  const r = rankLabel(card.rank);
  return `<div class="card ${cls || ""} ${red ? "red" : ""}">
    <div class="corner tl"><span class="r">${r}</span><span class="s">${card.suit}</span></div>
    <div class="pip">${card.suit}</div>
    <div class="corner br"><span class="r">${r}</span><span class="s">${card.suit}</span></div>
  </div>`;
}

// a seat (colored dot + name + card count) rendered the same for you and everyone else
function seatInner(pid, s) {
  const isTurn = pid === s.current && s.phase === "playing";
  const out = s.eliminated.includes(pid);
  const st = (s.standings || []).find((x) => x.pid === pid);
  const cnt = s.counts[pid] || 0;
  const you = pid === MY_PID ? ' <span class="you-tag">(you)</span>' : "";
  return {
    cls: `${isTurn ? "turn" : ""} ${out ? "out" : ""}`,
    html: `<div class="count"><span class="mini"></span>${cnt}</div>
      <span class="pdot lg" style="background:${pcolor(pid)}"></span>
      <div class="pname" style="color:${isTurn ? "" : pcolor(pid)}">${esc(pname(pid))}${you}</div>
      ${out && st ? `<span class="tag">OUT · #${st.place} · lasted ${st.turns_lasted}</span>` : ""}`,
  };
}

// ---- render ----
function render() {
  if (!STATE) return;
  const s = STATE;

  // everyone sits around the table; you are at the bottom, same seat style as all.
  const order = s.players.slice();
  const mi = order.indexOf(MY_PID);
  const rot = mi >= 0 ? order.slice(mi).concat(order.slice(0, mi)) : order;

  const seatsEl = document.getElementById("seats");
  seatsEl.innerHTML = rot.map((pid) => {
    const si = seatInner(pid, s);
    return `<div class="seat ${si.cls}" id="seat-${pid}">${si.html}</div>`;
  }).join("");
  positionSeats(rot);

  // pile - fan the last few cards, newest on top. Gate the "just flipped" card on
  // the flip's seq so it never re-animates (fixes the double-drop on mobile).
  const newFlip = s.last_flip && s.last_flip.seq > lastFlipSeq;
  const pileEl = document.getElementById("pile");
  const pile = s.pile || [];
  const show = pile.slice(-6);
  pileEl.innerHTML = show.map((c, i) => {
    const n = show.length;
    const rotDeg = (i - (n - 1) / 2) * 7 + ((c.rank * 13 + i) % 5 - 2);
    const isTop = i === n - 1;
    const landing = newFlip && isTop;
    return `<div class="pcard ${landing ? "landing" : ""}" style="--rot:${rotDeg}deg;
      transform:translate(-50%,-50%) rotate(${rotDeg}deg); z-index:${i}">
      ${cardFace(c)}</div>`;
  }).join("");
  prevPile = pile.length;
  document.getElementById("pileCount").textContent =
    pile.length ? `${pile.length} card${pile.length > 1 ? "s" : ""} in the pile` : "";
  if (newFlip) {                       // a card was just flipped: fly it in and flip it
    flyCard(s.last_flip.pid, s.last_flip.card);
    playSafe(sndFlip);
    lastFlipSeq = s.last_flip.seq;
  }
  if (s.last_burn && s.last_burn.seq > lastBurnSeq && s.last_burn.card) {
    burnCard(s.last_burn.pid, s.last_burn.card);   // lift pile, slide burned card under, drop
    lastBurnSeq = s.last_burn.seq;
  }
  if (s.last_win && s.last_win.seq > lastWinSeq) {
    collectPile(s.last_win.pid, s.last_win.count);  // pile slides to whoever won it
    lastWinSeq = s.last_win.seq;
  }

  // challenge badge - shows the royalty card, how many are left, and who owes it
  const chEl = document.getElementById("challenge");
  if (s.challenge) {
    chEl.className = "challenge";
    chEl.innerHTML = `<div class="big">${s.challenge.label || ""}</div>` +
      `${s.challenge.chances_left} left for <b>${esc(pname(s.current))}</b>`;
  } else chEl.className = "";

  // your clickable face-down pile (bottom-left), labelled "flip"
  const myCnt = s.counts[MY_PID] || 0;
  const canFlip = s.phase === "playing" && s.current === MY_PID && !s.pending_win && myCnt > 0;
  const stackEl = document.getElementById("myStack");
  const backs = Math.min(myCnt, 4);
  stackEl.className = "stack-cards" + (canFlip ? " can-flip" : "");
  stackEl.innerHTML = Array.from({ length: Math.max(backs, myCnt ? 1 : 0) }, (_, i) =>
    `<div class="card-back" style="transform:translate(${i * 2}px,${-i * 2}px)"></div>`).join("");
  const flipLbl = document.getElementById("flipLbl");
  flipLbl.textContent = myCnt ? "flip" : "out";
  flipLbl.classList.toggle("hot", canFlip);

  // turn message
  const tm = document.getElementById("turnMsg");
  if (s.phase === "ended") tm.textContent = "";
  else if (s.pending_win) tm.textContent = `${pname(s.pending_win.pid)} collects…`;
  else if (s.current === MY_PID) tm.textContent = "Your turn - flip!";
  else tm.textContent = `${pname(s.current)} is up`;

  // rule chips
  const chips = ["double", "sandwich", "top-bottom"];
  if ((s.rules || []).includes("ten")) chips.push("tens");
  if ((s.rules || []).includes("kingqueen")) chips.push("K-Q");
  document.getElementById("ruleChips").innerHTML =
    chips.map((c) => `<span class="chip">${c}</span>`).join("");

  // standings
  const stand = (s.standings || []).slice().sort((a, b) => a.place - b.place);
  const stEl = document.getElementById("standings");
  const stTitle = document.getElementById("standTitle");
  if (stand.length) {
    stTitle.style.display = "block"; stEl.style.display = "block";
    stEl.innerHTML = stand.map((x) =>
      `<div class="st"><span><span class="pl">#${x.place}</span> <b style="color:${pcolor(x.pid)}">${esc(pname(x.pid))}</b></span>
       <span class="muted" style="color:#cbb">lasted ${x.turns_lasted}</span></div>`).join("");
  }

  // slap feed
  renderLog(s.log || []);

  // win overlay
  const ov = document.getElementById("overlay");
  if (s.phase === "ended" && s.winner) {
    document.getElementById("winName").textContent = pname(s.winner) + " wins!";
    ov.classList.add("show");
  }
}

function positionSeats(all) {
  const oval = document.querySelector(".table-oval").getBoundingClientRect();
  const cx = oval.left + oval.width / 2;
  const cy = oval.top + oval.height / 2;
  const rx = oval.width / 2 + 26;
  const ry = oval.height / 2 + 20;
  const n = all.length;
  all.forEach((pid, k) => {
    const el = document.getElementById("seat-" + pid);
    if (!el) return;
    // you (k = 0) sit at the bottom; everyone else spreads evenly around the table
    const theta = Math.PI / 2 + (2 * Math.PI * k) / n;
    el.style.left = cx + rx * Math.cos(theta) + "px";
    el.style.top = cy + ry * Math.sin(theta) + "px";
  });
}
window.addEventListener("resize", () => { if (STATE) render(); });

function entryHTML(e) {
  if (e.kind === "slap") {
    const rt = e.reaction_ms != null ? ` in ${(e.reaction_ms / 1000).toFixed(2)}s` : "";
    const rs = (e.reasons || []).map((r) => REASON[r] || r).join(" + ");
    const cards = e.cards != null ? `, +${e.cards} cards` : "";
    return `<b style="color:${e.color}">SLAP by ${esc(e.name)}</b>${rt} (${rs})${cards}`;
  }
  if (e.kind === "false")
    return `<b style="color:${e.color}">${esc(e.name)}</b> slapped early - burned ${e.burned}`;
  if (e.kind === "pile")
    return `<b style="color:${e.color}">${esc(e.name)}</b> takes the pile${e.on ? " on a " + e.on : ""}, +${e.cards} cards`;
  if (e.kind === "out")
    return `<b style="color:${e.color}">${esc(e.name)}</b> is out · #${e.place}, lasted ${e.turns_lasted} turns`;
  return "";
}

function renderLog(log) {
  const el = document.getElementById("slog");
  const recent = log.slice(-40);
  // autoscroll only when the reader is already at the bottom (so scrolling up to
  // read history is not yanked away).
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  const have = {};
  Array.from(el.children).forEach((c) => { have[c.dataset.id] = true; });
  const want = new Set(recent.map((e) => String(e.id)));
  Array.from(el.children).forEach((c) => { if (!want.has(c.dataset.id)) c.remove(); });

  const fresh = [];
  recent.forEach((e) => {
    if (have[String(e.id)]) return;
    const div = document.createElement("div");
    div.dataset.id = e.id;
    div.className = "entry" + (e.kind === "false" ? " false" : e.kind === "out" ? " out" : "");
    div.innerHTML = entryHTML(e);
    el.appendChild(div);
    if (e.id > lastLogId) fresh.push(e);
  });
  if (atBottom) el.scrollTop = el.scrollHeight;

  if (fresh.length && lastLogId) {
    if (fresh.some((e) => e.kind === "slap" || e.kind === "false")) playSafe(sndSlap);
    fresh.forEach((e) => {
      if (e.kind === "slap") slapHand(e.pid, e.color);
      if (e.kind === "false") { slapHand(e.pid, e.color); showX(); }
      if (e.kind === "false" && e.pid === MY_PID) slapCooldownUntil = Date.now() + 2000;
    });
    const slap = fresh.slice().reverse().find((e) => e.kind === "slap");
    if (slap) { flash(); toast(`SLAP! ${slap.name}`); }
    else if (fresh.some((e) => e.kind === "false" && e.pid === MY_PID)) toast("Too early!");
  }
  if (recent.length) lastLogId = Math.max(lastLogId, ...recent.map((e) => e.id || 0));
}

function flash() {
  const f = document.getElementById("flash");
  f.classList.remove("go"); void f.offsetWidth; f.classList.add("go");
}
let toastTimer = null;
function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 900);
}

// ---- actions ----
function doFlip() {
  if (!STATE || STATE.phase !== "playing") return;
  if (STATE.current !== MY_PID || STATE.pending_win) return;
  socket.emit("flip", { code: GAME_CODE });
}
function doSlap() {
  if (!STATE || STATE.phase !== "playing") return;
  if (Date.now() < slapCooldownUntil) return;   // frozen out after a wrong slap
  socket.emit("slap", { code: GAME_CODE });
}
window.doFlip = doFlip;
window.doSlap = doSlap;

document.addEventListener("keydown", (e) => {
  if (e.repeat) return;
  if (e.code === "Space") { e.preventDefault(); doSlap(); }
  else if (e.key === "f" || e.key === "F") { doFlip(); }
});

// ---- animations ----
// Animations live inside the table so their z-index sits relative to the pile
// (fly/hand above it, the burned card tucked below it).
function fx() { return document.querySelector(".table-page") || document.body; }
function centerOf(el) {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}

// A face-down card flies from the flipper's seat to the pile and flips face-up.
function flyCard(pid, card) {
  const seat = document.getElementById("seat-" + pid);
  const pileEl = document.getElementById("pile");
  if (!seat || !pileEl || !card) return;
  const a = centerOf(seat), b = centerOf(pileEl);
  const fly = document.createElement("div");
  fly.className = "fly-card";
  fly.style.left = a.x + "px";
  fly.style.top = a.y + "px";
  fly.style.setProperty("--dx", (b.x - a.x) + "px");
  fly.style.setProperty("--dy", (b.y - a.y) + "px");
  fly.innerHTML = `<div class="fly-inner">
      <div class="fly-face fly-back"></div>
      <div class="fly-face fly-front">${cardFace(card)}</div>
    </div>`;
  fx().appendChild(fly);
  requestAnimationFrame(() => fly.classList.add("go"));
  setTimeout(() => fly.remove(), 420);
}

// On a wrong slap: lift the pile, slide the burned card underneath face-up (so
// everyone sees the new bottom card), then drop the pile back on top of it.
function burnCard(pid, card) {
  const seat = document.getElementById("seat-" + pid);
  const pileEl = document.getElementById("pile");
  if (!seat || !pileEl || !card) return;
  const a = centerOf(seat), b = centerOf(pileEl);
  pileEl.classList.add("lifted");
  const burn = document.createElement("div");
  burn.className = "burn-card";
  burn.style.left = a.x + "px";
  burn.style.top = a.y + "px";
  burn.style.setProperty("--dx", (b.x - a.x) + "px");
  burn.style.setProperty("--dy", (b.y - a.y + 30) + "px");   // ends in the gap below the lifted pile
  burn.innerHTML = cardFace(card);                            // face-up
  fx().appendChild(burn);
  requestAnimationFrame(() => burn.classList.add("go"));
  setTimeout(() => pileEl.classList.remove("lifted"), 900);   // drop the pile back down
  setTimeout(() => burn.remove(), 1300);
}

function handSVG(color) {
  return `<svg viewBox="0 0 100 120" width="86" height="104" aria-hidden="true">
    <g fill="${color}" stroke="rgba(0,0,0,.32)" stroke-width="2" stroke-linejoin="round">
      <rect x="22" y="46" width="58" height="60" rx="16"/>
      <rect x="25" y="12" width="12" height="42" rx="6"/>
      <rect x="41" y="5" width="12" height="50" rx="6"/>
      <rect x="57" y="8" width="12" height="48" rx="6"/>
      <rect x="73" y="16" width="12" height="40" rx="6"/>
      <rect x="4" y="54" width="20" height="14" rx="7" transform="rotate(-28 14 61)"/>
    </g></svg>`;
}

// When a pile is won, a little stack of cards slides from the pile to that player.
function collectPile(pid, count) {
  const seat = document.getElementById("seat-" + pid);
  const pileEl = document.getElementById("pile");
  if (!seat || !pileEl) return;
  const a = centerOf(pileEl), b = centerOf(seat);
  const n = Math.min(5, Math.max(2, count || 2));
  for (let i = 0; i < n; i++) {
    const c = document.createElement("div");
    c.className = "collect-card";
    c.style.left = a.x + "px";
    c.style.top = a.y + "px";
    c.style.setProperty("--dx", (b.x - a.x) + "px");
    c.style.setProperty("--dy", (b.y - a.y) + "px");
    c.style.animationDelay = (i * 45) + "ms";
    fx().appendChild(c);
    setTimeout(() => c.remove(), 520 + i * 45);
  }
}

// A red X pops at the pile on a wrong slap.
function showX() {
  const pileEl = document.getElementById("pile");
  if (!pileEl) return;
  const b = centerOf(pileEl);
  const x = document.createElement("div");
  x.className = "slap-x";
  x.style.left = b.x + "px";
  x.style.top = b.y + "px";
  x.textContent = "✕";
  fx().appendChild(x);
  setTimeout(() => x.remove(), 700);
}

// A colored hand shoots in from the slapper's seat and smacks the pile.
function slapHand(pid, color) {
  const seat = document.getElementById("seat-" + pid);
  const pileEl = document.getElementById("pile");
  if (!seat || !pileEl) return;
  const a = centerOf(seat), b = centerOf(pileEl);
  const ang = Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI + 90;
  const h = document.createElement("div");
  h.className = "slap-hand";
  h.style.left = a.x + "px";
  h.style.top = a.y + "px";
  h.style.setProperty("--tx", (b.x - a.x) + "px");
  h.style.setProperty("--ty", (b.y - a.y) + "px");
  h.innerHTML = `<div class="hand-rot" style="transform:rotate(${ang}deg)">${handSVG(color || "#f2c94c")}</div>`;
  fx().appendChild(h);
  setTimeout(() => h.remove(), 520);
}
