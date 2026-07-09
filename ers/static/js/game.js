/* Egyptian Rat Screw - table client. Renders the wooden table, the pile, the
   slap feed and standings; sends flip/slap over the socket. The server is the
   authority for every rule. */

const socket = io();
let STATE = null;
let prevPile = 0;
let lastLogT = 0;

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
    html: `<span class="pdot lg" style="background:${pcolor(pid)}"></span>
      <div class="pname" style="color:${isTurn ? "" : pcolor(pid)}">${esc(pname(pid))}${you}</div>
      <div class="count"><span class="mini"></span>${cnt}</div>
      ${out && st ? `<span class="tag">OUT · #${st.place} · lasted ${st.turns_lasted}</span>` : ""}`,
  };
}

// ---- render ----
function render() {
  if (!STATE) return;
  const s = STATE;

  // opponents fan around the top of the table; you are your own pile bottom-left.
  const order = s.players.slice();
  const mi = order.indexOf(MY_PID);
  const rot = mi >= 0 ? order.slice(mi).concat(order.slice(0, mi)) : order;
  const others = rot.filter((pid) => pid !== MY_PID);

  const seatsEl = document.getElementById("seats");
  seatsEl.innerHTML = others.map((pid) => {
    const si = seatInner(pid, s);
    return `<div class="seat ${si.cls}" id="seat-${pid}">${si.html}</div>`;
  }).join("");
  positionSeats(others);

  // pile - fan the last few cards, newest on top
  const pileEl = document.getElementById("pile");
  const pile = s.pile || [];
  const show = pile.slice(-6);
  pileEl.innerHTML = show.map((c, i) => {
    const n = show.length;
    const rotDeg = (i - (n - 1) / 2) * 7 + ((c.rank * 13 + i) % 5 - 2);
    const isTop = i === n - 1;
    const grew = pile.length > prevPile && isTop;
    return `<div class="pcard ${grew ? "new" : ""}" style="--rot:${rotDeg}deg;
      transform:translate(-50%,-50%) rotate(${rotDeg}deg); z-index:${i}">
      ${cardFace(c, isTop ? "" : "")}</div>`;
  }).join("");
  if (pile.length === prevPile + 1) playSafe(sndFlip);   // a card was placed
  prevPile = pile.length;
  document.getElementById("pileCount").textContent =
    pile.length ? `${pile.length} card${pile.length > 1 ? "s" : ""} in the pile` : "";

  // challenge badge
  const chEl = document.getElementById("challenge");
  if (s.challenge) {
    chEl.className = "challenge";
    chEl.innerHTML = `<div class="big">${s.challenge.label || ""}</div>${s.challenge.chances_left} to beat`;
  } else chEl.className = "";

  // your own seat (rendered exactly like the others) plus your clickable pile
  const myCnt = s.counts[MY_PID] || 0;
  const canFlip = s.phase === "playing" && s.current === MY_PID && !s.pending_win && myCnt > 0;
  const mine = seatInner(MY_PID, s);
  const mySeatEl = document.getElementById("mySeat");
  mySeatEl.className = "seat me " + mine.cls;
  mySeatEl.innerHTML = mine.html;
  const stackEl = document.getElementById("myStack");
  const backs = Math.min(myCnt, 4);
  stackEl.className = "stack-cards" + (canFlip ? " can-flip" : "");
  stackEl.innerHTML = Array.from({ length: Math.max(backs, myCnt ? 1 : 0) }, (_, i) =>
    `<div class="card-back" style="transform:translate(${i * 2}px,${-i * 2}px)"></div>`).join("");

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

function positionSeats(others) {
  const oval = document.querySelector(".table-oval").getBoundingClientRect();
  const cx = oval.left + oval.width / 2;
  const cy = oval.top + oval.height / 2;
  const rx = oval.width / 2 + 26;
  const ry = oval.height / 2 + 20;
  const n = others.length;
  others.forEach((pid, k) => {
    const el = document.getElementById("seat-" + pid);
    if (!el) return;
    // spread opponents across the top of the table (bottom is your own pile)
    const frac = n === 1 ? 0.5 : (k + 0.5) / n;
    const theta = Math.PI * (170 + 200 * frac) / 180;
    el.style.left = cx + rx * Math.cos(theta) + "px";
    el.style.top = cy + ry * Math.sin(theta) + "px";
  });
}
window.addEventListener("resize", () => { if (STATE) render(); });

function renderLog(log) {
  const el = document.getElementById("slog");
  el.innerHTML = log.slice(-14).map((e) => {
    if (e.kind === "slap") {
      const rt = e.reaction_ms != null ? ` in ${(e.reaction_ms / 1000).toFixed(2)}s` : "";
      const rs = (e.reasons || []).map((r) => REASON[r] || r).join(" + ");
      const cards = e.cards != null ? `, +${e.cards} cards` : "";
      return `<div class="entry"><b style="color:${e.color}">SLAP by ${esc(e.name)}</b>${rt} (${rs})${cards}</div>`;
    }
    if (e.kind === "false")
      return `<div class="entry false"><b style="color:${e.color}">${esc(e.name)}</b> slapped early - burned ${e.burned}</div>`;
    if (e.kind === "pile")
      return `<div class="entry"><b style="color:${e.color}">${esc(e.name)}</b> takes the pile, +${e.cards} cards</div>`;
    if (e.kind === "out")
      return `<div class="entry out"><b style="color:${e.color}">${esc(e.name)}</b> is out · #${e.place}, lasted ${e.turns_lasted} turns</div>`;
    return "";
  }).join("");

  // flash + toast on the newest slap
  const fresh = log.filter((e) => (e.t || 0) > lastLogT);
  if (fresh.length && lastLogT) {
    if (fresh.some((e) => e.kind === "slap" || e.kind === "false")) playSafe(sndSlap);
    const slap = fresh.slice().reverse().find((e) => e.kind === "slap");
    if (slap) { flash(); toast(`SLAP! ${slap.name}`); }
    else {
      const mine = fresh.find((e) => e.kind === "false" && e.name === pname(MY_PID));
      if (mine) toast("Too early!");
    }
  }
  if (log.length) lastLogT = Math.max(lastLogT, ...log.map((e) => e.t || 0));
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
  socket.emit("slap", { code: GAME_CODE });
}
window.doFlip = doFlip;
window.doSlap = doSlap;

document.addEventListener("keydown", (e) => {
  if (e.repeat) return;
  if (e.code === "Space") { e.preventDefault(); doSlap(); }
  else if (e.key === "f" || e.key === "F") { doFlip(); }
});
