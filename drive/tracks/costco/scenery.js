// Costco Wholesale: the shell the road drives into, and everything inside it.
//
// The pool's only *interior*, and the reason `tracks/<slug>/scenery.js` exists at
// all. No amount of palette configuration produces a warehouse: it needs walls
// with doorways cut where the road goes through them, a roof with holes where the
// travelators come up, and racking that is solid enough to hit.
//
// Registered on a plain global rather than imported, and inlined into the play
// page as a classic `<script>`. See the note above `sceneryFor` in trackmesh.js
// for why that is forced rather than lazy - the short version is that a classic
// inline script runs before any deferred module, so there is nothing to import
// from yet, and that the same shape is what lets `jsrt` concatenate this file
// into the QuickJS bundle for the anti-cheat.
//
// **This file is in the collider, not just the picture.** `verify.py` re-drives
// submitted laps through `buildTrack`, so a lap that grazed a shelf in the browser
// has to graze the same shelf on the server.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.costco = { props: props };

  /**
   * Everything the old top-level `addBuilding` closed over, now handed in.
   *
   * `shade`, `mulberry`, `inside`, `plate` and `sheet` were module-level helpers
   * in trackmesh.js and are passed on `ctx` instead; `KIND` is the collision
   * surface enum. Nothing else changed - the geometry below is the geometry that
   * was there.
   */
  function props(ctx) {
    const { solid, bright, signs, col, track, pal, cfg } = ctx;
    const { KIND, shade, mulberry, inside, plate, sheet } = ctx;
    addBuilding(solid, bright, signs, col, track, pal, cfg);

  /**
   * The Costco: a shell the road drives into, and everything inside it.
   *
   * This is the pool's only *interior*, and it is a sibling of `addScenery`
   * rather than a use of Spa's `furniture` block, deliberately. `addFurniture` is
   * only reachable from inside `buildTrack`'s `else if (terrain)` branch, so
   * borrowing it would mean giving a flat track a height field it has no use for -
   * and its vocabulary is grandstands, pit buildings and gantries, which is not
   * what a warehouse is made of. What it does borrow is the parts that are already
   * proven: both faces on everything (the world mesh is `MeshLambertMaterial`,
   * which is `FrontSide`), the `bright` buffer for anything that should read as
   * lit, and the existing `signs` contract for the only textured geometry here.
   *
   * Three things are derived from the road rather than authored beside it, because
   * each of them is a place where a second copy would drift:
   *
   *  * **the doorways** are wherever the road crosses a wall. There is no list of
   *    door positions to get wrong, and a leg that moves takes its door with it;
   *  * **the holes in the roof** are wherever the road passes *through* the roof
   *    plane, which is the two travelator ramps and nothing else. The rooftop deck
   *    passes over the roof rather than through it and keeps its roof;
   *  * **the racking** stands half an aisle either side of every straight aisle
   *    station, which is the midpoint between two aisles, clipped by `toRoad` so a
   *    run stops rather than crossing the next aisle - the same signal Spa's
   *    armco, run-off and grandstands all read.
   *
   * The shell's four numbers are the one thing that *is* authored, and they are
   * not derived from the road on purpose: the road is authored to pass *through*
   * these walls, so deriving the walls from the road is circular - the wall
   * position would depend on which stations you were using to decide where the
   * wall goes. They arrive on `cfg` from `tracks/costco/palette.py`, which reads
   * them from the same constants the track's own geometry uses.
   *
   * **They used to be a second copy.** The palette was a JavaScript object in
   * trackmesh.js while the road was authored in Python, so `SHELL_X`/`SHELL_Z`/
   * `SHELL_CEIL` existed twice in two languages and were held together by a test
   * that scraped this file with a regular expression. The palette is Python now,
   * so there is one copy and the test is gone.
   */
  function addBuilding(solid, bright, signs, col, track, pal, cfg) {
    const line = track.line, n = line.length;
    const X0 = cfg.x[0], X1 = cfg.x[1], Z0 = cfg.z[0], Z1 = cfg.z[1];
    const CEIL = cfg.ceil != null ? cfg.ceil : 11;
    const DOOR = cfg.door != null ? cfg.door : 24;
    const base = track.ground != null ? track.ground : 0;   // the floor plate
    const WALL = cfg.wall != null ? cfg.wall : 0xdcd8d0;
    const STEEL = cfg.steel != null ? cfg.steel : 0x8e949c;
    const T = 1.4;                       // wall thickness: tilt-up concrete

    // Both faces. A wall is looked at from inside and from out, and a single
    // winding gives you one of those and an invisible wall for the other - which
    // is exactly how Spa's pit building spent an afternoon as a roof floating in
    // the sky.
    const face = (a, b, c, d, k) => { solid.quad(a, b, c, d, k); solid.quad(a, d, c, b, k); };

    // Drawn and solid, five faces as WALL - the same single-sided-per-side rule
    // `solidBox` in buildTrack uses, and for the same reason: the wall query works
    // its push-out direction from the closest point on the triangle.
    const box = (cx, cy, cz, hx, hy, hz, k) => {
      solid.box(cx, cy, cz, hx, hy, hz, k);
      const P = (sx, sy, sz) => [cx + sx * hx, cy + sy * hy, cz + sz * hz];
      const v = [P(-1, -1, -1), P(1, -1, -1), P(1, -1, 1), P(-1, -1, 1),
                 P(-1, 1, -1), P(1, 1, -1), P(1, 1, 1), P(-1, 1, 1)];
      col.addQuad(v[4], v[7], v[6], v[5], KIND.WALL);
      col.addQuad(v[0], v[4], v[5], v[1], KIND.WALL);
      col.addQuad(v[1], v[5], v[6], v[2], KIND.WALL);
      col.addQuad(v[2], v[6], v[7], v[3], KIND.WALL);
      col.addQuad(v[3], v[7], v[4], v[0], KIND.WALL);
    };

    // How far (x,z) is from the nearest road centre that is anywhere near height
    // `y`, in plan.
    //
    // This is `terrain.toRoad` for a track with no terrain to ask, and it answers
    // the one question every piece of trackside furniture in this game has to ask
    // before it builds: is some *other* part of the track already here?
    //
    // **The height window is the whole difference on this track**, and leaving it
    // out is a bug that looks like nothing. Spa's legs all lie in one sheet, so a
    // plan distance is the right question there; here a rooftop car park flies
    // 14.5 units over the aisles, and a plan-only answer reports the deck as being
    // "at" every point below it. What that cost: the racking down the south side of
    // aisle one, silently, because the deck's south leg passes 4.7 units from it in
    // plan and three metres over its head. One aisle came out shelved on one side.
    const toRoad = (x, z, y) => {
      let best = Infinity;
      for (let i = 0; i < n; i++) {
        const p = line[i].p;
        if (y != null && Math.abs(p[1] - y) > 5) continue;
        const dx = p[0] - x, dz = p[2] - z;
        const d = dx * dx + dz * dz;
        if (d < best) best = d;
      }
      return Math.sqrt(best);
    };

    // A board onto the existing `signs` list, so everything textured here is
    // painted by the same canvas path and batched with every other board reading
    // the same words. A board canvas is 4:1, so the height follows the width.
    const put = (text, cx, cy, cz, r, nv, hw) => {
      signs.push({ text, c: [cx, cy, cz], r, u: [0, 1, 0], hw, hh: hw / 4, n: nv });
    };
    const sg = cfg.sign || {};

    const inShell = (x, z) => x > X0 + T && x < X1 - T && z > Z0 + T && z < Z1 - T;

    // The last stretch indoors: everything still at floor level after the
    // travelator has brought you back down, up to the door. Found rather than
    // authored, so it stays the checkout run however the lap is retimed - and
    // worked out up here because the racking needs it too, to keep out of it.
    let lastUp = -1;
    for (let i = 0; i < n; i++) if (line[i].p[1] > 1.0) lastUp = i;
    const tills = [];
    for (let i = lastUp + 1; i < n; i++) {
      if (!inShell(line[i].p[0], line[i].p[2])) break;
      tills.push(i);
    }

    // ---- the walls, and the doorways the road cuts in them -------------------
    // `axis` 0 is a wall of constant x, 2 one of constant z. Returns where along
    // the wall the road goes through it.
    const crossings_ = (axis, at, lo, hi) => {
      const oax = axis === 0 ? 2 : 0;
      const out = [];
      for (let i = 1; i < n; i++) {
        const a = line[i - 1].p, b = line[i].p;
        if ((a[axis] - at) * (b[axis] - at) >= 0) continue;
        const t = (at - a[axis]) / (b[axis] - a[axis]);
        const o = a[oax] + (b[oax] - a[oax]) * t;
        if (o >= lo && o <= hi) out.push(o);
      }
      return out.sort((p, q) => p - q);
    };

    // A doorway is the full height of the wall on purpose, with no header over
    // it. The chase camera rides 4.3 units above the car and swings wide of it
    // through a turn, so a lintel is a thing for the camera to pop through at the
    // exact moment the car is going through the door - and a Costco entrance is a
    // full-height opening anyway.
    const wall = (axis, at, lo, hi) => {
      const cuts = crossings_(axis, at, lo, hi);
      let s = lo;
      const spans = [];
      for (const c of cuts) {
        if (c - DOOR > s) spans.push([s, c - DOOR]);
        s = Math.max(s, c + DOOR);
      }
      if (hi > s) spans.push([s, hi]);
      const h = (CEIL - base) / 2;
      for (const [a, b] of spans) {
        const mid = (a + b) / 2, half = (b - a) / 2;
        if (half <= 0.2) continue;
        if (axis === 0) box(at, base + h, mid, T, h, half, WALL);
        else box(mid, base + h, at, half, h, T, WALL);
        // A parapet, so the roofline reads as built rather than as a cut edge.
        // Lifted off the roof plane rather than resting exactly on it, or its
        // underside is coplanar with the edge roof panel the whole way round.
        if (axis === 0) box(at, CEIL + 0.62, mid, T * 1.2, 0.5, half, shade(WALL, -0.12));
        else box(mid, CEIL + 0.62, at, half, 0.5, T * 1.2, shade(WALL, -0.12));
      }
      return cuts;
    };

    const westDoors = wall(0, X0, Z0, Z1);
    const eastDoors = wall(0, X1, Z0, Z1);
    wall(2, Z0, X0, X1);
    wall(2, Z1, X0, X1);

    // ---- the entrance ------------------------------------------------------
    // A projecting portal round each front door. Two jobs: a 240-by-188 shed 12
    // units tall is honestly what a Costco is, and from the car park it reads as a
    // kerb rather than as a building, so the front needs something with height on
    // it. And it is the one piece of this the preview picture is guaranteed to
    // frame, because the lap starts out here.
    //
    // The header's underside is held at 9.5 deliberately. The chase camera rides
    // about 5 units up and comes through the doorway a beat after the car does, so
    // anything lower is a beam for the camera to pop through at exactly the wrong
    // moment - which is also why the opening itself has no lintel.
    const trim = pal.kerb2 != null ? pal.kerb2 : 0xe31837;
    // The entrance portal, and the board that goes on it. `SIGN_HW` is derived
    // from the header's own height because the board canvas is 4:1 and the header
    // is nearer 9:1 - so the board cannot fill it, and the colour band under it has
    // to agree with the board rather than with the header, or it runs out past both
    // ends of the name and reads as a separate stripe.
    const OUT = 6, TOP = CEIL + 4.5, HEAD = 9.5;
    const SIGN_HW = (TOP - HEAD) * 2;
    const portal = (at, o, sgn) => {
      const xo = at + sgn * OUT / 2;
      for (const q of [-1, 1]) {
        box(xo, base + (TOP - base) / 2, o + q * (DOOR + 2.6), OUT / 2,
            (TOP - base) / 2, 2.6, shade(WALL, 0.05));
      }
      // The header. Its front face is what the wordmark goes on - see the signage
      // block - so all that is added here is a band of colour under it.
      box(xo, (HEAD + TOP) / 2, o, OUT / 2, (TOP - HEAD) / 2, DOOR + 2.6, shade(WALL, 0.05));
      box(at + sgn * (OUT + 0.3), HEAD + 0.45, o, 0.3, 0.45, SIGN_HW + 1.0, trim);
    };
    for (const z of westDoors) portal(X0, z, -1);
    for (const z of eastDoors) portal(X1, z, 1);

    // ---- the roof -----------------------------------------------------------
    // Cells, so a hole is a skipped cell rather than a boolean subtraction. A cell
    // goes if the road is near the roof plane there: that is the two ramps
    // punching through, and the rooftop deck, which is road *above* the roof and
    // is its own roof over the part of the shell it covers.
    const CELLR = 12;
    // How thick the roof slab is - see the note on the soffit below. Small enough
    // that the cut edge at a travelator hole is not worth closing, big enough that
    // the depth buffer never has to choose between the two faces.
    const DEEP = 0.3;
    // A cell goes only where the road passes *through* the roof plane, which on
    // this track is the two travelator ramps and nothing else.
    //
    // The test has to be "near the plane", not "above it". Above it also catches
    // the rooftop deck - which is road 3.5 units over the roof, standing on it -
    // and carved the deck's whole rectangular loop out of the roof it stands on.
    // What that looks like from the aisles is a moth-eaten ceiling with daylight
    // through it, which reads as a lighting bug rather than as missing geometry.
    const throughRoof = (x, z, r) => {
      for (let i = 0; i < n; i++) {
        const p = line[i].p;
        if (Math.abs(p[1] - CEIL) > 2.2) continue;
        if (Math.abs(p[0] - x) < r + line[i].hw && Math.abs(p[2] - z) < r + line[i].hw) return true;
      }
      return false;
    };
    const skyCol = cfg.skylight != null ? cfg.skylight : 0xeef6ff;
    const topCol = shade(WALL, -0.34);
    const litCol = shade(cfg.inner != null ? cfg.inner : 0xcfcbc4, 0.06);
    let ix = 0;
    for (let x = X0; x < X1; x += CELLR, ix++) {
      let iz = 0;
      for (let z = Z0; z < Z1; z += CELLR, iz++) {
        const x2 = Math.min(x + CELLR, X1), z2 = Math.min(z + CELLR, Z1);
        const cx = (x + x2) / 2, cz = (z + z2) / 2;
        if (throughRoof(cx, cz, CELLR / 2)) continue;
        const A = [x, CEIL, z], B = [x, CEIL, z2], C = [x2, CEIL, z2], D = [x2, CEIL, z];
        // A regular grid of daylight panels, which is what a warehouse roof is,
        // and it also stops the inside reading as a cave.
        const day = (ix % 3) === 1 && (iz % 2) === 0;
        // The top, lit, because it is the floor of the view from the rooftop deck.
        solid.quad(A, B, C, D, day ? shade(skyCol, -0.2) : topCol);
        // And the underside *unlit*, which is not a stylistic choice. A
        // downward-facing quad gets nothing from a key light overhead and only the
        // hemisphere's ground colour from below, so a lit ceiling comes out very
        // nearly black - and a black ceiling over the car is the single most
        // obvious thing in here. The `bright` buffer is what makes a surface read
        // as lit rather than as shadowed, and a warehouse ceiling is exactly that:
        // a pale soffit under daylight panels.
        //
        // **`DEEP` below the top, and it has to be something.** Drawn at the same
        // y these two are coplanar, and coplanar quads in two different meshes are
        // a depth-buffer coin toss: the roof flickers between its top and its
        // soffit as the camera moves, which from inside reads as the ceiling
        // strobing. Giving the roof real thickness settles the depth test the same
        // way lifting the apron off the height field does, and a roof having depth
        // is true anyway.
        const U = CEIL - DEEP;
        bright.quad([x, U, z], [x2, U, z], [x2, U, z2], [x, U, z2],
                    day ? skyCol : litCol);
      }
    }
    // Exposed joists under it, and the fluorescent battens hung off them. Neither
    // is in the collider: nothing drives up here, and a joist a car could hit
    // would be a car trap in the one place a driver never looks.
    const strip = cfg.strip != null ? cfg.strip : 0xfff2d8;
    // Hung clear underneath, in that order, and the clearances matter: a joist
    // centred so its top face lands *on* the roof plane is the roof's own flicker
    // again, and a batten inside the joist it hangs from is geometry buried in
    // geometry. Roof at CEIL, soffit at CEIL - DEEP, then these.
    const JOIST = CEIL - DEEP - 0.65, BATTEN = CEIL - DEEP - 1.55;
    for (let x = X0 + 8; x < X1; x += 16) {
      solid.box(x, JOIST, (Z0 + Z1) / 2, 0.35, 0.5, (Z1 - Z0) / 2, STEEL);
      for (let z = Z0 + 14; z < Z1; z += 34) {
        if (throughRoof(x, z, 6)) continue;
        bright.quad([x - 0.5, BATTEN, z - 7], [x + 0.5, BATTEN, z - 7],
                    [x + 0.5, BATTEN, z + 7], [x - 0.5, BATTEN, z + 7], strip);
      }
    }

    // ---- pallet racking -----------------------------------------------------
    // Runs along the ribbon at half an aisle out, which is the midline between
    // this aisle and the next. Straights only: `off` units to the inside of a
    // hairpin is the middle of the hairpin, and a shelf there is a wall on the
    // apex of a corner the racing line is already using.
    const R = cfg.rack || {};
    const off = R.off != null ? R.off : 14;
    const rh = R.h != null ? R.h : 9.5;
    // Shrink-wrapped stock, tinned goods, the blue pallet wrap everything arrives
    // in. Four colours is enough for the floor to stop reading as one product.
    const PALLET = [0xb08657, 0x2f6fb5, 0xb5432f, 0xd8d2c4];
    // What is actually on the shelves. Eight is enough that a hundred and fifty
    // units of racking never reads as one product repeated, and few enough that an
    // aisle still looks like a warehouse rather than a sweet shop.
    const GOODS = [0xc9542e, 0x2f6fb5, 0xe0c04a, 0x3f8f56,
                   0xa8332c, 0xe3ded2, 0x8a5a3c, 0x5f4b8b];
    const rack = [];
    for (let i = 1; i < n; i++) {
      const e = line[i];
      // Nothing past `lastUp`: that is the checkout run and the food court, and
      // shelving it as well leaves the last stretch indoors indistinguishable from
      // the four aisles you have just driven.
      const ok = e.p[1] < 1.0 && !e.curv && !e.air && i <= lastUp
              && inShell(e.p[0], e.p[2]);
      for (const s of [-1, 1]) {
        const k = s < 0 ? 0 : 1;
        // Half an aisle out, or hard against the wall if half an aisle out is
        // through it. The outermost aisle runs closer to the shell than the aisles
        // run to each other, so without the clamp its outer side gets no racking
        // at all and you drive the length of the building beside a blank wall -
        // which reads as unfinished rather than as a design. Racking against the
        // outer wall is what a warehouse does there anyway.
        const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
        const x = clamp(e.p[0] + e.lat[0] * off * s, X0 + 3, X1 - 3);
        const z = clamp(e.p[2] + e.lat[2] * off * s, Z0 + 3, Z1 - 3);
        const good = ok && inShell(x, z) && toRoad(x, z, e.p[1]) > e.hw + 2.5;
        if (!good) { rack[k] = null; continue; }
        const prev = rack[k];
        rack[k] = [x, z, e.lat[0] * -s, e.lat[2] * -s, i];
        if (!prev) continue;
        // The face toward the road, and one collision quad - the same economy
        // `wallStrip` explains: the wall query works its push-out direction from
        // the closest point on the triangle, so one face per side is both
        // necessary and sufficient.
        const a = [prev[0], base, prev[1]], b = [x, base, z];
        const at = [prev[0], base + rh, prev[1]], bt = [x, base + rh, z];
        face(a, b, bt, at, STEEL);
        col.addQuad(a, b, bt, at, KIND.WALL);
        // Shelf beams, so nine units of steel reads as racking and not as a wall.
        //
        // Stood off the face rather than laid on it: coplanar with it they z-fight,
        // and what that looks like at a glancing angle down an aisle is not
        // flicker but long tan splinters shooting off into the distance, which
        // reads as stray geometry rather than as two surfaces at the same depth.
        const nx = prev[2], nz = prev[3], OFF = 0.22;
        const LEVELS = [0.3, 0.56, 0.82];
        for (const f of LEVELS) {
          const y = base + rh * f;
          bright.quad([prev[0] + nx * OFF, y, prev[1] + nz * OFF],
                      [x + nx * OFF, y, z + nz * OFF],
                      [x + nx * OFF, y + 0.42, z + nz * OFF],
                      [prev[0] + nx * OFF, y + 0.42, prev[1] + nz * OFF],
                      shade(R.pallet != null ? R.pallet : 0xb08657, (f - 0.55) * 0.5));
        }
        // Stock on the shelves, two lots per bay per level so a run never reads as
        // one product repeated down the whole aisle.
        //
        // Drawn as panels standing on the beams and proud of the face, rather than
        // as boxes inside the racking: the face is opaque from both sides, so
        // anything tucked in behind it is stock nobody can see. Unlit for the same
        // reason the beams are - the aisles run east-west under a sun off to one
        // side, so a lit panel is bright down one side of an aisle and black down
        // the other, and it is the *variety* that has to survive, not the shading.
        const PO = OFF + 0.07;
        for (let L = 0; L < LEVELS.length; L++) {
          const y0 = base + rh * LEVELS[L] + 0.42;
          const ph = L === LEVELS.length - 1 ? 1.05 : 1.7;
          for (let q = 0; q < 2; q++) {
            const t0 = q / 2, t1 = (q + 1) / 2;
            const ax = prev[0] + (x - prev[0]) * t0, az = prev[1] + (z - prev[1]) * t0;
            const bx = prev[0] + (x - prev[0]) * t1, bz = prev[1] + (z - prev[1]) * t1;
            const g = GOODS[(i * 7 + L * 3 + q) % GOODS.length];
            bright.quad([ax + nx * PO, y0, az + nz * PO], [bx + nx * PO, y0, bz + nz * PO],
                        [bx + nx * PO, y0 + ph, bz + nz * PO],
                        [ax + nx * PO, y0 + ph, az + nz * PO], g);
          }
        }
        // An upright every couple of bays, and the top rail, so the run has a
        // silhouette instead of being a flat panel.
        if ((i % 8) === 0) {
          box(x, base + rh / 2, z, 0.4, rh / 2, 0.4, shade(STEEL, 0.16));
        }
        // Stock broken out onto the floor in front of the racking, which is most of
        // what tells a warehouse from a car park with shelves in it. Kept to the
        // rack's own side so it never reaches the racing line.
        if ((i % 14) === 3) {
          const pc = PALLET[(i / 14 | 0) % PALLET.length];
          const px = x + nx * 2.4, pz = z + nz * 2.4;
          if (toRoad(px, pz, e.p[1]) > e.hw + 2.0) {
            box(px, base + 1.4, pz, 2.0, 1.4, 2.0, pc);
          }
        }
        face([prev[0], base + rh, prev[1]], [x, base + rh, z],
             [x + nx * -1.6, base + rh, z + nz * -1.6],
             [prev[0] + nx * -1.6, base + rh, prev[1] + nz * -1.6],
             shade(STEEL, -0.22));
      }
    }

    // ---- the refrigerated aisle ---------------------------------------------
    // A run of cases down the inside of the north wall, drawn unlit so it reads as
    // lit glass rather than as a pale grey box. It is scenery in every sense - the
    // grip under it is the same tarmac as everywhere else, because a third surface
    // would mean a new collider kind, a constant in tuning.py and a term in
    // laptime.py, which is to say it would move every medal time in the pool for
    // the sake of one aisle.
    const chill = cfg.chill != null ? cfg.chill : 0xbfe4f2;
    for (let x = X0 + 12; x < X1 - 12; x += 9) {
      const z = Z1 - 6;
      if (toRoad(x, z, base) < 12) continue;
      box(x, base + 1.6, z, 4.0, 1.6, 3.0, shade(STEEL, 0.1));
      // Stood off the case's own front face. Laid *on* it the two are coplanar and
      // the glass flickers against the cabinet, which is the roof's bug in
      // miniature.
      const fz = z - 3.06;
      bright.quad([x - 4, base + 3.2, fz], [x + 4, base + 3.2, fz],
                  [x + 4, base + 1.0, fz], [x - 4, base + 1.0, fz], chill);
    }

    // ---- structural columns -------------------------------------------------
    // A warehouse is a grid of columns, and this track needs them to be real: the
    // rooftop deck's own trestles now decline to stand on the aisles they fly over
    // (see `overRoad` in buildTrack), so without these the deck reads as floating.
    // `toRoad` is what keeps one out of a road, which is the whole reason the grid
    // is filtered rather than authored.
    for (let x = X0 + 20; x < X1 - 10; x += 30) {
      for (let z = Z0 + 18; z < Z1 - 10; z += 32) {
        if (toRoad(x, z, base) < 11) continue;
        box(x, base + (CEIL - base) / 2, z, 0.7, (CEIL - base) / 2, 0.7, shade(STEEL, -0.1));
      }
    }

    // ---- the checkouts and the food court -----------------------------------
    // A counter standing off the road and following it: front face, top slab, one
    // collision quad. Same shape as the racking, and same reason for one quad.
    const counter = (i0, i1, o, h, k, topk) => {
      if (i1 >= n) return;
      const a = line[i0], b = line[i1];
      const dv = (o < 0 ? -1 : 1) * 2.6;          // away from the road
      const P = (e, off, up) => [e.p[0] + e.lat[0] * off, base + up, e.p[2] + e.lat[2] * off];
      const A = P(a, o, 0), B = P(b, o, 0), At = P(a, o, h), Bt = P(b, o, h);
      face(A, B, Bt, At, k);
      col.addQuad(A, B, Bt, At, KIND.WALL);
      face(At, Bt, P(b, o + dv, h), P(a, o + dv, h), topk);
    };

    // The tills: a line of them either side, with the road running between, which
    // is what makes the chicane through here read as lanes rather than as a kink.
    for (let j = 2; j + 4 < tills.length; j += 6) {
      const i = tills[j], e = line[i];
      for (const s of [-1, 1]) {
        counter(i, tills[j + 4], (e.hw + 3.2) * s, 1.5,
                shade(STEEL, 0.2), shade(WALL, -0.05));
        // The lane divider post, and a lit lane number board on top of it.
        const o = (e.hw + 1.6) * s;
        const px = e.p[0] + e.lat[0] * o, pz = e.p[2] + e.lat[2] * o;
        box(px, base + 1.9, pz, 0.28, 1.9, 0.28, shade(STEEL, -0.1));
        // Clear of the post's front face (0.28), not inside it - at 0.06 the board
        // was buried in the very thing it is mounted on.
        const bz = pz - 0.36;
        bright.quad([px - 0.9, base + 4.1, bz], [px + 0.9, base + 4.1, bz],
                    [px + 0.9, base + 3.0, bz], [px - 0.9, base + 3.0, bz],
                    trim);
      }
    }

    // The food court, down the side of the checkout run with room for it. Serving
    // counter, a scatter of tables, and the one board everybody actually comes for.
    if (tills.length > 10) {
      const mid = tills[Math.floor(tills.length * 0.45)];
      const e = line[mid];
      // Whichever side has the room. The checkout run hugs one wall on its way out.
      const side = (e.p[2] + e.lat[2] * 18 > Z1 - 6) ? -1 : 1;
      const co = (e.hw + 13) * side;
      counter(tills[2], tills[Math.min(tills.length - 1, 14)], co, 2.1,
              shade(trim, -0.1), shade(WALL, 0.04));
      const rnd2 = mulberry(0x150150);
      for (let j = 3; j < Math.min(tills.length - 1, 16); j += 3) {
        const t = line[tills[j]];
        const o = (t.hw + 7.5 + rnd2() * 2.4) * side;
        const tx = t.p[0] + t.lat[0] * o, tz = t.p[2] + t.lat[2] * o;
        if (toRoad(tx, tz, base) < t.hw + 2.4) continue;
        box(tx, base + 0.95, tz, 1.9, 0.12, 1.9, shade(WALL, -0.02));   // table top
        box(tx, base + 0.48, tz, 0.22, 0.48, 0.22, shade(STEEL, -0.1)); // and its leg
      }
      // Hung over the counter, facing the road.
      const so = (e.hw + 11.4) * side;
      const sx = e.p[0] + e.lat[0] * so, sz = e.p[2] + e.lat[2] * so;
      const fx = -e.lat[0] * side, fz = -e.lat[2] * side;   // back toward the road
      put(sg.food || '$1.50 HOT DOG', sx, base + 5.6, sz,
          [fz, 0, -fx], [fx, 0, fz], 5.2);
    }

    // ---- the rooftop railing ------------------------------------------------
    // A parapet down both edges of the deck, because a car park nineteen units up
    // has one and because falling off it is not the point of this track.
    //
    // It cannot be a ribbon `rail`: this is a ground track, and
    // `test_barriers_are_opt_in` requires a ground track to carry no walled
    // stations at all. So it is collider geometry standing beside the road, the way
    // the racking is - which also keeps it outside the kerb, so the racing line
    // never touches it and no medal time moves. It leans with the banking, taking
    // its up from the station's own normal for the reason `wallStrip` does.
    const railH = 1.15, railC = pal.rail != null ? pal.rail : 0xd8dde2;
    const rprev = [null, null];
    for (let i = 0; i < n; i++) {
      const e = line[i];
      const onDeck = e.p[1] > CEIL && !e.air;
      for (const s of [-1, 1]) {
        const k = s < 0 ? 0 : 1;
        if (!onDeck) { rprev[k] = null; continue; }
        const o = (e.hw + 0.9) * s;
        const p = [e.p[0] + e.lat[0] * o, e.p[1] + e.lat[1] * o, e.p[2] + e.lat[2] * o];
        const q = rprev[k];
        rprev[k] = [p, e.n];
        if (!q) continue;
        const t = (v, nv) => [v[0] + nv[0] * railH, v[1] + nv[1] * railH, v[2] + nv[2] * railH];
        const A = q[0], B = p, At = t(q[0], q[1]), Bt = t(p, e.n);
        face(A, B, Bt, At, railC);
        col.addQuad(A, B, Bt, At, KIND.WALL);
      }
    }

    // ---- signage ------------------------------------------------------------
    // `put` and `sg` are declared up with the helpers rather than here, because the
    // food court hangs its board while it is building its counter and a `const` is
    // not merely hoisted - it is in its temporal dead zone until its own line runs,
    // so using it earlier throws rather than reading as undefined.
    // On the front face of each entrance header, filling it, which is where a
    // warehouse puts its name. Not on the wall behind: the portal projects six
    // units and would stand squarely in front of it, and not below the header
    // either, because below the header is the doorway and a board hung across that
    // is a board hung across the road.
    for (const z of westDoors) {
      put(sg.facade || 'COSTCO WHOLESALE', X0 - OUT - 0.5, (HEAD + TOP) / 2 + 0.5, z,
          [0, 0, 1], [-1, 0, 0], SIGN_HW);
    }
    for (const z of eastDoors) {
      put(sg.facade || 'COSTCO WHOLESALE', X1 + OUT + 0.5, (HEAD + TOP) / 2 + 0.5, z,
          [0, 0, -1], [1, 0, 0], SIGN_HW);
    }
    // And one standing on the roof, which is what you read on the way round the
    // deck. It sits on the parapet at the south wall, facing out.
    put(sg.roof || 'COSTCO WHOLESALE', (X0 + X1) / 2, CEIL + 5.4, Z0 - T - 0.4,
        [1, 0, 0], [0, 0, -1], 30);

    // ---- the car park -------------------------------------------------------
    // Placed here rather than by `addScenery`, because the scatter's vocabulary is
    // trees and rocks and the palette therefore sets `density: 0`.
    // Painted bays, and nothing standing up in them. Lamp columns were the first
    // go at this and they are wrong twice over: from a car they are a field of
    // grey posts with no cars under them, which reads as scaffolding rather than as
    // a car park, and being the only vertical thing out here they draw the eye off
    // the building. What says "car park" at this scale is the *paint*.
    //
    // Bays come in back-to-back pairs with a driving aisle between, which is how a
    // lot is actually set out, and the whole of it is one unlit quad per line.
    const L = cfg.lot || {};
    const paint = L.line != null ? L.line : 0xe8e8e4;
    const BAY = 3.4;                  // one bay wide
    const DEEP_BAY = 7.0;             // and deep
    const LIFT = 0.12;                // clear of the ground plate, or they z-fight
    const y = base + LIFT;
    const W2 = 0.17;                  // half the width of a painted line
    const line2 = (xa, za, xb, zb) => bright.quad(
      [xa, y, za], [xb, y, za], [xb, y, zb], [xa, y, zb], paint);
    for (let z = Z0 - 84; z < Z1 + 84; z += DEEP_BAY * 2 + 9) {
      for (let x = -60; x < X1 + 170; x += BAY) {
        // Off the road, and near enough it to be the car park serving it. Without
        // the upper bound the paint runs to the edge of the ground plate, which is
        // the whole bounding box.
        const d = toRoad(x, z, base);
        if (d < 13 || d > 78) continue;
        if (x > X0 - 4 && x < X1 + 4 && z > Z0 - 4 && z < Z1 + 4) continue;
        // A bay is a |_| - two sides and a closed end - not a single stroke. Rows
        // come nose to nose in pairs, so the closed ends meet in the middle at `z`
        // and the open ends face the driving aisle either side; the head line is
        // therefore shared, drawn once, and butts up against its neighbours into a
        // continuous kerb line.
        const rows = [-1, 1].filter(s => toRoad(x + BAY / 2, z + s * DEEP_BAY * 0.6,
                                                base) >= 11);
        if (!rows.length) continue;
        line2(x, z - W2, x + BAY, z + W2);                       // the closed end
        for (const s of rows) {
          for (const e of [0, BAY]) {                            // and the two sides
            line2(x + e - W2, z, x + e + W2, z + s * DEEP_BAY);
          }
        }
      }
    }
  }
  }
})();
