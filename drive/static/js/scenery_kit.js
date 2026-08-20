/**
 * The scenery library: models you drop on a track, by name and by number.
 *
 * Read the five hand-written `scenery.js` files beside each other and they are
 * the same file five times - the same four helpers, then three hundred lines of
 * boxes derived off the ribbon. This is that, once, as a vocabulary: a
 * grandstand is `{o: 'stand', at: 0.08, side: -1, tiers: 7}` and the engine
 * knows how to draw one.
 *
 * **It is engine code, and it runs everywhere a track is built** - the editor's
 * preview, the play page, the track switcher and the QuickJS anti-cheat - because
 * the placement list rides the track dict exactly as the palette does. There is
 * no second interpreter to keep in step and no path that can miss the collider.
 *
 * Six defects in `docs/track-defects.md` stop being reachable rather than merely
 * warned about, and each one is structural:
 *
 *  * **geometry that does not move when the road does.** There is no way to
 *    write a world coordinate here. Every placement is a fraction of the lap.
 *  * **a quad wound the wrong way is invisible.** Nothing in a placement is a
 *    quad; `face` draws both windings and `kitObox` is built from `face`.
 *  * **geometry floating in the sky.** Everything stands on `ground(i, off)`.
 *  * **scenery standing on nothing past the edge of the ground.** `kitAnchor`
 *    clamps the offset to the plate.
 *  * **a scenery.js that throws leaves the suite green.** Data does not throw,
 *    and an unknown `o` or a parameter out of range is refused by name.
 *  * **the collider missing on one path.** One interpreter, four callers.
 *
 * Everything is flat-shaded boxes and quads, which is the house style, and
 * every colour comes from the palette through `shade` - so a model follows a
 * palette change instead of fighting it.
 */

// Everything at the top level of this file shares one scope with every other
// bundled file when `jsrt.py` concatenates them for QuickJS, so the helpers are
// prefixed. `clamp` was not, and collided with `bot.js`'s - which is a
// SyntaxError, not a shadow, so it took out every bot test at once.
// `tests/test_no_js_name_clashes.py` now guards the whole bundle.
const kitClamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

/**
 * The colour a building should be, off whatever palette it lands on.
 *
 * `rail` and not `prop2`, and the difference is not cosmetic. `prop2` is the
 * palette's *second structural* colour, and a track whose second structure is
 * trees sets it to a dark foliage green - Spa does - so a factory keyed off it
 * came out olive on the first pass. `rail` is required on every palette, is
 * always a built colour, and tracks light and dark palettes the same way, so a
 * tower shaded down off it is dark on a night track and pale on a bright one.
 *
 * `prop2` is still right for things that genuinely *are* secondary structure -
 * trestles, columns, fence posts - which is what the contract says it is for.
 */
function kitBuilt(ctx, amt) {
  return ctx.shade(ctx.pal.rail || 0xd8dde2, amt || 0);
}

/** Where a placement stands: station, offset, world point, ground height. */
function kitAnchor(ctx, p) {
  const n = ctx.track.line.length;
  const i = ctx.at(kitClamp(Number(p.at) || 0, 0, 1));
  // The side is a sign and the offset is a distance, kept separate so `side`
  // can be flipped in the editor without the author having to notice that the
  // number they typed was negative.
  const side = (Number(p.side) < 0) ? -1 : 1;
  const off = side * Math.abs(Number(p.off) || 0);
  const [x, z] = ctx.spot(i, off);
  return { i, n, side, off, x, z, y: ctx.ground(i, off) };
}

/** The road's forward and rightward directions at a station, in world xz. */
function kitFrame(ctx, i) {
  const line = ctx.track.line, n = line.length;
  const a = line[kitClamp(i - 1, 0, n - 1)].p, b = line[kitClamp(i + 1, 0, n - 1)].p;
  let fx = b[0] - a[0], fz = b[2] - a[2];
  const fl = Math.hypot(fx, fz) || 1;
  fx /= fl; fz /= fl;
  const lat = line[kitClamp(i, 0, n - 1)].lat;
  let rx = lat[0], rz = lat[2];
  const rl = Math.hypot(rx, rz) || 1;
  return { fx, fz, rx: rx / rl, rz: rz / rl };
}

/**
 * A box that lines up with the road, which `solid.box` cannot be.
 *
 * `solid.box` is axis-aligned, so a hangar beside a corner sits at whatever
 * angle the world happens to be at - which reads as a mistake, because it is
 * one. Built out of `face`, so both windings come for free and there is no way
 * to end up with an invisible wall.
 *
 *   `along` is half its length down the road, `across` half its width, `up` its
 *   full height measured from `y` upward.
 */
function kitObox(ctx, f, x, y, z, along, up, across, colour, buf) {
  const b = buf || ctx.solid;
  const P = (da, du, dc) => [x + f.fx * da + f.rx * dc,
                             y + du,
                             z + f.fz * da + f.rz * dc];
  const v = [P(-along, 0, -across), P(along, 0, -across),
             P(along, 0, across), P(-along, 0, across),
             P(-along, up, -across), P(along, up, -across),
             P(along, up, across), P(-along, up, across)];
  ctx.face(v[4], v[5], v[6], v[7], colour);          // roof
  ctx.face(v[0], v[3], v[2], v[1], colour);          // floor
  ctx.face(v[0], v[1], v[5], v[4], colour);
  ctx.face(v[1], v[2], v[6], v[5], colour);
  ctx.face(v[2], v[3], v[7], v[6], colour);
  ctx.face(v[3], v[0], v[4], v[7], colour);
  return v;
}

/** A flat panel lying on the ground, for markings. */
function kitSlab(ctx, f, x, y, z, along, across, colour) {
  const P = (da, dc) => [x + f.fx * da + f.rx * dc, y,
                         z + f.fz * da + f.rz * dc];
  ctx.face(P(-along, -across), P(along, -across), P(along, across),
           P(-along, across), colour);
}

// ---------------------------------------------------------------------------
// The models
// ---------------------------------------------------------------------------
// Every one takes `(ctx, p)` where `p` is the placement, and draws with
// `kitAnchor`, `kitFrame`, `kitObox` and `kitSlab` and nothing else. Colours come off the
// palette so a model follows a palette change.

const MODELS = {

  /* ---- nature ---------------------------------------------------------- */

  tree: {
    name: 'Tree', group: 'Nature',
    blurb: 'A broadleaf. Three whorls on a trunk.',
    params: { at: [0, 1, 0.002, 0.2], off: [12, 260, 1, 34],
              h: [4, 26, 0.5, 11], spread: [0.5, 3, 0.05, 1] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const trunk = ctx.shade(ctx.pal.prop || 0x37624a, -0.45);
      const leaf = ctx.pal.prop || 0x37624a;
      kitObox(ctx, f, a.x, a.y, a.z, 0.5, p.h * 0.45, 0.5, trunk);
      for (let k = 0; k < 3; k++) {
        const r = (2.6 - k * 0.7) * p.spread;
        const yy = a.y + p.h * (0.38 + k * 0.2);
        kitObox(ctx, f, a.x, yy, a.z, r, p.h * 0.16, r,
             ctx.shade(leaf, k * 0.07 - 0.05));
      }
    },
  },

  pine: {
    name: 'Pine', group: 'Nature',
    blurb: 'A conifer: a stack of shrinking slabs. Reads at any distance.',
    params: { at: [0, 1, 0.002, 0.2], off: [12, 260, 1, 34],
              h: [5, 34, 0.5, 15], tiers: [3, 8, 1, 5] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const leaf = ctx.pal.prop || 0x37624a;
      kitObox(ctx, f, a.x, a.y, a.z, 0.45, p.h * 0.3, 0.45,
           ctx.shade(leaf, -0.5));
      const tiers = Math.round(p.tiers);
      for (let k = 0; k < tiers; k++) {
        const t = k / tiers;
        const r = 3.2 * (1 - t * 0.78);
        kitObox(ctx, f, a.x, a.y + p.h * (0.22 + t * 0.72), a.z,
             r, p.h * 0.13, r, ctx.shade(leaf, t * 0.14 - 0.08));
      }
    },
  },

  palm: {
    name: 'Palm', group: 'Nature',
    blurb: 'A leaning trunk and six fronds. For anywhere warm.',
    params: { at: [0, 1, 0.002, 0.2], off: [12, 260, 1, 30],
              h: [6, 22, 0.5, 12], lean: [-3, 3, 0.1, 0.8] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const trunk = ctx.shade(ctx.pal.prop || 0x37624a, -0.3);
      const seg = 5;
      for (let k = 0; k < seg; k++) {
        const t = k / seg;
        kitObox(ctx, f, a.x + f.rx * p.lean * t * 2, a.y + p.h * t,
             a.z + f.rz * p.lean * t * 2, 0.42, p.h / seg + 0.1, 0.42,
             ctx.shade(trunk, t * 0.1));
      }
      const tx = a.x + f.rx * p.lean * 2, tz = a.z + f.rz * p.lean * 2;
      const leaf = ctx.pal.prop || 0x37624a;
      for (let k = 0; k < 6; k++) {
        const th = (k / 6) * Math.PI * 2;
        const dx = Math.cos(th) * 3.4, dz = Math.sin(th) * 3.4;
        ctx.face([tx, a.y + p.h, tz],
                 [tx + dx, a.y + p.h - 1.1, tz + dz],
                 [tx + dx * 1.15, a.y + p.h - 1.9, tz + dz * 1.15],
                 [tx + dx * 0.2, a.y + p.h - 0.2, tz + dz * 0.2],
                 ctx.shade(leaf, k % 2 ? 0.12 : 0));
      }
    },
  },

  rock: {
    name: 'Rock', group: 'Nature',
    blurb: 'A boulder, the colour of the ground it is sitting on.',
    params: { at: [0, 1, 0.002, 0.2], off: [12, 260, 1, 26],
              size: [1, 14, 0.2, 3] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const c = ctx.shade(ctx.pal.ground || 0x5ea364, -0.3);
      kitObox(ctx, f, a.x, a.y - p.size * 0.2, a.z, p.size,
           p.size * 0.8, p.size * 0.85, c);
      kitObox(ctx, f, a.x + f.fx * p.size * 0.4, a.y + p.size * 0.3,
           a.z + f.fz * p.size * 0.4, p.size * 0.5, p.size * 0.5,
           p.size * 0.5, ctx.shade(c, 0.08));
    },
  },

  /* ---- buildings -------------------------------------------------------- */

  shed: {
    name: 'Shed', group: 'Buildings',
    blurb: 'A plain building with a lip of roof. The workhorse.',
    params: { at: [0, 1, 0.002, 0.3], off: [14, 260, 1, 40],
              len: [6, 90, 1, 24], w: [4, 60, 1, 14], h: [3, 30, 0.5, 7] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const wall = kitBuilt(ctx, -0.04);
      kitObox(ctx, f, a.x, a.y, a.z, p.len / 2, p.h, p.w / 2, wall);
      kitObox(ctx, f, a.x, a.y + p.h, a.z, p.len / 2 + 0.7, 0.55,
           p.w / 2 + 0.7, ctx.shade(wall, -0.28));
    },
  },

  hangar: {
    name: 'Hangar', group: 'Buildings',
    blurb: 'A long shed with a curved roof and a door you can see.',
    params: { at: [0, 1, 0.002, 0.3], off: [16, 260, 1, 48],
              len: [12, 120, 1, 44], w: [8, 60, 1, 24], h: [5, 30, 0.5, 11] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const wall = kitBuilt(ctx, 0.04);
      kitObox(ctx, f, a.x, a.y, a.z, p.len / 2, p.h, p.w / 2, wall);
      // The roof as four shallow slabs, which reads as a curve at this scale
      // and costs eight quads.
      const steps = 4;
      for (let k = 0; k < steps; k++) {
        const t = (k + 0.5) / steps;
        const wide = (p.w / 2) * Math.cos(t * 1.15);
        kitObox(ctx, f, a.x, a.y + p.h + k * 0.75, a.z, p.len / 2 + 0.4,
             0.8, wide, ctx.shade(wall, -0.1 - k * 0.05));
      }
      // A door on one end, dark, so the building has a front. On the *end* -
      // the first version offset it by zero, which put it in the middle of the
      // building where nothing can see it.
      kitObox(ctx, f, a.x + f.fx * p.len / 2, a.y, a.z + f.fz * p.len / 2,
           0.25, p.h * 0.78, p.w * 0.34, ctx.shade(wall, -0.55));
    },
  },

  tower: {
    name: 'Tower', group: 'Buildings',
    blurb: 'A tall block with lit windows. Stack a few for a skyline.',
    params: { at: [0, 1, 0.002, 0.3], off: [20, 400, 1, 90],
              w: [6, 50, 1, 16], h: [10, 160, 1, 60] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const wall = kitBuilt(ctx, -0.42);
      kitObox(ctx, f, a.x, a.y, a.z, p.w / 2, p.h, p.w / 2, wall);
      kitObox(ctx, f, a.x, a.y + p.h, a.z, p.w / 2 - 1.2, 1.4,
           p.w / 2 - 1.2, ctx.shade(wall, -0.3));
      // Windows are unlit geometry, so they read as light rather than as a
      // paler wall - which is the whole difference at night.
      const rows = Math.max(1, Math.floor(p.h / 7));
      const lit = ctx.pal.deco || 0xf2c94c;
      const rnd = ctx.mulberry(Math.round(p.at * 9973) + Math.round(p.h));
      for (let r = 0; r < rows; r++) {
        for (let c = -1; c <= 1; c++) {
          if (rnd() < 0.42) continue;
          const yy = a.y + 4 + r * (p.h - 6) / rows;
          kitObox(ctx, f, a.x + f.rx * c * p.w * 0.28,
               yy, a.z + f.rz * c * p.w * 0.28,
               p.w / 2 + 0.06, 2.2, p.w * 0.1,
               ctx.shade(lit, rnd() * 0.2 - 0.1), ctx.bright);
        }
      }
    },
  },

  container: {
    name: 'Container', group: 'Buildings',
    blurb: 'A shipping container, ribbed. Good in twos and threes.',
    params: { at: [0, 1, 0.002, 0.3], off: [12, 260, 1, 30],
              stack: [1, 4, 1, 1] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const base = ctx.pal.kerb2 || 0xc0392b;
      const rnd = ctx.mulberry(Math.round(p.at * 7919));
      for (let s = 0; s < Math.round(p.stack); s++) {
        const c = ctx.shade(base, (rnd() - 0.5) * 0.5);
        kitObox(ctx, f, a.x, a.y + s * 5.2, a.z, 6.1, 5, 2.4, c);
        for (let k = -5; k <= 5; k++) {
          kitObox(ctx, f, a.x + f.fx * k * 1.1, a.y + s * 5.2 + 0.4,
               a.z + f.fz * k * 1.1, 0.14, 4.2, 2.55, ctx.shade(c, -0.2));
        }
      }
    },
  },

  watertower: {
    name: 'Water tower', group: 'Buildings',
    blurb: 'A tank on four legs. One of these makes a place feel real.',
    params: { at: [0, 1, 0.002, 0.3], off: [16, 260, 1, 44],
              h: [8, 40, 0.5, 18], r: [2, 10, 0.2, 5] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const c = ctx.shade(ctx.pal.rail || 0xd8dde2, -0.18);
      for (const sx of [-1, 1]) {
        for (const sz of [-1, 1]) {
          kitObox(ctx, f, a.x + f.fx * sx * p.r * 0.7 + f.rx * sz * p.r * 0.7,
               a.y, a.z + f.fz * sx * p.r * 0.7 + f.rz * sz * p.r * 0.7,
               0.28, p.h, 0.28, ctx.shade(c, -0.3));
        }
      }
      kitObox(ctx, f, a.x, a.y + p.h, a.z, p.r, p.r * 1.1, p.r, c);
      kitObox(ctx, f, a.x, a.y + p.h + p.r * 1.1, a.z, p.r * 0.72, p.r * 0.4,
           p.r * 0.72, ctx.shade(c, -0.22));
    },
  },

  /* ---- the circuit ------------------------------------------------------ */

  stand: {
    name: 'Grandstand', group: 'Circuit',
    blurb: 'Stepped seating under a flat roof. Faces the road.',
    params: { at: [0, 1, 0.002, 0.1], off: [14, 120, 1, 28],
              len: [14, 140, 1, 56], tiers: [3, 14, 1, 8] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const concrete = ctx.shade(ctx.pal.rail || 0xb9b6ae, -0.1);
      const seat = ctx.pal.kerb2 || 0xd23b32;
      const tiers = Math.round(p.tiers);
      for (let k = 0; k < tiers; k++) {
        // Each tier steps back *away* from the road, so the stand leans over
        // the track the way a real one does.
        const back = a.side * (1.4 + k * 1.55);
        kitObox(ctx, f, a.x + f.rx * back, a.y + k * 1.15, a.z + f.rz * back,
             p.len / 2, 1.15, 0.8, k % 2 ? seat : ctx.shade(seat, -0.16));
      }
      const roofBack = a.side * (1.4 + tiers * 1.55 * 0.55);
      kitObox(ctx, f, a.x + f.rx * roofBack, a.y + tiers * 1.15 + 3.4,
           a.z + f.rz * roofBack, p.len / 2 + 1.5, 0.7,
           tiers * 0.9, ctx.shade(concrete, -0.2));
      for (const e of [-1, 1]) {
        kitObox(ctx, f, a.x + f.fx * e * p.len / 2 + f.rx * a.side * tiers * 1.55,
             a.y, a.z + f.fz * e * p.len / 2 + f.rz * a.side * tiers * 1.55,
             0.5, tiers * 1.15 + 3.4, tiers * 0.85, concrete);
      }
    },
  },

  pits: {
    name: 'Pit garages', group: 'Circuit',
    blurb: 'A row of garages with dark open doors, and a low wall in front.',
    params: { at: [0, 1, 0.002, 0.02], off: [14, 90, 1, 26],
              bays: [2, 20, 1, 8], h: [4, 12, 0.5, 6] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const wall = ctx.shade(ctx.pal.rail || 0xb9b6ae, 0.05);
      const bays = Math.round(p.bays);
      const bay = 7.5;
      const len = bays * bay;
      kitObox(ctx, f, a.x, a.y, a.z, len / 2, p.h, 7, wall);
      kitObox(ctx, f, a.x, a.y + p.h, a.z, len / 2 + 1.2, 0.6, 8.4,
           ctx.shade(wall, -0.3));
      // The doors are what make it read as garages rather than as one long
      // shed, and they are dark because an open door is a hole.
      for (let k = 0; k < bays; k++) {
        const d = (k - (bays - 1) / 2) * bay;
        kitObox(ctx, f, a.x + f.fx * d - f.rx * a.side * 7.05,
             a.y, a.z + f.fz * d - f.rz * a.side * 7.05,
             bay * 0.38, p.h * 0.8, 0.2, ctx.shade(wall, -0.62));
      }
      // The pit wall, between the garages and the road.
      kitObox(ctx, f, a.x - f.rx * a.side * 12, a.y,
           a.z - f.rz * a.side * 12, len / 2, 1.1, 0.4,
           ctx.shade(wall, -0.12));
    },
  },

  gantry: {
    name: 'Gantry', group: 'Circuit',
    blurb: 'A kitFrame over the road. Put one on the start line.',
    params: { at: [0, 1, 0.002, 0.0], h: [5, 20, 0.5, 9],
              span: [10, 60, 1, 26] },
    build(ctx, p) {
      const i = ctx.at(kitClamp(Number(p.at) || 0, 0, 1));
      const f = kitFrame(ctx, i);
      const c = ctx.shade(ctx.pal.rail || 0xd8dde2, -0.35);
      for (const s of [-1, 1]) {
        const [lx, lz] = ctx.spot(i, s * p.span / 2);
        const ly = ctx.ground(i, s * p.span / 2);
        kitObox(ctx, f, lx, ly, lz, 0.55, p.h, 0.55, c);
      }
      const [cx, cz] = ctx.spot(i, 0);
      const cy = ctx.ground(i, 0);
      kitObox(ctx, f, cx, cy + p.h, cz, 0.6, 1.1, p.span / 2, c);
      kitObox(ctx, f, cx, cy + p.h + 1.1, cz, 0.4, 1.6, p.span * 0.22,
           ctx.pal.deco || 0xf2c94c);
    },
  },

  boards: {
    name: 'Hoardings', group: 'Circuit',
    blurb: 'A run of advertising boards along the edge of the road.',
    params: { at: [0, 1, 0.002, 0.1], to: [0, 1, 0.002, 0.2],
              off: [10, 60, 1, 14], h: [1.5, 6, 0.1, 2.6] },
    build(ctx, p) {
      const from = ctx.at(kitClamp(Math.min(p.at, p.to), 0, 1));
      const to = ctx.at(kitClamp(Math.max(p.at, p.to), 0, 1));
      const side = (Number(p.side) < 0) ? -1 : 1;
      const off = side * Math.abs(p.off);
      const board = ctx.shade(ctx.pal.rail || 0xd8dde2, 0.2);
      const dark = ctx.shade(ctx.pal.prop2 || 0x12161c, -0.4);
      for (let i = from; i < to; i += 3) {
        const f = kitFrame(ctx, i);
        const [x, z] = ctx.spot(i, off);
        const y = ctx.ground(i, off);
        kitObox(ctx, f, x, y, z, 5.0, p.h, 0.22, board);
        kitObox(ctx, f, x, y + p.h * 0.18, z, 4.4, p.h * 0.6, 0.3, dark);
      }
    },
  },

  tyres: {
    name: 'Tyre stack', group: 'Circuit',
    blurb: 'A pile of tyres. Cheap, and it says motorsport instantly.',
    params: { at: [0, 1, 0.002, 0.2], off: [10, 90, 1, 16],
              wide: [1, 6, 1, 3], high: [1, 5, 1, 2] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const rubber = 0x22252a;
      for (let w = 0; w < Math.round(p.wide); w++) {
        for (let h = 0; h < Math.round(p.high); h++) {
          kitObox(ctx, f, a.x + f.fx * (w - p.wide / 2) * 1.9,
               a.y + h * 0.85, a.z + f.fz * (w - p.wide / 2) * 1.9,
               0.85, 0.8, 0.85, ctx.shade(rubber, (w + h) % 2 ? 0.1 : 0));
        }
      }
    },
  },

  cones: {
    name: 'Cones', group: 'Circuit',
    blurb: 'A line of cones. Marks out a chicane without changing the road.',
    params: { at: [0, 1, 0.002, 0.2], to: [0, 1, 0.002, 0.26],
              off: [4, 40, 0.5, 8], every: [1, 12, 1, 4] },
    build(ctx, p) {
      const from = ctx.at(kitClamp(Math.min(p.at, p.to), 0, 1));
      const to = ctx.at(kitClamp(Math.max(p.at, p.to), 0, 1));
      const side = (Number(p.side) < 0) ? -1 : 1;
      const c = ctx.pal.kerb2 || 0xe8453c;
      for (let i = from; i <= to; i += Math.max(1, Math.round(p.every))) {
        const f = kitFrame(ctx, i);
        const [x, z] = ctx.spot(i, side * p.off);
        const y = ctx.ground(i, side * p.off);
        kitObox(ctx, f, x, y, z, 0.5, 0.55, 0.5, c);
        kitObox(ctx, f, x, y + 0.55, z, 0.3, 0.45, 0.3,
             ctx.shade(c, 0.45), ctx.bright);
      }
    },
  },

  lamp: {
    name: 'Floodlight', group: 'Circuit',
    blurb: 'A mast with a lit head. A row of them makes it a night race.',
    params: { at: [0, 1, 0.002, 0.2], off: [12, 90, 1, 24],
              h: [6, 40, 0.5, 18] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const post = ctx.shade(ctx.pal.rail || 0xd8dde2, -0.4);
      kitObox(ctx, f, a.x, a.y, a.z, 0.32, p.h, 0.32, post);
      kitObox(ctx, f, a.x - f.rx * a.side * 1.2, a.y + p.h,
           a.z - f.rz * a.side * 1.2, 1.9, 0.9, 0.7,
           ctx.shade(post, -0.2));
      kitObox(ctx, f, a.x - f.rx * a.side * 1.2, a.y + p.h - 0.35,
           a.z - f.rz * a.side * 1.2, 1.7, 0.35, 0.55,
           0xfff3d0, ctx.bright);
    },
  },

  /* ---- the ground, and the one thing that changes lap times ------------- */

  paint: {
    name: 'Ground marking', group: 'Ground',
    blurb: 'A flat panel on the ground - a runway, an apron, a patch of spill.',
    params: { at: [0, 1, 0.002, 0.2], to: [0, 1, 0.002, 0.35],
              off: [0, 300, 1, 60], w: [4, 200, 1, 30] },
    build(ctx, p) {
      const from = ctx.at(kitClamp(Math.min(p.at, p.to), 0, 1));
      const to = ctx.at(kitClamp(Math.max(p.at, p.to), 0, 1));
      const side = (Number(p.side) < 0) ? -1 : 1;
      const off = side * Math.abs(p.off);
      const c = ctx.shade(ctx.pal.ground || 0x5ea364, -0.22);
      // Lifted a hair off the plate: co-planar with it, the two fight for the
      // same depth and the result flickers as the camera moves.
      for (let i = from; i < to; i += 2) {
        const f = kitFrame(ctx, i);
        const [x, z] = ctx.spot(i, off);
        kitSlab(ctx, f, x, ctx.ground(i, off) + 0.04, z, 4.0, p.w / 2, c);
      }
    },
  },

  /* ---- more nature ------------------------------------------------------ */

  bush: {
    name: 'Bush', group: 'Nature',
    blurb: 'Low scrub. Cheap, and it breaks up an empty verge.',
    params: { at: [0, 1, 0.002, 0.2], off: [8, 260, 1, 22],
              size: [1, 8, 0.2, 2.4] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const leaf = ctx.pal.prop || 0x37624a;
      const rnd = ctx.mulberry(Math.round(p.at * 6421));
      for (let k = 0; k < 3; k++) {
        const r = p.size * (0.5 + rnd() * 0.5);
        kitObox(ctx, f, a.x + f.fx * (rnd() - 0.5) * p.size,
                a.y, a.z + f.fz * (rnd() - 0.5) * p.size,
                r, r * 0.8, r, ctx.shade(leaf, rnd() * 0.2 - 0.1));
      }
    },
  },

  deadtree: {
    name: 'Dead tree', group: 'Nature',
    blurb: 'A bare trunk and three branches. One of these sets a mood.',
    params: { at: [0, 1, 0.002, 0.2], off: [10, 260, 1, 30],
              h: [4, 22, 0.5, 10] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const wood = ctx.shade(ctx.pal.prop || 0x37624a, -0.55);
      kitObox(ctx, f, a.x, a.y, a.z, 0.4, p.h, 0.4, wood);
      for (let k = 0; k < 3; k++) {
        const th = k * 2.1, up = p.h * (0.5 + k * 0.16);
        const dx = Math.cos(th) * p.h * 0.22, dz = Math.sin(th) * p.h * 0.22;
        ctx.face([a.x, a.y + up, a.z],
                 [a.x + dx, a.y + up + p.h * 0.16, a.z + dz],
                 [a.x + dx, a.y + up + p.h * 0.2, a.z + dz],
                 [a.x, a.y + up + 0.4, a.z], ctx.shade(wood, 0.1));
      }
    },
  },

  cactus: {
    name: 'Cactus', group: 'Nature',
    blurb: 'A saguaro with two arms. For anywhere dry.',
    params: { at: [0, 1, 0.002, 0.2], off: [10, 260, 1, 26],
              h: [3, 14, 0.5, 7] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const green = ctx.shade(ctx.pal.prop || 0x37624a, 0.1);
      kitObox(ctx, f, a.x, a.y, a.z, 0.6, p.h, 0.6, green);
      for (const sgn of [-1, 1]) {
        const yy = a.y + p.h * (sgn > 0 ? 0.5 : 0.66);
        kitObox(ctx, f, a.x + f.rx * sgn * 1.3, yy, a.z + f.rz * sgn * 1.3,
                0.42, 0.42, 1.4, green);
        kitObox(ctx, f, a.x + f.rx * sgn * 2.1, yy, a.z + f.rz * sgn * 2.1,
                0.42, p.h * 0.3, 0.42, ctx.shade(green, -0.06));
      }
    },
  },

  hedge: {
    name: 'Hedge', group: 'Nature',
    blurb: 'A run of clipped hedge along the edge. Reads as somewhere kept.',
    params: { at: [0, 1, 0.002, 0.2], to: [0, 1, 0.002, 0.3],
              off: [8, 120, 1, 22], h: [1, 6, 0.1, 2.2] },
    build(ctx, p) {
      const from = ctx.at(kitClamp(Math.min(p.at, p.to), 0, 1));
      const to = ctx.at(kitClamp(Math.max(p.at, p.to), 0, 1));
      const side = (Number(p.side) < 0) ? -1 : 1;
      const off = side * Math.abs(p.off);
      const leaf = ctx.shade(ctx.pal.prop || 0x37624a, -0.05);
      for (let i = from; i < to; i += 2) {
        const f = kitFrame(ctx, i);
        const [x, z] = ctx.spot(i, off);
        kitObox(ctx, f, x, ctx.ground(i, off), z, 3.6, p.h, 1.1,
                ctx.shade(leaf, (i % 4) ? 0.04 : -0.04));
      }
    },
  },

  /* ---- more buildings --------------------------------------------------- */

  house: {
    name: 'House', group: 'Buildings',
    blurb: 'Walls, a pitched roof and a chimney. A few make a village.',
    params: { at: [0, 1, 0.002, 0.3], off: [16, 260, 1, 44],
              w: [5, 24, 0.5, 10], h: [3, 12, 0.5, 5] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const wall = ctx.shade(ctx.pal.rail || 0xd8dde2, 0.05);
      const roof = ctx.shade(ctx.pal.kerb2 || 0xc0392b, -0.25);
      kitObox(ctx, f, a.x, a.y, a.z, p.w * 0.6, p.h, p.w / 2, wall);
      // The roof as two shrinking slabs: a real pitch needs triangles the
      // house does not earn, and this reads as one at any distance you see it.
      for (let k = 0; k < 3; k++) {
        const t = (k + 1) / 4;
        kitObox(ctx, f, a.x, a.y + p.h + k * p.h * 0.22, a.z,
                p.w * 0.62 * (1 - t * 0.5), p.h * 0.24,
                p.w * 0.52 * (1 - t * 0.7), ctx.shade(roof, -k * 0.05));
      }
      kitObox(ctx, f, a.x + f.fx * p.w * 0.3, a.y + p.h,
              a.z + f.fz * p.w * 0.3, 0.5, p.h * 0.9, 0.5,
              ctx.shade(wall, -0.35));
    },
  },

  barn: {
    name: 'Barn', group: 'Buildings',
    blurb: 'A big red shed with a hayloft door.',
    params: { at: [0, 1, 0.002, 0.3], off: [18, 260, 1, 50],
              len: [10, 60, 1, 26], w: [8, 40, 1, 16], h: [5, 20, 0.5, 9] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const red = ctx.shade(ctx.pal.kerb2 || 0xc0392b, -0.3);
      kitObox(ctx, f, a.x, a.y, a.z, p.len / 2, p.h, p.w / 2, red);
      for (let k = 0; k < 3; k++) {
        const t = (k + 1) / 4;
        kitObox(ctx, f, a.x, a.y + p.h + k * 1.1, a.z, p.len / 2 + 0.4,
                1.2, (p.w / 2) * (1 - t * 0.62),
                ctx.shade(ctx.pal.rail || 0xd8dde2, -0.4));
      }
      kitObox(ctx, f, a.x + f.fx * p.len / 2, a.y + p.h * 0.45,
              a.z + f.fz * p.len / 2, 0.25, p.h * 0.5, p.w * 0.2,
              ctx.shade(red, -0.4));
    },
  },

  silo: {
    name: 'Silo', group: 'Buildings',
    blurb: 'A tall cylinder with a domed cap. Good in pairs beside a barn.',
    params: { at: [0, 1, 0.002, 0.3], off: [16, 260, 1, 46],
              h: [8, 44, 0.5, 20], r: [2, 9, 0.2, 4 ] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const metal = ctx.shade(ctx.pal.rail || 0xd8dde2, -0.12);
      // Eight sides rather than a box: a silo is the one shape here where
      // being round is the whole silhouette.
      const sides = 8;
      for (let k = 0; k < sides; k++) {
        const th = (k / sides) * Math.PI * 2, th2 = ((k + 1) / sides) * Math.PI * 2;
        const P = (t, up) => [a.x + (f.fx * Math.cos(t) + f.rx * Math.sin(t)) * p.r,
                              a.y + up,
                              a.z + (f.fz * Math.cos(t) + f.rz * Math.sin(t)) * p.r];
        ctx.face(P(th, 0), P(th2, 0), P(th2, p.h), P(th, p.h),
                 ctx.shade(metal, Math.cos(th) * 0.1));
        ctx.face(P(th, p.h), P(th2, p.h),
                 [a.x, a.y + p.h + p.r * 0.7, a.z],
                 [a.x, a.y + p.h + p.r * 0.7, a.z],
                 ctx.shade(metal, -0.2));
      }
    },
  },

  factory: {
    name: 'Factory', group: 'Buildings',
    blurb: 'A shed with a sawtooth roof and a chimney. Industrial, instantly.',
    params: { at: [0, 1, 0.002, 0.3], off: [20, 300, 1, 60],
              len: [16, 120, 1, 46], w: [12, 60, 1, 28], h: [5, 24, 0.5, 10] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const wall = kitBuilt(ctx, -0.12);
      kitObox(ctx, f, a.x, a.y, a.z, p.len / 2, p.h, p.w / 2, wall);
      const teeth = Math.max(2, Math.round(p.len / 12));
      for (let k = 0; k < teeth; k++) {
        const d = (k - (teeth - 1) / 2) * (p.len / teeth);
        kitObox(ctx, f, a.x + f.fx * d, a.y + p.h, a.z + f.fz * d,
                p.len / teeth * 0.34, 2.4, p.w / 2 + 0.3,
                ctx.shade(wall, -0.22));
      }
      kitObox(ctx, f, a.x + f.fx * p.len * 0.36 - f.rx * a.side * p.w * 0.3,
              a.y, a.z + f.fz * p.len * 0.36 - f.rz * a.side * p.w * 0.3,
              1.5, p.h * 2.4, 1.5, ctx.shade(wall, -0.3));
    },
  },

  apartments: {
    name: 'Apartments', group: 'Buildings',
    blurb: 'A slab block with balconies. Fills a city edge fast.',
    params: { at: [0, 1, 0.002, 0.3], off: [24, 400, 1, 80],
              len: [12, 90, 1, 34], h: [10, 90, 1, 34] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const wall = kitBuilt(ctx, -0.3);
      kitObox(ctx, f, a.x, a.y, a.z, p.len / 2, p.h, 8, wall);
      const floors = Math.max(2, Math.round(p.h / 4.2));
      for (let k = 1; k < floors; k++) {
        kitObox(ctx, f, a.x - f.rx * a.side * 8.6, a.y + k * (p.h / floors),
                a.z - f.rz * a.side * 8.6, p.len / 2 - 1, 0.4, 1.4,
                ctx.shade(wall, -0.24));
      }
      kitObox(ctx, f, a.x, a.y + p.h, a.z, p.len / 2 + 0.8, 0.7, 8.8,
              ctx.shade(wall, -0.32));
    },
  },

  /* ---- more circuit ----------------------------------------------------- */

  podium: {
    name: 'Podium', group: 'Circuit',
    blurb: 'Three steps and a backdrop. Put it where the lap ends.',
    params: { at: [0, 1, 0.002, 0.02], off: [12, 80, 1, 24] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const box = ctx.shade(ctx.pal.rail || 0xd8dde2, -0.06);
      const steps = [[0, 3.2], [-1, 2.2], [1, 2.6]];
      for (const [d, h] of steps) {
        kitObox(ctx, f, a.x + f.fx * d * 3.2, a.y, a.z + f.fz * d * 3.2,
                1.5, h, 2.2, ctx.shade(box, d === 0 ? 0.08 : -0.04));
      }
      kitObox(ctx, f, a.x - f.rx * a.side * 2.6, a.y,
              a.z - f.rz * a.side * 2.6, 5.4, 6.4, 0.3,
              ctx.shade(ctx.pal.kerb2 || 0xe8453c, -0.1));
    },
  },

  marshal: {
    name: 'Marshal post', group: 'Circuit',
    blurb: 'A hut with a flag. Real circuits have one at every corner.',
    params: { at: [0, 1, 0.002, 0.2], off: [10, 80, 1, 18] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const hut = ctx.shade(ctx.pal.rail || 0xd8dde2, -0.15);
      kitObox(ctx, f, a.x, a.y, a.z, 1.6, 2.6, 1.4, hut);
      kitObox(ctx, f, a.x, a.y + 2.6, a.z, 2.0, 0.35, 1.8,
              ctx.shade(hut, -0.3));
      kitObox(ctx, f, a.x + f.fx * 2.2, a.y, a.z + f.fz * 2.2, 0.16, 5, 0.16,
              ctx.shade(hut, -0.4));
      kitObox(ctx, f, a.x + f.fx * 2.2 - f.rx * a.side * 0.9, a.y + 4.1,
              a.z + f.fz * 2.2 - f.rz * a.side * 0.9, 0.05, 0.7, 0.9,
              ctx.pal.deco || 0xf2c94c, ctx.bright);
    },
  },

  lights: {
    name: 'Start lights', group: 'Circuit',
    blurb: 'A lit gantry over the road. Five reds, and they are unlit '
         + 'geometry so they read as lights.',
    params: { at: [0, 1, 0.002, 0.0], h: [5, 18, 0.5, 8],
              span: [10, 60, 1, 24] },
    build(ctx, p) {
      const i = ctx.at(kitClamp(Number(p.at) || 0, 0, 1));
      const f = kitFrame(ctx, i);
      const post = ctx.shade(ctx.pal.rail || 0xd8dde2, -0.42);
      for (const sgn of [-1, 1]) {
        const [lx, lz] = ctx.spot(i, sgn * p.span / 2);
        kitObox(ctx, f, lx, ctx.ground(i, sgn * p.span / 2), lz,
                0.5, p.h, 0.5, post);
      }
      const [cx, cz] = ctx.spot(i, 0);
      const cy = ctx.ground(i, 0);
      kitObox(ctx, f, cx, cy + p.h, cz, 0.5, 1.0, p.span / 2, post);
      kitObox(ctx, f, cx, cy + p.h - 1.9, cz, 0.35, 1.7, p.span * 0.28,
              ctx.shade(post, -0.35));
      for (let k = 0; k < 5; k++) {
        const o = (k - 2) * p.span * 0.1;
        kitObox(ctx, f, cx + f.rx * o, cy + p.h - 1.5, cz + f.rz * o,
                0.42, 0.9, 0.55, 0xe8221a, ctx.bright);
      }
    },
  },

  tecpro: {
    name: 'Barrier blocks', group: 'Circuit', collides: true,
    blurb: 'A run of energy-absorbing blocks. Solid: this one changes lap '
         + 'times, and it is how a fast corner gets an edge you can lean on.',
    params: { at: [0, 1, 0.002, 0.2], to: [0, 1, 0.002, 0.27],
              off: [6, 60, 0.5, 16], h: [0.8, 3, 0.1, 1.2] },
    build(ctx, p) {
      const from = ctx.at(kitClamp(Math.min(p.at, p.to), 0, 1));
      const to = ctx.at(kitClamp(Math.max(p.at, p.to), 0, 1));
      const side = (Number(p.side) < 0) ? -1 : 1;
      const off = side * Math.abs(p.off);
      const blue = ctx.shade(ctx.pal.rail || 0xd8dde2, -0.1);
      for (let i = from; i < to; i++) {
        const [x0, z0] = ctx.spot(i, off), [x1, z1] = ctx.spot(i + 1, off);
        const y0 = ctx.ground(i, off), y1 = ctx.ground(i + 1, off);
        const a = [x0, y0, z0], b = [x1, y1, z1];
        const c = [x1, y1 + p.h, z1], d = [x0, y0 + p.h, z0];
        ctx.face(a, b, c, d, (i % 2) ? blue : ctx.shade(blue, -0.35));
        ctx.col.addQuad(a, b, c, d, ctx.KIND.WALL);
      }
    },
  },

  catchfence: {
    name: 'Catch fence', group: 'Circuit',
    blurb: 'Posts and mesh above the barrier. Mesh only - the car goes '
         + 'through it, which is why it goes *above* a real barrier.',
    params: { at: [0, 1, 0.002, 0.2], to: [0, 1, 0.002, 0.3],
              off: [8, 80, 0.5, 20], h: [2, 10, 0.2, 5 ] },
    build(ctx, p) {
      const from = ctx.at(kitClamp(Math.min(p.at, p.to), 0, 1));
      const to = ctx.at(kitClamp(Math.max(p.at, p.to), 0, 1));
      const side = (Number(p.side) < 0) ? -1 : 1;
      const off = side * Math.abs(p.off);
      const steel = ctx.shade(ctx.pal.rail || 0xd8dde2, -0.3);
      for (let i = from; i < to; i += 4) {
        const f = kitFrame(ctx, i);
        const [x, z] = ctx.spot(i, off);
        kitObox(ctx, f, x, ctx.ground(i, off), z, 0.22, p.h, 0.22, steel);
      }
      // Three horizontal rails rather than a solid panel: a fence you can see
      // the track through is the point of a fence.
      for (let k = 1; k <= 3; k++) {
        for (let i = from; i < to; i++) {
          const [x0, z0] = ctx.spot(i, off), [x1, z1] = ctx.spot(i + 1, off);
          const y0 = ctx.ground(i, off) + p.h * k / 3.2;
          const y1 = ctx.ground(i + 1, off) + p.h * k / 3.2;
          ctx.face([x0, y0, z0], [x1, y1, z1], [x1, y1 + 0.18, z1],
                   [x0, y0 + 0.18, z0], steel);
        }
      }
    },
  },

  flags: {
    name: 'Flag poles', group: 'Circuit',
    blurb: 'A run of poles with flags. Each one a different colour off the '
         + 'palette.',
    params: { at: [0, 1, 0.002, 0.2], to: [0, 1, 0.002, 0.26],
              off: [8, 90, 1, 22], h: [4, 20, 0.5, 9], every: [2, 20, 1, 6] },
    build(ctx, p) {
      const from = ctx.at(kitClamp(Math.min(p.at, p.to), 0, 1));
      const to = ctx.at(kitClamp(Math.max(p.at, p.to), 0, 1));
      const side = (Number(p.side) < 0) ? -1 : 1;
      const off = side * Math.abs(p.off);
      const pole = ctx.shade(ctx.pal.rail || 0xd8dde2, 0.15);
      const cols = [ctx.pal.kerb2 || 0xe8453c, ctx.pal.deco || 0xf2c94c,
                    ctx.pal.rail || 0xd8dde2];
      let n = 0;
      for (let i = from; i <= to; i += Math.max(2, Math.round(p.every))) {
        const f = kitFrame(ctx, i);
        const [x, z] = ctx.spot(i, off);
        const y = ctx.ground(i, off);
        kitObox(ctx, f, x, y, z, 0.14, p.h, 0.14, pole);
        kitObox(ctx, f, x - f.rx * side * 0.9, y + p.h * 0.72,
                z - f.rz * side * 0.9, 0.04, p.h * 0.2, 0.85,
                cols[n++ % cols.length]);
      }
    },
  },

  /* ---- the street ------------------------------------------------------- */

  streetlamp: {
    name: 'Street light', group: 'Street',
    blurb: 'A curved lamp post. A run of them down a straight reads as a road '
         + 'rather than a track.',
    params: { at: [0, 1, 0.002, 0.2], off: [8, 60, 0.5, 15],
              h: [4, 16, 0.5, 8] },
    build(ctx, p) {
      const a = kitAnchor(ctx, p), f = kitFrame(ctx, a.i);
      const post = ctx.shade(ctx.pal.rail || 0xd8dde2, -0.5);
      kitObox(ctx, f, a.x, a.y, a.z, 0.2, p.h, 0.2, post);
      for (let k = 0; k < 3; k++) {
        kitObox(ctx, f, a.x - f.rx * a.side * (0.6 + k * 0.7),
                a.y + p.h + k * 0.3, a.z - f.rz * a.side * (0.6 + k * 0.7),
                0.18, 0.32, 0.7, post);
      }
      kitObox(ctx, f, a.x - f.rx * a.side * 2.4, a.y + p.h + 0.6,
              a.z - f.rz * a.side * 2.4, 0.3, 0.26, 0.8,
              0xfff0c8, ctx.bright);
    },
  },

  pole: {
    name: 'Telegraph poles', group: 'Street',
    blurb: 'A run of poles with a crossbar and wires between them.',
    params: { at: [0, 1, 0.002, 0.2], to: [0, 1, 0.002, 0.34],
              off: [12, 120, 1, 34], h: [6, 20, 0.5, 11], every: [4, 30, 1, 12] },
    build(ctx, p) {
      const from = ctx.at(kitClamp(Math.min(p.at, p.to), 0, 1));
      const to = ctx.at(kitClamp(Math.max(p.at, p.to), 0, 1));
      const side = (Number(p.side) < 0) ? -1 : 1;
      const off = side * Math.abs(p.off);
      const wood = ctx.shade(ctx.pal.prop || 0x37624a, -0.6);
      const step = Math.max(4, Math.round(p.every));
      let prev = null;
      for (let i = from; i <= to; i += step) {
        const f = kitFrame(ctx, i);
        const [x, z] = ctx.spot(i, off);
        const y = ctx.ground(i, off);
        kitObox(ctx, f, x, y, z, 0.24, p.h, 0.24, wood);
        kitObox(ctx, f, x, y + p.h * 0.88, z, 0.16, 0.24, 1.7,
                ctx.shade(wood, 0.08));
        if (prev) {
          for (const sgn of [-1, 1]) {
            const ax = prev[0] + prev[3] * sgn * 1.5;
            const az = prev[2] + prev[4] * sgn * 1.5;
            const bx = x + f.rx * sgn * 1.5, bz = z + f.rz * sgn * 1.5;
            const ay = prev[1] + p.h * 0.86, by = y + p.h * 0.86;
            ctx.face([ax, ay, az], [bx, by, bz],
                     [bx, by - 0.12, bz], [ax, ay - 0.12, az],
                     ctx.shade(wood, -0.2));
          }
        }
        prev = [x, y, z, f.rx, f.rz];
      }
    },
  },

  bollards: {
    name: 'Bollards', group: 'Street',
    blurb: 'A line of short posts. Marks an edge without being solid.',
    params: { at: [0, 1, 0.002, 0.2], to: [0, 1, 0.002, 0.26],
              off: [4, 40, 0.5, 11], every: [1, 10, 1, 3] },
    build(ctx, p) {
      const from = ctx.at(kitClamp(Math.min(p.at, p.to), 0, 1));
      const to = ctx.at(kitClamp(Math.max(p.at, p.to), 0, 1));
      const side = (Number(p.side) < 0) ? -1 : 1;
      const c = ctx.shade(ctx.pal.rail || 0xd8dde2, -0.05);
      for (let i = from; i <= to; i += Math.max(1, Math.round(p.every))) {
        const f = kitFrame(ctx, i);
        const [x, z] = ctx.spot(i, side * p.off);
        const y = ctx.ground(i, side * p.off);
        kitObox(ctx, f, x, y, z, 0.3, 1.0, 0.3, c);
        kitObox(ctx, f, x, y + 1.0, z, 0.24, 0.2, 0.24,
                ctx.shade(ctx.pal.kerb2 || 0xe8453c, 0));
      }
    },
  },

  /* ---- more ground ------------------------------------------------------ */

  grid: {
    name: 'Starting grid', group: 'Ground',
    blurb: 'Painted grid boxes in two staggered columns.',
    params: { at: [0, 1, 0.002, 0.0], rows: [2, 16, 1, 6] },
    build(ctx, p) {
      const start = ctx.at(kitClamp(Number(p.at) || 0, 0, 1));
      const paint = ctx.shade(ctx.pal.kerb || 0xf4f4f2, 0.1);
      const rows = Math.round(p.rows);
      for (let r = 0; r < rows; r++) {
        const i = Math.min(ctx.track.line.length - 2, start + 3 + r * 4);
        const f = kitFrame(ctx, i);
        const o = (r % 2 ? 1 : -1) * 2.6;
        const [x, z] = ctx.spot(i, o);
        kitSlab(ctx, f, x, ctx.ground(i, o) + 0.05, z, 2.6, 1.1, paint);
      }
    },
  },

  skids: {
    name: 'Skid marks', group: 'Ground',
    blurb: 'Two dark lines on the road. Best through a corner.',
    params: { at: [0, 1, 0.002, 0.2], to: [0, 1, 0.002, 0.24],
              off: [-8, 8, 0.5, 0] },
    build(ctx, p) {
      const from = ctx.at(kitClamp(Math.min(p.at, p.to), 0, 1));
      const to = ctx.at(kitClamp(Math.max(p.at, p.to), 0, 1));
      const dark = ctx.shade(ctx.pal.road || 0x4d5464, -0.4);
      for (let i = from; i < to; i++) {
        const f = kitFrame(ctx, i);
        for (const sgn of [-1, 1]) {
          const o = (Number(p.off) || 0) + sgn * 0.9;
          const [x, z] = ctx.spot(i, o);
          // On the road, so it takes the road's own height and not the
          // ground's - the ground beside it is 1.2 lower.
          kitSlab(ctx, f, x, ctx.track.line[i].p[1] + 0.03, z, 2.0, 0.35, dark);
        }
      }
    },
  },

  wall: {
    name: 'Barrier', group: 'Ground', collides: true,
    blurb: 'Solid, and the only model here a lap time can feel: it is how you '
         + 'stop a corner being cut.',
    params: { at: [0, 1, 0.002, 0.2], to: [0, 1, 0.002, 0.28],
              off: [4, 60, 0.5, 13], h: [0.6, 4, 0.1, 1.5] },
    build(ctx, p) {
      const from = ctx.at(kitClamp(Math.min(p.at, p.to), 0, 1));
      const to = ctx.at(kitClamp(Math.max(p.at, p.to), 0, 1));
      const side = (Number(p.side) < 0) ? -1 : 1;
      const off = side * Math.abs(p.off);
      const c = ctx.pal.rail || 0xd8dde2;
      for (let i = from; i < to; i++) {
        const [x0, z0] = ctx.spot(i, off), [x1, z1] = ctx.spot(i + 1, off);
        const y0 = ctx.ground(i, off), y1 = ctx.ground(i + 1, off);
        const a = [x0, y0, z0], b = [x1, y1, z1];
        const cc = [x1, y1 + p.h, z1], d = [x0, y0 + p.h, z0];
        ctx.face(a, b, cc, d, c);
        ctx.col.addQuad(a, b, cc, d, ctx.KIND.WALL);
      }
    },
  },
};

/**
 * The whole library as a description, for the editor's palette and for the spec
 * handed to somebody's AI. Derived from MODELS, so a model added is a model
 * both of those know about.
 */
export function catalogue() {
  return Object.entries(MODELS).map(([o, m]) => ({
    o, name: m.name, group: m.group, blurb: m.blurb,
    params: m.params, collides: !!m.collides,
  }));
}

/** Every placement's default parameters, ready to drop in. */
export function placementDefaults(o) {
  const m = MODELS[o];
  if (!m) return null;
  const p = { o };
  for (const [k, [, , , d]] of Object.entries(m.params)) p[k] = d;
  if (m.params.off) p.side = -1;
  return p;
}

// A placement list is data, and the budget is on the numbers it produces. The
// pool runs 534 to 13,188 collider triangles; these are set above the busiest
// track that ships, and the same limits the code sandbox uses - one budget,
// whichever way the geometry was authored.
export const KIT_LIMITS = { items: 240, mesh: 24000, collider: 3000 };

/**
 * Draw a placement list. The one interpreter, reached by all four callers.
 *
 * Refuses by name rather than throwing something opaque: an unknown `o` is a
 * placement the author or their model invented, and "there is no model called
 * `gazebo`" is the message that fixes it. A parameter outside its declared
 * range is clamped rather than refused - the range is what the editor's slider
 * offers, and a document that arrived from elsewhere should draw *something*
 * rather than nothing.
 *
 * Returns a list of problems, which the editor shows and the play page ignores:
 * a live track's placements were validated when it was approved.
 */
export function placeAll(ctx, list) {
  const problems = [];
  if (!Array.isArray(list) || !list.length) return problems;
  if (list.length > KIT_LIMITS.items) {
    problems.push('Too many placements: ' + list.length + ', and the limit is '
      + KIT_LIMITS.items + '.');
    list = list.slice(0, KIT_LIMITS.items);
  }
  list.forEach((p, idx) => {
    if (!p || typeof p !== 'object') return;
    const m = MODELS[p.o];
    if (!m) {
      problems.push('#' + idx + ': there is no model called "' + p.o + '". '
        + 'The library is: ' + Object.keys(MODELS).join(', ') + '.');
      return;
    }
    // Clamped to the declared range, and filled in where absent, so a model
    // never receives a NaN and three.js never gets a vertex at nowhere.
    const q = { o: p.o, side: p.side };
    for (const [k, [lo, hi, , d]] of Object.entries(m.params)) {
      const v = Number(p[k]);
      q[k] = Number.isFinite(v) ? kitClamp(v, lo, hi) : d;
    }
    if (p.to !== undefined && m.params.to === undefined) q.to = p.to;
    try {
      m.build(ctx, q);
    } catch (e) {
      problems.push('#' + idx + ' (' + m.name + '): ' + (e && e.message || e));
    }
  });
  return problems;
}

export { MODELS, kitAnchor, kitFrame, kitObox, kitSlab };
