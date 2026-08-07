// The garage: one car on a turntable, filling the screen, and the things you
// can change about it floating on top of it.
//
// It reuses the game's own `Renderer` and `CarView` rather than drawing a second
// car, which is the whole reason this file is short. `Renderer` needs no track:
// `trackGroup` and `sky` start null and `render(dt)` is only the particles and a
// draw, so a studio costs one canvas and nothing else - and the page opens
// instantly rather than paying `buildTrack`.
//
// Two things are deliberately not here. There is no `OrbitControls`: it is a
// three.js addon and is not vendored, and what this needs is forty lines of drag
// rather than a dependency. And there is no second copy of what a car may wear -
// every chip and every swatch on screen is built from the payload the server
// rendered into the page, so the options here cannot drift from the ones
// `garage.py` enforces, and neither can the sentence on a locked one.

import * as THREE from './vendor/three.module.js';
import { MeshBuf } from './trackmesh.js';
import { Renderer, CarView } from './render.js';

const G = window.DRIVE_GARAGE;
const $ = (id) => document.getElementById(id);
const QS = new URLSearchParams(location.search);

// Where the camera can be sent, and the numbers behind them. Yaw is measured
// with the camera at +Z, which is behind the car, so the nose (-Z) is at pi.
// The pitches differ on purpose: a front or side elevation wants to be nearly
// level to read as one, and a three-quarter wants to look down on the car.
const VIEWS = [
  ['Front', 'front', Math.PI, 0.14],
  ['¾', '34', 2.45, 0.28],
  ['Side', 'side', Math.PI / 2, 0.14],
  ['Rear', 'rear', 0.15, 0.26],
];

const S = {
  livery: Object.assign({}, G.livery),
  renderer: null, view: null,
  // Framing. The distance itself is not stored, because it is not a constant:
  // it comes from the shape of the window (see `fitDist`) and this is what the
  // scroll wheel multiplies it by.
  yaw: 2.45, pitch: 0.28, zoom: 1,
  // Where a preset is easing us to, or null when the camera is where it was put.
  target: null,
  spin: true,              // idle rotation, until you take hold of it
  wheel: 0,
  tab: 'body',
  // What the line under the bar is currently saying, or null. Set by pressing a
  // locked chip; see `noteLine`.
  said: null,
  saveTimer: null,
  resetArmed: false,
  // The open colour picker: `{slot, tile, h, s, v}`, or null. Hue/sat/val and not
  // a hex, because the panel's two controls are those axes - round-tripping
  // through a hex on every pointermove would make a drag along the top of the
  // square drift its hue, since a fully desaturated colour has no hue to read
  // back.
  pick: null,
};

// Which slots are locked and which were earned, from the gates the server sent.
// Keyed `slot|value` because a gate is a value inside a slot and not a slot:
// `shield` is one of nine badges and the other eight are always yours.
//
// Two maps rather than one, because the two sentences are different sentences. A
// locked chip wants the thing still to do ("Win a multiplayer race"); a chip you
// are *wearing* wants what it was for ("winning a multiplayer race"), and bending
// one into the other gets half of them wrong - see `GATES` in `garage.py`.
const LOCKED = new Map();
const EARNED_FOR = new Map();
for (const g of G.gates || []) {
  if (!g.got) LOCKED.set(g.slot + '|' + g.value, g.text);
  else if (g.done) EARNED_FOR.set(g.slot + '|' + g.value, g.done);
}

// ---------------------------------------------------------------------------
// The car
// ---------------------------------------------------------------------------

function rebuild() {
  if (S.view) S.view.dispose();
  // Rebuilt wholesale on every change rather than poked material by material.
  // It is one car on an empty scene, so there is nothing to save by being clever
  // - and a rebuild cannot leave a stale material behind, which the clever
  // version would do the first time a slot was added and not wired up.
  S.view = new CarView(S.renderer.scene, S.livery);
  S.view.setLabel(null);
}

/**
 * How far back the camera has to be, for the window it is actually in.
 *
 * `Renderer`'s camera is 66 degrees **vertical**, so the frame is `1.3 * dist`
 * units tall and `1.3 * dist * aspect` wide - which means a fixed distance
 * frames a car by its height, and a car is a long low thing framed by its
 * length. On a wide stage that never bites. In portrait on a phone the frame is
 * narrower than the car is long, and a distance tuned on a laptop put the nose
 * and the tail off both sides of the screen.
 *
 * So the wide value is the tuned one and everything narrower backs off from it.
 * Not proportionally: a portrait frame has room going spare above and below and
 * none at the sides, so the car is allowed to fill more of the width there than
 * it does on a desktop - the exponent is what buys that, and the clamp stops a
 * very tall thin window pushing the car to a dot.
 */
function fitDist() {
  const c = S.renderer.renderer.domElement;
  const a = (c.clientWidth || 1) / Math.max(1, c.clientHeight);
  const WIDE = 4.8, REF = 1.5;
  return WIDE * (a >= REF ? 1 : Math.min(2.0, Math.pow(REF / a, 0.78)));
}

/** The shortest way round from one angle to another, in (-pi, pi]. */
function shortest(a, b) {
  let d = (b - a) % (Math.PI * 2);
  if (d > Math.PI) d -= Math.PI * 2;
  if (d < -Math.PI) d += Math.PI * 2;
  return d;
}

function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.05, (now - (frame.last || now)) / 1000);
  frame.last = now;

  if (S.target) {
    // Eased rather than cut, because a preset is a request to *look* at the car
    // from over there and the turn is what tells you which way it went round.
    const k = 1 - Math.pow(0.001, dt);
    const dy = shortest(S.yaw, S.target.yaw);
    S.yaw += dy * k;
    S.pitch += (S.target.pitch - S.pitch) * k;
    if (Math.abs(dy) < 0.002 && Math.abs(S.target.pitch - S.pitch) < 0.002) {
      S.yaw = S.target.yaw; S.pitch = S.target.pitch; S.target = null;
      // Which view you are on is only true once the camera has arrived, and
      // arriving is not something anybody clicked - so this is the one place
      // the controls are redrawn by the frame loop rather than by an event.
      // Without it the highlight was computed at the moment of the press, when
      // the answer is still "none of them", and no view button ever lit up.
      render();
    }
  } else if (S.spin) {
    S.yaw += dt * 0.32;
  }
  // The wheels turn with the turntable, because a car rotating on stationary
  // wheels reads as a model and a car whose wheels are going reads as a car.
  S.wheel += dt * 0.32 * 4.0;

  const cy = Math.cos(S.pitch), sy = Math.sin(S.pitch);
  const cam = S.renderer.camera;
  // Recomputed every frame rather than on a resize event, because it is one
  // divide and it then cannot be stale - rotating a phone, opening the dev
  // tools and the address bar sliding away are all resizes, and only one of
  // them fires the event reliably.
  const dist = fitDist() * S.zoom;
  cam.position.set(Math.sin(S.yaw) * dist * cy, 0.80 + sy * dist,
                   Math.cos(S.yaw) * dist * cy);
  // Aimed a little above the car's middle, which puts the car itself a little
  // below the middle of the frame - and the top of the frame is where the two
  // control bars are.
  cam.lookAt(0, 0.62, 0);
  cam.updateProjectionMatrix();

  // The car sits at the origin with the floor at y=0, so its own contact shadow
  // does the grounding - the same shadow it has on the road, which is why there
  // is no separate studio floor shadow to get subtly wrong.
  S.view.update(new THREE.Vector3(0, 0, 0), new THREE.Quaternion(),
                { spin: S.wheel, groundY: 0, groundN: new THREE.Vector3(0, 1, 0) });
  S.renderer.render(dt);
}

function setView(id) {
  const v = VIEWS.find((x) => x[1] === id);
  if (!v) return;
  S.target = { yaw: v[2], pitch: v[3] };
  S.spin = false;
  render();
}

// ---------------------------------------------------------------------------
// Spinning it
// ---------------------------------------------------------------------------

function bindDrag(el) {
  let down = false, lx = 0, ly = 0;
  const start = (x, y) => {
    down = true; lx = x; ly = y; S.spin = false; S.target = null; render();
  };
  const move = (x, y) => {
    if (!down) return;
    S.yaw -= (x - lx) * 0.01;
    // Clamped so you cannot end up under the floor or looking at the roof from
    // directly above, both of which are views of nothing.
    S.pitch = Math.max(-0.05, Math.min(1.1, S.pitch + (y - ly) * 0.006));
    lx = x; ly = y;
  };
  const end = () => { down = false; };

  el.addEventListener('pointerdown', (e) => { el.setPointerCapture(e.pointerId);
                                              start(e.clientX, e.clientY); });
  el.addEventListener('pointermove', (e) => move(e.clientX, e.clientY));
  el.addEventListener('pointerup', end);
  el.addEventListener('pointercancel', end);
  el.addEventListener('wheel', (e) => {
    e.preventDefault();
    // A multiplier on whatever the window's own framing is, so a zoom survives
    // a resize instead of becoming a distance that means something else.
    S.zoom = Math.max(0.55, Math.min(2.4, S.zoom * (e.deltaY > 0 ? 1.08 : 0.926)));
  }, { passive: false });
}

// ---------------------------------------------------------------------------
// Saving
// ---------------------------------------------------------------------------

function save() {
  clearTimeout(S.saveTimer);
  // Debounced, because dragging a colour picker fires continuously and every
  // one of those is a write. A second of quiet is the end of a decision.
  S.saveTimer = setTimeout(async () => {
    try {
      const r = await fetch('/api/garage', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(S.livery),
      });
      const d = await r.json();
      if (d && d.ok) {
        // The server's answer wins: it has applied the gates, so if something in
        // here was not earned this is where it goes back. Silently, because the
        // chip that offered it already says why it is locked.
        S.livery = Object.assign({}, d.livery);
        rebuild();
        render();
        flash();
      }
    } catch (e) { /* offline: the car on screen is still right, so say nothing */ }
  }, 700);
}

function flash() {
  const el = $('gsaved');
  el.classList.add('show');
  clearTimeout(flash._t);
  flash._t = setTimeout(() => el.classList.remove('show'), 1100);
}

function set(slot, value) {
  S.livery[slot] = value;
  rebuild();
  // The controls are redrawn from `S.livery` on every change, not just on the
  // ones that happen to know they changed something else. One direction:
  // livery -> screen, always.
  render();
  save();
}

// ---------------------------------------------------------------------------
// The controls
// ---------------------------------------------------------------------------

const esc = (s) => (s + '').replace(/[&<>"]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// A word for every value the garage offers, and for nothing else. `metallic` and
// `pearl` were here after the finishes they named were retired - harmless, since
// `validate` turns a stored one into matte long before the garage sees it, and a
// lie about what is in the cabinet. `test_rules_js.py` checks both directions.
const TITLE = {
  none: 'None', stock: 'Stock', matte: 'Matte', gloss: 'Gloss',
  centre: 'Centre', twin: 'Twin',
  band: 'Band', hoop: 'Hoop', halves: 'Halves', fade: 'Fade',
  pinstripe: 'Pinstripe', spoke5: '5-spoke', spoke6: '6-spoke', mesh: 'Mesh',
  dish: 'Dish', forged: 'Split 5',
  // The badges. Named for the shape rather than for what earns it, because the
  // gate's own sentence is already on the chip when it is locked and is the wrong
  // thing to read once it is not - "Win a race" on a car you have already won a
  // race in tells you nothing about what is on the bonnet.
  laurel: 'Laurel', checkers: 'Checkers', chevrons: 'Chevrons', crown: 'Crown',
  podium: 'Podium', sunburst: 'Sunburst', ribbon: 'Ribbon', shield: 'Shield',
};
const label = (v) => TITLE[v] || v;

/**
 * A row of chips for one enumerated slot. A locked one is greyed and still there.
 *
 * **The cost used to be printed inside the chip**, which made one chip in a row
 * three times the height of its neighbours and turned a row of names into a row of
 * paragraphs. The chip is just greyed now, and it is *not* `disabled`: pressing it
 * is how you find out what it wants, and a disabled button cannot be pressed. It
 * says so in the line under the bar, which is the one place in this UI that exists
 * to answer a question you just asked.
 */
function chips(slot, values, current) {
  return values.map((v) => {
    const lock = LOCKED.get(slot + '|' + v);
    const on = current === v;
    return `<button class="gopt${on ? ' on' : ''}${lock ? ' locked' : ''}"
             data-slot="${esc(slot)}" data-value="${esc(v)}"
             ${lock ? `data-locked="${esc(lock)}" ` : ''}title="${esc(label(v))}"
             >${esc(label(v))}</button>`;
  }).join('');
}

/**
 * A colour slot, as swatches.
 *
 * The first chip is what the slot does when nobody has said - the trim follows
 * the body, the stripe follows the trim, the glass is the standard tint - and it
 * is a chip rather than an absence because "follows the body" is a choice you
 * might want back. It writes `null`, which is exactly what the server already
 * means by a missing key. `autoLabel` is there because on a stock wheel that
 * choice is not "the standard silver" but *no lip at all*, and calling it Auto
 * would be describing a colour that is not going to appear.
 *
 * **No slot label.** There used to be a RIM / STRIPE / TRIM caption in front of
 * each row, which on every tab but one said the name of the tab you were already
 * on. `label` is still taken, because the tabs that show *two* colour rows need to
 * say which is which, and those are the only ones that get it.
 *
 * Then **this slot's own swatches**, as a shortcut rather than a rule -
 * `validate` accepts any hex in these slots - and last a tile that opens the
 * picker for anything else. The tile is a conic sweep because at 26px that reads
 * as "any colour" where a plus sign reads as "add another one", and it shows the
 * colour once there is one, so it answers what your custom choice currently is.
 *
 * Every slot used to offer the eighteen *body* colours, which is wrong for all
 * four of them and absurd for glass. The body's list is held to rules about being
 * told apart from other cars and from the world, and a stripe is not that thing:
 * there was no white anywhere in the garage, and the glass tint could be pink.
 * `G.palette` is the fallback rather than the answer, so a slot nobody has
 * written a list for still works.
 */
function colorSlot(slot, current, label = '', autoLabel = 'Auto') {
  const list = (G.swatches && G.swatches[slot]) || G.palette;
  const custom = current && list.indexOf(current) < 0;
  const sw = list.map((c) => `<button class="gsw${current === c ? ' on' : ''}"
      data-slot="${esc(slot)}" data-value="${esc(c)}"
      style="background:${esc(c)}" title="${esc(c)}"></button>`).join('');
  return `${label ? `<span class="gslot-label">${esc(label)}</span>` : ''}
    <button class="gopt${current ? '' : ' on'}" data-slot="${esc(slot)}"
            data-value="">${esc(autoLabel)}</button>
    <span class="gcolors">${sw}<button
      class="gsw gcustom${custom ? ' has' : ''}" data-pick="${esc(slot)}"
      title="Any other colour"${custom ? ` style="--pick:${esc(current)}"` : ''}
      ></button></span>`;
}

const TABS = [
  // The body has no custom tile - it is the one slot that is a curated list rather
  // than any hex - so a colour that is *worn* but no longer *offered* would have
  // nothing lit and no way back to it. It gets appended, for whoever chose one of
  // the eight the palette dropped (`garage.RETIRED`); it disappears the moment they
  // pick something else, and it is nobody else's extra swatch.
  ['body', 'Body', (L) => {
    const list = G.palette.slice();
    if (L.body && list.indexOf(L.body) < 0) list.push(L.body);
    return `<span class="gcolors">${list.map((c) =>
      `<button class="gsw${L.body === c ? ' on' : ''}" data-slot="body"
         data-value="${esc(c)}" style="background:${esc(c)}"
         title="${esc(c)}"></button>`).join('')}</span>`;
  }],
  // **Two rows, because they were two things sharing one colour.** This was the
  // Trim tab: one colour painted the spoiler *and*, if a "Two-tone roof" toggle was
  // on, the roof. So a two-tone was always spoiler-coloured, and a white roof on a
  // red car with a black wing could not be asked for at all. Two colours say that
  // and everything else, and the toggle has nothing left to do.
  //
  // The only tab with two colour rows, and therefore the only one whose rows are
  // labelled - everywhere else the label repeated the name of the tab it was on.
  ['trim', 'Detail', (L) =>
    colorSlot('trim', L.trim, 'Spoiler') +
    `<span class="gsep"></span>` +
    colorSlot('roof', L.roof, 'Roof', 'Body')],
  ['livery', 'Livery', (L) => chips('livery', G.liveries, L.livery) +
    (L.livery && L.livery !== 'none'
      ? `<span class="gsep"></span>` + colorSlot('stripe', L.stripe)
      : '')],
  // The Rim colour is offered for **every** style including stock, which is the
  // one that used to hide it. Stock has no rim face until you paint one, so here
  // Auto genuinely means "no lip" rather than "the standard silver" - which is
  // the honest reading of a slot whose absence is a real choice.
  ['rim_style', 'Wheels', (L) => chips('rim_style', G.rim_styles, L.rim_style) +
    `<span class="gsep"></span>` +
    colorSlot('rim', L.rim, '', L.rim_style === 'stock' ? 'None' : 'Auto')],
  ['glass', 'Glass', (L) => colorSlot('glass', L.glass)],
  // **Second to last, before Badge.** It was second in the list, next to Body,
  // which is where you would put it if a finish were a kind of paint. It is a
  // property *of* the paint, so it belongs at the end with the other things you
  // add once the car is the colour you want.
  ['finish', 'Finish', (L) => chips('finish', G.finishes, L.finish)],
  // A colour row only once a badge is on, for the livery's reason: a colour for a
  // thing that is not being drawn is a control with nothing on the other end of it.
  // `Auto` here means the badge's own colour - green for the three about records,
  // gold for the sunburst, bronze for the podium - so the meaning survives for
  // anybody who does not go looking.
  ['badge', 'Badge', (L) => chips('badge', G.badges, L.badge) +
    (L.badge && L.badge !== 'none'
      ? `<span class="gsep"></span>` + colorSlot('badge_color', L.badge_color)
      : '')],
];

/** Whether a tab holds anything this account has not earned yet. */
function tabLocked(slot) {
  return (G.gates || []).some((g) => !g.got && g.slot === slot);
}

/**
 * The one line under the bar, and what it is for.
 *
 * It counted things: "3 of 10 unlocked - Chevrons: Reach Ace rating (1180/1250)".
 * Nobody asked how many they had, and the nearest-gate half was a fact about a
 * chip somewhere else on the screen. So it answers **the thing you just did**
 * instead: what the badge you are wearing was earned for, and what a locked chip
 * you pressed wants. Empty the rest of the time, which is most of the time.
 *
 * `S.said` is set by a press and survives until the next render that has nothing
 * of its own to say - so it is a reply rather than a status, and it cannot sit
 * there being true about something you have moved on from.
 */
function noteLine() {
  if (S.said) return `<span class="gearn">${S.said}</span>`;
  const L = S.livery;
  // A worn badge says what earned it. Only the badge, and only on its own tab:
  // this is a line about what you are looking at, and it would be a caption on
  // nothing anywhere else.
  if (S.tab === 'badge' && L.badge && L.badge !== 'none') {
    const done = EARNED_FOR.get('badge|' + L.badge);
    if (done) {
      // One line with no break in it: HTML would collapse the newline, but the
      // text is read as text by `test_garage_js`-style checks and by a screen
      // reader, and "Laurel:\n        unlocked" is not a sentence.
      const w = `<b>${esc(label(L.badge))}</b>: unlocked for ${esc(done)}`;
      return `<span class="gearn">${w}</span>`;
    }
  }
  return '';
}

/**
 * What a locked chip says when you press it: the requirement, and how far along.
 *
 * The requirement used to be printed *inside* the chip, which made one chip in a
 * row three times the height of the others and turned a row of names into a row of
 * paragraphs. Pressing is the natural way to ask, and the answer goes where every
 * other answer in this UI goes.
 */
function sayLocked(slot, value) {
  const want = LOCKED.get(slot + '|' + value);
  if (!want) return;
  const g = (G.gates || []).find((x) => x.slot === slot && x.value === value);
  const prog = g && g.need > 1 ? ` (${g.have}/${g.need})` : '';
  S.said = `<b>${esc(label(value))}</b>: ${esc(want)}${esc(prog)}`;
  render();
  // Long enough to read twice, and it goes on its own - a requirement is an answer
  // to a press and not a state the page is in.
  clearTimeout(sayLocked._t);
  sayLocked._t = setTimeout(() => { S.said = null; render(); }, 4000);
}

function render() {
  const L = S.livery;
  const tab = TABS.find((t) => t[0] === S.tab) || TABS[0];

  $('gtabs').innerHTML = TABS.map(([slot, name]) =>
    `<button class="gtab${S.tab === slot ? ' on' : ''}" data-tab="${esc(slot)}"
      >${esc(name)}${tabLocked(slot) ? '<i class="glockdot"></i>' : ''}</button>`
  ).join('');
  $('gopts').innerHTML = tab[2](L);
  $('gearn').innerHTML = noteLine();
  $('gviews').innerHTML = VIEWS.map(([name, id, yaw, pitch]) =>
    `<button class="gview${!S.target && Math.abs(shortest(S.yaw, yaw)) < 0.01
                            ? ' on' : ''}" data-view="${esc(id)}"
      >${esc(name)}</button>`).join('');

  for (const b of $('gtabs').querySelectorAll('button[data-tab]')) {
    b.onclick = () => { S.tab = b.dataset.tab; render(); };
  }
  for (const b of $('gviews').querySelectorAll('button[data-view]')) {
    b.onclick = () => setView(b.dataset.view);
  }
  for (const b of $('gopts').querySelectorAll('button[data-slot]')) {
    // A locked chip is a live button on purpose: pressing it is how you find out
    // what it wants, and `disabled` would make that impossible.
    b.onclick = () => {
      if (b.dataset.locked !== undefined) {
        sayLocked(b.dataset.slot, b.dataset.value);
        return;
      }
      S.said = null;
      set(b.dataset.slot, b.dataset.value || null);
    };
  }
  for (const b of $('gopts').querySelectorAll('button[data-pick]')) {
    b.onclick = () => openPick(b.dataset.pick, b);
  }
  // The panel outlives this redraw, so if it is open on a slot the tab still
  // shows, it re-anchors to the tile that has just been rebuilt under it.
  if (S.pick) anchorPick();
}

// ---------------------------------------------------------------------------
// The colour picker
// ---------------------------------------------------------------------------
// It used to be an `<input type="color">` hidden inside the tile, which meant the
// browser's own dialog: you had to hit a 26px target exactly to open it, it opened
// wherever the OS felt like, and on a phone it is a modal sheet over the car you
// are trying to look at. This is a panel of our own - drag anywhere in the square,
// let go outside it, click away to close - which is also the only version where
// the car keeps updating under your cursor while you choose.
//
// The maths is here rather than leaning on the browser because there is nothing to
// lean on: a `<canvas>` would need a pixel read per move, and a CSS gradient can
// *show* a hue field but cannot tell you which colour a point in it is.

/** #rrggbb -> {h: 0..360, s: 0..1, v: 0..1}. */
function hexToHsv(hex) {
  const n = parseInt((hex || '').replace('#', ''), 16);
  const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  let h = 0;
  if (d) {
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    else if (max === g) h = ((b - r) / d + 2) / 6;
    else h = ((r - g) / d + 4) / 6;
  }
  return { h: h * 360, s: max ? d / max : 0, v: max };
}

/** {h, s, v} -> #rrggbb. */
function hsvToHex(h, s, v) {
  const c = ((h % 360) + 360) % 360 / 60;
  const f = (n) => {
    const k = (n + c) % 6;
    return v * (1 - s * Math.max(0, Math.min(k, 4 - k, 1)));
  };
  const hx = (x) => Math.round(x * 255).toString(16).padStart(2, '0');
  return '#' + hx(f(5)) + hx(f(3)) + hx(f(1));
}

const clamp01 = (x) => Math.max(0, Math.min(1, x));

function openPick(slot, tile) {
  // A second click on the same tile closes it, which is what a disclosure does.
  if (S.pick && S.pick.slot === slot) return closePick();
  const start = S.livery[slot] || '#888888';
  S.pick = Object.assign({ slot, tile }, hexToHsv(start));
  $('gpickslot').textContent = TITLE[slot] || slot;
  $('gpick').hidden = false;
  anchorPick();
  drawPick();
}

function closePick() {
  S.pick = null;
  $('gpick').hidden = true;
}

/**
 * Put the panel under the tile that opened it, and **inside the stage**.
 *
 * Clamped rather than simply placed, because the tile can be at either end of a
 * two-row swatch block on a phone - and a picker whose right half is off the edge
 * of the screen is one you cannot use at all on the side it fell off.
 */
function anchorPick() {
  const p = $('gpick'), tile = S.pick && S.pick.tile;
  if (!tile || !tile.isConnected) return;
  // Re-found by slot after a redraw: the element that opened the panel has been
  // replaced by innerHTML, so the reference is stale and its rect is nonsense.
  const live = $('gopts').querySelector(`button[data-pick="${S.pick.slot}"]`);
  if (live) S.pick.tile = live;
  const t = (live || tile).getBoundingClientRect();
  const stage = document.querySelector('.gstage').getBoundingClientRect();
  const w = p.offsetWidth || 190;
  const x = clamp01((t.left + t.width / 2 - w / 2 - stage.left)
                    / Math.max(1, stage.width - w)) * (stage.width - w);
  p.style.left = Math.round(x) + 'px';
  p.style.top = Math.round(t.bottom - stage.top + 10) + 'px';
}

/** The panel's own controls, from `S.pick`. Does not touch the car. */
function drawPick() {
  const k = S.pick;
  if (!k) return;
  const hex = hsvToHex(k.h, k.s, k.v);
  $('gpicksv').style.setProperty('--hue', k.h);
  $('gpicksvdot').style.left = (k.s * 100) + '%';
  $('gpicksvdot').style.top = ((1 - k.v) * 100) + '%';
  $('gpickhuedot').style.left = ((k.h / 360) * 100) + '%';
  $('gpickchip').style.background = hex;
  $('gpickhex').textContent = hex;
}

/**
 * One drag over `el`, in its own coordinates, for as long as the finger is down.
 *
 * `setPointerCapture` is the whole reason this feels like a colour picker rather
 * than like a series of clicks: events keep coming to this element after the
 * pointer has left it, so a drag that runs off the edge of the square pins to the
 * edge and carries on instead of stopping dead. It is also one code path for a
 * mouse and a thumb.
 */
function dragArea(el, onMove) {
  const at = (e) => {
    const r = el.getBoundingClientRect();
    onMove(clamp01((e.clientX - r.left) / r.width),
           clamp01((e.clientY - r.top) / r.height));
  };
  el.addEventListener('pointerdown', (e) => {
    el.setPointerCapture(e.pointerId);
    e.preventDefault();
    at(e);
  });
  el.addEventListener('pointermove', (e) => {
    if (el.hasPointerCapture(e.pointerId)) at(e);
  });
}

function bindPick() {
  const push = () => {
    const k = S.pick;
    // `set` redraws the controls and saves; `save` is already debounced a second,
    // which is what makes it safe to call this on every pointermove.
    set(k.slot, hsvToHex(k.h, k.s, k.v));
    drawPick();
  };
  dragArea($('gpicksv'), (x, y) => {
    S.pick.s = x; S.pick.v = 1 - y; push();
  });
  dragArea($('gpickhue'), (x) => { S.pick.h = x * 360; push(); });
  $('gpickclose').onclick = () => closePick();
  // Anywhere else. `pointerdown` and not `click`, so it closes on the press
  // rather than waiting for a release that may land somewhere else entirely.
  document.addEventListener('pointerdown', (e) => {
    if (!S.pick) return;
    if ($('gpick').contains(e.target)) return;
    if (e.target.closest && e.target.closest('button[data-pick]')) return;
    closePick();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && S.pick) { e.preventDefault(); closePick(); }
  });
}

// ---------------------------------------------------------------------------
// Reset
// ---------------------------------------------------------------------------

function bindReset() {
  const btn = $('greset'), lab = $('gresetlabel');
  btn.onclick = () => {
    if (!S.resetArmed) {
      S.resetArmed = true;
      btn.classList.add('armed');
      lab.textContent = 'Sure?';
      // Disarms itself, so a press you did not mean to make does not sit there
      // waiting for the next one.
      clearTimeout(bindReset._t);
      bindReset._t = setTimeout(() => {
        S.resetArmed = false; btn.classList.remove('armed'); lab.textContent = 'Reset';
      }, 3000);
      return;
    }
    clearTimeout(bindReset._t);
    S.resetArmed = false; btn.classList.remove('armed'); lab.textContent = 'Reset';
    // The server's defaults, not a copy of them here - `body: null` resolves to
    // the hashed colour on the way back, which is the stock car.
    S.livery = Object.assign({}, G.defaults);
    rebuild(); render(); save();
  };
}

// ---------------------------------------------------------------------------
// The studio
// ---------------------------------------------------------------------------

const BACKDROP = 0x0d1016;
// Two numbers that both want to be smaller than instinct says. The pool started
// at 0x39435a fading over 26 units and it did not read as a pool at all: at a
// low camera the far half of it piles up against the horizon, so a wide fade
// becomes a pale wall behind the car with a hard line along the top. Tight and
// dim is a floor; wide and bright is a backdrop you did not mean to build.
const POOL = 0x4a5670;
const FADE = 9;

const lerpHex = (a, b, t) => {
  const ch = (s) => {
    const x = (a >> s) & 255, y = (b >> s) & 255;
    return Math.round(x + (y - x) * t) & 255;
  };
  return (ch(16) << 16) | (ch(8) << 8) | ch(0);
};

// **A vertex colour is not a hex colour**, and this floor is the one place in
// the project where the difference is visible rather than academic.
//
// three.js has colour management on (r169). `new THREE.Color(0x0d1016)` is read
// as sRGB and converted into the linear working space, and the renderer encodes
// back to sRGB on output - so a `Color` round-trips and comes out as the value
// you typed. A raw colour *attribute* is assumed to already be linear and gets
// no conversion in, only the encode out, so writing 0x0d1016 into a vertex
// colour draws it as roughly 0x404753: a floor about twice as bright as asked
// for, and, worse here, an outer ring that no longer matches `scene.background`
// and therefore a hard disc rim across the screen.
//
// `MeshBuf` is deliberately left alone: the track's palette was picked by eye
// against this exact pipeline, so "fixing" it there would restyle twelve tracks.
// It is only this floor that needs colours that mean what they say, because it
// is the only one that has to *match* a managed colour exactly.
const _lin = new THREE.Color();
const linear = (hex) => {
  _lin.setHex(hex);
  return (Math.round(_lin.r * 255) << 16) | (Math.round(_lin.g * 255) << 8)
       | Math.round(_lin.b * 255);
};

/**
 * A pool of light with no edge.
 *
 * The floor used to be a `CircleGeometry(9)` in one flat colour, which at this
 * size put its own rim in shot: the car stood on a visible disc floating in a
 * void. This is a much larger disc of concentric rings whose colour runs from a
 * lifted pool under the car out to **exactly the backdrop** at the rim, so there
 * is nothing to see an edge of - the last ring and the background are the same
 * colour.
 *
 * Unlit, so the gradient is the colours chosen rather than the colours chosen
 * times whatever the lighting rig is doing. Its actual job is still to be the
 * thing the car's own contact shadow lands on.
 */
function studioFloor() {
  const buf = new MeshBuf();
  const R = 60, RINGS = 30, SEG = 56;
  // Squared, so the rings bunch up near the car where the gradient is steepest
  // and thin out where it is nearly flat - the same number of triangles buys a
  // much smoother pool.
  const radius = (i) => R * Math.pow(i / RINGS, 2);
  // Mixed in sRGB, which is where the two endpoints were chosen, then converted
  // once at the end - so the ramp looks like the ramp and the last ring is
  // exactly the background.
  const shade = (r) =>
    linear(lerpHex(POOL, BACKDROP, Math.min(1, Math.pow(r / FADE, 0.85))));
  for (let i = 0; i < RINGS; i++) {
    const r0 = radius(i), r1 = radius(i + 1);
    const c0 = shade(r0), c1 = shade(r1);
    for (let j = 0; j < SEG; j++) {
      const a0 = (j / SEG) * Math.PI * 2, a1 = ((j + 1) / SEG) * Math.PI * 2;
      const P = (a, r) => [Math.sin(a) * r, 0, Math.cos(a) * r];
      // Anticlockwise seen from above, so the normals point up at the camera.
      buf.quadV(P(a0, r0), P(a0, r1), P(a1, r1), P(a1, r0), c0, c1, c1, c0);
    }
  }
  return buf.toMesh(new THREE.MeshBasicMaterial({ vertexColors: true }));
}

// ---------------------------------------------------------------------------

function boot() {
  const canvas = $('gcanvas');
  S.renderer = new Renderer(canvas);
  S.renderer.scene.background = new THREE.Color(BACKDROP);
  // No sky dome and no fog: both exist to sell distance, and there is none here.
  S.renderer.scene.fog = null;
  S.renderer.scene.add(studioFloor());

  // A fill from the opposite side to the sun. The track's rig is one hard key
  // plus a hemisphere, which is right outdoors where the sky does most of the
  // work and wrong in a black room: every face turned away from the key fell to
  // the same flat shadow, so a flat-shaded car read as a paper cut-out of
  // itself. Dim and cool, and only there to put an edge back on the dark side.
  const fill = new THREE.DirectionalLight(0x9fb4d8, 0.55);
  fill.position.set(-90, 45, -70);
  S.renderer.scene.add(fill);

  // `?view=front|34|side|rear` puts the camera on a fixed angle at load, the
  // same idea as the play page's `?panel=` and `?draft=`: there is no browser in
  // CI and a screenshot cannot drag, so this is the only way to photograph the
  // car from a known angle. It also makes a link to "look at the front of this"
  // a thing that exists.
  const want = QS.get('view');
  if (want) {
    const v = VIEWS.find((x) => x[1] === want);
    if (v) { S.yaw = v[2]; S.pitch = v[3]; S.spin = false; }
  }

  rebuild();
  render();
  bindDrag(canvas);
  bindReset();
  bindPick();
  requestAnimationFrame(frame);
}

boot();
