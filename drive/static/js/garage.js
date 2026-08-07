// The garage: one car on a turntable, and the things you can change about it.
//
// It reuses the game's own `Renderer` and `CarView` rather than drawing a second
// car, which is the whole reason this file is short. `Renderer` needs no track:
// `trackGroup` and `sky` start null and `render(dt)` is only the particles and a
// draw, so a studio costs one canvas and nothing else - and the page opens
// instantly rather than paying `buildTrack`.
//
// Two things are deliberately not here. There is no `OrbitControls`: it is a
// three.js addon and is not vendored, and what this needs is thirty lines of
// drag rather than a dependency. And there is no second copy of what a car may
// wear - every list on screen is built from the payload the server rendered into
// the page, so the options here cannot drift from the ones `garage.py` enforces.

import * as THREE from './vendor/three.module.js';
import { Renderer, CarView } from './render.js';

const G = window.DRIVE_GARAGE;
const $ = (id) => document.getElementById(id);

const S = {
  livery: Object.assign({}, G.livery),
  renderer: null, view: null,
  // Framing, and the numbers are worth a word. `Renderer`'s camera is 66 degrees
  // vertical, so the frame is `2 * dist * tan(33)` units tall - at the chase
  // camera's ~9 that is twelve units for a car 1.2 tall, and it comes out a
  // tenth of the screen high. This is a portrait, not a chase: at 5.9 the car is
  // about a third of the frame, which is as close as it can go before a
  // three-quarter view starts clipping its own nose.
  yaw: 2.5, pitch: 0.22, dist: 5.9,
  spin: true,              // idle rotation, until you take hold of it
  wheel: 0,
  saveTimer: null,
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

function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.05, (now - (frame.last || now)) / 1000);
  frame.last = now;

  if (S.spin) S.yaw += dt * 0.35;
  // The wheels turn with the turntable, because a car rotating on stationary
  // wheels reads as a model and a car whose wheels are going reads as a car.
  S.wheel += dt * 0.35 * 4.0;

  const cy = Math.cos(S.pitch), sy = Math.sin(S.pitch);
  const cam = S.renderer.camera;
  cam.position.set(Math.sin(S.yaw) * S.dist * cy, 1.05 + sy * S.dist,
                   Math.cos(S.yaw) * S.dist * cy);
  cam.lookAt(0, 0.55, 0);
  cam.updateProjectionMatrix();

  // The car sits at the origin with the floor at y=0, so its own contact shadow
  // does the grounding - the same shadow it has on the road, which is why there
  // is no separate studio floor shadow to get subtly wrong.
  S.view.update(new THREE.Vector3(0, 0, 0), new THREE.Quaternion(),
                { spin: S.wheel, groundY: 0, groundN: new THREE.Vector3(0, 1, 0) });
  S.renderer.render(dt);
}

// ---------------------------------------------------------------------------
// Spinning it
// ---------------------------------------------------------------------------

function bindDrag(el) {
  let down = false, lx = 0, ly = 0;
  const start = (x, y) => { down = true; lx = x; ly = y; S.spin = false; };
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
    S.dist = Math.max(4.2, Math.min(12, S.dist + Math.sign(e.deltaY) * 0.5));
  }, { passive: false });
}

// ---------------------------------------------------------------------------
// The slots
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
        // row that offered it already says why it is locked.
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
  // ones that happen to know they changed something else. Only the two-tone
  // toggle used to do this, so picking a body colour or a rim moved the car and
  // left the button you had just pressed looking unpressed - the selection
  // highlight was drawn once at boot and then quietly lied for the rest of the
  // session. One direction: livery -> screen, always.
  render();
  save();
}

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

/** A row of choices. Locked ones are shown, greyed, with what they cost. */
function chooser(slot, values, current) {
  return values.map((v) => {
    const lock = LOCKED.get(slot + '|' + v);
    const on = current === v;
    return `<button class="gopt${on ? ' on' : ''}${lock ? ' locked' : ''}"
             data-slot="${esc(slot)}" data-value="${esc(v)}"
             ${lock ? `disabled title="${esc(lock)}"` : ''}>${esc(label(v))}${
      lock ? `<span class="glock">${esc(lock)}</span>` : ''}</button>`;
  }).join('');
}

function swatches(slot, current) {
  return G.palette.map((c) => `<button class="gsw${current === c ? ' on' : ''}"
      data-slot="${esc(slot)}" data-value="${esc(c)}"
      style="background:${esc(c)}" title="${esc(c)}"></button>`).join('');
}

/** A free colour, with a way back to "whatever the car did before". */
function picker(slot, current, fallbackNote) {
  const v = current || '#888888';
  return `<div class="gpick">
      <input type="color" data-slot="${esc(slot)}" value="${esc(v)}"/>
      <button class="gopt small" data-slot="${esc(slot)}" data-value="">Default</button>
      <span class="gnote">${esc(fallbackNote)}</span>
    </div>`;
}

function render() {
  const L = S.livery;
  $('gslots').innerHTML = `
    <div class="gsec"><h3>Body</h3><div class="gswatches">${swatches('body', L.body)}</div></div>
    <div class="gsec"><h3>Finish</h3>${chooser('finish', G.finishes, L.finish)}</div>
    <div class="gsec"><h3>Trim</h3>
      ${picker('trim', L.trim, 'Nose, wing and rear wing. Default follows the body.')}
      <button class="gopt${L.two_tone ? ' on' : ''}" data-toggle="two_tone">Two-tone roof</button>
    </div>
    <div class="gsec"><h3>Livery</h3>${chooser('livery', G.liveries, L.livery)}
      ${picker('stripe', L.stripe, 'The stripe colour.')}</div>
    <div class="gsec"><h3>Wheels</h3>${chooser('rim_style', G.rim_styles, L.rim_style)}
      ${picker('rim', L.rim, 'Rim colour. Pick a style first.')}</div>
    <div class="gsec"><h3>Glass</h3>${picker('glass', L.glass, 'Default is the standard tint.')}</div>
    <div class="gsec"><h3>Badge</h3>${chooser('badge', G.badges, L.badge)}</div>`;

  for (const b of $('gslots').querySelectorAll('button[data-slot]')) {
    b.onclick = () => set(b.dataset.slot, b.dataset.value || null);
  }
  for (const b of $('gslots').querySelectorAll('button[data-toggle]')) {
    b.onclick = () => set(b.dataset.toggle, !S.livery[b.dataset.toggle]);
  }
  for (const i of $('gslots').querySelectorAll('input[type=color]')) {
    i.oninput = () => set(i.dataset.slot, i.value);
  }
}

// ---------------------------------------------------------------------------

function boot() {
  const canvas = $('gcanvas');
  S.renderer = new Renderer(canvas);
  // A graded backdrop and nothing else. No sky dome, no fog: both exist to sell
  // distance, and there is no distance here.
  S.renderer.scene.background = new THREE.Color(0x10141b);
  S.renderer.scene.fog = null;
  // A floor for the shadow to land on, dark enough to read as a surface and not
  // as a second car-sized object.
  // Enough lighter than the backdrop to read as a surface. At the value it
  // started on the two were within a few points of each other and the car
  // floated in a void with a smudge under it - the contact shadow needs
  // something to be a shadow *on*.
  const floor = new THREE.Mesh(new THREE.CircleGeometry(9, 40),
                               new THREE.MeshLambertMaterial({ color: 0x2a3340 }));
  floor.rotation.x = -Math.PI / 2;
  S.renderer.scene.add(floor);

  // A fill from the opposite side to the sun. The track's rig is one hard key
  // plus a hemisphere, which is right outdoors where the sky does most of the
  // work and wrong in a black room: every face turned away from the key fell to
  // the same flat shadow, so a flat-shaded car read as a paper cut-out of
  // itself. Dim and cool, and only there to put an edge back on the dark side.
  const fill = new THREE.DirectionalLight(0x9fb4d8, 0.55);
  fill.position.set(-90, 45, -70);
  S.renderer.scene.add(fill);

  rebuild();
  render();
  bindDrag(canvas);
  requestAnimationFrame(frame);
}

boot();
