/* The track editor.
 *
 * Two screens: pick a shape to start from, then edit it.
 *
 * The one architectural thing worth knowing: **this file does not build roads.**
 * `tracks/builder.py` is the only turtle there is, and the editor asks it over
 * `/api/make/build` (debounced) rather than carrying a second copy in
 * JavaScript. That follows the rule `tuning.py` already sets - there is
 * deliberately no second copy of `ACCEL` in a .js file - and a second copy of
 * the turtle would be the same mistake with more surface, drifting the first
 * time somebody changed how a hill eases. Replaying a document costs about 4ms
 * on the server, so the round trip is the cheap part of a keystroke.
 *
 * Drawing, on the other hand, is entirely the existing stack: `buildTrack` from
 * trackmesh.js and `Renderer` from render.js, exactly as the play page uses
 * them. The editor's world is not a preview of the game, it is the game's world
 * with the camera somewhere else.
 */
import * as THREE from './vendor/three.module.js';
import { buildTrack, sceneryContext, shade, mulberry }
  from './trackmesh.js';
import { Renderer } from './render.js';
import { EXAMPLES, exampleSource } from './scenery_examples.js';
import { catalogue, placementDefaults } from './scenery_kit.js';

const M = window.MAKE || {};
const T = window.DRIVE_TUNING;
const $ = (id) => document.getElementById(id);

/* ------------------------------------------------------------------ *
 *  Screen one: pick a shape
 * ------------------------------------------------------------------ */
function renderPick() {
  const host = $('shapes');
  if (!host) return;
  for (const s of M.shapes || []) {
    const a = document.createElement('button');
    a.type = 'button';
    a.className = 'shape';
    a.style.setProperty('--d', `var(--diff-${s.difficulty})`);
    const pips = Array.from({ length: 5 },
      (_, i) => `<i class="${i < s.difficulty ? 'on' : ''}"></i>`).join('');
    const tag = s.closed ? 'closed lap' : (s.void ? 'no ground' : '');
    a.innerHTML =
      `<svg viewBox="0 0 200 96" aria-hidden="true">
         <path d="${s.plan}" fill="none" stroke="#1d1d1f" stroke-opacity=".22"
               stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
         <path d="${s.plan}" fill="none" stroke="#1d1d1f" stroke-opacity=".62"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
       </svg>
       <div class="body">
         <b>${s.name}<span class="pips">${pips}</span></b>
         <small>${s.about}</small>
         ${tag ? `<span class="tag">${tag}</span>` : ''}
       </div>`;
    a.addEventListener('click', () => { location.href = '/make/' + s.shape; });
    host.appendChild(a);
  }
}

/* ------------------------------------------------------------------ *
 *  Inspector metadata
 * ------------------------------------------------------------------ *
 * Ranges only - the *fields* and their defaults come from the server, which
 * takes them from the Builder's own signature. These are how wide a slider is,
 * which is a UI question and belongs on this side.
 *
 * The floors are not arbitrary. `min` on a corner radius is 12 because
 * `test_corner_radii_are_varied_and_drivable` fails below it, so a slider that
 * went lower would only ever be offering somebody a track that cannot ship.
 */
const RANGE = {
  run:   [10, 120, 1, 'run to the line'],
  len:   [4, 320, 1, 'length'],
  rise:  [-30, 30, 0.2, 'rise'],
  deg:   [-180, 180, 1, 'angle'],
  rad:   [12, 300, 0.5, 'radius'],
  bank:  [0, 24, 1, 'bank'],
  drop:  [0, 40, 0.5, 'drop'],
  gap:   [4, 60, 1, 'gap'],
  kick:  [2, 30, 0.5, 'kicker'],
  land:  [10, 90, 1, 'landing'],
  bow:   [0, 12, 0.2, 'arc through the air'],
  shift: [8, 60, 1, 'exit offset'],
  depth: [1, 10, 0.25, 'wall height'],
  floor: [0.05, 0.9, 0.01, 'flat floor'],
  pre:   [8, 60, 1, 'run-up'],
  post:  [8, 60, 1, 'run-off'],
  w:     [7, 26, 0.5, 'road width'],
};

// What the "add" bar offers, in the order a beginner needs them.
const ADDABLE = [
  ['straight', '+ straight'], ['arc', '+ turn'], ['cp', '+ ⛳ checkpoint'],
  ['hump', '+ hill'], ['crest', '+ crest'], ['jump', '+ jump'],
  ['gap', '+ gap'], ['loop', '+ loop'], ['boost', '+ pad'],
  ['bounce', '+ bounce'], ['pipe', '+ pipe'], ['flat', '+ flat'],
];

// Sensible new moves. Every one has to be legal on its own, because a beginner
// pressing "+ turn" and getting a track that will not build has been told the
// editor is broken.
const NEW_MOVE = {
  straight: () => ({ t: 'straight', len: 40 }),
  arc:      () => ({ t: 'arc', deg: -60, rad: 40 }),
  cp:       () => ({ t: 'cp' }),
  hump:     () => ({ t: 'hump', rise: 3.2, len: 30 }),
  crest:    () => ({ t: 'crest', rise: 2.5, len: 20 }),
  jump:     () => ({ t: 'jump', rise: 2.6, gap: 20, drop: 5, land: 34 }),
  gap:      () => ({ t: 'gap', len: 18, drop: 4 }),
  loop:     () => ({ t: 'loop', rad: 20, dir: 'l' }),
  boost:    () => ({ t: 'boost', len: 14 }),
  bounce:   () => ({ t: 'bounce', len: 14 }),
  pipe:     () => ({ t: 'pipe' }),
  flat:     () => ({ t: 'flat' }),
};

const LAYS_ROAD = new Set(['start', 'straight', 'arc', 'crest', 'hump', 'gap',
  'jump', 'loop', 'boost', 'bounce', 'cp', 'finish']);
const RAILS = [['', 'open'], ['l', 'left'], ['r', 'right'], ['lr', 'both']];

/* ------------------------------------------------------------------ *
 *  Bring your own AI
 * ------------------------------------------------------------------ *
 * The failure mode this exists to prevent is easy to picture: somebody types
 * "make me a city" into a chat window and gets back code using `THREE.Mesh`,
 * `document`, world coordinates and single-winding quads - none of which exist
 * here. No model has seen this API. So the deliverable is not a button, it is
 * making the API legible to whatever model the player already has, which is what
 * `apiSpec()` and the error text are for.
 *
 * The key goes in localStorage and the request goes from the browser straight to
 * the provider. **This box never sees a prompt, a token or a bill**, and that is
 * worth saying in those words, because the tempting shortcut is a proxy on the
 * server that "just adds the key" - which is an open model endpoint on somebody
 * else's account. There is no such route and there must never be one.
 */
const PROVIDERS = {
  claude: {
    name: 'Claude',
    // Newest first; the first is the default. `claude-opus-5` because this is a
    // code-writing task against an API the model has never seen, which is the
    // case for the strongest one rather than the cheapest.
    models: ['claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5'],
    keyHint: 'console.anthropic.com → API keys. Starts sk-ant-.',
    url: () => 'https://api.anthropic.com/v1/messages',
    headers: (key) => ({
      'content-type': 'application/json',
      'x-api-key': key,
      'anthropic-version': '2023-06-01',
      // Without this a browser-origin call is refused with a 401 that names
      // the header. The word is deliberate and it means what it says: anybody
      // with devtools can read this key. Bring-your-own-key is the documented
      // legitimate use, because the key belongs to the person whose browser
      // this is.
      'anthropic-dangerous-direct-browser-access': 'true',
    }),
    body: (model, blocks, turns) => ({
      model,
      // Thinking is on by default on Opus 5 and `max_tokens` caps thinking and
      // reply *together*, so this is sized with headroom - too tight and the
      // code comes back cut off mid-function.
      max_tokens: 16000,
      // Two blocks, and a cache breakpoint after the first. The vocabulary and
      // the scenery API are ~9KB and identical on every turn of every chat, so
      // marking them ephemeral means the second message onward pays for the
      // track state and nothing else. The dynamic block deliberately sits
      // *after* the breakpoint - putting it first would invalidate the prefix
      // on every keystroke, which is worse than not caching at all.
      system: [
        { type: 'text', text: blocks.stat,
          cache_control: { type: 'ephemeral' } },
        { type: 'text', text: blocks.live },
      ],
      messages: turns.map(t => ({ role: t.role, content: t.text })),
      // No temperature, top_p or top_k. On claude-opus-5 and claude-sonnet-5
      // they are rejected with a 400 - gone, not deprecated. Steer with the
      // prompt.
    }),
    read: (j) => (j.content || []).filter(b => b.type === 'text')
                   .map(b => b.text).join('\n'),
    error: (j) => j.error && j.error.message,
  },
  openai: {
    name: 'ChatGPT',
    models: ['gpt-5', 'gpt-5-mini'],
    keyHint: 'platform.openai.com → API keys. Starts sk-.',
    url: () => 'https://api.openai.com/v1/chat/completions',
    headers: (key) => ({ 'content-type': 'application/json',
                         authorization: 'Bearer ' + key }),
    // No explicit cache control, but the ordering still earns its keep: OpenAI
    // caches long identical prefixes automatically, so static-first is free.
    body: (model, blocks, turns) => ({
      model,
      messages: [{ role: 'system', content: blocks.stat + '\n\n' + blocks.live }]
        .concat(turns.map(t => ({ role: t.role, content: t.text }))),
    }),
    read: (j) => (((j.choices || [])[0] || {}).message || {}).content || '',
    error: (j) => j.error && j.error.message,
  },
  gemini: {
    name: 'Gemini',
    models: ['gemini-2.5-pro', 'gemini-2.5-flash'],
    keyHint: 'aistudio.google.com → Get API key.',
    url: (model, key) => 'https://generativelanguage.googleapis.com/v1beta/'
      + 'models/' + encodeURIComponent(model) + ':generateContent?key='
      + encodeURIComponent(key),
    headers: () => ({ 'content-type': 'application/json' }),
    body: (model, blocks, turns) => ({
      // Two parts, static first, for the same implicit-caching reason.
      systemInstruction: { parts: [{ text: blocks.stat }, { text: blocks.live }] },
      contents: turns.map(t => ({
        role: t.role === 'assistant' ? 'model' : 'user',
        parts: [{ text: t.text }],
      })),
    }),
    read: (j) => ((((j.candidates || [])[0] || {}).content || {}).parts || [])
                   .map(p => p.text).filter(Boolean).join('\n'),
    error: (j) => j.error && j.error.message,
  },
};

/**
 * The API surface, as data, because it is read by two things that must agree:
 * the spec put on the clipboard for a model, and `test_scenery_code.py`, which
 * checks it against what the sandbox actually hands to `props(ctx)`. A spec that
 * can drift from the code is a spec that will - the same reason the palette
 * contract is checked rather than documented.
 */
const CTX_API = [
  ['at(f)', 'number',
   'A fraction of the lap (0 to 1) as a station index. Every position starts '
   + 'here - there is no way to write a world coordinate, on purpose, because '
   + 'anything that did would be wrong after the next layout change.'],
  ['spot(i, off)', '[x, z]',
   'World x and z at station i, `off` units to the road\'s right. Negative is '
   + 'left. Note it is x and z - two numbers, not three.'],
  ['ground(i, off)', 'number',
   'The height of the ground there. Everything stands on this. Inside the '
   + 'apron it is the road less 1.2; beyond it, the height field.'],
  ['face(a, b, c, d, colour)', 'void',
   'A quad, drawn both windings. Always use this rather than solid.quad - the '
   + 'world material is FrontSide, so a single winding is invisible from one '
   + 'side, and an invisible wall is not an error in either language.'],
  ['solid.box(cx, cy, cz, hx, hy, hz, colour)', 'void',
   'A lit box from its centre and half-extents. The workhorse.'],
  ['solid.quad(a, b, c, d, colour) / solid.tri(...)', 'void',
   'Lit geometry, one winding. Prefer face().'],
  ['bright.box / .quad / .tri', 'void',
   'Unlit geometry, for anything that should read as emitting light.'],
  ['col.addQuad(a, b, c, d, kind)', 'void',
   'Collider. `kind` may be KIND.WALL or KIND.OFFROAD and nothing else.'],
  ['KIND', '{WALL, OFFROAD}',
   'The only two collider kinds scenery may emit. BOOST, BOUNCE and ROAD are '
   + 'refused: the anti-cheat re-drives submitted laps against this exact '
   + 'collider, so a pad you added would be a certified speed hack.'],
  ['track.line', 'array',
   'The ribbon. Each station has p (x,y,z), n (up normal) and lat (the '
   + 'road\'s right). track.line.length is how many there are.'],
  ['pal', 'object',
   'The palette. Take colours from it - pal.prop, pal.prop2, pal.rail - so '
   + 'scenery follows a palette change instead of fighting it.'],
  ['bbox', '{x0, x1, z0, z1}', 'How far the lap reaches, in world x and z.'],
  ['terrain', 'null or {height(x, z)}',
   'The height field, on the few tracks that have one, or null. Prefer '
   + 'ground(i, off) - it knows about the run-off apron beside the road, where '
   + 'the raw field returns whichever leg of the lap is nearest and jumps '
   + 'between them wherever the layout folds back on itself.'],
  ['shade(colour, amount)', 'number',
   'Lighten (positive) or darken (negative) a packed colour. shade(pal.prop, '
   + '-0.3) is a darker version of the same green.'],
  ['kit.<model>(opts)', 'void',
   'The scenery library, on the context: kit.stand({at: 0.1, side: -1, '
   + 'tiers: 9}), kit.hangar({...}), and sixteen others. Same models the '
   + 'author can drop in from the palette, so starting from one and changing '
   + 'it is the shortest route to anything.'],
  ['place(list)', 'void',
   'Draw a whole list of library placements: place([{o: "tree", at: 0.2, '
   + 'off: 30}, ...]).'],
  ['mulberry(seed)', 'function',
   'A seeded random. Use it rather than Math.random so the track looks the '
   + 'same every time it loads - and it must, because the baked geometry is '
   + 'what ships.'],
];

/* ------------------------------------------------------------------ *
 *  The palette
 * ------------------------------------------------------------------ *
 * Every key `tracks/look.py:KNOWN` lists and the editor can draw a control
 * for, in the order somebody actually works in: the road first, then what is
 * beside it, then the sky over it. Paths are dotted because the sky is nested
 * and flattening it here would mean a second shape for the same data.
 *
 * What is deliberately NOT here: `terrain`, `furniture`, `building`, `shore`
 * and `rainbow*`. Those are scenery - geometry derived off the ribbon - not
 * colour, and they get the scenery editor. A palette that carries them keeps
 * them untouched; see `borrowLook`.
 */
const LOOK = [
  ['The road', [
    ['road', 'c', 'surface'], ['kerb', 'c', 'kerb, light'],
    ['kerb2', 'c', 'kerb, dark'], ['rail', 'c', 'barriers'],
    ['gravel', 'c', 'run-off'], ['deco', 'c', 'markings'],
  ]],
  ['Beside it', [
    ['ground', 'c', 'ground'], ['prop', 'c', 'plants'],
    ['prop2', 'c', 'structures'], ['snow', 'c', 'snow'],
    ['density', 'n', 'how much scatter', 0, 0.5, 0.005],
  ]],
  ['Toys', [
    ['pad', 'c', 'boost pad'], ['padBase', 'c', 'pad base'],
    ['cap', 'c', 'bounce cap'], ['capSpot', 'c', 'cap spots'],
  ]],
  ['The sun', [
    ['sky.sun.color', 'c', 'disc'], ['sky.light.color', 'c', 'key light'],
    ['sky.light.intensity', 'n', 'key strength', 0, 3, 0.05],
    ['sky.sun.az', 'n', 'azimuth', -3.15, 3.15, 0.01],
    ['sky.sun.el', 'n', 'elevation', -0.2, 1.5, 0.01],
    ['sky.sun.size', 'n', 'disc size', 0, 900, 5],
  ]],
  ['The bounce', [
    ['sky.hemi.sky', 'c', 'from above'], ['sky.hemi.ground', 'c', 'from below'],
    ['sky.hemi.intensity', 'n', 'strength', 0, 2, 0.02],
  ]],
  ['Glow and distance', [
    ['sky.glow', 'c', 'glow'], ['fog', 'c', 'fog'], ['sky.fog', 'c', 'sky fog'],
    ['sky.glowStrength', 'n', 'glow strength', 0, 1, 0.01],
    ['sky.glowFocus', 'n', 'glow focus', 1, 20, 0.1],
    ['sky.fogNear', 'n', 'fog starts', 0, 900, 10],
    ['sky.fogFar', 'n', 'fog ends', 200, 3000, 25],
  ]],
];

// Which palette key each `look.advise` message is about, mapped to the control
// it should appear under. `advise` returns the key it is talking about for
// exactly this reason: a warning in a list at the bottom of a long pane is a
// warning about nothing in particular.
const ADVICE_AT = {
  road: 'road', ground: 'ground', density: 'density',
  hemi: 'sky.hemi.ground', glowStrength: 'sky.glowStrength',
  fogFar: 'sky.fogFar', stops: 'stops',
};

const hex = (n) => '#' + (n >>> 0).toString(16).padStart(6, '0').slice(-6);
const unhex = (s) => parseInt(s.slice(1), 16);

function dig(o, path) {
  for (const k of path.split('.')) {
    if (o == null) return undefined;
    o = o[k];
  }
  return o;
}
function plant(o, path, v) {
  const ks = path.split('.');
  while (ks.length > 1) {
    const k = ks.shift();
    if (o[k] == null || typeof o[k] !== 'object') o[k] = {};
    o = o[k];
  }
  o[ks[0]] = v;
}

/* ------------------------------------------------------------------ *
 *  Screen two: the editor
 * ------------------------------------------------------------------ */
function startEditor() {
  const state = {
    doc: M.doc,
    track: M.track,
    sel: 0,
    pick: -1,        // the placement selected in the Scenery tab
    history: [],
    built: null,
    pending: null,
    lapTimer: null,
  };

  /* -- the render stack, exactly the game's ------------------------- */
  const renderer = new Renderer($('gl'));
  const cam = { yaw: 0.9, pitch: 0.42, dist: 120, target: new THREE.Vector3() };
  // Read by the Playwright checks. The camera rules below - hold the angle
  // through an edit, expand the distance but never contract it - are the kind
  // of thing that only breaks on a real page, and CI has no browser.
  M.cam = cam;
  let hi = null;                                  // the selected stretch

  // Why the world is being rebuilt, because the camera should do a different
  // thing for each. Editing must not move the camera: watching the road change
  // is the entire point of a live preview, and a camera that re-frames on every
  // keystroke makes a slider drag unusable.
  //
  //   'first'  - just opened. Frame the whole track from above.
  //   'select' - a deliberate navigation. Fly to the chosen move.
  //   'edit'   - a parameter changed. Hold the angle; follow the geometry.
  function mount(track, why) {
    state.track = track;
    state.built = buildTrack(track, T);
    renderer.setTrack(state.built);
    hi = null;
    aim(why || 'edit');
    drawProfile();
    drawHud();
  }

  /* -- camera ------------------------------------------------------- */
  // Orbit rather than chase: there is no car here, and the thing you want to
  // look at is whichever move you are editing.
  function aim(why) {
    const line = state.track && state.track.line;
    if (!line || !line.length) return;
    const whole = why === 'first' || why === 'frame-all';
    const span = whole ? null : (state.track.spans || [])[state.sel];
    let pts = whole ? line : line.slice(span ? span[0] : 0,
                                       span ? span[1] + 1 : line.length);
    if (!pts.length) pts = line;

    // The target follows the selection even on an edit, and it has to: a change
    // to move 2 shifts every station after it in world space, so a target left
    // where it was would drift off the road entirely.
    let x = 0, y = 0, z = 0;
    for (const e of pts) { x += e.p[0]; y += e.p[1]; z += e.p[2]; }
    cam.target.set(x / pts.length, y / pts.length, z / pts.length);

    let r = 0;
    for (const e of pts) r = Math.max(r, cam.target.distanceTo(
      new THREE.Vector3(e.p[0], e.p[1], e.p[2])));
    const fit = Math.max(46, Math.min(520, r * (whole ? 1.9 : 2.4) + 30));

    if (why === 'frame' || why === 'frame-all') {
      // The one deliberate re-frame. Everything else holds the angle, which
      // left an author who had zoomed right in with no way back out - so this
      // is the way back, and it is the only thing that resets the angle.
      cam.userMoved = false;
      cam.dist = fit;
      cam.pitch = whole ? 0.78 : 0.42;
    } else if (why === 'edit') {
      // Hold the angle. Pull back only if the edit has grown past the frame -
      // never push in, because a shrinking road that yanked the camera closer
      // would be just as jarring as one that re-framed.
      cam.dist = Math.max(cam.dist, fit);
    } else if (!cam.userMoved) {
      cam.dist = fit;
      // The overview looks *down*. On a void track the world underneath is
      // enormous - a whole downtown drawn to the horizon - and a shallow angle
      // puts all of it between the camera and the road.
      cam.pitch = whole ? 0.78 : 0.42;
    } else {
      // They have orbited to an angle they chose. It is theirs now: follow the
      // selection, keep their framing.
      cam.dist = Math.max(cam.dist, Math.min(fit, cam.dist * 1.6));
    }
    highlight(whole ? null : span);
  }

  function highlight(span) {
    if (hi) { renderer.scene.remove(hi); hi.geometry.dispose(); hi = null; }
    const line = state.track && state.track.line;
    if (!span || !line) return;
    const pts = [];
    for (let i = span[0]; i <= span[1] && i < line.length; i++) {
      const e = line[i];
      // Lifted clear of the tarmac along the station's own normal, so it stays
      // visible inside a loop and up a pipe wall rather than sinking into the
      // surface the moment the road is not flat.
      pts.push(new THREE.Vector3(e.p[0] + e.n[0] * 1.4,
                                 e.p[1] + e.n[1] * 1.4,
                                 e.p[2] + e.n[2] * 1.4));
    }
    if (pts.length < 2) return;
    hi = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: 0xe8453c }));
    hi.renderOrder = 5;
    renderer.scene.add(hi);
  }

  /* -- riding it ----------------------------------------------------- *
   * A palette is judged in motion or it is not judged. The log this editor was
   * designed against says it plainly: a night palette can be beautiful in a
   * still render and unreadable at speed, and the question that matters is
   * whether the *next corner* is legible - which an orbit camera parked above
   * the track cannot answer at any distance.
   *
   * So this flies the ribbon from the driver's seat, using the game's own chase
   * camera geometry rather than an approximation of it: same set-back, same
   * lift, same look-ahead, all of them speed-dependent the same way. It is not
   * a simulation - there is no car and no physics, it runs the centreline at a
   * steady pace - and it does not need to be. What it reproduces is the framing,
   * and the framing is what a palette is read through.
   */
  const RIDE_SPEED = 46;                  // u/s: a real pace on a real track
  const ride = { on: false, at: 0 };
  const rv = {
    pos: new THREE.Vector3(), fwd: new THREE.Vector3(),
    up: new THREE.Vector3(), want: new THREE.Vector3(),
    look: new THREE.Vector3(),
  };

  function toggleRide(on) {
    ride.on = on === undefined ? !ride.on : on;
    $('ride').classList.toggle('on', ride.on);
    $('ride').textContent = ride.on ? 'Stop' : 'Ride it';
    if (ride.on) {
      // From the selected move, not from the start line: you turned this on
      // because you want to see the stretch you have been working on.
      const span = (state.track && state.track.spans || [])[state.sel];
      ride.at = span ? span[0] : 0;
    }
  }

  function rideCamera(dt) {
    const line = state.track && state.track.line;
    if (!line || line.length < 4) return false;
    // Stations are not evenly spaced in world units, so advance by distance and
    // let the index follow - otherwise the ride speeds up through a hairpin,
    // where the stations bunch, and that is exactly where you are looking.
    let left = RIDE_SPEED * dt;
    while (left > 0) {
      const i = Math.floor(ride.at) % (line.length - 1);
      const step = Math.max(0.001, new THREE.Vector3(...line[i + 1].p)
        .distanceTo(new THREE.Vector3(...line[i].p)));
      const room = (1 - (ride.at - Math.floor(ride.at))) * step;
      if (left < room) { ride.at += left / step; break; }
      left -= room;
      ride.at = Math.floor(ride.at) + 1;
      if (ride.at >= line.length - 1) ride.at = 0;   // round again
    }
    const i = Math.floor(ride.at) % (line.length - 1);
    const f = ride.at - Math.floor(ride.at);
    const a = line[i], b = line[i + 1];
    rv.pos.set(a.p[0] + (b.p[0] - a.p[0]) * f,
               a.p[1] + (b.p[1] - a.p[1]) * f,
               a.p[2] + (b.p[2] - a.p[2]) * f);
    rv.fwd.set(b.p[0] - a.p[0], b.p[1] - a.p[1], b.p[2] - a.p[2]).normalize();
    rv.up.set(a.n[0], a.n[1], a.n[2]).normalize();
    // render.js: back = 8.2 + min(3.4, s*0.075), up = 3.2 + min(1.1, s*0.02),
    // looking at pos + fwd*(7 + s*0.16) + up*1.1.
    const back = 8.2 + Math.min(3.4, RIDE_SPEED * 0.075);
    const lift = 3.2 + Math.min(1.1, RIDE_SPEED * 0.02);
    rv.want.copy(rv.pos).addScaledVector(rv.fwd, -back).addScaledVector(rv.up, lift);
    rv.look.copy(rv.pos).addScaledVector(rv.fwd, 7 + RIDE_SPEED * 0.16)
      .addScaledVector(rv.up, 1.1);
    const c = renderer.camera;
    c.position.copy(rv.want);
    c.up.copy(rv.up);
    c.lookAt(rv.look);
    return true;
  }

  function placeCamera(dt) {
    if (ride.on && rideCamera(dt || 0)) return;
    const c = renderer.camera;
    const cp = Math.cos(cam.pitch);
    c.position.set(cam.target.x + Math.sin(cam.yaw) * cp * cam.dist,
                   cam.target.y + Math.sin(cam.pitch) * cam.dist,
                   cam.target.z + Math.cos(cam.yaw) * cp * cam.dist);
    c.up.set(0, 1, 0);
    c.lookAt(cam.target);
  }

  const view = $('gl').parentElement;
  let drag = null;
  view.addEventListener('pointerdown', (e) => {
    if (e.target !== $('gl')) return;
    // Grabbing the world is how you take the camera back off the ride. Anything
    // else - a second button, a modal - is a thing to learn for no reason.
    if (ride.on) toggleRide(false);
    drag = { x: e.clientX, y: e.clientY };
    $('gl').setPointerCapture(e.pointerId);
  });
  view.addEventListener('pointermove', (e) => {
    if (!drag) return;
    cam.yaw -= (e.clientX - drag.x) * 0.006;
    cam.pitch = Math.max(0.06, Math.min(1.45,
      cam.pitch + (e.clientY - drag.y) * 0.005));
    cam.userMoved = true;
    drag = { x: e.clientX, y: e.clientY };
  });
  view.addEventListener('pointerup', () => { drag = null; });
  view.addEventListener('wheel', (e) => {
    e.preventDefault();
    cam.dist = Math.max(20, Math.min(900, cam.dist * (1 + Math.sign(e.deltaY) * 0.1)));
    cam.userMoved = true;
  }, { passive: false });

  (function loop(prev) {
    return requestAnimationFrame((now) => {
      const dt = Math.min(0.05, (now - prev) / 1000);
      placeCamera(dt);
      renderer.render(dt);
      loop(now);
    });
  })(performance.now());

  /* -- rebuilding --------------------------------------------------- */
  // Debounced, and never overlapping: a slider drag fires dozens of times a
  // second and the editor wants the newest answer, not all of them.
  let inflight = false, again = null;
  function rebuild(why) {
    if (inflight) { again = why || 'edit'; return; }
    inflight = true;
    setPending(true);
    fetch('/api/make/build', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(state.doc),
    }).then(r => r.json().then(j => ({ ok: r.ok, j })))
      .then(({ ok, j }) => {
        if (!ok) { showError(j.error, j.kind); return; }
        clearError();
        notes = j.notes || [];
        mount(j.track, why || 'edit');
        drawInspector();
      })
      .catch(() => showError('Lost the connection to the server.'))
      .finally(() => {
        inflight = false;
        const next = again;
        again = null;
        if (next) { rebuild(next); } else { setPending(false); }
        scheduleLap();
      });
  }
  // Throttled rather than debounced, and the difference is the whole feature:
  // a debounce is cleared by every event, so a drag emitting a change every
  // frame never reaches its own trailing edge and the road only moved once the
  // pointer stopped. A throttle guarantees progress *during* the drag, and the
  // no-overlap guard above then paces it to whatever the round trip actually
  // costs. The trailing call is kept so the released value is never the one
  // that got dropped.
  const debounced = throttle(rebuild, 90);

  // The preview lags a drag by the debounce plus the build, which on a long
  // closed lap is enough to notice. So the pending state is raised the moment
  // the document changes rather than when the request goes out - covering the
  // debounce window too, which is exactly the part that reads as a dead
  // control if nothing says otherwise.
  //
  // Shown late and held briefly, which matters in both directions. On a fast
  // connection a build lands in a handful of milliseconds, so an indicator
  // raised the instant work starts would strobe once per frame of a drag -
  // louder than the lag it was reporting. So: nothing for the first SHOW_AFTER,
  // and once it is up it stays up for SHOW_LEAST, because a bar that appears
  // and vanishes inside two frames reads as a glitch rather than as progress.
  const SHOW_AFTER = 130, SHOW_LEAST = 320;
  let pending = false, showTimer = null, hideTimer = null, shownAt = 0;
  function setPending(on) {
    if (pending === on) return;
    pending = on;
    if (on) {
      clearTimeout(hideTimer); hideTimer = null;
      if (document.body.classList.contains('building') || showTimer) return;
      showTimer = setTimeout(() => {
        showTimer = null;
        if (!pending) return;
        shownAt = performance.now();
        document.body.classList.add('building');
      }, SHOW_AFTER);
    } else {
      clearTimeout(showTimer); showTimer = null;
      if (!document.body.classList.contains('building')) return;
      const held = performance.now() - shownAt;
      clearTimeout(hideTimer);
      hideTimer = setTimeout(() => {
        hideTimer = null;
        if (!pending) document.body.classList.remove('building');
      }, Math.max(0, SHOW_LEAST - held));
    }
  }

  // The lap estimate is its own call because it costs a hundred times the road:
  // a racing-line relaxation over every station. Asked for well after you stop
  // moving, and abandoned the moment you start again.
  function scheduleLap() {
    clearTimeout(state.lapTimer);
    state.lapTimer = setTimeout(() => {
      fetch('/api/make/lap', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify(state.doc),
      }).then(r => r.ok ? r.json() : null).then(j => {
        if (j && j.ideal) { state.lap = j; drawHud(); }
      }).catch(() => {});
    }, 900);
  }

  function showError(msg, kind) {
    $('errtext').textContent = msg || 'Something in the document is wrong.';
    $('err').querySelector('b').textContent =
      kind === 'closure' ? 'This lap no longer closes' : 'That did not build';
    $('err').classList.add('on');
  }
  const clearError = () => $('err').classList.remove('on');

  /* -- editing ------------------------------------------------------ */
  function pushHistory() {
    state.history.push(JSON.stringify(state.doc));
    if (state.history.length > 80) state.history.shift();
  }

  function commit(mutate, live) {
    // A drag snapshots once, at `dragging`'s start. Otherwise pulling a
    // straight from 40 to 300 would cost two hundred undos to walk back.
    if (!dragging) pushHistory();
    mutate();
    drawMoves();
    // Mid-drag the inspector must NOT be rebuilt: replacing the range input
    // under the cursor ends the drag on the spot. It is resynced on release,
    // which is when the hints below it can have changed anyway.
    if (!live) drawInspector();
    setPending(true);
    debounced();
  }

  function undo() {
    const was = state.history.pop();
    if (!was) return;
    state.doc = JSON.parse(was);
    state.sel = Math.min(state.sel, state.doc.moves.length - 1);
    drawMoves(); drawInspector(); rebuild();
  }

  function addMove(t) {
    commit(() => {
      const m = NEW_MOVE[t]();
      // Inherit the width and barriers of the move it lands after, so adding a
      // straight in the middle of a wide section does not pinch the road.
      const prev = state.doc.moves[state.sel];
      if (LAYS_ROAD.has(t) && prev) {
        if (prev.w != null) m.w = prev.w;
        if (prev.rail != null) m.rail = prev.rail;
      }
      // Never after the finish: a move past the flag is road nobody drives.
      const last = state.doc.moves.length - 1;
      const at = Math.min(state.sel + 1, Math.max(1, last));
      state.doc.moves.splice(at, 0, m);
      state.sel = at;
    });
  }

  function deleteMove() {
    const m = state.doc.moves[state.sel];
    if (!m) return;
    if (m.t === 'start' || m.t === 'finish' || m.t === 'finish_at_start') return;
    commit(() => {
      state.doc.moves.splice(state.sel, 1);
      state.sel = Math.max(0, state.sel - 1);
    });
  }

  function setField(key, value, live) {
    commit(() => { state.doc.moves[state.sel][key] = value; }, live);
  }

  /* -- selection ---------------------------------------------------- *
   * One function, because there are four things to redraw and the first
   * version updated three of them from the click handler and a different three
   * from the arrow keys - so the height strip kept marking whichever move was
   * selected at the last *rebuild*, which reads as a broken strip rather than
   * a stale one. */
  function select(i) {
    state.sel = Math.max(0, Math.min(state.doc.moves.length - 1, i));
    drawMoves();
    drawInspector();
    aim('select');
    drawProfile();
  }

  /* -- the moves list ---------------------------------------------- */
  function label(m) {
    switch (m.t) {
      case 'start': return '▶ start';
      case 'finish': return '⚑ finish';
      case 'finish_at_start': return '⚑ finish (start line)';
      case 'cp': return '⛳ checkpoint';
      case 'flat': return 'flat';
      case 'pipe': return 'pipe';
      case 'arc': {
        const d = m.deg || 0;
        const kind = Math.abs(d) >= 140 ? 'hairpin' : (d > 0 ? 'right' : 'left');
        return `${kind} ${Math.abs(d)}°`;
      }
      default: return m.t;
    }
  }
  function trailing(m) {
    if (m.t === 'arc') return `r${m.rad ?? ''}`;
    if (m.t === 'jump') return `gap ${m.gap ?? ''}`;
    if (m.t === 'loop') return `r${m.rad ?? 20}`;
    if (m.len != null) return String(m.len);
    if (m.rise != null) return `${m.rise > 0 ? '+' : ''}${m.rise}`;
    return '';
  }

  function drawMoves() {
    const ul = $('moves');
    ul.textContent = '';
    let w = null, rail = null;
    state.doc.moves.forEach((m, i) => {
      if (m.w != null && m.w !== w) {
        w = m.w;
        ul.appendChild(note(`width ${w}`));
      }
      if (m.rail != null && m.rail !== rail) {
        rail = m.rail;
        const named = { '': 'no barriers', l: 'barrier left',
                        r: 'barrier right', lr: 'barriers both sides' }[rail];
        ul.appendChild(note(named));
      }
      const li = document.createElement('li');
      li.className = (i === state.sel ? 'sel ' : '') +
        (m.t === 'cp' || m.t.startsWith('finish') || m.t === 'start' ? 'gate' : '');
      li.innerHTML = `<span class="grip">≡</span><span>${label(m)}</span>` +
                     `<span class="n">${trailing(m)}</span>`;
      li.addEventListener('click', () => { select(i); });
      ul.appendChild(li);
    });
  }
  function note(text) {
    const d = document.createElement('div');
    d.className = 'state-note';
    d.textContent = '— ' + text;
    return d;
  }

  /* -- the inspector ----------------------------------------------- */
  function drawInspector() {
    const m = state.doc.moves[state.sel];
    const host = $('insp');
    host.textContent = '';
    if (!m) { $('insph').textContent = 'Nothing selected'; return; }
    $('insph').textContent = label(m).replace(/[▶⚑⛳]\s*/, '');

    const fields = Object.keys(RANGE).filter(k =>
      m[k] !== undefined || defaultFor(m.t, k) !== undefined);
    for (const key of fields) {
      if (key === 'w') continue;                 // shown below, with barriers
      const cur = m[key] !== undefined ? m[key] : defaultFor(m.t, key);
      if (cur === undefined || cur === null) continue;
      host.appendChild(slider(key, cur,
        (v, live) => setField(key, v, live)));
    }
    if (m.t === 'arc') host.appendChild(segment('turns', [['l', 'left'], ['r', 'right']],
      (m.deg || 0) > 0 ? 'r' : 'l',
      v => setField('deg', Math.abs(m.deg || 60) * (v === 'r' ? 1 : -1))));
    if (m.t === 'loop') host.appendChild(segment('exits', [['l', 'left'], ['r', 'right']],
      m.dir || 'l', v => setField('dir', v)));
    if (m.t === 'straight' || m.t === 'boost' || m.t === 'bounce') {
      host.appendChild(segment('shape', [['smooth', 'smooth hill'], ['kick', 'kicker']],
        m.ease === false ? 'kick' : 'smooth',
        v => setField('ease', v === 'smooth')));
    }
    if (LAYS_ROAD.has(m.t)) {
      host.appendChild(slider('w', m.w != null ? m.w : state.doc.width,
                              (v, live) => setField('w', v, live)));
      host.appendChild(segment('edges', RAILS, m.rail != null ? m.rail : '',
                               v => setField('rail', v)));
    }
    // What is wrong with this move, said on this move. A refusal here is a
    // track that builds and cannot be driven, which is a different thing from a
    // document that will not build - so it is shown next to the number that
    // caused it rather than in the error strip over the road.
    for (const n of notes.filter(n => n.at === state.sel)) {
      host.appendChild(adviceNode({ level: n.level === 'refuse' ? 'warn' : 'note',
                                    text: n.text }));
    }
    if (m.free && m.free.length) {
      host.appendChild(hint(
        `The closure solver may adjust this move's ${m.free.join(' and ')} to `
        + `make the lap meet itself.`, 'ok'));
    }
    if (m.t === 'boost') {
      host.appendChild(hint('A pad is worth about a second. It belongs somewhere '
        + 'the speed is usable — out of a slow corner, into a jump — and never '
        + 'into a braking zone.'));
    }
    if (m.t === 'bounce') {
      host.appendChild(hint('Widen the road over a cap. A 12-wide disc at the '
        + 'end of a fifty-unit flight is a coin toss rather than a line.', 'warn'));
    }
    if (m.t === 'loop' && (m.rad || 20) < 18) {
      host.appendChild(hint('Under about 18 a loop is undrivable at racing '
        + 'speed however good the geometry is — only gravity holds the car on '
        + 'over the top.', 'warn'));
    }
    for (const n of notes.filter(n => n.at == null)) {
      host.appendChild(adviceNode({ level: n.level === 'refuse' ? 'warn' : 'note',
                                    text: n.text }));
    }
    if (m.t !== 'start' && !m.t.startsWith('finish')) {
      const d = document.createElement('div');
      d.className = 'danger';
      d.innerHTML = '<button type="button">Delete this move</button>';
      d.querySelector('button').addEventListener('click', deleteMove);
      host.appendChild(d);
    }
  }

  function defaultFor(t, key) {
    // The server sends only fields that differ from their default, so the
    // inspector has to know which fields a move *has*. Kept as a small table
    // rather than fetched: it is which sliders to draw, not what they mean.
    const has = {
      start: ['run'], straight: ['len', 'rise'], arc: ['deg', 'rad', 'rise', 'bank'],
      crest: ['rise', 'len'], hump: ['rise', 'len'],
      gap: ['len', 'drop', 'bow'], jump: ['rise', 'gap', 'drop', 'kick', 'land'],
      loop: ['rad', 'shift'], boost: ['len', 'rise'], bounce: ['len', 'rise'],
      pipe: ['depth', 'floor'], cp: ['pre', 'post'], finish: ['pre', 'post'],
      flat: [], finish_at_start: [],
    }[t] || [];
    if (!has.includes(key)) return undefined;
    return { run: 14, len: 40, rise: 0, deg: -60, rad: 40, bank: 0, drop: 0,
             bow: 0, gap: 20, kick: 8, land: 14, shift: 0, depth: 4.5,
             floor: 0.34, pre: 17, post: 17 }[key];
  }

  // A slider previews the road *while* it is dragged, and the three ways of
  // getting that wrong are all one symptom - the road sits still through the
  // drag and then jumps once, with the number above it the only thing that
  // moved. In order of how long each took to find:
  //
  //  1. Committing on `change`. For a range input that fires on release, so
  //     there was nothing live about it.
  //  2. `drawInspector()` on every commit, which replaces the input under the
  //     cursor and ends the drag one frame in. Hence the `live` flag, and hence
  //     `dragging` - the field currently held.
  //  3. Ending the drag on `change` after all: Chromium fires it the instant
  //     the pointer lands, because clicking the track *is* a commit. So a
  //     pointer drag ends on `pointerup` and only a keyboard one ends on
  //     `change`, where it fires once per arrow press and means it - which is
  //     what `dragMode` is for.
  let dragging = null, dragMode = null, endDrag = null;
  let refocus = null;     // the key to hand focus back to after a resync

  // One window listener for every slider there will ever be. Registering it
  // inside `slider()` leaked one per slider per redraw of the inspector - which
  // happens on every commit - each holding a detached input alive.
  window.addEventListener('pointerup', () => {
    if (dragMode === 'pointer' && endDrag) endDrag();
  });

  function slider(key, value, onChange) {
    const [min, max, step, name] = RANGE[key];
    const d = document.createElement('div');
    d.className = 'field';
    d.innerHTML = `<label>${name}<b>${fmt(value)}</b></label>`
      + `<input type="range" min="${min}" max="${max}" step="${step}" value="${value}">`;
    const out = d.querySelector('b'), input = d.querySelector('input');
    d.dataset.key = key;

    const begin = (mode) => {
      if (dragging) return;
      pushHistory();            // the pre-drag document, once
      dragging = d;
      dragMode = mode;
      endDrag = end;
      d.classList.add('live');
    };
    const end = () => {
      if (dragging !== d) return;
      dragging = null;
      dragMode = null;
      endDrag = null;
      d.classList.remove('live');
      refocus = key;
      drawInspector();          // the hints below it read the value too
    };

    input.addEventListener('pointerdown', () => begin('pointer'));
    input.addEventListener('input', () => {
      out.textContent = fmt(Number(input.value));
      begin('key');             // keyboard arrows send no pointerdown
      onChange(Number(input.value), true);
    });
    input.addEventListener('change', () => {
      if (dragMode !== 'key') return;   // see the note above `dragging`
      onChange(Number(input.value), false);
      end();
    });
    // The last live commit already carries the released value, so a pointer
    // release settles the inspector and nothing else.
    const stop = () => { if (dragMode === 'pointer') end(); };
    input.addEventListener('pointerup', stop);
    input.addEventListener('pointercancel', stop);
    input.addEventListener('blur', stop);

    if (refocus === key) {
      refocus = null;
      requestAnimationFrame(() => input.focus({ preventScroll: true }));
    }
    return d;
  }

  function segment(name, opts, current, onChange) {
    const wrap = document.createElement('div');
    const lab = document.createElement('div');
    lab.className = 'field';
    lab.innerHTML = `<label>${name}</label>`;
    const row = document.createElement('div');
    row.className = 'seg';
    for (const [val, text] of opts) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = text;
      if (val === current) b.className = 'on';
      b.addEventListener('click', () => onChange(val));
      row.appendChild(b);
    }
    wrap.appendChild(lab); wrap.appendChild(row);
    return wrap;
  }

  function hint(text, tone) {
    const d = document.createElement('div');
    d.className = 'note' + (tone ? ' ' + tone : '');
    d.textContent = text;
    return d;
  }

  /* -- HUD and the height strip ------------------------------------ */
  function drawHud() {
    const t = state.track;
    const caps = M.caps || {};
    const bits = [];
    if (t) {
      bits.push([`${Math.round(t.units || 0)} units`,
                 (t.units || 0) > caps.units * 0.9]);
      bits.push([`${t.checkpoints} checkpoint${t.checkpoints === 1 ? '' : 's'}`, false]);
      bits.push([`${state.doc.moves.length}/${caps.moves} moves`,
                 state.doc.moves.length > caps.moves * 0.9]);
      if (state.lap) bits.push([`~${state.lap.ideal.toFixed(1)}s`, false]);
      if (t.closed) bits.push(['closed lap', false]);
      if ((t.closure || []).length) {
        bits.push([`solver adjusted ${t.closure.length}`, false]);
      }
    }
    $('hud').innerHTML = bits.map(([text, warn]) =>
      `<span class="${warn ? 'warn' : ''}">${text}</span>`).join('');
  }

  function drawProfile() {
    // A display, never a control - but not decoration either. `track-defects.md`
    // lists "a profile that dives and then climbs straight back up for no
    // reason" as a real defect, and it is invisible from a per-move rise field.
    const svg = $('prof');
    const line = state.track && state.track.line;
    svg.textContent = '';
    if (!line || line.length < 2) return;
    const ys = line.map(e => e.p[1]);
    const lo = Math.min(...ys), hi2 = Math.max(...ys);
    const span = Math.max(1e-6, hi2 - lo);
    const H = 52, PAD = 6;
    const xy = (i) => [i / (line.length - 1) * 1000,
                       H - PAD - (ys[i] - lo) / span * (H - 2 * PAD)];
    const ns = 'http://www.w3.org/2000/svg';
    const base = document.createElementNS(ns, 'line');
    base.setAttribute('x1', 0); base.setAttribute('x2', 1000);
    base.setAttribute('y1', H - PAD); base.setAttribute('y2', H - PAD);
    base.setAttribute('stroke', 'rgba(29,29,31,.14)');
    svg.appendChild(base);

    const path = document.createElementNS(ns, 'polyline');
    path.setAttribute('points', line.map((_, i) => xy(i).join(',')).join(' '));
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', 'rgba(29,29,31,.55)');
    path.setAttribute('stroke-width', '1.6');
    svg.appendChild(path);

    const span2 = (state.track.spans || [])[state.sel];
    if (span2) {
      const seg = document.createElementNS(ns, 'polyline');
      const pts = [];
      for (let i = span2[0]; i <= span2[1] && i < line.length; i++) pts.push(xy(i).join(','));
      seg.setAttribute('points', pts.join(' '));
      seg.setAttribute('fill', 'none');
      seg.setAttribute('stroke', '#e8453c');
      seg.setAttribute('stroke-width', '2.8');
      svg.appendChild(seg);
    }
    const climb = line.reduce((a, e, i) =>
      i ? a + Math.max(0, e.p[1] - line[i - 1].p[1]) : 0, 0);
    const fall = line.reduce((a, e, i) =>
      i ? a + Math.max(0, line[i - 1].p[1] - e.p[1]) : 0, 0);
    $('proflabel').textContent =
      `+${climb.toFixed(0)} climb · −${fall.toFixed(0)} fall`;
  }

  /* -- wiring ------------------------------------------------------- */
  const bar = $('add');
  for (const [t, text] of ADDABLE) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = text;
    b.addEventListener('click', () => addMove(t));
    bar.appendChild(b);
  }
  $('ride').addEventListener('click', () => toggleRide());
  $('frame').addEventListener('click', () => aim('frame-all'));
  $('undo').addEventListener('click', undo);
  $('drive').addEventListener('click', () => {
    // Parked on the server under a token rather than put in the URL: a document
    // is kilobytes and a URL is not the place for one. The editor keeps its own
    // copy, so a failure here costs a click and nothing else.
    const b = $('drive');
    b.disabled = true;
    fetch('/api/make/draft', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(state.doc),
    }).then(r => r.json()).then(j => {
      if (j.token) location.href = '/make/drive/' + j.token;
      else { showError(j.error); b.disabled = false; }
    }).catch(() => { showError('Could not reach the server.'); b.disabled = false; });
  });

  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault(); undo(); return;
    }
    if (e.key === 'Backspace' || e.key === 'Delete') { e.preventDefault(); deleteMove(); }
    if (e.key === 'ArrowDown' || e.key === 'j') {
      select(Math.min(state.doc.moves.length - 1, state.sel + 1));
    }
    if (e.key === 'ArrowUp' || e.key === 'k') select(Math.max(0, state.sel - 1));
    if (e.key === 'f' || e.key === 'F') aim(e.shiftKey ? 'frame-all' : 'frame');
    if (e.key === 'v' || e.key === 'V') toggleRide();
    if (e.key === 'Escape' && !$('codePane').hidden) closeCode();
    if (e.key === 'Escape' && !$('pubPane').hidden) closePublish();
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
      e.preventDefault(); openPublish();
    }
  });

  /* -- the Look tab -------------------------------------------------- *
   * A palette edit never goes to the server for its picture. The palette is
   * read by `buildTrack` and by the renderer and by nothing else, so the road
   * recolours locally in a few milliseconds - there is no ribbon to replay and
   * no closure to re-solve. What the server is asked for is the *words*: the
   * eight taste warnings live in `tracks/look.py` beside the contract they are
   * about, and a second copy of them in here is the drift that moved palettes
   * into Python in the first place.
   */
  let advice = [];                 // [{level, key, text}] from /api/make/look
  let notes = [];                  // [{level, at, text}] from /api/make/build
  let tab = 'move';

  function showTab(which) {
    tab = which;
    for (const b of document.querySelectorAll('.tab'))
      b.classList.toggle('on', b.dataset.tab === which);
    $('tabmove').hidden = which !== 'move';
    $('tablook').hidden = which !== 'look';
    $('tabscenery').hidden = which !== 'scenery';
    $('tabai').hidden = which !== 'ai';
    document.body.classList.toggle('aiwide', which === 'ai');
    if (which === 'look') drawLook();
    if (which === 'scenery') drawScenery();
    if (which === 'ai') openChat();
  }

  function pal() {
    // The document owns the palette. A track built from it carries a copy, and
    // editing the copy would be edited away by the next rebuild.
    if (!state.doc.pal) state.doc.pal = {};
    return state.doc.pal;
  }

  /** Repaint the world from the palette, with no round trip. */
  function repaint() {
    if (!state.track) return;
    state.track.pal = JSON.parse(JSON.stringify(pal()));
    // The placement list is drawn by `buildTrack`, so a placement edit is the
    // same few milliseconds of local work a colour is - no ribbon to replay and
    // no round trip. The server only needs it when the draft is handed to the
    // play page.
    state.track.placed = (state.doc.scenery || []).slice();
    state.built = buildTrack(state.track, T);
    renderer.setTrack(state.built);
    hi = null;
    highlight((state.track.spans || [])[state.sel]);
    askAdvice();
  }

  const askAdvice = throttle(() => {
    fetch('/api/make/look', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(pal()),
    }).then(r => r.json()).then(j => {
      advice = j.advice || [];
      if (j.ok === false && j.error) advice = [{ level: 'warn', key: 'road',
                                                text: j.error }];
      if (tab === 'look') drawLook();
    }).catch(() => {});
  }, 260);

  function adviceFor(path) {
    return advice.filter(a => (ADVICE_AT[a.key] || a.key) === path);
  }

  function adviceNode(a) {
    const d = document.createElement('div');
    d.className = 'adv ' + (a.level === 'warn' ? 'warn' : 'note');
    d.innerHTML = '<b>' + (a.level === 'warn' ? 'probably wrong'
                                              : 'worth a look') + '</b>';
    d.appendChild(document.createTextNode(a.text));
    return d;
  }

  function drawLook() {
    const host = $('look');
    host.textContent = '';

    // Borrow a look, first, because nobody should start from a colour wheel:
    // a palette that already works is the only good starting point, and this is
    // nineteen of them. Two stripes each - road over ground - which is the pair
    // the plan-view warning is about, so the chooser shows you the thing.
    const bh = document.createElement('div');
    bh.className = 'lgroup';
    bh.innerHTML = '<h3>Borrow a look</h3>';
    const grid = document.createElement('div');
    grid.className = 'borrow';
    for (const L of (M.looks || [])) {
      const b = document.createElement('button');
      b.type = 'button';
      b.title = 'Take ' + L.name + "'s palette";
      const sky = (L.pal.sky && L.pal.sky.stops) ? L.pal.sky.stops : null;
      const top = sky ? sky[Math.floor(sky.length / 2)][1] : (L.pal.fog || 0);
      b.innerHTML = '<i style="background:' + hex(top) + '"></i>'
                  + '<i style="background:' + hex(L.pal.road || 0) + '"></i>';
      b.addEventListener('click', () => borrowLook(L));
      grid.appendChild(b);
    }
    bh.appendChild(grid);
    host.appendChild(bh);

    const flagged = new Set(advice.map(a => ADVICE_AT[a.key] || a.key));
    for (const [title, keys] of LOOK) {
      const g = document.createElement('div');
      g.className = 'lgroup';
      g.innerHTML = '<h3>' + title + '</h3>';
      const sw = document.createElement('div');
      sw.className = 'swatches';
      for (const spec of keys) {
        const [path, kind] = spec;
        if (kind === 'c') sw.appendChild(swatch(spec, flagged.has(path)));
      }
      if (sw.children.length) g.appendChild(sw);
      for (const spec of keys) {
        if (spec[1] !== 'n') continue;
        g.appendChild(number(spec));
        for (const a of adviceFor(spec[0])) g.appendChild(adviceNode(a));
      }
      for (const spec of keys) {
        if (spec[1] !== 'c') continue;
        for (const a of adviceFor(spec[0])) g.appendChild(adviceNode(a));
      }
      host.appendChild(g);
    }

    host.appendChild(skyStops());

    if (!advice.length) {
      const ok = document.createElement('div');
      ok.className = 'allclear';
      ok.textContent = 'Nothing to flag. This palette is inside the range the '
                     + 'nineteen tracks in the pool sit in.';
      host.appendChild(ok);
    }
  }

  function swatch(spec, flagged) {
    const [path, , name] = spec;
    const d = document.createElement('label');
    d.className = 'sw' + (flagged ? ' flag' : '');
    // A key the palette does not carry still gets a control - that is what
    // "every key, for everyone" means - but it is drawn as absent and shows
    // what the track would fall back to. Six unset keys all painted a
    // confident grey read as a grey palette instead of as six unused keys.
    let cur = dig(pal(), path);
    const unset = cur == null;
    if (unset) cur = dig(M.fallback || {}, path);
    if (cur == null) cur = 0x808080;
    if (unset) d.classList.add('unset');
    const inp = document.createElement('input');
    inp.type = 'color';
    inp.value = hex(cur);
    inp.addEventListener('input', () => {
      d.classList.remove('unset');
      plant(pal(), path, unhex(inp.value));
      touchLook(true);
    });
    inp.addEventListener('change', () => touchLook(false));
    const t = document.createElement('span');
    t.textContent = name;
    d.appendChild(inp); d.appendChild(t);
    return d;
  }

  function number(spec) {
    const [path, , name, min, max, step] = spec;
    const cur = dig(pal(), path);
    const unset = cur == null;
    // Same rule as the swatches, and it matters more here: a slider parked at
    // its minimum is indistinguishable from somebody having chosen the minimum.
    let val = cur;
    if (val == null) val = dig(M.fallback || {}, path);
    if (val == null) val = min;
    val = Math.max(min, Math.min(max, val));
    const d = document.createElement('div');
    d.className = 'field' + (unset ? ' unset' : '');
    d.dataset.key = path;
    d.innerHTML = '<label>' + name + '<b>' + fmt(val) + '</b></label>';
    const inp = document.createElement('input');
    inp.type = 'range';
    inp.min = min; inp.max = max; inp.step = step; inp.value = val;
    const out = d.querySelector('b');
    inp.addEventListener('pointerdown', () => d.classList.add('live'));
    inp.addEventListener('input', () => {
      const v = Number(inp.value);
      out.textContent = fmt(v);
      d.classList.add('live');
      d.classList.remove('unset');
      plant(pal(), path, v);
      touchLook(true);
    });
    const done = () => { d.classList.remove('live'); touchLook(false); };
    inp.addEventListener('change', done);
    inp.addEventListener('pointerup', done);
    d.appendChild(inp);
    return d;
  }

  // A palette edit is cheap but not free - it rebuilds every mesh on the track -
  // so a drag repaints on a throttle and settles once on release. The pane is
  // only redrawn on release, for the same reason the move inspector is not
  // redrawn mid-drag: it would replace the input under the cursor.
  const repaintSoon = throttle(repaint, 90);
  function touchLook(live) {
    if (!live) pushHistory();
    setPending(true);
    repaintSoon();
    if (!live) setTimeout(() => { if (tab === 'look') drawLook(); }, 0);
    setPending(false);
  }

  function borrowLook(L) {
    pushHistory();
    // Whole, not merged. A half-taken palette is the worst of both - Sandy
    // Cove's sand under Tokyo's night sky is not either track's look - and the
    // keys the editor cannot draw (terrain, furniture, a shoreline) come along
    // rather than being silently dropped from the track that had them.
    state.doc.pal = JSON.parse(JSON.stringify(L.pal));
    repaint();
    drawLook();
  }

  function skyStops() {
    const g = document.createElement('div');
    g.className = 'lgroup';
    g.innerHTML = '<h3>The dome</h3>';
    const sky = (pal().sky && typeof pal().sky === 'object') ? pal().sky : null;
    const stops = (sky && sky.stops) ? sky.stops : null;
    if (!stops) {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'stopadd';
      b.textContent = '+ give this track a graded sky';
      b.addEventListener('click', () => {
        pushHistory();
        plant(pal(), 'sky.stops', [[0, 0x9fb8cc], [0.35, 0xc6d9e8],
                                   [0.5, 0xdcebf5], [0.62, 0xa9c9e6],
                                   [0.8, 0x74a5da], [1, 0x4478c4]]);
        repaint(); drawLook();
      });
      g.appendChild(b);
      for (const a of adviceFor('stops')) g.appendChild(adviceNode(a));
      return g;
    }

    // The gradient itself, top of the dome on the left. It is a picture of the
    // list under it, which is the only way a six-to-nine stop sky is legible.
    const bar = document.createElement('div');
    bar.className = 'grad';
    const sorted = stops.slice().sort((a, b) => a[0] - b[0]);
    bar.style.background = 'linear-gradient(90deg,'
      + sorted.map(([at, c]) => hex(c) + ' ' + (at * 100).toFixed(1) + '%')
              .join(',') + ')';
    g.appendChild(bar);

    const list = document.createElement('div');
    list.className = 'stops';
    stops.forEach(([at, c], i) => {
      const row = document.createElement('div');
      row.className = 'stop';
      const col = document.createElement('input');
      col.type = 'color'; col.value = hex(c);
      const pos = document.createElement('input');
      pos.type = 'range'; pos.min = 0; pos.max = 1; pos.step = 0.005;
      pos.value = at;
      const kill = document.createElement('button');
      kill.type = 'button'; kill.textContent = '×';
      kill.title = 'Remove this stop';
      // Six is the floor `look.advise` measures against, so the control agrees
      // with the advice instead of letting you walk under it and then say so.
      kill.disabled = stops.length <= 2;
      col.addEventListener('input', () => {
        stops[i][1] = unhex(col.value); touchLook(true);
      });
      col.addEventListener('change', () => { touchLook(false); });
      pos.addEventListener('input', () => {
        stops[i][0] = Number(pos.value); touchLook(true);
      });
      pos.addEventListener('change', () => { touchLook(false); });
      kill.addEventListener('click', () => {
        pushHistory(); stops.splice(i, 1); repaint(); drawLook();
      });
      row.appendChild(col); row.appendChild(pos); row.appendChild(kill);
      list.appendChild(row);
    });
    g.appendChild(list);

    const add = document.createElement('button');
    add.type = 'button'; add.className = 'stopadd';
    add.textContent = '+ another stop';
    add.addEventListener('click', () => {
      pushHistory();
      const s2 = stops.slice().sort((a, b) => a[0] - b[0]);
      // Halfway into the widest gap, coloured by the two it lands between: a
      // stop added at 0.5 on top of one already there does nothing visible and
      // reads as a broken button.
      let best = 0, gap = -1;
      for (let i = 1; i < s2.length; i++) {
        if (s2[i][0] - s2[i - 1][0] > gap) { gap = s2[i][0] - s2[i - 1][0]; best = i; }
      }
      const a = s2[best - 1] || [0, 0x9fb8cc], b = s2[best] || [1, 0x4478c4];
      const mid = (a[0] + b[0]) / 2;
      const mix = (x, y) => Math.round((x + y) / 2);
      stops.push([mid, (mix((a[1] >> 16) & 255, (b[1] >> 16) & 255) << 16)
                     | (mix((a[1] >> 8) & 255, (b[1] >> 8) & 255) << 8)
                     | mix(a[1] & 255, b[1] & 255)]);
      stops.sort((p, q) => p[0] - q[0]);
      repaint(); drawLook();
    });
    g.appendChild(add);
    for (const a of adviceFor('stops')) g.appendChild(adviceNode(a));
    return g;
  }

  for (const b of document.querySelectorAll('.tab'))
    b.addEventListener('click', () => showTab(b.dataset.tab));
  askAdvice();

  /* -- the scenery sandbox ------------------------------------------- *
   * One sentence: code runs while you author, geometry ships. A player's
   * JavaScript executes in a Worker inside an iframe with an opaque origin, and
   * what comes back is numbers. The play page, the switcher and the QuickJS
   * anti-cheat only ever see the numbers - none of them runs a stranger's code,
   * which is what makes this a feature rather than a remote code execution
   * hole with a nice UI.
   *
   * The three primitives the worker needs are *injected by source* rather than
   * copied into it: `sceneryContext`, `shade` and `mulberry` are pure top-level
   * functions, so `Function.prototype.toString()` puts the live engine version
   * in the sandbox with no possibility of the two drifting. That is not
   * fastidiousness - the first hand-written copy of `shade` in the worker had it
   * as a multiplier instead of an amount, which is a function that looks right
   * and darkens everything it touches.
   */
  const sandbox = {
    frame: null, booted: null, seq: 0, waiting: new Map(),

    async boot() {
      if (this.booted) return this.booted;
      this.booted = (async () => {
        const [host, work, kitSrc] = await Promise.all([
          fetch('/static/js/scenery_host.js').then(r => r.text()),
          fetch('/static/js/scenery_worker.js').then(r => r.text()),
          fetch('/static/js/scenery_kit.js').then(r => r.text()),
        ]);
        // The library, as source, with its module syntax removed - the same
        // thing `jsrt.py:_strip_modules` does to put this file into QuickJS.
        // Sent rather than reimplemented so a player's code, the engine's own
        // placements and the anti-cheat are drawing the same grandstand.
        const kit = kitSrc.replace(/^\s*import\s+[^;]*;\s*$/gm, '')
                          .replace(/^export\s+\{[^}]*\};?\s*$/gm, '')
                          .replace(/^export\s+/gm, '');
        // The engine's own functions, as text. `sceneryContext` takes every
        // input as a parameter and closes over nothing, which is what makes
        // this legitimate rather than a trick.
        const inject = 'const sceneryContext = ' + sceneryContext.toString()
                     + ';\nconst shade = ' + shade.toString()
                     + ';\nconst mulberry = ' + mulberry.toString() + ';\n';
        const f = document.createElement('iframe');
        // No `allow-same-origin`, and that omission is the whole point.
        f.setAttribute('sandbox', 'allow-scripts');
        f.style.display = 'none';
        f.srcdoc = '<!doctype html><meta charset="utf-8"><script>' + host
                 + '<\/script>';
        const ready = new Promise((res) => {
          const on = (e) => {
            if (e.source !== f.contentWindow) return;
            const m = e.data || {};
            if (m.type === 'hello') {
              f.contentWindow.postMessage(
                { type: 'boot', worker: inject + kit + work }, '*');
            } else if (m.type === 'ready') {
              res();
            } else if (m.type === 'done') {
              const w = this.waiting.get(m.id);
              if (w) { this.waiting.delete(m.id); w(m.result); }
            }
          };
          window.addEventListener('message', on);
        });
        document.body.appendChild(f);
        this.frame = f;
        await ready;
      })();
      return this.booted;
    },

    async run(code) {
      await this.boot();
      const id = ++this.seq;
      const job = jobFor(code);
      if (!job) return { ok: false, kind: 'host', error: 'No track to place '
                         + 'scenery on yet.' };
      const done = new Promise((res) => this.waiting.set(id, res));
      this.frame.contentWindow.postMessage({ type: 'run', id, job }, '*');
      return done;
    },
  };

  /** Everything the sandbox needs about this track, as plain data. */
  function jobFor(code) {
    if (!state.track || !state.built) return null;
    const t = state.track;
    // The line, and only the fields the four helpers read. Sending the whole
    // ribbon would be several times the size for nothing.
    const line = (t.line || []).map(e => ({ p: e.p, n: e.n, lat: e.lat }));
    return {
      code,
      track: { line, slug: 'draft', closed: !!t.closed },
      pal: t.pal || {},
      groundY: t.ground == null ? null : t.ground,
      bbox: state.built.bbox,
      terrain: sampleTerrain(),
      deadline: 2000,
    };
  }

  /**
   * A height field, sampled onto a grid.
   *
   * The field itself is a closure over the built ribbon and cannot cross a
   * postMessage, and rebuilding it in the sandbox would be a second
   * implementation of the one thing scenery is least able to guess at. So it is
   * measured instead: 128 by 128 over the bounding box is 64KB and about a
   * unit and a half of resolution on a big track, which is finer than anything
   * standing on it cares about.
   */
  function sampleTerrain() {
    const terrain = state.built && state.built.terrain;
    if (!terrain || !terrain.height) return null;
    const bb = state.built.bbox;
    const N = 128;
    const x0 = bb.x0, z0 = bb.z0;
    const dx = (bb.x1 - bb.x0) / (N - 1), dz = (bb.z1 - bb.z0) / (N - 1);
    const h = new Float32Array(N * N);
    for (let j = 0; j < N; j++) {
      for (let i = 0; i < N; i++) h[j * N + i] = terrain.height(x0 + i * dx,
                                                               z0 + j * dz);
    }
    return { x0, z0, dx, dz, nx: N, nz: N, h };
  }

  /* -- the library --------------------------------------------------- *
   * Eighteen models, dropped in by name and adjusted by number. The whole
   * point is that this is the path that does not need code: `{o: 'stand', at:
   * 0.1, side: -1, tiers: 9}` is a grandstand, and the engine knows how to draw
   * one on any track.
   *
   * It is drawn by `buildTrack`, which is what makes a placement reach the play
   * page, the switcher and the QuickJS anti-cheat with no further plumbing -
   * measured: a barrier placed here adds its triangles to the collider the
   * verifier re-drives laps against.
   */
  const KIT = catalogue();
  const KIT_BY_O = Object.fromEntries(KIT.map(k => [k.o, k]));

  function placements() {
    if (!Array.isArray(state.doc.scenery)) state.doc.scenery = [];
    return state.doc.scenery;
  }

  /** Where round the lap the move you are looking at is. */
  function selFraction() {
    const span = (state.track && state.track.spans || [])[state.sel];
    const n = ((state.track && state.track.line) || []).length;
    if (!span || n < 2) return 0.15;
    return Math.min(0.98, Math.max(0, span[0] / (n - 1)));
  }

  let scrollToPick = false;

  function addPlacement(o) {
    const p = placementDefaults(o);
    if (!p) return;
    scrollToPick = true;
    pushHistory();
    // Dropped where you are looking, not at the start line. The move you have
    // selected is the one you are working on, and a grandstand that appears
    // somewhere else is a grandstand you then have to go and find.
    p.at = Math.round(selFraction() * 500) / 500;
    if (p.to !== undefined) p.to = Math.min(1, p.at + 0.06);
    placements().push(p);
    state.pick = placements().length - 1;
    repaint();
    drawScenery();
  }

  function drawScenery() {
    const host = $('scenery');
    host.textContent = '';
    const list = placements();

    // -- what is on the track ------------------------------------------
    const head = document.createElement('div');
    head.className = 'lgroup';
    head.innerHTML = '<h3>On this track</h3>';
    if (!list.length) {
      const p = document.createElement('div');
      p.className = 'sccount';
      p.textContent = 'Nothing yet. Drop something in from the library below - '
        + 'it lands where the move you have selected is.';
      head.appendChild(p);
    } else {
      const ul = document.createElement('ul');
      ul.className = 'placed';
      list.forEach((p, i) => {
        const k = KIT_BY_O[p.o];
        const li = document.createElement('li');
        if (i === state.pick) li.className = 'sel';
        const nm = document.createElement('b');
        nm.textContent = k ? k.name : p.o;
        const at = document.createElement('span');
        at.textContent = (p.at * 100).toFixed(0) + '%'
          + (p.side !== undefined ? (p.side < 0 ? ' left' : ' right') : '');
        const x = document.createElement('button');
        x.type = 'button'; x.textContent = '×'; x.title = 'Remove';
        x.addEventListener('click', (e) => {
          e.stopPropagation();
          pushHistory();
          list.splice(i, 1);
          if (state.pick >= list.length) state.pick = list.length - 1;
          repaint(); drawScenery();
        });
        li.appendChild(nm); li.appendChild(at); li.appendChild(x);
        li.addEventListener('click', () => {
          state.pick = i;
          aimAtPlacement(p);
          scrollToPick = true;
          drawScenery();
        });
        ul.appendChild(li);
      });
      head.appendChild(ul);
    }
    host.appendChild(head);

    // -- the selected one's numbers ------------------------------------
    const cur = list[state.pick];
    if (cur && KIT_BY_O[cur.o]) {
      const k = KIT_BY_O[cur.o];
      const g = document.createElement('div');
      g.className = 'lgroup';
      g.innerHTML = '<h3>' + k.name + '</h3>';
      const b = document.createElement('div');
      b.className = 'note';
      b.textContent = k.blurb;
      g.appendChild(b);
      if (cur.side !== undefined) {
        g.appendChild(segment('which side', [['l', 'left'], ['r', 'right']],
          cur.side < 0 ? 'l' : 'r', (v) => {
            pushHistory();
            cur.side = v === 'l' ? -1 : 1;
            repaint(); drawScenery();
          }));
      }
      for (const [key, [lo, hi, step]] of Object.entries(k.params)) {
        g.appendChild(kitSlider(cur, key, lo, hi, step));
      }
      // The library is at the bottom of a long pane and these controls are at
      // the top of it, so without this you click Floodlight and nothing appears
      // to happen - the thing you just made is off-screen in the other
      // direction.
      if (scrollToPick) {
        scrollToPick = false;
        requestAnimationFrame(() => g.scrollIntoView(
          { block: 'nearest', behavior: 'smooth' }));
      }
      if (k.collides) {
        g.appendChild(hint('This one is solid: the car hits it, and it is in '
          + 'the collider the anti-cheat measures laps against. It is how you '
          + 'stop a corner being cut.', 'warn'));
      }
      host.appendChild(g);
    }

    // -- the library ---------------------------------------------------
    const groups = [];
    for (const k of KIT) {
      let g = groups.find(x => x[0] === k.group);
      if (!g) { g = [k.group, []]; groups.push(g); }
      g[1].push(k);
    }
    for (const [name, items] of groups) {
      const g = document.createElement('div');
      g.className = 'lgroup';
      g.innerHTML = '<h3>' + name + '</h3>';
      const grid = document.createElement('div');
      grid.className = 'kit';
      for (const k of items) {
        const b = document.createElement('button');
        b.type = 'button';
        b.title = k.blurb;
        b.textContent = k.name;
        if (k.collides) b.className = 'solid';
        b.addEventListener('click', () => addPlacement(k.o));
        grid.appendChild(b);
      }
      g.appendChild(grid);
      host.appendChild(g);
    }

    // -- and the escape hatch ------------------------------------------
    const g = document.createElement('div');
    g.className = 'lgroup';
    g.innerHTML = '<h3>Or write it</h3>';
    const p = document.createElement('div');
    p.className = 'sccount';
    p.textContent = baked
      ? (baked.counts.solid + baked.counts.bright).toLocaleString()
        + ' triangles from your code, ' + baked.counts.collider.toLocaleString()
        + ' of them solid.'
      : (code ? 'Written, not run yet.'
              : 'The library covers most things. Code is for when it does not - '
                + 'and the same models are on `ctx.kit`, so you can start from '
                + 'one.');
    g.appendChild(p);
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'scbtn';
    btn.textContent = code ? 'Open the code' : 'Write scenery in code';
    btn.addEventListener('click', () => openCode());
    g.appendChild(btn);
    host.appendChild(g);

    // -- anything the interpreter refused ------------------------------
    for (const why of ((state.built && state.built.sceneryProblems) || [])) {
      host.appendChild(adviceNode({ level: 'warn', text: why }));
    }
  }

  /** A slider bound to one field of one placement, live while dragged. */
  function kitSlider(p, key, lo, hi, step) {
    const d = document.createElement('div');
    d.className = 'field';
    d.dataset.key = key;
    d.innerHTML = '<label>' + KIT_LABEL[key] + '<b>' + fmt(p[key])
                + '</b></label>';
    const out = d.querySelector('b');
    const inp = document.createElement('input');
    inp.type = 'range';
    inp.min = lo; inp.max = hi; inp.step = step; inp.value = p[key];
    let began = false;
    inp.addEventListener('input', () => {
      if (!began) { began = true; pushHistory(); d.classList.add('live'); }
      const v = Number(inp.value);
      out.textContent = fmt(v);
      p[key] = v;
      // A range model whose end has crossed its start draws nothing, which
      // reads as a broken slider rather than an empty range.
      if (key === 'at' && p.to !== undefined && p.to < v) p.to = Math.min(1, v + 0.01);
      if (key === 'to' && v < p.at) p.at = Math.max(0, v - 0.01);
      repaintSoon();
    });
    const done = () => {
      if (!began) return;
      began = false;
      d.classList.remove('live');
      drawScenery();
    };
    inp.addEventListener('change', done);
    inp.addEventListener('pointerup', done);
    d.appendChild(inp);
    return d;
  }

  // Plain words for the parameter names, because `off` and `h` are the author's
  // problem only if the editor makes them so.
  const KIT_LABEL = {
    at: 'where round the lap', to: 'and ends at',
    off: 'distance from the road', h: 'height', w: 'width', len: 'length',
    tiers: 'rows', bays: 'garages', span: 'width over the road',
    size: 'size', spread: 'spread', lean: 'lean', r: 'radius',
    stack: 'how many stacked', wide: 'how many across',
    high: 'how many high', every: 'one every', side: 'which side',
  };

  function aimAtPlacement(p) {
    const line = state.track && state.track.line;
    if (!line || !line.length) return;
    const i = Math.round((p.at || 0) * (line.length - 1));
    const e = line[Math.max(0, Math.min(line.length - 1, i))];
    cam.target.set(e.p[0], e.p[1], e.p[2]);
  }

  /* -- the scenery tab and the code sheet ---------------------------- */
  // What an empty editor opens with. The first worked example rather than a
  // third copy of one: it is code the test suite runs, so what a player starts
  // from is known to work on their track rather than known to have compiled on
  // mine.
  const STARTER_CODE = [
    '// Scenery for your track. This runs in a sandbox while you are looking at',
    '// it. When you submit, the geometry is baked to numbers and it is the',
    '// numbers that ship - so nothing here ever runs on anybody else\'s',
    '// machine. Press "Copy API for your AI" before asking a model: no model',
    '// has seen this API, and it will guess three.js if you let it.',
    '',
    exampleSource(EXAMPLES[0][1]),
  ].join('\n');

  let code = state.doc.source || '';
  let baked = null;                  // the last good result out of the sandbox


  function openCode() {
    if (!code) code = STARTER_CODE;
    $('codeText').value = code;
    $('codePane').hidden = false;
    $('codeText').focus();
    runCode();
  }
  function closeCode() { $('codePane').hidden = true; }

  const runSoon = throttle(() => runCode(), 700);

  async function runCode() {
    code = $('codeText').value;
    state.doc.source = code;
    setStat('running…', '');
    const r = await sandbox.run(code);
    if (!r || !r.ok) {
      baked = null;
      showCodeError(r || { error: 'The sandbox did not answer.' });
      setStat('did not run', 'bad');
      applyScenery(null);
      drawScenery();
      return;
    }
    $('codeErr').hidden = true;
    baked = r;
    const tris = r.counts.solid + r.counts.bright;
    setStat(tris.toLocaleString() + ' triangles · '
            + r.counts.collider.toLocaleString() + ' collider · ' + r.ms + 'ms',
            'good');
    applyScenery(r);
    drawScenery();
  }

  function setStat(text, cls) {
    const e = $('codeStat');
    e.textContent = text;
    e.className = 'cstat' + (cls ? ' ' + cls : '');
  }

  /**
   * Errors written to be pasted back into a chat.
   *
   * The sandbox already knows what went wrong and, for the common mistakes, what
   * the right call is. Saying both turns the loop into paste the error, get the
   * fix, run - which is most of the value of the AI panel and costs almost
   * nothing.
   */
  const HINTS = [
    [/\bTHREE\b/, 'This API has no THREE and no DOM. To stand a box:\n'
      + '  solid.box(x, y, z, hx, hy, hz, colour)\n'
      + 'Position it off the ribbon, never in world space:\n'
      + '  const i = at(0.42), [x, z] = spot(i, 40);\n'
      + '  const y = ground(i, 40);'],
    [/\b(document|window|localStorage|fetch)\b/,
      'There is no DOM, no storage and no network in here. Everything you need '
      + 'is on ctx - see Copy API for your AI.'],
    [/KIND\.(BOOST|BOUNCE|ROAD)|only add KIND/,
      'Scenery may only add KIND.WALL and KIND.OFFROAD. If you want the car to '
      + 'bounce off it, that is KIND.WALL.'],
    [/not three finite numbers/,
      'Something arithmetic came out undefined or NaN. `spot()` returns two '
      + 'numbers - [x, z] - so a point is [x, ground(i, off), z], not spot() '
      + 'on its own.'],
    [/props is not defined|is not a function/,
      'The sandbox calls `props(ctx)`. Define exactly that:\n'
      + '  function props(ctx) { ... }'],
  ];

  function errorText(r) {
    let out = (r.name ? r.name + ': ' : '') + (r.error || 'Something failed.');
    if (r.stack) out += '\n' + r.stack;
    for (const [re, say] of HINTS) {
      if (re.test(out) || re.test(code)) { out += '\n\n' + say; break; }
    }
    return out;
  }

  function showCodeError(r) {
    $('codeErr').hidden = false;
    $('codeErrKind').textContent = {
      refused: 'not allowed', budget: 'over budget', geometry: 'not a point',
      timeout: 'too slow', syntax: 'will not parse', host: 'sandbox',
      throw: 'threw',
    }[r.kind] || 'error';
    $('codeErrText').textContent = errorText(r);
  }

  /** Put the baked geometry into the world, as three meshes and a collider. */
  let userMesh = null;
  function applyScenery(r) {
    if (userMesh) {
      renderer.scene.remove(userMesh);
      userMesh.traverse(o => { if (o.geometry) o.geometry.dispose(); });
      userMesh = null;
    }
    if (!r) return;
    const grp = new THREE.Group();
    for (const [part, mat] of [['solid', 'lambert'], ['bright', 'basic']]) {
      const b = r[part];
      if (!b || !b.pos.length) continue;
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(b.pos, 3));
      g.setAttribute('color', new THREE.Float32BufferAttribute(b.col, 3));
      g.computeVertexNormals();
      grp.add(new THREE.Mesh(g, mat === 'lambert'
        ? new THREE.MeshLambertMaterial({ vertexColors: true })
        : new THREE.MeshBasicMaterial({ vertexColors: true })));
    }
    renderer.scene.add(grp);
    userMesh = grp;
  }

  /**
   * The whole API, the rules and two worked examples, on the clipboard.
   *
   * Generated from `CTX_API` rather than written out as prose, so a change to
   * what the sandbox hands over is a change to what the spec says. About 3KB,
   * which is nothing to paste and enough to turn a model that has never seen
   * this API into one that can write against it.
   */
  function apiSpec() {
    const L = [];
    L.push('# Drive scenery API');
    L.push('');
    L.push('You are writing scenery for a track in a browser racing game. Reply');
    L.push('with one JavaScript function and nothing else:');
    L.push('');
    L.push('    function props(ctx) { ... }');
    L.push('');
    L.push('It runs in a sandbox with no DOM, no network and no three.js. Every');
    L.push('drawing call is on `ctx`. Destructure what you need from it.');
    L.push('');
    L.push('## What is on ctx');
    L.push('');
    for (const [sig, ret, why] of CTX_API) {
      L.push('- `' + sig + '` -> ' + ret);
      L.push('  ' + why.replace(/\s+/g, ' '));
    }
    L.push('');
    L.push('## Five rules');
    L.push('');
    L.push('1. **Derive every position from the ribbon.** at() then spot() then');
    L.push('   ground(). There is no way to write a world coordinate and that is');
    L.push('   deliberate: the layout is re-solved for closure, so anything with');
    L.push('   a literal coordinate in it is wrong after the next edit.');
    L.push('2. **Draw quads with face(), which draws both windings.** The world');
    L.push('   material is FrontSide. One winding is invisible from one side.');
    L.push('3. **Stand everything on ground(i, off).** Not on 0, not on a');
    L.push('   guess. Geometry floating in the sky is the most common mistake.');
    L.push('4. **Only KIND.WALL and KIND.OFFROAD may reach the collider.**');
    L.push('   BOOST, BOUNCE and ROAD are refused by the sandbox.');
    L.push('5. **Budgets:** ' + 20000 .toLocaleString() + ' mesh triangles,');
    L.push('   2,500 collider triangles, and it must finish in two seconds.');
    L.push('   A loop over every station inside a loop over every station is');
    L.push('   hundreds of thousands of quads - do not.');
    L.push('');
    L.push('## The library');
    L.push('');
    L.push('Eighteen models the engine can draw. Prefer these over building');
    L.push('something out of boxes - they are aligned to the road, they stand');
    L.push('on the ground, and they take their colours from the palette.');
    L.push('');
    for (const k of KIT) {
      const ps = Object.entries(k.params)
        .map(([n, [lo, hi, , d]]) => n + ' ' + lo + '..' + hi + ' (' + d + ')')
        .join(', ');
      L.push('- `' + k.o + '` — ' + k.name + '. '
             + String(k.blurb).replace(/\s+/g, ' '));
      L.push('  ' + ps + (k.params.off ? ', side -1 or 1' : '')
             + (k.collides ? '. **Solid: this one changes lap times.**' : ''));
    }
    L.push('');
    L.push('## Worked examples');
    L.push('');
    for (const [, fn] of EXAMPLES) {
      L.push('```js');
      L.push(exampleSource(fn));
      L.push('```');
      L.push('');
    }
    L.push('');
    // Deliberately says nothing about *this* track: everything track-specific
    // lives in `trackContext`, on the other side of the cache breakpoint. One
    // station count in here would invalidate 9KB of prefix on every edit.
    return L.join('\n');
  }



  /**
   * The move vocabulary, written out for a model.
   *
   * This is the half no model can guess at. Scenery at least looks like
   * graphics code; a document of `{"t": "arc", "deg": -150, "rad": 17}` looks
   * like nothing at all, and a model asked to help with a track layout without
   * this writes three.js, or a Bezier curve, or an SVG path. Built from
   * `M.vocab`, which app.py generates from `moves.SPEC` and `moves.HELP`, so a
   * move gaining a field is a move whose description gains it too.
   */
  function layoutSpec() {
    const V = M.vocab || { moves: [], limits: {}, per_move: {} };
    const L = [];
    L.push('# Drive track layout');
    L.push('');
    L.push('A track is an ordered list of moves - a turtle walking a road into');
    L.push('existence. There are no coordinates and no curves: you say "turn 90');
    L.push('degrees on a 46 radius" and the road goes there. One unit is about a');
    L.push('metre, a road is 9 wide by default.');
    L.push('');
    L.push('    {"t": "arc", "deg": -150, "rad": 17, "rise": 7}');
    L.push('');
    L.push('## The vocabulary');
    L.push('');
    for (const m of V.moves) {
      const f = Object.entries(m.fields)
        .map(([k, d]) => k + (d === 'required' ? ' (required)'
             : d === null ? '' : ' = ' + JSON.stringify(d)))
        .join(', ');
      L.push('### ' + m.t + (f ? '  —  ' + f : ''));
      L.push(String(m.what).replace(/\s+/g, ' '));
      L.push('');
    }
    L.push('## On every move that lays road');
    L.push('');
    for (const [k, why] of Object.entries(V.per_move)) {
      L.push('- `' + k + '`: ' + why);
    }
    L.push('');
    L.push('Carried on the move itself and never inherited from the one before.');
    L.push('In a list you can reorder, and sticky width means deleting one move');
    L.push('silently rewidens nine others.');
    L.push('');
    L.push('## Rules that are not opinions');
    L.push('');
    const lim = V.limits;
    L.push('- Exactly one `start`, first. Exactly one `finish` or');
    L.push('  `finish_at_start`, last.');
    L.push('- `arc.rad` below ' + lim.min_arc_radius + ' cannot be driven at all.');
    L.push('- `loop.rad` below ' + lim.min_loop_radius + ' cannot be driven at');
    L.push('  racing speed however good the geometry is.');
    L.push('- At most ' + lim.moves + ' moves and ' + lim.units + ' units of road.');
    L.push('- Use at least ' + lim.distinct_radii + ' different corner radii. A');
    L.push('  lap where every corner is the same corner has nothing to learn.');
    L.push('- A closed lap (`finish_at_start`) is re-solved so the two ends');
    L.push('  meet. Mark the legs it may adjust with');
    L.push('  `"free": ["len"]` on a straight or `["deg"]` on an arc, and it can');
    L.push('  stretch one by at most '
           + Math.round((lim.closure_stretch || 0.15) * 100) + '%. Without');
    L.push('  enough free legs the lap refuses to close and nothing builds.');
    L.push('- Turn one should not be more than ' + lim.first_turn_deg
           + ' degrees away from');
    L.push('  the pole side, or the car on pole starts on the outside of it.');
    L.push('');
    L.push('## What makes a track good rather than valid');
    L.push('');
    L.push('- Vary the corner radii. Six identical 40s in a row is a road, not a');
    L.push('  circuit.');
    L.push('- Something has to be at stake somewhere: a hill you carry speed');
    L.push('  over, a gap that is only clearable if you got the corner right.');
    L.push('- A pad belongs where the speed is usable - out of a slow corner,');
    L.push('  into a jump - and never into a braking zone.');
    L.push('- Three or four checkpoints round a lap.');
    L.push('- Do not make it long for the sake of it. Cutting the last movement');
    L.push('  off a track is almost always free.');
    L.push('');
    L.push('## How to change a layout');
    L.push('');
    L.push('Reply with an **edit script**, not the whole track:');
    L.push('');
    L.push('```json');
    L.push('{"ops": [');
    L.push('  {"op": "set",     "at": 6,  "fields": {"rad": 24}},');
    L.push('  {"op": "insert",  "at": 9,  "moves": [{"t": "arc", "deg": -158, "rad": 16}]},');
    L.push('  {"op": "delete",  "at": 11, "count": 2},');
    L.push('  {"op": "replace", "at": 4,  "moves": [{"t": "straight", "len": 80}]}');
    L.push(']}');
    L.push('```');
    L.push('');
    L.push('`at` is the number in the listing below, always as you see it now:');
    L.push('the ops are applied from the highest index down, so one insert does');
    L.push('not shift the index of the next op. `set` merges fields and leaves');
    L.push('the rest of the move alone.');
    L.push('');
    L.push('An edit script rather than a whole document for two reasons, and');
    L.push('neither is size. It says what you meant - "make turn three tighter"');
    L.push('is one `set`, and a rewritten document is 400 moves the author has');
    L.push('to read to find your change in. And it cannot rewrite something by');
    L.push('accident on the way past.');
    L.push('');
    L.push('If you are genuinely redesigning the whole track, `{"moves": [...]}`');
    L.push('with the complete list is accepted too. Do not use it for an edit.');
    return L.join('\n');
  }

  /**
   * The track as it is, compactly. Rebuilt every turn; the vocabulary is not.
   *
   * One line per move, only the fields that are not the default, and width and
   * barriers only where they change. On a twelve-move sprint that is 300 bytes
   * against 1.6KB of JSON, and on a long track the difference is the difference
   * between a chat that stays affordable and one that does not - the document
   * is the one part of the prompt that cannot be cached, because it changes on
   * every edit.
   *
   * Indices are explicit and are what the edit script addresses.
   */
  function trackContext() {
    const L = [];
    const V = M.vocab || { moves: [] };
    const defaults = {};
    for (const m of V.moves) defaults[m.t] = m.fields || {};

    L.push('# The track being edited, right now');
    L.push('');
    L.push('- name: ' + (state.doc.name || 'untitled')
           + ', difficulty ' + (state.doc.difficulty || 3));
    L.push('- ' + (state.doc.closed ? 'a closed lap (finishes on the start line)'
                                    : 'point to point'));
    L.push('- default road width ' + state.doc.width
           + (state.doc.ground == null
              ? ', and no ground at all - it floats in a void, so it needs '
                + 'barriers' : ', ground at ' + state.doc.ground));
    if (state.track) {
      L.push('- ' + Math.round(state.track.units || 0) + ' units of road, '
             + (state.track.line || []).length + ' stations'
             + (state.lap && state.lap.ideal
                ? ', a lap takes about ' + state.lap.ideal.toFixed(1) + 's'
                : ''));
    }
    L.push('');
    L.push('## Moves');
    L.push('');
    L.push('```');
    let w = null, rail = null;
    (state.doc.moves || []).forEach((m, i) => {
      const parts = [String(i).padStart(3, ' '), m.t];
      const d = defaults[m.t] || {};
      for (const [k, v] of Object.entries(m)) {
        if (k === 't' || k === 'w' || k === 'rail' || k === 'free') continue;
        // The default is the thing not worth a token: a model reading
        // `ease=true` on every straight learns that it matters, and it does not.
        if (d[k] !== 'required' && JSON.stringify(d[k]) === JSON.stringify(v)) {
          continue;
        }
        parts.push(k + '=' + JSON.stringify(v));
      }
      if (m.free && m.free.length) parts.push('free=' + m.free.join('+'));
      // Only where it changes, which is how the editor's own list shows it -
      // and it is honest, because the value is carried on every move but is
      // almost always the same as the one before.
      if (m.w !== undefined && m.w !== w) { parts.push('width=' + m.w); w = m.w; }
      if (m.rail !== undefined && m.rail !== rail) {
        parts.push('rails=' + (m.rail || 'none')); rail = m.rail;
      }
      L.push(parts.join(' '));
    });
    L.push('```');

    const pal = state.doc.pal || {};
    const cols = Object.keys(pal).filter(k => typeof pal[k] === 'number');
    if (cols.length) {
      L.push('');
      L.push('## Palette keys with a colour in them');
      L.push('');
      L.push(cols.join(', ') + ' — take scenery colours from these so it '
             + 'follows a palette change instead of fighting it.');
    }
    L.push('');
    L.push('## Scenery already placed');
    L.push('');
    const pl = state.doc.scenery || [];
    if (!pl.length) {
      L.push('Nothing from the library yet.');
    } else {
      for (const p of pl) {
        L.push('- ' + JSON.stringify(p));
      }
    }
    L.push('');
    L.push('## Scenery code');
    L.push('');
    if (code) {
      L.push('```js');
      L.push(code);
      L.push('```');
      if (baked) {
        L.push('');
        L.push('That currently draws ' + (baked.counts.solid
               + baked.counts.bright) + ' triangles and adds '
               + baked.counts.collider + ' to the collider.');
      }
    } else {
      L.push('None yet.');
    }
    if (notes.length) {
      L.push('');
      L.push('## The editor is currently complaining about');
      L.push('');
      for (const n of notes) {
        L.push('- ' + (n.at != null ? 'move ' + n.at + ': ' : '')
               + n.text.replace(/\s+/g, ' '));
      }
    }
    return L.join('\n');
  }

  /**
   * The prompt, in two blocks, and the split is the whole optimisation.
   *
   * `stat` is the vocabulary and the scenery API: about 9KB, byte-identical on
   * every turn of every chat on every track. `live` is the track itself, which
   * changes whenever anything is edited and therefore can never be cached.
   *
   * Keeping them in that order and in that shape is what makes the caching
   * work - all three providers cache on a *prefix*, so one dynamic byte early
   * in the prompt throws away the whole thing. Anthropic gets an explicit
   * breakpoint between them; the other two get the same benefit implicitly.
   */
  function promptBlocks() {
    return {
      stat: [
        'You are helping somebody build a track in Drive, a browser racing',
        'game. They may ask about the layout, the scenery, or both. Two things',
        'you can produce, and the fence tag says which:',
        '',
        '- **a layout edit**: one ```json block. See "How to change a layout".',
        '- **scenery placements**: one ```json block of',
        '  {"scenery": [{"o": "stand", "at": 0.1, "side": -1, ...}]}. Prefer',
        '  this over code whenever the library covers what they asked for -',
        '  the author gets sliders for every number, which they do not get for',
        '  code.',
        '- **scenery code**: one ```js block containing a whole',
        '  `function props(ctx)`. For when the library does not cover it.',
        '',
        'Never both in one reply. Say in a sentence or two what you did and',
        'why. Do not explain the API back to them - they can read it.',
        '',
        'Nothing you produce is applied without the author seeing it: a layout',
        'edit is shown as a diff with an Apply button, and scenery lands in an',
        'editor they can read. So propose the real change rather than the',
        'cautious one.',
        '',
        '---',
        '',
        layoutSpec(),
        '',
        '---',
        '',
        apiSpec(),
      ].join('\n'),
      live: trackContext(),
    };
  }

  /**
   * A minimal edit script between two move lists.
   *
   * A model asked to add a hairpin returns the whole document, and on the way
   * past it can quietly rewrite four other corners - so the author is shown
   * what would actually change rather than a count. Longest common subsequence
   * on the stringified moves: the lists are at most 400 long, so the table is
   * trivial and the answer is the real minimum rather than a positional guess.
   */
  function diffMoves(a, b) {
    const A = a.map(m => JSON.stringify(m)), B = b.map(m => JSON.stringify(m));
    const n = A.length, m2 = B.length;
    const t = [];
    for (let i = 0; i <= n; i++) t.push(new Uint16Array(m2 + 1));
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m2 - 1; j >= 0; j--) {
        t[i][j] = A[i] === B[j] ? t[i + 1][j + 1] + 1
                                : Math.max(t[i + 1][j], t[i][j + 1]);
      }
    }
    const out = [];
    let i = 0, j = 0;
    while (i < n && j < m2) {
      if (A[i] === B[j]) { out.push(['same', a[i]]); i++; j++; }
      else if (t[i + 1][j] >= t[i][j + 1]) { out.push(['del', a[i]]); i++; }
      else { out.push(['add', b[j]]); j++; }
    }
    while (i < n) out.push(['del', a[i++]]);
    while (j < m2) out.push(['add', b[j++]]);
    return out;
  }

  function diffNode(script) {
    const d = document.createElement('div');
    d.className = 'diff';
    let shown = 0, hidden = 0;
    for (const [op, mv] of script) {
      // Unchanged runs are context, not content: two either side of a change is
      // enough to see where it is, and a 60-move list of `same` is noise.
      if (op === 'same') { hidden++; continue; }
      if (hidden) {
        if (shown) {
          const r = document.createElement('div');
          r.className = 'more';
          r.textContent = hidden + ' unchanged';
          d.appendChild(r);
        }
        hidden = 0;
      }
      const r = document.createElement('div');
      r.className = 'drow ' + op;
      r.innerHTML = '<i>' + (op === 'add' ? '+' : '−') + '</i>';
      r.appendChild(document.createTextNode(label(mv).replace(/[▶⚑⛳]\s*/, '')));
      d.appendChild(r);
      shown++;
    }
    if (!shown) {
      const r = document.createElement('div');
      r.className = 'more';
      r.textContent = 'nothing would change';
      d.appendChild(r);
    }
    return d;
  }

  /**
   * A placement list a model has proposed.
   *
   * Checked against the library here rather than by drawing it and seeing what
   * happens: an unknown `o` is a model the author's AI invented, and the answer
   * to that is its name and the eighteen that exist - not a silent gap in the
   * scenery.
   */
  function proposeScenery(text, into) {
    let doc = null;
    try { doc = JSON.parse(text); } catch (e) {
      say('err', 'That was not valid JSON: ' + e.message);
      return;
    }
    const list = Array.isArray(doc) ? doc : doc && doc.scenery;
    if (!Array.isArray(list) || !list.length) {
      say('err', 'That JSON has no `scenery` array in it.');
      return;
    }
    const unknown = [...new Set(list.map(p => p && p.o)
                                    .filter(o => !KIT_BY_O[o]))];
    if (unknown.length) {
      say('err', 'There is no model called ' + unknown.map(o => '"' + o + '"')
        .join(' or ') + '. The library is: ' + KIT.map(k => k.o).join(', ')
        + '.\n\nPaste this back and it can pick a real one.');
      return;
    }
    const was = placements().length;
    into.appendChild(document.createTextNode(
      '\n' + list.length + ' placement' + (list.length === 1 ? '' : 's') + ': '
      + list.map(p => KIT_BY_O[p.o].name).join(', ')));
    const row = document.createElement('div');
    row.className = 'diff';
    for (const p of list) {
      const r = document.createElement('div');
      r.className = 'drow add';
      r.innerHTML = '<i>+</i>';
      r.appendChild(document.createTextNode(
        KIT_BY_O[p.o].name + '  ' + Math.round((p.at || 0) * 100) + '%'
        + (p.side !== undefined ? (p.side < 0 ? ' left' : ' right') : '')));
      row.appendChild(r);
    }
    into.appendChild(row);
    const go = document.createElement('button');
    go.type = 'button'; go.className = 'apply';
    go.textContent = was ? 'Add these to the ' + was + ' already there'
                         : 'Place these';
    go.addEventListener('click', () => {
      pushHistory();
      placements().push(...list);
      state.pick = placements().length - 1;
      repaint();
      if (tab === 'scenery') drawScenery();
      go.textContent = 'Placed';
      go.className = 'apply done';
      go.disabled = true;
    });
    into.appendChild(go);
    $('aiMsgs').scrollTop = $('aiMsgs').scrollHeight;
  }

  /**
   * A layout a model has proposed. Validated, shown, and applied only on ask.
   *
   * Validated by the real builder rather than by a schema check here: the
   * document goes to `/api/make/build`, which replays it through the same
   * `tracks/builder.py` that builds Spa - so a closed lap that cannot close and
   * a corner nothing can drive are both caught by the thing that would have to
   * cope with them, and the error is the error the author would have seen.
   */
  /**
   * Apply an edit script to a move list, without mutating the original.
   *
   * Highest index first, which is the whole reason the indices are unambiguous:
   * every `at` refers to the list as the model was shown it, and working
   * backwards means an insert at 9 cannot shift the meaning of a delete at 4.
   * Sorting here rather than asking the model to order them is the right side of
   * that trade - it is one comparator, and the alternative is a rule in the
   * prompt that will sometimes be got wrong and always be got wrong silently.
   */
  function applyOps(moves, ops) {
    const out = moves.map(m => JSON.parse(JSON.stringify(m)));
    const sorted = ops.slice().sort((a, b) => (b.at | 0) - (a.at | 0));
    for (const op of sorted) {
      const at = Math.max(0, Math.min(out.length, op.at | 0));
      const what = (op.op || '').toLowerCase();
      if (what === 'set') {
        if (!out[at]) throw new Error('set at ' + op.at + ': there is no move '
          + op.at + ' - the track has ' + out.length + '.');
        Object.assign(out[at], op.fields || {});
      } else if (what === 'insert') {
        out.splice(at, 0, ...(op.moves || []));
      } else if (what === 'delete') {
        out.splice(at, Math.max(1, op.count | 0 || 1));
      } else if (what === 'replace') {
        out.splice(at, Math.max(1, op.count | 0 || 1), ...(op.moves || []));
      } else {
        throw new Error('"' + op.op + '" is not an op. It is one of set, '
          + 'insert, delete, replace.');
      }
    }
    return out;
  }

  async function proposeLayout(text, into) {
    let doc = null;
    try { doc = JSON.parse(text); } catch (e) {
      say('err', 'That layout was not valid JSON: ' + e.message);
      return;
    }
    let moves = null;
    if (doc && Array.isArray(doc.ops)) {
      try {
        moves = applyOps(state.doc.moves || [], doc.ops);
      } catch (e) {
        say('err', 'That edit script would not apply: ' + e.message);
        return;
      }
    } else {
      moves = doc && (Array.isArray(doc) ? doc : doc.moves);
    }
    if (!Array.isArray(moves) || !moves.length) {
      say('err', 'That JSON has neither an `ops` list nor a `moves` array.');
      return;
    }
    const next = Object.assign({}, state.doc,
                               Array.isArray(doc) ? {} : doc, { moves });
    delete next.ops;
    const r = await fetch('/api/make/build', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(next),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      say('err', 'That layout does not build: ' + (j.error || r.status)
        + '\n\nCopy this back into the chat - it is the same message the '
        + 'editor would show you.');
      return;
    }
    const refused = (j.notes || []).filter(n => n.level === 'refuse');
    if (refused.length) {
      // It built. It cannot be driven. Applying it would put the author in a
      // state the submit gate refuses anyway, several edits later and with no
      // memory of where it came from.
      say('err', 'That layout builds but cannot be driven, so it has not been '
        + 'offered:\n\n' + refused.map(n => '• ' + n.text).join('\n\n')
        + '\n\nPaste this back and it can fix it.');
      return;
    }
    const script = diffMoves(state.doc.moves, moves);
    const adds = script.filter(x => x[0] === 'add').length;
    const dels = script.filter(x => x[0] === 'del').length;
    into.appendChild(document.createTextNode(
      '\n' + moves.length + ' moves, ' + Math.round(j.track.units || 0)
      + ' units' + (adds || dels ? ' — ' + adds + ' added, ' + dels
                                   + ' removed' : '')));
    into.appendChild(diffNode(script));
    for (const n of (j.notes || [])) {
      into.appendChild(adviceNode({ level: 'note', text: n.text }));
    }
    const go = document.createElement('button');
    go.type = 'button'; go.className = 'apply';
    go.textContent = 'Apply this layout';
    go.addEventListener('click', () => {
      pushHistory();
      state.doc = next;
      state.sel = Math.min(state.sel, moves.length - 1);
      drawMoves(); drawInspector(); drawProfile();
      rebuild('edit');
      go.textContent = 'Applied';
      go.className = 'apply done';
      go.disabled = true;
    });
    into.appendChild(go);
    $('aiMsgs').scrollTop = $('aiMsgs').scrollHeight;
  }

  /* -- the chat ------------------------------------------------------ */
  const ai = { provider: 'claude', model: null, turns: [], busy: false };

  const keyOf = (p) => 'drive.ai.key.' + p;
  function loadKey(p) {
    try { return localStorage.getItem(keyOf(p)) || ''; } catch (e) { return ''; }
  }
  function saveKey(p, v) {
    try {
      if (v) localStorage.setItem(keyOf(p), v);
      else localStorage.removeItem(keyOf(p));
    } catch (e) { /* private mode */ }
  }

  function initChat() {
    const ps = $('aiProvider');
    ps.textContent = '';
    for (const [id, P] of Object.entries(PROVIDERS)) {
      const o = document.createElement('option');
      o.value = id; o.textContent = P.name;
      ps.appendChild(o);
    }
    try {
      const was = localStorage.getItem('drive.ai.provider');
      if (was && PROVIDERS[was]) ai.provider = was;
    } catch (e) { /* private mode */ }
    ps.value = ai.provider;
    ps.addEventListener('change', () => {
      ai.provider = ps.value;
      try { localStorage.setItem('drive.ai.provider', ai.provider); }
      catch (e) { /* private mode */ }
      fillModels();
      showKeyRow(!loadKey(ai.provider));
    });
    fillModels();
    $('aiModel').addEventListener('change', () => { ai.model = $('aiModel').value; });
    $('aiKeyBtn').addEventListener('click',
      () => showKeyRow($('aiKeyRow').hidden));
    $('aiKeySave').addEventListener('click', () => {
      saveKey(ai.provider, $('aiKey').value.trim());
      $('aiKey').value = '';
      showKeyRow(false);
      say('ai', 'Key saved in this browser. It goes straight to '
        + PROVIDERS[ai.provider].name + ' and never to this site.');
    });
    $('aiForm').addEventListener('submit', (e) => { e.preventDefault(); ask(); });
    $('aiInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault(); ask();
      }
    });
    showKeyRow(!loadKey(ai.provider));
  }

  function fillModels() {
    const ms = $('aiModel');
    ms.textContent = '';
    for (const m of PROVIDERS[ai.provider].models) {
      const o = document.createElement('option');
      o.value = m; o.textContent = m;
      ms.appendChild(o);
    }
    ai.model = PROVIDERS[ai.provider].models[0];
    ms.value = ai.model;
  }

  function showKeyRow(on) {
    $('aiKeyRow').hidden = !on;
    $('aiKeyNote').textContent = on
      ? PROVIDERS[ai.provider].keyHint + ' It is kept in this browser only and '
        + 'sent straight to ' + PROVIDERS[ai.provider].name + ' - this site '
        + 'never sees it, and there is no server of ours in the middle.'
      : '';
  }

  function say(who, text, art) {
    const d = document.createElement('div');
    d.className = 'msg ' + who;
    d.appendChild(document.createTextNode(text));
    if (art && art.kind === 'scenery') {
      // Code is shown, because reading it is how the API gets learned - and
      // because the author is the one publishing it under their own name.
      const pre = document.createElement('pre');
      pre.textContent = art.body;
      d.appendChild(pre);
      const use = document.createElement('button');
      use.type = 'button'; use.className = 'use';
      use.textContent = 'Use this scenery';
      use.addEventListener('click', () => {
        code = art.body;
        $('codeText').value = art.body;
        $('codePane').hidden = false;
        runCode();
        use.textContent = 'In the editor';
      });
      d.appendChild(use);
    }
    $('aiMsgs').appendChild(d);
    $('aiMsgs').scrollTop = $('aiMsgs').scrollHeight;
    // Neither a layout nor a placement list is pasted anywhere - both are shown
    // against the track and wait for the author to press Apply.
    if (art && art.kind === 'layout') proposeLayout(art.body, d);
    if (art && art.kind === 'placements') proposeScenery(art.body, d);
    return d;
  }

  /**
   * What the reply is offering, if anything: a layout or some scenery.
   *
   * The fence tag decides, because the system prompt asks for exactly one and
   * says which tag means which. The fallback sniff is for a model that returns
   * bare code with no fence at all, which happens - and a bare document is
   * unmistakable: it starts with a brace and has a `"moves"` in it.
   */
  function pickArtefact(text) {
    const fenced = /```(js|javascript|json)?\s*\n([\s\S]*?)```/.exec(text);
    if (fenced) {
      const body = fenced[2].trim();
      const tag = (fenced[1] || '').toLowerCase();
      if (tag === 'json') {
        // One tag, two documents. Which one is unambiguous from the keys, and
        // asking a model to remember two different fence tags would be one more
        // rule to get silently wrong.
        return { kind: /"scenery"\s*:/.test(body) && !/"(ops|moves)"\s*:/
                   .test(body) ? 'placements' : 'layout', body };
      }
      if (tag) return { kind: 'scenery', body };
      // Untagged: guess from the first character, which is reliable here
      // because one of the two is JSON and the other never starts with a brace.
      return { kind: body.startsWith('{') || body.startsWith('[')
                 ? 'layout' : 'scenery', body };
    }
    if (/^\s*(\/\/|function\s+props|const\s|let\s)/.test(text)) {
      return { kind: 'scenery', body: text.trim() };
    }
    if (/^\s*[[{]/.test(text) && /"moves"/.test(text)) {
      return { kind: 'layout', body: text.trim() };
    }
    return null;
  }

  /**
   * The conversation, with the parts that have been superseded taken out.
   *
   * An old reply's code block is not history, it is a wrong answer: the live
   * block already carries what the code actually is now, and an earlier version
   * of it in the transcript is something for the model to be confused by. So
   * fenced blocks are kept on the two most recent turns and replaced by a
   * placeholder before that, which keeps the shape of the conversation - "you
   * offered scenery, they asked for a change" - at a fraction of the tokens.
   */
  function trimTurns(turns) {
    const keep = turns.length - 2;
    return turns.map((t, i) => i >= keep ? t : {
      role: t.role,
      text: t.text.replace(/```[\s\S]*?```/g,
                           '[an earlier version, superseded]'),
    });
  }

  async function ask() {
    if (ai.busy) return;
    const q = $('aiInput').value.trim();
    if (!q) return;
    const key = loadKey(ai.provider);
    if (!key) { showKeyRow(true); return; }
    $('aiInput').value = '';
    say('me', q);
    ai.busy = true;
    $('aiSend').disabled = true;
    const thinking = say('ai', 'Thinking…');

    const P = PROVIDERS[ai.provider];
    // Rebuilt every turn rather than pasted once into the conversation. It is
    // what makes the model able to write either of these at all, and it carries
    // the *current* track - so after three edits the model is looking at the
    // track as it is now rather than as it was when the chat opened.
    const blocks = promptBlocks();
    // The code and the document are already in the live block, so the turns
    // carry only what was *said*. They used to prepend the whole scenery source
    // to every message, which meant the same code arrived twice per turn and a
    // ten-turn chat carried ten stale copies of it.
    const turns = trimTurns(ai.turns).concat([{ role: 'user', text: q }]);
    try {
      const res = await fetch(P.url(ai.model, key), {
        method: 'POST',
        headers: P.headers(key),
        body: JSON.stringify(P.body(ai.model, blocks, turns)),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) {
        thinking.remove();
        const why = P.error(j) || (res.status + ' from ' + P.name);
        say('err', why + (res.status === 401
          ? '\n\nThat usually means the key is wrong or has no credit.' : ''));
        return;
      }
      const text = P.read(j) || '(an empty reply)';
      thinking.remove();
      const art = pickArtefact(text);
      say('ai', art ? text.replace(/```[\s\S]*?```/, '').trim()
                      || 'Here you go.' : text, art);
      ai.turns.push({ role: 'user', text: q });
      ai.turns.push({ role: 'assistant', text: text });
      if (ai.turns.length > 16) ai.turns.splice(0, ai.turns.length - 16);
    } catch (err) {
      thinking.remove();
      say('err', 'Could not reach ' + P.name + ': ' + err
        + '\n\nIf this says the request was blocked, the page policy only '
        + 'allows the three providers in the picker.');
    } finally {
      ai.busy = false;
      $('aiSend').disabled = false;
    }
  }

  /* -- wiring -------------------------------------------------------- */
  $('codeText').addEventListener('input', () => {
    code = $('codeText').value;
    state.doc.source = code;
    setStat('changed…', '');
    runSoon();
  });
  $('codeClose').addEventListener('click', closeCode);
  $('codeAsk').addEventListener('click', () => showTab('ai'));

  function openChat() {
    if ($('aiMsgs').children.length) return;
    say('ai', 'I have the whole move vocabulary and the whole scenery API, and '
      + 'the shape of this track, so ask in plain words.\n\n'
      + 'Layout: "add a hairpin after the second checkpoint", "make the back '
      + 'straight longer and put a jump in it", "this is too easy".\n'
      + 'Scenery: "hangars along the back straight", "a barrier on the inside '
      + 'of turn three".\n\n'
      + 'You see every layout change as a diff before anything is applied. '
      + 'Your key stays in this browser.');
  }
  $('codeSpec').addEventListener('click', async () => {
    const text = apiSpec();
    try {
      await navigator.clipboard.writeText(text);
      $('codeSpec').textContent = 'Copied - paste it first';
      setTimeout(() => { $('codeSpec').textContent = 'Copy API for your AI'; },
                 2200);
    } catch (e) {
      // Clipboard needs a permission this page may not have. Select it instead
      // rather than saying nothing happened.
      $('codeText').value = text;
    }
  });
  $('codeErrCopy').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText($('codeErrText').textContent);
      $('codeErrCopy').textContent = 'copied';
      setTimeout(() => { $('codeErrCopy').textContent = '⧉ copy for your AI'; },
                 1800);
    } catch (e) { /* no clipboard permission */ }
  });
  initChat();

  /* -- keeping it ---------------------------------------------------- *
   * Building and driving need no account; keeping does. A saved track has an
   * author, an address and a board, and none of those exist without an
   * identity - but asking who somebody is before showing them a road is how you
   * lose most of them, so this is the only place a login is mentioned.
   */
  let saved = { slug: state.doc.slug || null, status: null };

  function openPublish() {
    $('pubPane').hidden = false;
    $('pubName').value = state.doc.name || '';
    drawPips();
    $('pubChecks').innerHTML = '<li class="ok"><i>&middot;</i><b>Checking…</b></li>';
    $('pubNotes').textContent = '';
    pubMsg('');
    runChecks();
  }
  const closePublish = () => { $('pubPane').hidden = true; };

  function pubMsg(text, tone) {
    const e = $('pubMsg');
    e.textContent = text;
    e.className = 'pubmsg' + (tone ? ' ' + tone : '');
  }

  function drawPips() {
    const host = $('pubPips');
    host.textContent = '';
    for (let d = 1; d <= 5; d++) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = String(d);
      if ((state.doc.difficulty || 3) === d) b.className = 'on';
      // The author picks, and Chinmay can overrule - which is the right way
      // round: nobody else has driven it yet.
      b.title = ['a first track', 'easy', 'a real lap', 'hard',
                 'brutal'][d - 1];
      b.addEventListener('click', () => {
        state.doc.difficulty = d;
        drawPips();
      });
      host.appendChild(b);
    }
  }

  async function runChecks() {
    const r = await fetch('/api/make/checks', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(state.doc),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      $('pubChecks').textContent = '';
      pubMsg(j.error || 'That did not build.', 'bad');
      return;
    }
    const ul = $('pubChecks');
    ul.textContent = '';
    for (const row of j.checks) {
      const li = document.createElement('li');
      li.className = row.ok ? 'ok' : 'no';
      li.innerHTML = '<i>' + (row.ok ? '&#10003;' : '&#10007;') + '</i>';
      const b = document.createElement('b');
      b.textContent = row.label;
      li.appendChild(b);
      if (row.detail) {
        const sp = document.createElement('span');
        sp.textContent = ' — ' + row.detail;
        li.appendChild(sp);
      }
      ul.appendChild(li);
    }
    // Taste, listed and not blocking. The palette warnings and the layout notes
    // are advice: this is somebody else's track.
    const notes = $('pubNotes');
    notes.textContent = '';
    for (const n of j.notes || []) {
      notes.appendChild(adviceNode({ level: 'note', text: n.text }));
    }
    $('pubSubmit').disabled = !j.ready;
    if (!j.signed_in) {
      pubMsg('Sign in to keep it. Everything you have built is still here.',
             'bad');
    } else if (j.ready) {
      pubMsg(saved.status === 'queued'
        ? 'In the queue. Chinmay drives it, then it goes live.'
        : 'Ready.', 'good');
    } else {
      pubMsg('');
    }
  }

  async function save() {
    state.doc.name = ($('pubName').value || '').trim()
      || state.doc.name || 'Untitled';
    const r = await fetch('/api/make/save', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ doc: state.doc, slug: saved.slug }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      if (j.need_login) {
        pubMsg('Sign in to keep it - nothing you have built is lost.', 'bad');
        // The draft is parked under a token first, so the round trip through
        // the login page comes back to this track rather than to a blank one.
        const tok = await fetch('/api/make/draft', {
          method: 'POST', headers: { 'content-type': 'application/json' },
          body: JSON.stringify(state.doc),
        }).then(x => x.json()).then(x => x.token).catch(() => null);
        const back = tok ? '/make/edit/' + tok : location.pathname;
        location.href = '/login?next=' + encodeURIComponent(back);
        return null;
      }
      pubMsg(j.error || 'Could not save that.', 'bad');
      return null;
    }
    saved = { slug: j.slug, status: j.status };
    state.doc.slug = j.slug;
    $('save').textContent = 'Saved';
    setTimeout(() => { $('save').textContent = 'Save'; }, 1800);
    pubMsg(!j.requeued ? 'Saved as /' + j.slug + '.'
      : j.geom_changed
        ? 'Saved, and back in the queue: the road moved, so the times it had '
          + 'were set on a different one.'
        : 'Saved, and back in the queue - the scenery changed. The board is '
          + 'kept; lap times do not depend on it.', 'good');
    return j;
  }

  async function submit() {
    const s = await save();
    if (!s) return;
    const r = await fetch('/api/make/submit', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ slug: saved.slug }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      pubMsg(j.error || 'Not ready.', 'bad');
      if (j.checks) runChecks();
      return;
    }
    saved.status = 'queued';
    pubMsg('Submitted. Chinmay drives it, then it goes live.', 'good');
    $('pubSubmit').disabled = true;
    $('pubSubmit').textContent = 'In the queue';
  }

  $('save').addEventListener('click', openPublish);
  $('pubClose').addEventListener('click', closePublish);
  $('pubSave').addEventListener('click', () => save());
  $('pubSubmit').addEventListener('click', () => submit());
  $('pubName').addEventListener('input', () => {
    state.doc.name = $('pubName').value;
  });

  drawMoves();
  drawInspector();
  if (state.track) mount(state.track, 'first'); else rebuild('first');
  scheduleLap();
}

/* -- odds and ends -------------------------------------------------- */
function debounce(fn, ms) {
  let t = null;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
function throttle(fn, ms) {
  let last = 0, t = null, pend = null;
  return (...a) => {
    pend = a;
    if (t) return;
    t = setTimeout(() => {
      t = null; last = performance.now(); fn(...pend);
    }, Math.max(0, ms - (performance.now() - last)));
  };
}
function fmt(v) {
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/0$/, '');
}

if (M.shape) startEditor(); else renderPick();
