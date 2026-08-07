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
  saveTimer: null,
  resetArmed: false,
};

// Which slots are locked, from the gates the server sent. `slot|value` because a
// gate is a value inside a slot, not a slot: `pearl` is one of four finishes and
// the other three are always yours.
const LOCKED = new Map();
for (const g of G.gates || []) {
  if (!g.got) LOCKED.set(g.slot + '|' + g.value, g.text);
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

const TITLE = {
  none: 'None', stock: 'Stock', matte: 'Matte', gloss: 'Gloss',
  metallic: 'Metallic', pearl: 'Pearl', centre: 'Centre', twin: 'Twin',
  band: 'Band', hoop: 'Hoop', halves: 'Halves', fade: 'Fade',
  pinstripe: 'Pinstripe', spoke5: '5-spoke', spoke6: '6-spoke', mesh: 'Mesh',
  dish: 'Dish', forged: 'Split 5', laurel: 'Laurel',
};
const label = (v) => TITLE[v] || v;

/** A row of chips for one enumerated slot. Locked ones are shown, with the cost. */
function chips(slot, values, current) {
  return values.map((v) => {
    const lock = LOCKED.get(slot + '|' + v);
    const on = current === v;
    return `<button class="gopt${on ? ' on' : ''}${lock ? ' locked' : ''}"
             data-slot="${esc(slot)}" data-value="${esc(v)}"
             ${lock ? `disabled title="${esc(lock)}"` : ''}>${esc(label(v))}${
      lock ? `<span class="glock">${esc(lock)}</span>` : ''}</button>`;
  }).join('');
}

/**
 * A colour slot, as swatches.
 *
 * `auto` is what the slot does when nobody has said - the trim follows the body,
 * the stripe follows the trim, the glass is the standard tint - and it is a
 * chip rather than an absence because "follows the body" is a choice you might
 * want back. It writes `null`, which is exactly what the server already means by
 * a missing key.
 *
 * Then the same eighteen the body offers, as a shortcut rather than a rule -
 * `validate` accepts any hex in these slots - and last a tile that opens the
 * browser's own picker for anything else. The tile is a conic sweep because at
 * 26px that reads as "any colour" where a plus sign reads as "add another one",
 * and it shows the colour once there is one, so it answers what your custom
 * choice currently is.
 */
function colorSlot(slot, current, autoWord) {
  const custom = current && G.palette.indexOf(current) < 0;
  const sw = G.palette.map((c) => `<button class="gsw${current === c ? ' on' : ''}"
      data-slot="${esc(slot)}" data-value="${esc(c)}"
      style="background:${esc(c)}" title="${esc(c)}"></button>`).join('');
  return `<span class="gslot-label">${esc(autoWord)}</span>
    <button class="gopt${current ? '' : ' on'}" data-slot="${esc(slot)}"
            data-value="">Auto</button>
    <span class="gcolors">${sw}<button
      class="gsw gcustom${custom ? ' has' : ''}" data-pick="${esc(slot)}"
      title="Any other colour"${custom ? ` style="--pick:${esc(current)}"` : ''}
      ><input type="color" data-slot="${esc(slot)}"
              value="${esc(current || '#888888')}"/></button></span>`;
}

const TABS = [
  ['body', 'Body', (L) => `<span class="gcolors">${G.palette.map((c) =>
    `<button class="gsw${L.body === c ? ' on' : ''}" data-slot="body"
       data-value="${esc(c)}" style="background:${esc(c)}"
       title="${esc(c)}"></button>`).join('')}</span>`],
  ['finish', 'Finish', (L) => chips('finish', G.finishes, L.finish)],
  ['trim', 'Trim', (L) =>
    `<button class="gopt${L.two_tone ? ' on' : ''}" data-toggle="two_tone"
      >Two-tone roof</button><span class="gsep"></span>` +
    colorSlot('trim', L.trim, 'Trim')],
  ['livery', 'Livery', (L) => chips('livery', G.liveries, L.livery) +
    (L.livery && L.livery !== 'none'
      ? `<span class="gsep"></span>` + colorSlot('stripe', L.stripe, 'Stripe')
      : '')],
  ['rim_style', 'Wheels', (L) => chips('rim_style', G.rim_styles, L.rim_style) +
    (L.rim_style && L.rim_style !== 'stock'
      ? `<span class="gsep"></span>` + colorSlot('rim', L.rim, 'Rim')
      : '')],
  ['glass', 'Glass', (L) => colorSlot('glass', L.glass, 'Glass')],
  ['badge', 'Badge', (L) => chips('badge', G.badges, L.badge)],
];

/** Whether a tab holds anything this account has not earned yet. */
function tabLocked(slot) {
  return (G.gates || []).some((g) => !g.got && g.slot === slot);
}

/** One line: how much of the locked stuff is yours, and the nearest one that is not. */
function earnLine() {
  const gates = G.gates || [];
  if (!gates.length) return '';
  const left = gates.filter((g) => !g.got);
  if (!left.length) {
    return `<span class="gearn done">Everything unlocked</span>`;
  }
  // The nearest one is the one you are furthest along, so it is the one worth
  // naming - a list of four would be a list, and this is a line.
  const near = left.slice().sort((a, b) =>
    (b.need ? b.have / b.need : 0) - (a.need ? a.have / a.need : 0))[0];
  // A colon rather than "needs", and the gate's text left exactly as the server
  // wrote it. Two of the four are instructions ("Finish every track", "Set a
  // track record") and two are noun phrases ("A gold on any 3 tracks"), so
  // anything that reads them into a sentence gets half of them wrong - "Laurel
  // needs set a track record". A colon takes either.
  const prog = near.need > 1 ? ` (${near.have}/${near.need})` : '';
  return `<span class="gearn">${gates.length - left.length} of ${gates.length}
    unlocked · <b>${esc(label(near.value))}</b>:
    ${esc(near.text || '')}${esc(prog)}</span>`;
}

function render() {
  const L = S.livery;
  const tab = TABS.find((t) => t[0] === S.tab) || TABS[0];

  $('gtabs').innerHTML = TABS.map(([slot, name]) =>
    `<button class="gtab${S.tab === slot ? ' on' : ''}" data-tab="${esc(slot)}"
      >${esc(name)}${tabLocked(slot) ? '<i class="glockdot"></i>' : ''}</button>`
  ).join('');
  $('gopts').innerHTML = tab[2](L);
  $('gearn').innerHTML = earnLine();
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
    b.onclick = () => set(b.dataset.slot, b.dataset.value || null);
  }
  for (const b of $('gopts').querySelectorAll('button[data-toggle]')) {
    b.onclick = () => set(b.dataset.toggle, !S.livery[b.dataset.toggle]);
  }
  // The tile is the button; the input inside it is the browser's picker and is
  // never seen. Clicking the tile opens it, and `input` fires continuously as
  // the picker is dragged, which is what `save`'s debounce is for.
  for (const b of $('gopts').querySelectorAll('button[data-pick]')) {
    const inp = b.querySelector('input[type=color]');
    b.onclick = (e) => { if (e.target !== inp) inp.click(); };
    inp.oninput = () => set(inp.dataset.slot, inp.value);
  }
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
  requestAnimationFrame(frame);
}

boot();
