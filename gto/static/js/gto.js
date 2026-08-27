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
 *
 * **Chips move before the server answers.** A bet the table only shows once the
 * round trip lands feels like lag, so `applyChips` does to the local state what
 * the engine is about to do to the real one - stack down, chips out in front,
 * pot up - for the hero the moment they act and for each bot as its event is
 * paced out. The authoritative state overwrites all of it when the response
 * arrives, so a wrong guess lives for one paint and cannot accumulate.
 *
 * **Every shortcut key is a button.** The keyboard finds the button by its
 * `data-key` and clicks it, so a key can never fire an action the table is not
 * offering, and the badge on the button and the binding cannot drift apart.
 */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

let state = window.GTO;
let busy = false;
let speed = 1;

//: Pacing once the hero is out of the pot. See `gto/CLAUDE.md`.
const RUSH_MS = 120;
let rushing = false;
let skipRest = false;
let dealPending = false;

//: What each seat is saying, and what it last had in front of it - both keyed
//: by seat index, both only so a redraw can tell what changed and animate it.
let says = new Map();
let shown = new Map();
let shownStack = new Map();
let shownCards = new Map();
let pacedStreet = null;

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
  return { x: 50 + 40 * Math.cos(a), y: 47 + 40 * Math.sin(a) };
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
    // A seat is rebuilt on every event, so cards that have not changed must not
    // replay their deal - otherwise the whole table flickers each time a bot acts.
    const sig = `${s.hole}|${s.folded}|${hero}`;
    const same = shownCards.get(i) === sig;
    shownCards.set(i, sig);
    if (!s.folded || hero) {
      const held = s.hole ? s.hole.split(" ") : [null, null];
      held.forEach(c => cards.appendChild(
        cardEl(c, (hero ? "hero" : "small") + (s.folded ? " muck" : "") + (same ? " still" : ""))));
    }
    if (!cards.childElementCount) cards.classList.add("empty");
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
      <div class="stack${shownStack.has(i) && shownStack.get(i) !== s.stack ? " bump" : ""}">${money(s.stack)}</div>
      ${s.tilt > 0.15 ? `<div class="tiltbar"><i style="width:${Math.round(s.tilt * 100)}%"></i></div>` : ""}`;
    el.appendChild(plate);

    if (s.committed > 0 && !state.complete) {
      const bet = document.createElement("div");
      bet.className = "bet" + (shown.get(i) === s.committed ? "" : " fresh");
      bet.textContent = money(s.committed);
      bet.style.top = y > 55 ? "-16px" : "calc(100% + 6px)";
      bet.style.setProperty("--from", y > 55 ? "12px" : "-12px");
      el.appendChild(bet);
    }
    shown.set(i, s.committed);
    shownStack.set(i, s.stack);
    // The hero gets no bubble: their own chips going out said it already, and
    // below their seat is where the buttons are.
    if (says.has(i) && !hero) {
      const say = document.createElement("div");
      say.className = "say";
      say.textContent = says.get(i);
      if (y <= 55) {                  // chips hang below this seat; queue under them
        say.style.top = "calc(100% + 32px)";
        say.style.bottom = "auto";
      }
      el.appendChild(say);
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

/** What the engine is about to do, done locally so the table answers at once.
 *  Overwritten wholesale by the state the server sends back. */
function applyChips(i, action, amount) {
  const s = (state.seats || [])[i];
  if (!s) return;
  let put = 0;
  if (action === "call") put = Math.min(amount || 0, s.stack);
  else if (action === "bet" || action === "raise") {
    put = Math.min(Math.max(0, (amount || 0) - s.committed), s.stack);
  } else if (action === "fold") s.folded = true;
  s.stack -= put;
  s.committed += put;
  if (put > 0 && s.stack === 0) s.all_in = true;
  state.pot = (state.pot || 0) + put;
}

//: How much of the board is out on each street, so the pacing can deal it.
const BOARD_BY_STREET = { preflop: 0, flop: 3, turn: 4, river: 5 };

/** The table as the deal left it, before any bot acted: everyone on the stack
 *  they sat down with, the blinds out, the hero's cards up.
 *
 *  Derived from the answer rather than remembered, because the answer is the
 *  only thing that knows about a rebuy: a seat's stack plus whatever it has
 *  since put in, less its blind, is what it started the hand with. Without this
 *  the whole pacing plays out over the *previous* hand's table. */
function dealt(fresh) {
  const blind = s => s.position === "SB" ? (fresh.sb || 0)
    : s.position === "BB" ? (fresh.bb || 0) : 0;
  return {
    ...fresh,
    complete: false,
    street: "preflop",
    board: [],
    legal: [],
    to_act: null,
    pot: fresh.seats.reduce((n, s) => n + blind(s), 0),
    seats: fresh.seats.map(s => ({
      ...s,
      stack: s.stack + Math.max(0, s.committed - blind(s)),
      committed: blind(s),
      folded: false,
      all_in: false,
    })),
  };
}

/** The chips in front of everybody go to the pot at the end of a street. */
function sweep() {
  (state.seats || []).forEach(s => { s.committed = 0; });
  shown.clear();
}

function phrase(action, amount) {
  if (action === "call" && amount) return `calls ${money(amount)}`;
  if (action === "bet") return `bets ${money(amount)}`;
  if (action === "raise") return `raises to ${money(amount)}`;
  return action + "s";
}

/* ----------------------------------------------------------------- actions */

function drawActions() {
  const row = $("#actions");
  row.innerHTML = "";
  const legal = state.legal || [];
  const sizerRow = $("#sizer-row");
  sizerRow.hidden = true;

  // Built enabled rather than through `button`'s `busy`: it has to work
  // during the request that is still playing the hand out.
  if (rushing) {
    const b = button("Next hand", "act go", () => {}, "n");
    b.disabled = false;
    b.onclick = () => { skipRest = true; dealPending = true; b.disabled = true; };
    row.appendChild(b);
    return;
  }
  if (state.needs_rebuy) {
    row.appendChild(button("Rebuy", "act go", async () => {
      await post("/api/rebuy", {});
      toast("Bought in again.");
    }, "n"));
    return;
  }
  if (!legal.length) {
    row.appendChild(button(state.hands_played ? "Next hand" : "Take a seat",
      "act go", deal, "n"));
    return;
  }

  const raise = legal.find(a => a.action === "raise" || a.action === "bet");
  legal.forEach(a => {
    if (a.action === "fold") {
      row.appendChild(button("Fold", "act fold", () => act({ action: "fold" }), "f"));
    } else if (a.action === "check") {
      row.appendChild(button("Check", "act", () => act({ action: "check" }), "k"));
    } else if (a.action === "call") {
      row.appendChild(button(`Call<small>${money(a.amount)}</small>`, "act go",
        () => act({ action: "call" }), "c"));
    }
  });
  if (raise) {
    setupSizer(raise);
    sizerRow.hidden = false;
    const label = raise.action === "bet" ? "Bet" : "Raise to";
    row.appendChild(button(`${label}<small id="raise-amt">${money(currentSize())}</small>`,
      "act raise", () => act({ action: raise.action, to: currentSize() }), "b"));
  }
}

function button(html, cls, fn, key) {
  const b = document.createElement("button");
  b.className = cls;
  b.innerHTML = html + (key ? `<span class="key">${key.toUpperCase()}</span>` : "");
  if (key) b.dataset.key = key;
  b.onclick = () => { if (!busy) fn(); };
  b.disabled = busy;
  return b;
}

let sizeRange = { min: 0, max: 0 };

/** The bet this spot opens on, in chips.
 *
 *  A slider position is a fraction of `[minimum raise, your whole stack]`, which
 *  is not a poker size and cannot be one - see `gto/CLAUDE.md`. */
function defaultRaiseTo(raise) {
  const bb = state.bb || 25;
  const seats = state.seats || [];
  const level = Math.max(0, ...seats.map(s => s.committed || 0));
  let want;
  if (state.street === "preflop") {
    if (level <= bb) {
      // Not `committed >= bb`: the blinds are equal, so the small blind has
      // already matched without limping. See `gto/CLAUDE.md`.
      const limpers = seats.filter(
        s => !s.folded && !s.you && s.position !== "BB" && s.position !== "SB"
          && (s.committed || 0) >= bb).length;
      want = bb * 2.5 + bb * limpers;
    } else {
      const callers = seats.filter(
        s => !s.folded && !s.you && (s.committed || 0) === level).length - 1;
      want = level * (3 + Math.max(0, callers));
    }
  } else {
    want = (state.pot || 0) * 0.66 + (currentCall() || 0);
  }
  return Math.max(raise.min, Math.min(raise.max, Math.round(want)));
}

function setupSizer(raise) {
  sizeRange = { min: raise.min, max: raise.max };
  const slider = $("#size");
  const bb = state.bb || 25;
  slider.min = raise.min;
  slider.max = raise.max;
  slider.step = Math.max(1, Math.round(bb / 4));

  // A redraw inside one decision must not undo a drag; a new decision must not
  // inherit the last one's slider fraction.
  const spot = `${state.street}|${state.pot}|${raise.min}|${raise.max}`;
  if (slider.dataset.spot !== spot) {
    slider.dataset.spot = spot;
    delete slider.dataset.touched;
  }
  if (!slider.dataset.touched) slider.value = defaultRaiseTo(raise);
  slider.oninput = () => { slider.dataset.touched = "1"; refreshSize(); };
  $$(".chip").forEach(c => c.onclick = () => {
    const frac = parseFloat(c.dataset.frac);
    const want = frac >= 99 ? sizeRange.max
      : (state.pot || 0) * frac + (currentCall() || 0);
    slider.value = clampSize(want);
    slider.dataset.touched = "1";
    refreshSize();
  });
  refreshSize();
}

function currentCall() {
  const c = (state.legal || []).find(a => a.action === "call");
  return c ? c.amount : 0;
}

function clampSize(chips) {
  return Math.max(sizeRange.min, Math.min(sizeRange.max, Math.round(chips)));
}

function currentSize() {
  return clampSize(parseFloat($("#size").value) || sizeRange.min);
}

function refreshSize() {
  const v = currentSize();
  $("#size-label").textContent = money(v);
  const amt = $("#raise-amt");
  if (amt) amt.textContent = money(v);
}

/* -------------------------------------------------------------- the server */

async function post(url, body, preface) {
  busy = true;
  skipRest = false;
  pacedStreet = state.street || null;
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
      render();                       // the optimistic chips were wrong; undo them
      return null;
    }
    if (preface && data.state && !data.state.complete) {
      state = preface(data.state);
      pacedStreet = state.street;
      shown.clear();
      render();
    }
    if (data.events) await playEvents(data.events, data.state);
    if (data.state) state = data.state;
    render();
    // Next hand mid-rush: do not open the drawer just to close it again.
    if (data.review && data.review.length && !dealPending) {
      showReview(data.review, data.adaptation);
    }
    return data;
  } catch (e) {
    toast("Lost the connection to the table.");
    return null;
  } finally {
    busy = false;
    rushing = false;
    drawActions();
    if (dealPending) {
      dealPending = false;
      skipRest = false;
      deal();
    }
  }
}

/** Play the opponents out one at a time. The authoritative state is applied
 *  afterwards; these bubbles are only the pacing. */
async function playEvents(events, fresh) {
  const hero = (state.seats || []).find(s => s.you);
  rushing = !!(hero && hero.folded);
  if (rushing) drawActions();
  for (const e of events) {
    if (e.kind === "hand_over") continue;
    if (e.street && pacedStreet && e.street !== pacedStreet) {
      // The street turned under them: chips to the pot, and deal the cards
      // they are about to act on. The answer already carries the whole board.
      sweep();
      state.street = e.street;
      state.board = (fresh && fresh.board || []).slice(0, BOARD_BY_STREET[e.street] || 0);
      drawMiddle();
    }
    if (e.street) pacedStreet = e.street;
    state.to_act = e.seat;              // the gold ring is their think time
    drawSeats();
    await sleep(pace(e));
    applyChips(e.seat, e.action, e.amount);
    says.set(e.seat, phrase(e.action, e.amount));
    state.to_act = null;
    drawSeats();
    drawMiddle();
  }
  await sleep(rushing || skipRest ? 60 : 220 * speed);
  rushing = false;
}

/** How long to leave one bot's action on the felt. The rush is a cap, never a
 *  floor. */
function pace(e) {
  const full = Math.max(60, (e.delay || 0.6) * 1000 * speed);
  if (skipRest) return 0;
  return rushing ? Math.min(RUSH_MS, full) : full;
}

async function deal() {
  says.clear();
  shown.clear();
  shownCards.clear();
  $("#review-drawer").classList.remove("open");
  await post("/api/hand", {}, dealt);
}

async function act(a) {
  const i = (state.seats || []).findIndex(s => s.you);
  if (i >= 0) {
    const amount = a.action === "call" ? currentCall() : (a.to || 0);
    applyChips(i, a.action, amount);
    says.set(i, phrase(a.action, amount));
    state.to_act = null;
    drawSeats();
    drawMiddle();
  }
  await post("/api/act", a);
}

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

/** One decision: a row you can scan, a body you can open. */
function markEl(m) {
  const el = document.createElement("details");
  el.className = "mark";
  const did = m.action + (m.amount ? " " + money(m.amount) : "");
  el.innerHTML = `
    <summary>
      <span class="st">${escapeHtml(m.street)}${m.position ? " · " + escapeHtml(m.position) : ""}</span>
      <span class="did">You ${escapeHtml(did)}</span>
      ${m.loss_bb ? `<span class="cost">−${m.loss_bb}bb</span>` : ""}
      <span class="tag ${m.verdict}">${m.verdict}</span>
    </summary>
    <div class="headline">${escapeHtml(m.headline)}</div>`;
  (m.lines || []).forEach(l => {
    const d = document.createElement("div");
    d.className = "line";
    d.innerHTML = `
      <div class="lab">${escapeHtml(l.label)}
        <span class="src ${l.confidence}" title="${escapeHtml(l.confidence_text)}">${l.confidence}</span></div>
      <div class="txt">${escapeHtml(l.text)}</div>
      ${chartHtml(l.chart)}
      ${l.note ? `<details class="note"><summary>why</summary>${escapeHtml(l.note)}</details>` : ""}`;
    el.appendChild(d);
  });
  return el;
}

/** The picture beside a line. The line's own text always says the same thing. */
function chartHtml(c) {
  if (!c) return "";
  if (c.kind === "sizes") return sizesHtml(c);
  if (c.kind === "buckets") return bucketsHtml(c);
  return "";
}

function sizesHtml(c) {
  const rows = c.rows || [];
  if (!rows.length) return "";
  const evs = rows.map(r => r.ev_bb);
  const top = Math.max(...evs), bottom = Math.min(0, ...evs);
  const span = (top - bottom) || 1;
  const best = evs.indexOf(top);
  const zero = (0 - bottom) / span * 100;
  const body = rows.map((r, i) => {
    const lo = Math.min(r.ev_bb, 0), hi = Math.max(r.ev_bb, 0);
    const left = (lo - bottom) / span * 100;
    const width = Math.max(0.8, (hi - lo) / span * 100);
    const cls = [i === best ? "best" : "", r.yours ? "yours" : ""].join(" ");
    return `<tr class="${cls}">
      <th>${r.check ? "check" : Math.round(r.fraction * 100) + "% pot"
            + (r.all_in ? " (all in)" : "")}</th>
      <td class="n">${r.check ? "" : r.bb.toFixed(1) + "bb"}</td>
      <td class="n">${r.check ? "" : Math.round(r.fold_pct) + "%"}</td>
      <td class="n">${r.check || r.equity_called == null ? "" : Math.round(r.equity_called) + "%"}</td>
      <td class="bar"><i style="left:${left}%;width:${width}%"></i></td>
      <td class="n ev">${r.ev_bb >= 0 ? "+" : ""}${r.ev_bb.toFixed(2)}</td>
    </tr>`;
  }).join("");
  return `<table class="curve" style="--zero:${zero}%">
    <thead><tr><th></th><th class="n">size</th><th class="n">folds</th>
      <th class="n">eq&nbsp;if&nbsp;called</th><th></th><th class="n">EV&nbsp;bb</th></tr></thead>
    <tbody>${body}</tbody></table>`;
}

function bucketsHtml(c) {
  const rows = c.rows || [], labels = c.labels || [];
  const total = rows.reduce((a, r) => a + r.combos, 0) || 1;
  return `<div class="buckets">` + rows.map((r, i) => `
    <div class="bk b${i}" style="flex:${Math.max(r.combos, total * 0.02)} 1 96px">
      <b>${r.combos}</b>
      <span>${Math.round(r.equity)}%</span>
      <em>${escapeHtml(labels[i] || "")}</em>
    </div>`).join("") + `</div>`;
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
/** Every shortcut is a button: the key finds it by `data-key` and clicks it, so
 *  nothing can fire an action the table is not currently offering. */
function press(sel) {
  const b = $(sel);
  if (b && !b.disabled) { b.click(); return true; }
  return false;
}

/** Arrow keys move the bet by a quarter pot, not by a slider percent. */
function nudgeSize(by) {
  const slider = $("#size");
  if (!slider || $("#sizer-row").hidden) return;
  const stepChips = Math.max(state.bb || 25, Math.round((state.pot || 0) * 0.25));
  slider.value = clampSize(currentSize() + by * stepChips);
  slider.dataset.touched = "1";
  refreshSize();
}

document.addEventListener("keydown", e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === "Escape") { $$(".drawer").forEach(d => d.classList.remove("open")); return; }

  const tag = (e.target && e.target.tagName) || "";
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(tag)) return;
  if (e.key === " " && tag === "BUTTON") return;      // the browser is clicking it

  const key = e.key.toLowerCase();
  if (key === "r") {
    e.preventDefault();
    $("#review-drawer").classList.toggle("open");
    return;
  }
  if ($("#settings-drawer").classList.contains("open")) return;   // it has the keyboard
  if (busy) return;

  if (key === " " || key === "n") { if (press("#actions button[data-key='n']")) e.preventDefault(); return; }
  if ("fckb".includes(key) && key.length === 1) {
    // C calls, or checks when there is nothing to call - the muscle memory is
    // "put in what you owe", and what you owe is often nothing.
    if (press(`#actions button[data-key='${key}']`)) return;
    if (key === "c") press("#actions button[data-key='k']");
    return;
  }
  if (["1", "2", "3", "4", "a"].includes(key)) { press(`.chip[data-key='${key}']`); return; }
  if (e.key === "ArrowUp") { e.preventDefault(); nudgeSize(1); }
  if (e.key === "ArrowDown") { e.preventDefault(); nudgeSize(-1); }
});

speed = (state.prefs && state.prefs.bot_speed) ?? 1;
render();
