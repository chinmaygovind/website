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
  renderer: null,
  // The showroom: one car per body, the index in focus, the plinth rings, what
  // the camera is framing and where it is looking now (eased).
  cars: [], focus: 0, rings: [], discs: [], slot: 0, slotTo: 0, part: null, zoomTo: null, look: null, floor: null,
  // Framing. The distance itself is not stored, because it is not a constant:
  // it comes from the shape of the window (see `fitDist`) and this is what the
  // scroll wheel multiplies it by.
  yaw: 2.45, pitch: 0.26, zoom: 1.4,
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

// ---------------------------------------------------------------------------
// The showroom
// ---------------------------------------------------------------------------
// Every body parked in a row on its own plinth, each wearing *your* paint, the
// way the Chinese Rocket League shelves its cars. The arrows, the arrow keys or
// a click on a car rolls along the row to it; landing on one you have earned
// puts you in it, and one you have not is a translucent shell with its
// requirement under it. Dragging turns the car on its turntable rather than
// moving the camera, so the row always stays a row across the screen.

const GAP = 6.4;                 // plinth to plinth
// Laid out toward -x, which is screen-right from where the camera stands, so the
// next car is to the right and the right arrow goes to it.
//
// **The row loops.** `S.slot` is where along an endless row the camera is, and
// each car stands at whichever repeat of its own place is nearest to it - so
// past the last car is the first one again, with no rewind across the row.
const carSlot = (i) => {
  const n = MODELS.length;
  return i + n * Math.round((S.slot - i) / n);
};
const carX = (i) => -carSlot(i) * GAP;
const CAM_YAW = Math.PI;         // the camera stands square in front of the row
const MODELS = G.models && G.models.length ? G.models : ['classic'];
const modelAt = (i) => MODELS[(i + MODELS.length) % MODELS.length];
const isLocked = (m) => LOCKED.has('model|' + m);

/** Where each tab points the camera: an offset on the car (its own frame), the
 *  view angle round it, how high, and how close. Forza's trick - you are shown
 *  the part you are changing. */
const PARTS = {
  body:      { at: [0, 0.62, 0],     yaw: 2.45, pitch: 0.26, zoom: 1.4 },
  trim:      { at: [0, 0.95, 0.6],   yaw: 0.55, pitch: 0.42, zoom: 0.85 },
  livery:    { at: [0, 0.7, 0],      yaw: 2.2,  pitch: 0.62, zoom: 1.15 },
  rim_style: { at: 'wheel',          yaw: Math.PI / 2 + 0.3, pitch: 0.06, zoom: 0.42 },
  glass:     { at: [0, 0.9, -0.3],   yaw: 2.7,  pitch: 0.16, zoom: 0.72 },
  finish:    { at: [0, 0.62, 0],     yaw: 2.0,  pitch: 0.32, zoom: 1.1 },
  badge:     { at: [0, 0.6, -1.2],   yaw: Math.PI, pitch: 0.8, zoom: 0.5 },
};

function disposeView(v) {
  if (!v) return;
  v.dispose();
  v.group.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    if (o.material && o.material.map) o.material.map.dispose();
    if (o.material) o.material.dispose();
  });
}

// The last car is a secret until it is earned: a dark cloud on its plinth, and a "?" for a name. The requirement still shows, so there is
// something to chase.
const MYSTERY = 'f1';
const mystery = (m) => m === MYSTERY && isLocked(m);

// A cloud where a car should be: a cluster of low-poly puffs in dark gray,
// a little see-through, each bobbing and swelling on its own slow cycle so the
// fog never holds still long enough to show a shape. Seeded, so it is the same
// cloud every time.
function fog() {
  const g = new THREE.Group();
  let seed = 7;
  const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const mat = new THREE.MeshLambertMaterial({ color: 0x6a707c, emissive: 0x1d2027,
                                             transparent: true, opacity: 0.32,
                                             depthWrite: false });
  const geo = new THREE.IcosahedronGeometry(1, 2);
  for (let i = 0; i < 34; i++) {
    const puff = new THREE.Mesh(geo, mat);
    const base = [(rnd() - 0.5) * 2.0, 0.3 + rnd() * 1.0, (rnd() - 0.5) * 3.6];
    const r = 0.4 + rnd() * 0.5, ph = rnd() * 6.28, sp = 0.4 + rnd() * 0.5;
    puff.rotation.set(rnd() * 6, rnd() * 6, rnd() * 6);
    puff.onBeforeRender = () => {
      const t = performance.now() / 1000 * sp + ph;
      puff.position.set(base[0] + Math.sin(t) * 0.08, base[1] + Math.sin(t * 1.3) * 0.06,
                        base[2] + Math.cos(t * 0.8) * 0.1);
      puff.scale.setScalar(r * (1 + Math.sin(t * 0.9) * 0.08));
      puff.rotation.y += 0.002;
    };
    puff.position.set(...base);
    puff.scale.setScalar(r);
    g.add(puff);
  }
  return g;
}

function buildCar(i) {
  const m = MODELS[i];
  disposeView(S.cars[i]);
  if (mystery(m)) {
    const v = new CarView(S.renderer.scene, { model: 'classic', body: '#34373e' });
    v.group.children.forEach((c) => { c.visible = false; });
    v.group.add(fog());
    v.setLabel(null);
    S.cars[i] = v;
    return;
  }
  const v = new CarView(S.renderer.scene, Object.assign({}, S.livery, { model: m }),
                        { ghost: isLocked(m) });
  v.setLabel(null);
  S.cars[i] = v;
}

/** Rebuilt on every change: the car in focus at once, the rest a moment later,
 *  so dragging a colour picker repaints one car per move rather than ten. */
function rebuild() {
  buildCar(S.focus);
  clearTimeout(rebuild._t);
  rebuild._t = setTimeout(() => {
    for (let i = 0; i < MODELS.length; i++) if (i !== S.focus) buildCar(i);
  }, 220);
}

function plinths() {
  const g = new THREE.Group();
  const top = new THREE.MeshLambertMaterial({ color: 0x1b2029 });
  S.rings = [];
  S.discs = [];
  for (let i = 0; i < MODELS.length; i++) {
    const disc = new THREE.Mesh(new THREE.CylinderGeometry(2.45, 2.55, 0.12, 48), top);
    disc.position.set(carX(i), -0.06, 0);
    g.add(disc);
    S.discs.push(disc);
    const ring = new THREE.Mesh(new THREE.RingGeometry(2.47, 2.55, 64),
      new THREE.MeshBasicMaterial({ color: 0x262d3a }));
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(carX(i), 0.001, 0);
    g.add(ring);
    S.rings.push(ring);
  }
  return g;
}

/** Roll `d` cars along the loop, and sit in the one you land on if it is yours. */
function step(d) {
  if (!d) return;
  S.slotTo += d;
  focusCar(((S.slotTo % MODELS.length) + MODELS.length) % MODELS.length);
}

function focusCar(i) {
  if (i === S.focus) return;
  S.focus = i;
  const m = MODELS[i];
  S.said = null;
  if (!isLocked(m) && S.livery.model !== m) {
    S.livery.model = m;
    save();
  }
  for (let k = 0; k < S.rings.length; k++) {
    S.rings[k].material.color.setHex(k === i ? 0x56709e : 0x262d3a);
  }
  render();
}

/** Point the camera at what tab `t` edits. */
function framePart(t) {
  const P = PARTS[t] || PARTS.body;
  S.target = { yaw: P.yaw, pitch: P.pitch };
  S.zoomTo = P.zoom;
  S.part = P;
  S.spin = false;
}

/** The part's point in the world, on the car in focus as it is turned now. */
function partPoint(carYaw) {
  const P = S.part || PARTS.body;
  let at = P.at;
  if (at === 'wheel') {
    const v = S.cars[S.focus];
    const hub = v && v.steered.find((h) => h.position.x > 0);
    at = hub ? [hub.position.x + 0.2, hub.position.y, hub.position.z] : [1, 0.4, -1.2];
  }
  const c = Math.cos(carYaw), s = Math.sin(carYaw);
  return [carX(S.focus) + at[0] * c + at[2] * s, at[1], -at[0] * s + at[2] * c];
}

/** The car under a click, by its centre's place on screen. */
function carAt(x, y) {
  const c = S.renderer.renderer.domElement, r = c.getBoundingClientRect();
  let best = -1, bd = 1e9;
  for (let i = 0; i < MODELS.length; i++) {
    const p = new THREE.Vector3(carX(i), 0.6, 0).project(S.renderer.camera);
    if (p.z > 1) continue;
    const sx = r.left + (p.x + 1) / 2 * r.width, sy = r.top + (1 - p.y) / 2 * r.height;
    const d = Math.hypot(sx - x, sy - y);
    if (d < bd) { bd = d; best = i; }
  }
  return bd < r.width * 0.12 ? best : -1;
}

/** A random car out of what you have earned: paint, pattern, wheels, finish. */
function randomize() {
  const pick = (a) => a[Math.floor(Math.random() * a.length)];
  const open = (slot, list) => list.filter((v) => !LOCKED.has(slot + '|' + v));
  const sw = (k) => (G.swatches && G.swatches[k]) || G.palette;
  const L = S.livery;
  L.body = pick(G.palette);
  L.livery = pick(open('livery', G.liveries));
  L.stripe = pick(sw('stripe'));
  L.rim_style = pick(open('rim_style', G.rim_styles));
  L.rim = pick(sw('rim'));
  L.finish = pick(open('finish', G.finishes));
  L.trim = Math.random() < 0.5 ? null : pick(sw('trim'));
  L.roof = Math.random() < 0.6 ? null : pick(sw('roof'));
  for (let i = 0; i < MODELS.length; i++) buildCar(i);
  render();
  save();
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
  const k = 1 - Math.pow(0.001, dt);

  if (S.target) {
    // Eased rather than cut: the turn is what tells you which way it went round.
    const dy = shortest(S.yaw, S.target.yaw);
    S.yaw += dy * k;
    S.pitch += (S.target.pitch - S.pitch) * k;
    if (Math.abs(dy) < 0.002 && Math.abs(S.target.pitch - S.pitch) < 0.002) {
      S.yaw = S.target.yaw; S.pitch = S.target.pitch; S.target = null;
      render();
    }
  } else if (S.spin) {
    S.yaw += dt * 0.32;
  }
  if (S.zoomTo != null) {
    S.zoom += (S.zoomTo - S.zoom) * k;
    if (Math.abs(S.zoomTo - S.zoom) < 0.002) { S.zoom = S.zoomTo; S.zoomTo = null; }
  }
  S.wheel += dt * 0.32 * 4.0;

  // `S.yaw` is the view angle round the car, as it always was; the camera now
  // stays on its side of the row and it is the car that turns to give it.
  S.slot += (S.slotTo - S.slot) * (1 - Math.pow(0.0004, dt));
  if (Math.abs(S.slotTo - S.slot) < 1e-4) S.slot = S.slotTo;
  for (let i = 0; i < S.discs.length; i++) {
    S.discs[i].position.x = S.rings[i].position.x = carX(i);
  }
  const carYaw = CAM_YAW - S.yaw;
  const want = partPoint(carYaw);
  const r = 1 - Math.pow(0.0004, dt);
  // The row's own position is eased already (`S.slot`), so only the part
  // offset is eased here - easing x twice would lag behind the cars.
  const off = [want[0] - carX(S.focus), want[1], want[2]];
  S.lookOff = S.lookOff ? S.lookOff.map((v, n) => v + (off[n] - v) * r) : off;
  S.look = [-S.slot * GAP + S.lookOff[0], S.lookOff[1], S.lookOff[2]];

  const cy = Math.cos(S.pitch), sy = Math.sin(S.pitch);
  const cam = S.renderer.camera;
  const dist = fitDist() * S.zoom;
  cam.position.set(S.look[0] + Math.sin(CAM_YAW) * dist * cy,
                   S.look[1] + 0.18 + sy * dist,
                   S.look[2] + Math.cos(CAM_YAW) * dist * cy);
  cam.lookAt(S.look[0], S.look[1], S.look[2]);
  cam.updateProjectionMatrix();
  if (S.floor) S.floor.position.x = S.look[0];

  const up = new THREE.Vector3(0, 1, 0), N = new THREE.Vector3(0, 1, 0);
  const rest = new THREE.Quaternion().setFromAxisAngle(up, CAM_YAW - 2.45);
  for (let i = 0; i < S.cars.length; i++) {
    const v = S.cars[i];
    if (!v) continue;
    const pos = new THREE.Vector3(carX(i), 0, 0);
    const q = i === S.focus ? new THREE.Quaternion().setFromAxisAngle(up, carYaw) : rest;
    v.update(pos, q, { spin: i === S.focus ? S.wheel : 0, groundY: 0, groundN: N });
    // A neighbour the camera has backed into would fill the screen with its
    // inside; it steps out of the way instead.
    v.setVisible(i === S.focus || cam.position.distanceTo(pos) > 3.2);
  }
  S.renderer.render(dt);
}

function setView(id) {
  const v = VIEWS.find((x) => x[1] === id);
  if (!v) return;
  S.target = { yaw: v[2], pitch: v[3] };
  S.part = PARTS.body;
  S.zoomTo = 1.4;
  S.spin = false;
  render();
}

// ---------------------------------------------------------------------------
// Spinning it
// ---------------------------------------------------------------------------

function bindDrag(el) {
  let down = false, lx = 0, ly = 0, ox = 0, oy = 0;
  const start = (x, y) => {
    down = true; lx = x; ly = y; ox = x; oy = y; S.spin = false; S.target = null; render();
  };
  const move = (x, y) => {
    if (!down) return;
    S.yaw -= (x - lx) * 0.01;
    // Clamped so you cannot end up under the floor or looking at the roof from
    // directly above, both of which are views of nothing.
    S.pitch = Math.max(-0.05, Math.min(1.1, S.pitch + (y - ly) * 0.006));
    lx = x; ly = y;
  };
  // A press that did not drag is a click, and a click on another car goes to it.
  const end = (e) => {
    if (down && e && Math.hypot(e.clientX - ox, e.clientY - oy) < 6) {
      const i = carAt(e.clientX, e.clientY);
      if (i >= 0 && i !== S.focus) step(carSlot(i) - S.slotTo);
    }
    down = false;
  };

  el.addEventListener('pointerdown', (e) => { el.setPointerCapture(e.pointerId);
                                              start(e.clientX, e.clientY); });
  el.addEventListener('pointermove', (e) => move(e.clientX, e.clientY));
  el.addEventListener('pointerup', end);
  el.addEventListener('pointercancel', end);
  el.addEventListener('wheel', (e) => {
    e.preventDefault();
    // A multiplier on whatever the window's own framing is, so a zoom survives
    // a resize instead of becoming a distance that means something else.
    S.zoom = Math.max(0.4, Math.min(2.6, S.zoom * (e.deltaY > 0 ? 1.08 : 0.926)));
  }, { passive: false });
}

// ---------------------------------------------------------------------------
// Saving
// ---------------------------------------------------------------------------

const EMBED = window.parent !== window;

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
        // Inside the game's settings: hand the game the car it should now be
        // driving, as the server resolved it.
        if (EMBED) parent.postMessage({ garage: d.livery }, location.origin);
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
  rusted: 'Rusted', chrome: 'Chrome', glow: 'Glow', radiant: 'Radiant',
  none: 'None', stock: 'Stock', matte: 'Matte', gloss: 'Gloss',
  centre: 'Center', twin: 'Twin',
  band: 'Band', hoop: 'Hoop', halves: 'Halves', fade: 'Fade',
  pinstripe: 'Pinstripe', spoke5: '5-spoke', spoke6: '6-spoke', mesh: 'Mesh',
  dish: 'Dish', forged: 'Split 5',
  // The badges. Named for the shape rather than for what earns it, because the
  // gate's own sentence is already on the chip when it is locked and is the wrong
  // thing to read once it is not - "Win a race" on a car you have already won a
  // race in tells you nothing about what is on the bonnet.
  laurel: 'Laurel', checkers: 'Checkers', chevrons: 'Chevrons', crown: 'Crown',
  podium: 'Podium', sunburst: 'Sunburst', ribbon: 'Ribbon', shield: 'Shield',
  classic: 'Classic', bubble: 'Bubble', beetle: 'Beetle', kart: 'Kart', van: 'Van', pickup: 'Pickup', gt: 'GT', sixties: '60s Racer',
  rally: 'Rally', muscle: 'Muscle', monster: 'Monster Truck', proto: 'Prototype',
  bigrig: 'Big Rig', f1: 'Formula',
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
function colorSlot(slot, current, label = '', autoLabel = 'Auto', off = false) {
  const list = (G.swatches && G.swatches[slot]) || G.palette;
  const custom = current && list.indexOf(current) < 0;
  const sw = list.map((c) => `<button class="gsw${current === c ? ' on' : ''}"
      data-slot="${esc(slot)}" data-value="${esc(c)}"
      style="background:${esc(c)}" title="${esc(c)}"></button>`).join('');
  // `off` keeps the row where it is and greys it, rather than removing it: a row
  // that comes and goes with another choice resizes the bar under your cursor.
  return `<span class="gslot${off ? ' off' : ''}">
    ${label ? `<span class="gslot-label">${esc(label)}</span>` : ''}
    <button class="gopt${current ? '' : ' on'}" data-slot="${esc(slot)}"
            data-value="">${esc(autoLabel)}</button>
    <span class="gcolors">${sw}<button
      class="gsw gcustom${custom ? ' has' : ''}" data-pick="${esc(slot)}"
      title="Any other color"${custom ? ` style="--pick:${esc(current)}"` : ''}
      ></button></span></span>`;
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
  ['trim', 'Detail', (L) => [
    colorSlot('trim', L.trim, 'Spoiler'),
    colorSlot('roof', L.roof, 'Roof', 'Body')]],
  ['livery', 'Livery', (L) => [chips('livery', G.liveries, L.livery),
    colorSlot('stripe', L.stripe, '', 'Auto', !L.livery || L.livery === 'none')]],
  // The Rim colour is offered for **every** style including stock, which is the
  // one that used to hide it. Stock has no rim face until you paint one, so here
  // Auto genuinely means "no lip" rather than "the standard silver" - which is
  // the honest reading of a slot whose absence is a real choice.
  ['rim_style', 'Wheels', (L) => [chips('rim_style', G.rim_styles, L.rim_style),
    colorSlot('rim', L.rim, '', L.rim_style === 'stock' ? 'None' : 'Auto')]],
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
  ['badge', 'Badge', (L) => [chips('badge', G.badges, L.badge),
    colorSlot('badge_color', L.badge_color, '', 'Auto', !L.badge || L.badge === 'none')]],
];

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
      >${esc(name)}</button>`
  ).join('');
  // One or two rows, centred in a bar of fixed size - so changing tab or choice
  // never changes the shape of anything.
  const rows = [].concat(tab[2](L));
  $('gopts').innerHTML = rows.map((r) => `<div class="grow">${r}</div>`).join('');
  const m = MODELS[S.focus];
  const g = (G.gates || []).find((x) => x.slot === 'model' && x.value === m);
  const want = isLocked(m) && g
    ? `<span class="gname-lock">${esc(g.text)}${g.need > 1 ? ` (${g.have}/${g.need})` : ''}</span>` : '';
  $('gname').innerHTML = `<b>${esc(mystery(m) ? '?' : label(m))}</b>${want}`;
  $('gearn').innerHTML = noteLine();
  $('gviews').innerHTML = VIEWS.map(([name, id, yaw, pitch]) =>
    `<button class="gview${!S.target && Math.abs(shortest(S.yaw, yaw)) < 0.01
                            ? ' on' : ''}" data-view="${esc(id)}"
      >${esc(name)}</button>`).join('');

  for (const b of $('gtabs').querySelectorAll('button[data-tab]')) {
    b.onclick = () => { S.tab = b.dataset.tab; framePart(S.tab); render(); };
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
  S.floor = studioFloor();
  S.floor.position.y = -0.12;
  S.renderer.scene.add(S.floor);
  S.renderer.scene.add(plinths());
  // A cool rim from behind, so every car in the row has an edge against the
  // dark - the studio's third light.
  const rim = new THREE.DirectionalLight(0xbcd2ff, 0.9);
  rim.position.set(20, 30, 80);
  S.renderer.scene.add(rim);

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

  S.focus = Math.max(0, MODELS.indexOf(S.livery.model || 'classic'));
  S.slot = S.slotTo = S.focus;
  for (let i = 0; i < MODELS.length; i++) buildCar(i);
  S.rings[S.focus].material.color.setHex(0x56709e);
  S.look = null;
  render();
  bindDrag(canvas);
  $('gprev').onclick = () => step(-1);
  $('gnext').onclick = () => step(1);
  $('grandom').onclick = randomize;
  addEventListener('keydown', (e) => {
    if (e.target.closest && e.target.closest('input, textarea')) return;
    if (e.key === 'ArrowLeft' || e.code === 'KeyA') step(-1);
    if (e.key === 'ArrowRight' || e.code === 'KeyD') step(1);
    if (EMBED && e.key === 'Escape' && !S.pick) parent.postMessage({ garageClose: true }, location.origin);
  });
  bindReset();
  bindPick();
  requestAnimationFrame(frame);
}

boot();
