/**
 * The sandbox that runs a player's scenery code.
 *
 * One sentence is the whole security model: **code runs while you author,
 * geometry ships.** This file executes untrusted JavaScript exactly once, in a
 * Worker, inside an iframe with an opaque origin, while its author is looking at
 * the result. What leaves is numbers - positions, colours and collider kinds -
 * and it is the numbers the play page, the track switcher and the QuickJS
 * anti-cheat consume. None of those ever runs a stranger's code.
 *
 * Three things make that hold rather than merely sound good:
 *
 *  * **the origin is opaque.** The parent creates the iframe with
 *    `sandbox="allow-scripts"` and no `allow-same-origin`, so this Worker
 *    inherits an origin that is nobody: no cookies, no storage, and a fetch back
 *    to the site is a credential-less cross-origin request the site refuses.
 *  * **the kinds are whitelisted, on the numbers.** See `KIND_OK`. This is the
 *    one real vulnerability in the whole feature and it is checked here, on the
 *    output, rather than by reading the code that produced it.
 *  * **it is bounded.** Triangle budgets from the pool's own measured range and
 *    a hard wall-clock deadline. A runaway loop costs its author two seconds and
 *    costs nobody else anything, because the parent terminates the Worker.
 *
 * `sceneryContext` is not defined in this file. The parent prepends it, taken
 * straight off the live `trackmesh.js` export with `Function.prototype
 * .toString()`, so the four helpers a player writes against are byte-identical
 * to the four the engine draws Silverstone's hangars with. A second copy in here
 * would be a spec that can drift from the code, which is the one thing the
 * palette contract was moved into Python to stop.
 */
/* eslint-env worker */

// trackmesh.js:30. A player's scenery may emit WALL and OFFROAD and nothing
// else, and that is not tidiness - it is the security boundary.
//
// A user-emitted BOOST quad is a boost pad baked into the road, and the verifier
// re-drives submitted laps against this same collider, so it would be a speed
// hack that arrives with a certificate of authenticity. BOUNCE is the same trick
// with a trampoline. ROAD is worse in a quieter way: fake road the ground probe
// picks up, a surface the car drives on with no ribbon under it.
const KIND = { ROAD: 0, WALL: 1, OFFROAD: 2, BOOST: 3, BOUNCE: 4 };
const KIND_OK = new Set([KIND.WALL, KIND.OFFROAD]);
const KIND_NAME = ['ROAD', 'WALL', 'OFFROAD', 'BOOST', 'BOUNCE'];

// From `test_scenery.py`, which pins every track in the pool: the pool runs 534
// to 13,188 collider triangles, with wall counts from 100 (Chicane Park) to
// 2,020 (The Gauntlet). Tokyo Drift's city is the shape of thing the mesh budget
// has to fit. Both are set above the busiest track that ships.
const BUDGET = { mesh: 20000, collider: 2500 };

// Three separate failures, because they are three separate things to be told
// and the label is most of the message. "Over budget" on a refused boost pad
// reads as "make it smaller", which is the wrong lesson entirely.
class Over extends Error {}       // too much geometry, or too slow
class Refused extends Error {}    // asked for something it may not have
class BadGeom extends Error {}    // NaN, undefined, a point that is not a point

/** Records triangles as plain numbers. Same surface as trackmesh's MeshBuf. */
class Rec {
  constructor(limit, what) {
    this.pos = []; this.col = []; this.limit = limit; this.what = what;
  }
  get tris() { return this.pos.length / 9; }
  _room() {
    if (this.tris >= this.limit) {
      throw new Over('Too much ' + this.what + ' geometry: the budget is '
        + this.limit.toLocaleString() + ' triangles, which is more than the '
        + 'busiest track in the game.');
    }
  }
  tri(a, b, c, color) {
    this._room();
    num3(a, 'tri'); num3(b, 'tri'); num3(c, 'tri');
    this.pos.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]);
    const r = ((color >> 16) & 255) / 255, g = ((color >> 8) & 255) / 255,
      bl = (color & 255) / 255;
    for (let i = 0; i < 3; i++) this.col.push(r, g, bl);
  }
  quad(a, b, c, d, color) { this.tri(a, b, c, color); this.tri(a, c, d, color); }
  triV(a, b, c, ca, cb, cc) {
    this._room();
    num3(a, 'triV'); num3(b, 'triV'); num3(c, 'triV');
    this.pos.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]);
    for (const k of [ca, cb, cc]) {
      this.col.push(((k >> 16) & 255) / 255, ((k >> 8) & 255) / 255,
                    (k & 255) / 255);
    }
  }
  quadV(a, b, c, d, ca, cb, cc, cd) {
    this.triV(a, b, c, ca, cb, cc); this.triV(a, c, d, ca, cc, cd);
  }
  box(cx, cy, cz, hx, hy, hz, color) {
    const P = (sx, sy, sz) => [cx + sx * hx, cy + sy * hy, cz + sz * hz];
    const v = [P(-1, -1, -1), P(1, -1, -1), P(1, -1, 1), P(-1, -1, 1),
               P(-1, 1, -1), P(1, 1, -1), P(1, 1, 1), P(-1, 1, 1)];
    this.quad(v[4], v[7], v[6], v[5], color);
    this.quad(v[0], v[1], v[2], v[3], color);
    this.quad(v[0], v[4], v[5], v[1], color);
    this.quad(v[1], v[5], v[6], v[2], color);
    this.quad(v[2], v[6], v[7], v[3], color);
    this.quad(v[3], v[7], v[4], v[0], color);
  }
}

/** Records collider triangles, and refuses every kind but two. */
class ColRec {
  constructor() { this.v = []; this.k = []; }
  get tris() { return this.k.length; }
  add(a, b, c, kind) {
    if (!KIND_OK.has(kind)) {
      throw new Refused('Scenery may only add KIND.WALL and KIND.OFFROAD to the '
        + 'collider. ' + (KIND_NAME[kind] ? 'KIND.' + KIND_NAME[kind]
        : String(kind)) + ' is refused: a pad or a surface you can drive on '
        + 'would change lap times, and the anti-cheat measures laps against '
        + 'this exact collider - so it would be a certified speed hack.');
    }
    if (this.tris >= BUDGET.collider) {
      throw new Over('Too much collider geometry: the budget is '
        + BUDGET.collider.toLocaleString() + ' triangles, and the busiest track '
        + 'in the game uses 2,020.');
    }
    num3(a, 'collider'); num3(b, 'collider'); num3(c, 'collider');
    this.v.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]);
    this.k.push(kind);
  }
  addQuad(a, b, c, d, kind) { this.add(a, b, c, kind); this.add(a, c, d, kind); }
}

/**
 * NaN is the failure that does not announce itself.
 *
 * three.js turns one into a vertex at nowhere and draws the whole mesh black or
 * not at all, and it comes from ordinary arithmetic - an undefined offset, a
 * divide by a zero-length span. Caught here so the message can name the call
 * instead of the author finding an invisible building.
 */
function num3(p, where) {
  if (!p || p.length < 3 || !Number.isFinite(p[0]) || !Number.isFinite(p[1])
      || !Number.isFinite(p[2])) {
    throw new BadGeom('A point handed to ' + where + '() is not three finite '
      + 'numbers: ' + JSON.stringify(p) + '. This is usually an offset that '
      + 'came out undefined, or a divide by a zero-length span.');
  }
}

// A stray promise inside a player's code must not surface as an error on the
// page that is hosting it. There is nothing here to await - the API is entirely
// synchronous - so an unhandled rejection is always the author's, and it is
// theirs to see rather than the parent's console's.
self.addEventListener('unhandledrejection', (e) => {
  e.preventDefault();
  self.postMessage({
    ok: false, kind: 'throw', name: 'UnhandledRejection',
    error: 'Something in this code failed asynchronously: '
      + ((e.reason && e.reason.message) || String(e.reason))
      + '. Nothing in this API is async - there is no network and no timer - so '
      + 'a promise here is almost always a call that does not exist.',
  });
});

self.onmessage = (e) => {
  const { code, track, pal, groundY, deadline } = e.data || {};
  const solid = new Rec(BUDGET.mesh, 'solid');
  const bright = new Rec(BUDGET.mesh, 'unlit');
  const col = new ColRec();
  const started = Date.now();
  // A soft deadline as well as the parent's hard terminate: a loop that is
  // merely slow gets a message it can act on, where being killed from outside
  // looks the same as a crash.
  const tick = () => {
    if (Date.now() - started > (deadline || 2000)) {
      throw new Over('This took longer than two seconds and was stopped. The '
        + 'usual cause is a loop over stations inside a loop over stations - '
        + 'a lap is hundreds of stations, so that is hundreds of thousands of '
        + 'quads.');
    }
  };
  const guard = (o) => new Proxy(o, {
    get(t, k) {
      const v = t[k];
      if (typeof v !== 'function') return v;
      return (...a) => { tick(); return v.apply(t, a); };
    },
  });

  // A terrain height field is data the sandbox cannot rebuild, so it arrives
  // sampled: a grid the parent baked off the real field, read with the same
  // signature the engine's `terrain.height` has.
  const terr = e.data.terrain ? {
    height: (x, z) => sampleGrid(e.data.terrain, x, z),
  } : null;

  try {
    const ctx = sceneryContext(solid, track, pal, terr, groundY, 1.2);
    const api = {
      ...ctx,
      solid: guard(solid), bright: guard(bright), col: guard(col),
      track, pal, terrain: terr, groundY,
      KIND: Object.freeze({ WALL: KIND.WALL, OFFROAD: KIND.OFFROAD }),
      bbox: e.data.bbox,
      shade, mulberry,
    };
    // The library, on the same context. A player writing code and a player
    // dropping a grandstand in from the palette are calling the same function,
    // so "start from one of the library models and change it" is a real thing
    // to say rather than advice about a different API.
    api.kit = {};
    for (const [o, m] of Object.entries(MODELS)) {
      api.kit[o] = (p) => m.build(api,
        Object.assign({ o }, placementDefaults(o), p));
    }
    api.place = (list) => placeAll(api, list);
    // Indirect, so the code cannot see this function's locals by closing over
    // them - and with the API as its one argument, so the spec and the call
    // agree about what a player is given.
    const fn = new Function('ctx', '"use strict";\n' + code
      + '\n;if (typeof props !== "function") {\n'
      // Silently drawing nothing is the worst answer here: the author wrote
      // code, pressed nothing, and got an empty world with a green status line.
      + '  throw new ReferenceError("No props function. The sandbox calls '
      + 'props(ctx), so the code has to define exactly that: function '
      + 'props(ctx) { ... }");\n}\nreturn props(ctx);');
    fn(api);
  } catch (err) {
    self.postMessage({
      ok: false,
      kind: err instanceof Refused ? 'refused'
        : err instanceof BadGeom ? 'geometry'
        : err instanceof Over ? 'budget'
        : (err && err.name) === 'SyntaxError' ? 'syntax' : 'throw',
      name: err && err.name || 'Error',
      error: err && err.message || String(err),
      // The line the author wrote, not the line in the wrapper. `new Function`
      // adds two lines of its own before the code.
      stack: cleanStack(err),
    });
    return;
  }

  const out = {
    ok: true,
    ms: Date.now() - started,
    solid: { pos: new Float32Array(solid.pos), col: new Float32Array(solid.col) },
    bright: { pos: new Float32Array(bright.pos), col: new Float32Array(bright.col) },
    col: { v: new Float32Array(col.v), k: new Uint8Array(col.k) },
    counts: { solid: solid.tris, bright: bright.tris, collider: col.tris },
  };
  self.postMessage(out, [out.solid.pos.buffer, out.solid.col.buffer,
                         out.bright.pos.buffer, out.bright.col.buffer,
                         out.col.v.buffer, out.col.k.buffer]);
};

function cleanStack(err) {
  const s = (err && err.stack) || '';
  return s.split('\n').slice(0, 4)
    // `new Function` code reports as `<anonymous>`; say `your scenery` instead,
    // because that is what it is and the author has to be able to read this.
    .map(l => l.replace(/eval at.*|<anonymous>/g, 'your scenery'))
    .join('\n');
}

function sampleGrid(g, x, z) {
  const u = (x - g.x0) / g.dx, v = (z - g.z0) / g.dz;
  const i = Math.max(0, Math.min(g.nx - 1, Math.round(u)));
  const j = Math.max(0, Math.min(g.nz - 1, Math.round(v)));
  return g.h[j * g.nx + i];
}

// `shade`, `mulberry` and `sceneryContext` are NOT defined here. The parent
// prepends all three, taken off the live `trackmesh.js` exports with
// `Function.prototype.toString()`. The first draft of this file carried a
// hand-written `shade` and got it wrong in the most plausible way - a multiplier
// rather than an amount, so every colour it touched came out darker and nothing
// said so. Injection cannot drift; a copy already had.
