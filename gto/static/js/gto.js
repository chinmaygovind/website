/* gto.cgovind.com - the table.
 *
 * The server owns the game and answers one request at a time. This file draws
 * whatever it is told and paces the opponents out so the table feels like a
 * room rather than a spreadsheet.
 *
 * **The pacing lives here, not on the server.** Every bot action arrives with a
 * `delay` in seconds; they are played out one at a time with the state applied
 * at the end. A server that slept for Bell's nine-second tank would hold one of
 * three gunicorn workers for nine seconds.
 */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

let state = window.GTO;
let busy = false;
let speed = 1;

const money = c => "$" + (c / 100).toFixed(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));

function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), 2600);
}

/* ----------------------------------------------------------------- drawing */

function cardEl(code, cls = "") {
  const d = document.createElement("div");
  d.className = "card " + cls;
  if (code) d.style.backgroundImage = `url("/static/cards/${code}.svg")`;
  else d.classList.add("back");
  return d;
}

/** Seats sit on an ellipse, hero at the bottom, the rest evenly around it.
 *  Placing them by angle rather than by hand-written coordinates is what makes
 *  five-handed and six-handed the same code. */
function place(i, n) {
  const a = (90 + i * (360 / n)) * Math.PI / 180;
  return { x: 50 + 40 * Math.cos(a), y: 47 + 44 * Math.sin(a) };
}

function initials(name) {
  return name.split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
}

function drawSeats() {
  const wrap = $("#seats");
  wrap.innerHTML = "";
  const seats = state.seats || [];
  const heroIndex = seats.findIndex(s => s.you);
  const n = seats.length;

  seats.forEach((s, i) => {
    const slot = (i - (heroIndex < 0 ? 0 : heroIndex) + n) % n;
    const { x, y } = place(slot, n);
    const el = document.createElement("div");
    el.className = "seat" + (s.folded ? " folded" : "") +
      (state.to_act === i && !state.complete ? " acting" : "");
    el.style.left = x + "%";
    el.style.top = y + "%";
    el.dataset.seat = i;

    const cards = document.createElement("div");
    cards.className = "cards";
    const hero = !!s.you;
    if (!s.folded || hero) {
      const shown = s.hole ? s.hole.split(" ") : [null, null];
      shown.forEach(c => cards.appendChild(
        cardEl(c, (hero ? "hero" : "small") + (s.folded ? " muck" : ""))));
    }
    el.appendChild(cards);

    const plate = document.createElement("div");
    plate.className = "plate";
    const streak = (state.streaks || {})[s.name] || 0;
    plate.innerHTML = `
      <div class="who-row">
        <div class="avatar"${s.avatar ? ` style="background-image:url('${s.avatar}')"` : ""}>${s.avatar ? "" : initials(s.name)}</div>
        <div>
          <div class="nm">${s.name}${streak >= 2 ? `<span class="streak">${streak} in a row</span>` : ""}</div>
          <div class="pos">${s.position || ""}${s.all_in ? " · all in" : ""}</div>
        </div>
      </div>
      <div class="stack">${money(s.stack)}</div>
      ${s.tilt > 0.15 ? `<div class="tiltbar"><i style="width:${Math.round(s.tilt * 100)}%"></i></div>` : ""}`;
    el.appendChild(plate);

    if (s.committed > 0) {
      const bet = document.createElement("div");
      bet.className = "bet";
      bet.textContent = money(s.committed);
      bet.style.top = y > 55 ? "-16px" : "calc(100% + 6px)";
      el.appendChild(bet);
    }
    if (state.button === i) {
      const b = document.createElement("div");
      b.className = "dot-btn";
      b.textContent = "D";
      b.style.right = "-6px";
      b.style.top = "50%";
      el.appendChild(b);
    }
    wrap.appendChild(el);
  });
}

function drawMiddle() {
  const board = $("#board");
  board.innerHTML = "";
  (state.board || []).forEach(c => board.appendChild(cardEl(c)));
  $("#pot").innerHTML = `Pot <b>${money(state.pot || 0)}</b>`;
  $("#street").textContent = state.complete ? "" : (state.street || "");
}

/* ----------------------------------------------------------------- actions */

function drawActions() {
  const row = $("#actions");
  row.innerHTML = "";
  const legal = state.legal || [];
  const sizerRow = $("#sizer-row");
  sizerRow.hidden = true;

  if (state.needs_rebuy) {
    row.appendChild(button("Rebuy", "act go", async () => {
      await post("/api/rebuy", {});
      toast("Bought in again.");
    }));
    return;
  }
  if (!legal.length) {
    row.appendChild(button(state.hands_played ? "Next hand" : "Take a seat",
      "act go", deal));
    return;
  }

  const raise = legal.find(a => a.action === "raise" || a.action === "bet");
  legal.forEach(a => {
    if (a.action === "fold") {
      row.appendChild(button("Fold", "act fold", () => act({ action: "fold" })));
    } else if (a.action === "check") {
      row.appendChild(button("Check", "act", () => act({ action: "check" })));
    } else if (a.action === "call") {
      row.appendChild(button(`Call<small>${money(a.amount)}</small>`, "act go",
        () => act({ action: "call" })));
    }
  });
  if (raise) {
    setupSizer(raise);
    sizerRow.hidden = false;
    const label = raise.action === "bet" ? "Bet" : "Raise to";
    row.appendChild(button(`${label}<small id="raise-amt">${money(currentSize())}</small>`,
      "act raise", () => act({ action: raise.action, to: currentSize() })));
  }
}

function button(html, cls, fn) {
  const b = document.createElement("button");
  b.className = cls;
  b.innerHTML = html;
  b.onclick = () => { if (!busy) fn(); };
  b.disabled = busy;
  return b;
}

let sizeRange = { min: 0, max: 0 };

function setupSizer(raise) {
  sizeRange = { min: raise.min, max: raise.max };
  const slider = $("#size");
  slider.min = 0;
  slider.max = 100;
  if (!slider.dataset.touched) slider.value = 35;
  slider.oninput = () => { slider.dataset.touched = "1"; refreshSize(); };
  $$(".chip").forEach(c => c.onclick = () => {
    const frac = parseFloat(c.dataset.frac);
    const want = frac >= 99 ? sizeRange.max
      : (state.pot || 0) * frac + (currentCall() || 0);
    const pct = 100 * (want - sizeRange.min) / Math.max(1, sizeRange.max - sizeRange.min);
    slider.value = Math.max(0, Math.min(100, pct));
    slider.dataset.touched = "1";
    refreshSize();
  });
  refreshSize();
}

function currentCall() {
  const c = (state.legal || []).find(a => a.action === "call");
  return c ? c.amount : 0;
}

function currentSize() {
  const pct = parseFloat($("#size").value) / 100;
  return Math.round(sizeRange.min + pct * (sizeRange.max - sizeRange.min));
}

function refreshSize() {
  const v = currentSize();
  $("#size-label").textContent = money(v);
  const amt = $("#raise-amt");
  if (amt) amt.textContent = money(v);
}

/* -------------------------------------------------------------- the server */

async function post(url, body) {
  busy = true;
  drawActions();
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json();
    if (!res.ok && data.error !== "rebuy") {
      toast(data.error || "Something went wrong.");
      if (data.state) state = data.state;
      return null;
    }
    if (data.events) await playEvents(data.events);
    if (data.state) state = data.state;
    render();
    if (data.review && data.review.length) showReview(data.review, data.adaptation);
    return data;
  } catch (e) {
    toast("Lost the connection to the table.");
    return null;
  } finally {
    busy = false;
    drawActions();
  }
}

/** Play the opponents out one at a time. The authoritative state is applied
 *  afterwards; these bubbles are only the pacing. */
async function playEvents(events) {
  for (const e of events) {
    if (e.kind === "hand_over") continue;
    await sleep(Math.max(60, (e.delay || 0.6) * 1000 * speed));
    const seat = $(`.seat[data-seat="${e.seat}"]`);
    if (!seat) continue;
    $$(".say", seat).forEach(n => n.remove());
    const say = document.createElement("div");
    say.className = "say";
    say.textContent = e.action === "call" && e.amount
      ? `calls ${money(e.amount)}`
      : (e.action === "raise" || e.action === "bet")
        ? `${e.action}s to ${money(e.amount)}` : e.action + "s";
    seat.appendChild(say);
    $$(".seat").forEach(s => s.classList.remove("acting"));
  }
  await sleep(220 * speed);
}

async function deal() { await post("/api/hand", {}); }
async function act(a) { await post("/api/act", a); }

/* ---------------------------------------------------------------- review */

const SOURCES = [
  ["solver", "from a solved equilibrium"],
  ["derived", "a solved range, moved for a stated reason"],
  ["heuristic", "nobody has solved this spot"],
  ["model", "exact against these five, not against equilibrium"],
  ["arithmetic", "true by definition"],
];

function legendEl() {
  const el = document.createElement("details");
  el.className = "legend";
  el.innerHTML = `<summary>What the tags on each line mean</summary>` +
    SOURCES.map(([k, t]) =>
      `<div class="lrow"><span class="src ${k}">${k}</span><span>${t}</span></div>`
    ).join("");
  return el;
}

function showReview(marks, adaptation) {
  if (state.prefs && state.prefs.review_after_each_hand === false) return;
  const body = $("#review-body");
  body.innerHTML = "";
  body.appendChild(legendEl());

  if (!marks.length) {
    body.insertAdjacentHTML("beforeend",
      `<p class="sub">You were not asked to make a decision.</p>`);
  }
  marks.forEach(m => body.appendChild(markEl(m)));

  (adaptation || []).forEach(text => {
    const p = document.createElement("div");
    p.className = "warnbox";
    p.textContent = text;
    body.appendChild(p);
  });
  $("#review-drawer").classList.add("open");
}

function markEl(m) {
  const el = document.createElement("div");
  el.className = "mark";
  const did = m.action + (m.amount ? " " + money(m.amount) : "");
  el.innerHTML = `
    <div class="top">
      <span class="st">${m.street}${m.position ? " · " + m.position : ""}</span>
      <span class="did">You ${did}</span>
      <span class="tag ${m.verdict}">${m.verdict}</span>
    </div>
    <div class="headline">${escapeHtml(m.headline)}</div>
    ${m.loss_bb ? `<div class="headline cost">That is about ${m.loss_bb}bb.</div>` : ""}`;
  (m.lines || []).forEach(l => {
    const d = document.createElement("div");
    d.className = "line";
    d.innerHTML = `
      <div class="lab">${escapeHtml(l.label)}
        <span class="src ${l.confidence}" title="${escapeHtml(l.confidence_text)}">${l.confidence}</span></div>
      <div class="txt">${escapeHtml(l.text)}</div>
      ${l.note ? `<div class="note">${escapeHtml(l.note)}</div>` : ""}`;
    el.appendChild(d);
  });
  return el;
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* --------------------------------------------------------------- settings */

function fillSettings() {
  const p = state.prefs || {};
  $("#p-sb").value = p.sb;
  $("#p-bb").value = p.bb;
  $("#p-buyin").value = p.buyin;
  $("#p-seats").value = String(p.seats || 0);
  $("#p-bounty").checked = !!p.bounty_on;
  $("#p-review").checked = p.review_after_each_hand !== false;
  $("#p-ranges").checked = p.show_ranges !== false;
  $("#p-rebuy").checked = !!p.auto_rebuy;
  $("#p-speed").value = Math.round((p.bot_speed ?? 1) * 100);
  speed = (p.bot_speed ?? 1);
  bountyNote();

  const list = $("#who-list");
  list.innerHTML = "";
  (window.GTO_OPPONENTS || []).forEach(o => {
    const d = document.createElement("div");
    d.className = "who-card";
    d.innerHTML = `
      <div class="h"><div class="avatar">${initials(o.name)}</div><b>${escapeHtml(o.name)}</b></div>
      <div class="blurb">${escapeHtml(o.blurb)}</div>
      <div class="nums">${o.vpip}/${o.pfr}/${o.three_bet} · plays ${o.vpip}% of hands, raises ${o.pfr}%</div>`;
    list.appendChild(d);
  });
}

/** The bounty is worth saying out loud, because at these stakes it is bigger
 *  than most of the pots. */
function bountyNote() {
  const bb = parseInt($("#p-bb").value || "25", 10) / 100;
  const seats = (state.seats || []).length || 6;
  const n = seats - 1;
  if (!$("#p-bounty").checked || bb <= 0) {
    $("#bounty-note").textContent = "Off. Pots are the only thing worth winning.";
    return;
  }
  $("#bounty-note").textContent =
    `At these blinds a third straight win pays $${(1 * n).toFixed(0)} — about ` +
    `${Math.round(1 * n / bb)} big blinds — and a fifth pays $${(3 * n).toFixed(0)}. ` +
    `The review prices that into every decision you make while a streak is live.`;
}

async function savePrefs() {
  const body = {
    sb: +$("#p-sb").value, bb: +$("#p-bb").value, buyin: +$("#p-buyin").value,
    seats: +$("#p-seats").value, bounty_on: $("#p-bounty").checked,
    review_after_each_hand: $("#p-review").checked,
    show_ranges: $("#p-ranges").checked, auto_rebuy: $("#p-rebuy").checked,
    bot_speed: (+$("#p-speed").value) / 100,
  };
  const res = await fetch("/api/prefs", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 401) { toast("Sign in to keep settings."); return; }
  toast("Saved. Dealing a fresh table.");
  $("#settings-drawer").classList.remove("open");
  const fresh = await fetch("/api/state").then(r => r.json());
  state = fresh;
  render();
}

/* ------------------------------------------------------------------- boot */

function render() {
  drawSeats();
  drawMiddle();
  drawActions();
}

$("#gear").onclick = () => { fillSettings(); $("#settings-drawer").classList.add("open"); };
$$("[data-close]").forEach(b => b.onclick = () => $("#" + b.dataset.close).classList.remove("open"));
$("#save-prefs").onclick = savePrefs;
$("#p-bounty").onchange = bountyNote;
$("#p-bb").oninput = bountyNote;
document.addEventListener("keydown", e => {
  if (e.key === "Escape") $$(".drawer").forEach(d => d.classList.remove("open"));
  if (busy) return;
  const legal = (state.legal || []).map(a => a.action);
  if (e.key === "f" && legal.includes("fold")) act({ action: "fold" });
  if (e.key === "c" && legal.includes("call")) act({ action: "call" });
  if (e.key === "c" && legal.includes("check")) act({ action: "check" });
  if (e.key === " " && !legal.length) { e.preventDefault(); deal(); }
});

speed = (state.prefs && state.prefs.bot_speed) ?? 1;
render();
