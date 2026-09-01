// Rickety Rails: the hole the railway is in.
//
// This track has no ground plane, and unlike the pool's other floating tracks it
// is not in the sky - it is underground, which is the same absence of a ground
// quad and the opposite problem. A void track normally solves it by putting a
// world a long way *below* (`pal.below`); here the world is a couple of dozen
// units below, a couple of dozen above, and thirty either side, and the whole
// look of the track is that enclosure.
//
// **Two height fields, and they are the same trick twice.**
//
//     floor(x,z) = min over solid stations of  ( y - DROP + rise(d) )
//     roof (x,z) = max over all    stations of  ( y + head(i) - fall(d) )
//
// The floor is a **lower** envelope of upward cones, which is Mount Joy's rule
// and is here for Mount Joy's reason: it is at most `y - DROP` at every station,
// so the rubble can never come up through the trestle - not by construction of
// the layout but arithmetically, for any layout. The roof is the same statement
// upside down: an **upper** envelope of downward cones, at least `y + head` over
// every station, so it can never come down through the road either. Between them
// the cave is whatever shape the railway is, and neither field has to be checked
// against the layout by anybody.
//
// **Where the two cross, the cave is sealed, and that is the point.** Away from
// the road the floor climbs and the roof falls until they meet, about thirty
// units out in the drifts and forty in the vault. That meeting *is* the cavern
// wall - there is no wall geometry here at all. Past it the cell is solid rock
// and is not drawn, which is also what keeps this cheap: only a corridor either
// side of the ribbon is ever built.
//
// **The gap stations are in one field and not the other**, and that is the whole
// of the winze. They are excluded from the floor, so under the jump the floor is
// set by the lip and the landing twenty-eight units below it and falls away into
// a pit; they are included in the roof, so there is headroom over the flight.
// Include them in the floor and the fill comes up under the jump, which is
// Shroom Street's mistake in `docs/track-defects.md` with the sign flipped.
//
// **Built as a chamfer sweep, not as a query.** Two raster passes taking
// `min(here, neighbour + G * step)` are the same cone field in O(cells) rather
// than cells x stations, and - the part that matters - with no reach cutoff, so
// there is no distance at which the field gives up and falls to a floor. Monaco
// pays 8.5M distance tests for the equivalent; this pays about 40,000 relaxations
// and runs in every page load and every lap the anti-cheat re-drives in QuickJS.
//
// **None of it is in the collider, and that is deliberate.** The track is 96%
// walled, so the only way off it is over the winze - and the floor there is
// twenty-six units down in a pit with no way out, so falling in wants to be a
// respawn rather than a scramble. The cost of that choice is that `test_scenery`
// pins collider triangles and this file adds none, so a throw in here leaves the
// suite green: `tools/validate_track.py` and its `uncaught:` line is what
// actually checks this file ran.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.railway = { props: props };

  // --- the shape of the hole ------------------------------------------------
  // How far under the deck the floor sits, and it is deep because **the thing
  // below this track is supposed to be a void, not a ravine**.
  //
  // Three passes at this. At 26 the floor was inside the key light, so it read
  // as a lit brown yard the trestle happened to stand in - and the rubble
  // scattered on it to give it depth was exactly what made it read as a yard.
  // At 40 it was a ravine: a real bottom, visibly there, just far away. Neither
  // is the reference. In the Gold Mine there is no floor under the track at all
  // - the supports go down and stop being visible, and what is under them is
  // nothing.
  //
  // So the floor is now 55 down and **black within 20 units of the road's own
  // level** (see the `deep` ramp below), which is well inside the fog. The
  // geometry is still there - it has to be, or you see the sky dome through the
  // gap - but nothing you can see of it is lit. What you get is the wall beside
  // the trestle falling away and simply ending.
  //
  // It also costs the engine's own trestle legs, and that is why this file draws
  // bents: `base` is a flat `p[1] - 16` for a groundless track, so at 40 the
  // engine's legs stop 24 units short and hang in the air.
  const DROP = 55.0;
  // The gentle gradients, which hold for SOFT units out from the road. These are
  // the rubble apron under the trestle and the roof's first fall away from it -
  // both are places you can see clearly, so both are shallow.
  const G_UP = 0.50, G_DOWN = 0.45, SOFT = 20.0;
  // ...and the steep ones past that, which are the cavern wall. Rock does not
  // sit at thirty degrees; a single gradient the whole way out gives a scree
  // bowl rather than a cave, and no amount of colouring fixes it.
  const STEEP_UP = 2.2, STEEP_DOWN = 1.5;
  // Past this the roof and the floor have long since met and everything is solid
  // rock, so nothing is drawn. Comfortably past the furthest they ever meet,
  // which is about 41 units in the vault.
  const REACH = 92.0;
  const CELLM = 13.0;       // grid pitch
  const PAD = 130.0;        // how far past the ribbon's bbox the grid runs
  const ROUGH = 3.4;        // floor noise, in units
  const ROUGH_UP = 5.6;     // roof noise: more, because you look straight at it
  // The roof's colour, and it is picked near-black rather than shaded off the
  // rock, which is the mistake the first pass made.
  //
  // `bright` is `MeshBasicMaterial` and nothing multiplies it down, but that is
  // only half of it: a vertex colour is handed to three.js as *linear* and
  // converted to sRGB on the way out, and that conversion lifts dark values
  // enormously. `shade(rock, -0.30)` is 0x201d22 in the file and measured
  // #605c62 on screen - three stops lighter, and it read as an overcast sky
  // rather than as rock over your head. Judge an unlit colour by sampling the
  // render, never by the swatch: 0x07 renders as about 0x2d.
  // Two of them, mixed per cell by the same noise the geometry uses, and
  // deliberately *not* `shade`d: at this end of the range `shade(0x0a, +0.05)`
  // is 0x16, which more than doubles the value and after the sRGB lift comes out
  // as a twilight sky. Near-black needs mixing between two near-blacks.
  const ROOF = 0x090714, ROOF_LOW = 0x030308;
  // The bottom of the ravine. Not quite black - a true 0x000000 floor
  // stops taking the fog and reads as a hole in the render.
  const VOID = 0x08070c;

  // How much headroom the roof keeps over the road, by fraction of the lap.
  //
  // **Authored as fractions rather than derived**, for the reason Monaco's
  // tunnel is: which stretch is in a tight drift and which is in an open cavern
  // is a fact about the place, not something the ribbon implies. Deriving it
  // from, say, corner radius would put the vault wherever the fastest corner
  // ended up.
  //
  // The floor is 13. The chase camera rides about 4.3 over the car and a cell is
  // 13 units across, so a station's roof can be quantised as low as
  // `head - G_DOWN * CELLM/2`, which at 13 is 10.1 - still clear of the lens,
  // and the tightest this may safely go.
  const HEAD = [
    [0.00, 13], [0.10, 14],                 // the adit: timbered, low, close
    [0.13, 26], [0.27, 28],                 // the gallery: worked out and open
    [0.30, 36], [0.36, 33],                 // the winze: a shaft, so tall
    [0.40, 17], [0.52, 17],                 // the sump: the roof comes back down
    [0.56, 52], [0.68, 46],                 // the vault: the big room
    [0.72, 21], [0.94, 25], [1.00, 23],     // the haulage way out
  ];
  // Under this the drift counts as timbered: portal frames over the road and
  // lamps on them. Over it it is a natural cavern and carries neither, which is
  // most of what tells the two kinds of place apart at speed.
  const TIMBER_HEAD = 24.0;
  const FRAME_EVERY = 9;    // stations between portal frames
  const LAMP_EVERY = 15;    // stations between lamps
  const LINT = 8.6;         // underside of a portal lintel: over the camera
  // Timbering only goes in where the drift is straight, and this is the number
  // that says so. A frame is square to its own station; put one every nine
  // stations round a 16-radius hairpin and consecutive frames are a hundred
  // degrees apart, which from the car is a row of gantries at wild angles
  // across a corner you are trying to read. A prop is set square to the drift
  // in real life for the same reason it looks right here.
  const FRAME_CURV = 1 / 46;

  // The daylight shaft, as a fraction of the lap: out on the vault's long
  // corner, which is the one place with the sightline to make it worth having.
  // **The offset has to be inside the cavern, and 52 was not.** The vault's roof
  // and floor meet 35.9 units out (`SOFT + (head - G_DOWN*SOFT + DROP -
  // G_UP*SOFT) / (STEEP_UP + STEEP_DOWN)`), so a shaft at 52 was built five
  // units *below* the road inside solid rock and never appeared - no error, no
  // warning, just a track with no daylight in it. Anything placed off the ribbon
  // in here has to be checked against where the cave closes, not against how far
  // away it looks on paper.
  const SHAFT_AT = 0.615, SHAFT_OFF = 26.0, SHAFT_R = 20.0, SHAFT_UP = 52.0;

  function props(ctx) {
    const { solid, bright, col, track, pal, bbox, KIND, shade, mulberry } = ctx;
    const line = track.line, n = line.length;

    // --- the grammar, declared before anything uses it ---------------------
    // A `const` in a long function is in its temporal dead zone until its own
    // line runs, so a helper used by two sections goes up here with the rest.
    // See the Costco's food-court note in `docs/tracks-and-geometry.md`.
    const rnd = mulberry(0x5a17);
    const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
    const at = (f) => clamp(Math.round(f * (n - 1)), 0, n - 1);
    const spot = (i, o) => {
      const e = line[clamp(i | 0, 0, n - 1)];
      return [e.p[0] + e.lat[0] * o, e.p[2] + e.lat[2] * o];
    };
    // Both windings on everything. `solid` is MeshLambertMaterial, which is
    // FrontSide, so a quad wound away from you is drawn, costed and invisible -
    // and an invisible wall is not an error in either language.
    const face = (a, b, c, d, k) => { solid.quad(a, b, c, d, k); solid.quad(a, d, c, b, k); };
    // Between two packed colours. `shade` moves toward white by a fraction of
    // what is left, which is the wrong curve for picking between two near-blacks.
    const mix = (a, b, t) => {
      const l = (sh) => ((a >> sh) & 255) + (((b >> sh) & 255) - ((a >> sh) & 255)) * t;
      return (Math.round(l(16)) << 16) | (Math.round(l(8)) << 8) | Math.round(l(0));
    };
    // A beam between two points, with a square-ish section. Oriented off its own
    // axis rather than the world's, so a lintel across a diagonal road is
    // actually across it.
    const bar = (a, b, w, h, k) => {
      const dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
      const L = Math.hypot(dx, dy, dz) || 1e-6;
      const f = [dx / L, dy / L, dz / L];
      let r = [f[2], 0, -f[0]];
      const rl = Math.hypot(r[0], r[2]);
      r = rl < 1e-6 ? [1, 0, 0] : [r[0] / rl, 0, r[2] / rl];
      let u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]];
      const ul = Math.hypot(u[0], u[1], u[2]) || 1e-6;
      u = [u[0] / ul, u[1] / ul, u[2] / ul];
      if (u[1] < 0) u = [-u[0], -u[1], -u[2]];
      const P = (p, sr, su) => [p[0] + r[0] * sr * w + u[0] * su * h,
                                p[1] + r[1] * sr * w + u[1] * su * h,
                                p[2] + r[2] * sr * w + u[2] * su * h];
      const v = [P(a, -1, -1), P(a, 1, -1), P(a, 1, 1), P(a, -1, 1),
                 P(b, -1, -1), P(b, 1, -1), P(b, 1, 1), P(b, -1, 1)];
      face(v[0], v[1], v[2], v[3], k); face(v[4], v[7], v[6], v[5], k);
      face(v[0], v[4], v[5], v[1], k); face(v[1], v[5], v[6], v[2], k);
      face(v[2], v[6], v[7], v[3], k); face(v[3], v[7], v[4], v[0], k);
      return v;
    };
    // **The posts are solid, and on this track that is the barrier.** It is
    // `exposed`, so there is no ribbon `rail` to run wide into - and a track
    // with nothing at all at the edge is a respawn every time you are half a
    // metre out, which is punishing rather than hard. A post at `hw + 1.7` is
    // off the road, so the racing line never touches one and no medal time
    // moves, but a wide moment hits timber instead of finding the void.
    //
    // Same pattern as the Costco's racking and Silverstone's barriers, and for
    // the same reason it has to be collider geometry rather than a rail:
    // `test_barriers_are_opt_in` counts *stations*, and railing these would cost
    // the track its `exposed` flag and the drop with it.
    //
    // Only the four sides, and only the uprights - the lintel is 8.6 up and the
    // braces are above the car, so colliding them is triangles nothing can
    // reach. `verify.py` re-drives submitted laps through this same file, so a
    // lap that clipped a post in the browser clips it on the server too.
    const collide = (v) => {
      col.addQuad(v[0], v[4], v[5], v[1], KIND.WALL);
      col.addQuad(v[1], v[5], v[6], v[2], KIND.WALL);
      col.addQuad(v[2], v[6], v[7], v[3], KIND.WALL);
      col.addQuad(v[3], v[7], v[4], v[0], KIND.WALL);
    };
    // **Is this station flat enough to stand something beside?**
    //
    // Everything in this file that is placed off the road uses `spot`, which
    // offsets along the station's `lat` - and `lat` *rotates with the surface*.
    // On a loop it goes vertical and then upside down, so a thing authored "46
    // units to the right, on the floor" is thrown into the plane of the loop
    // instead: three of the vault's rock pillars came out as slabs standing
    // through the middle of it, floor to roof, and the trestle bents drew legs
    // diagonally across it. Nothing about that is visible in the numbers - the
    // offsets are all correct, it is the frame they are measured in that moved.
    //
    // 0.85 is about 32 degrees off level, which passes every banked corner on
    // the track (the most is 8) and fails the whole loop.
    const flat = (e) => (e.n[1] || 0) > 0.85;
    const headAt = (f) => {
      for (let i = 1; i < HEAD.length; i++) {
        if (f <= HEAD[i][0]) {
          const a = HEAD[i - 1], b = HEAD[i];
          const t = (f - a[0]) / ((b[0] - a[0]) || 1);
          return a[1] + (b[1] - a[1]) * t;
        }
      }
      return HEAD[HEAD.length - 1][1];
    };

    // --- the two fields -----------------------------------------------------
    const gx0 = bbox.x0 - PAD, gz0 = bbox.z0 - PAD;
    const nx = Math.ceil((bbox.x1 + PAD - gx0) / CELLM) + 1;
    const nz = Math.ceil((bbox.z1 + PAD - gz0) / CELLM) + 1;
    const N = nx * nz;
    const fl = new Float64Array(N).fill(Infinity);    // floor cones, gentle
    const cl = new Float64Array(N).fill(-Infinity);   // roof cones, gentle
    const ds = new Float64Array(N).fill(Infinity);    // distance to the railway
    const ry = new Float64Array(N);                   // y of the nearest station
    const nz_ = new Float64Array(N);                  // per-cell rock noise
    for (let k = 0; k < N; k++) nz_[k] = rnd();

    for (let i = 0; i < n; i++) {
      const e = line[i], p = e.p;
      const cx = clamp(Math.round((p[0] - gx0) / CELLM), 0, nx - 1);
      const cz = clamp(Math.round((p[2] - gz0) / CELLM), 0, nz - 1);
      const k = cz * nx + cx;
      // Solid stations only, or the fill comes up under the winze.
      if (!e.air && fl[k] > p[1] - DROP) fl[k] = p[1] - DROP;
      const h = p[1] + headAt(i / (n - 1));
      if (cl[k] < h) cl[k] = h;
      ds[k] = 0; ry[k] = p[1];
    }

    const D1 = CELLM, D2 = CELLM * Math.SQRT2;
    const relax = (k, x, z, d) => {
      if (x < 0 || z < 0 || x >= nx || z >= nz) return;
      const j = z * nx + x;
      const f = fl[j] + G_UP * d; if (f < fl[k]) fl[k] = f;
      const c = cl[j] - G_DOWN * d; if (c > cl[k]) cl[k] = c;
      const s = ds[j] + d; if (s < ds[k]) { ds[k] = s; ry[k] = ry[j]; }
    };
    for (let z = 0; z < nz; z++) for (let x = 0; x < nx; x++) {
      const k = z * nx + x;
      relax(k, x - 1, z, D1); relax(k, x - 1, z - 1, D2);
      relax(k, x, z - 1, D1); relax(k, x + 1, z - 1, D2);
    }
    for (let z = nz - 1; z >= 0; z--) for (let x = nx - 1; x >= 0; x--) {
      const k = z * nx + x;
      relax(k, x + 1, z, D1); relax(k, x + 1, z + 1, D2);
      relax(k, x, z + 1, D1); relax(k, x - 1, z + 1, D2);
    }

    // The drawn surfaces. `extra` is the steep half of each gradient and is
    // zero within SOFT of any station, so it cannot lift the floor into a road
    // or drop the roof onto one - the guarantee the envelopes give survives it.
    // The noise is likewise only ever taken *away* from the floor and *added* to
    // the roof.
    const F = new Float64Array(N), C = new Float64Array(N);
    for (let k = 0; k < N; k++) {
      const d = ds[k];
      const eu = d <= SOFT ? 0 : (STEEP_UP - G_UP) * (d - SOFT);
      const ed = d <= SOFT ? 0 : (STEEP_DOWN - G_DOWN) * (d - SOFT);
      const f = fl[k] + eu - nz_[k] * ROUGH;
      const c = cl[k] - ed + nz_[(k + 977) % N] * ROUGH_UP
                          + nz_[(k * 7 + 13) % N] * ROUGH_UP * 0.45;
      // Where the two have crossed, the cell is solid rock. Clamping rather
      // than skipping is what makes the cave *sealed*: the floor follows the
      // roof down past the meeting line with a hand's breadth between them, so
      // there is no seam to see the void through and no coplanar pair to
      // z-fight. Skipping both would leave exactly one cell of daylight all the
      // way round.
      F[k] = Math.min(f, c);
      C[k] = Math.max(c, F[k] + 0.6);
    }
    const idx = (x, z) => clamp(z, 0, nz - 1) * nx + clamp(x, 0, nx - 1);
    const cellOf = (x, z) => [Math.round((x - gx0) / CELLM), Math.round((z - gz0) / CELLM)];
    const floorAt = (x, z) => { const c = cellOf(x, z); return F[idx(c[0], c[1])]; };
    const roofAt = (x, z) => { const c = cellOf(x, z); return C[idx(c[0], c[1])]; };
    const distAt = (x, z) => { const c = cellOf(x, z); return ds[idx(c[0], c[1])]; };

    // --- rock ---------------------------------------------------------------
    const rock = pal.ground;
    const shaftC = spot(at(SHAFT_AT), SHAFT_OFF);
    const shaftY = roofAt(shaftC[0], shaftC[1]);
    for (let z = 0; z < nz - 1; z++) {
      for (let x = 0; x < nx - 1; x++) {
        const a = idx(x, z), b = idx(x, z + 1), c = idx(x + 1, z + 1), d = idx(x + 1, z);
        if (ds[a] > REACH && ds[b] > REACH && ds[c] > REACH && ds[d] > REACH) continue;
        const X0 = gx0 + x * CELLM, X1 = X0 + CELLM;
        const Z0 = gz0 + z * CELLM, Z1 = Z0 + CELLM;
        // The floor, lit. Wound the way the engine's own ground quad is, which
        // is the copy worth taking rather than reasoning about: (x0,z0) ->
        // (x0,z1) -> (x1,z1) -> (x1,z0) faces up.
        // **Coloured by how far below the railway it is, not by where it is.**
        // The floor is one sheet and half of every frame down here is that
        // sheet, so what it is worth is entirely in whether it reads as having a
        // bottom. Near road level it is lit rock; forty units down it is
        // `VOID`, which with the fog over it is nothing at all. `ry` is the
        // nearest station's height, carried along the same chamfer sweep that
        // computes the distance - it costs one more array and no extra passes.
        // Black by twenty units under the railway rather than forty-six. This
        // ramp is what decides whether the drop reads as a ravine or as a void,
        // and it matters far more than DROP does - a shallow ramp over a deep
        // floor is still a visible bottom, just a distant one.
        const deep = Math.max(0, Math.min(1, (ry[a] - F[a] - 4) / 16));
        const wall = ds[a] > SOFT;
        const fc = mix(shade(rock, (nz_[a] - 0.45) * 0.30 + (wall ? 0.10 : -0.02)),
                       VOID, deep * deep);
        solid.quad([X0, F[a], Z0], [X0, F[b], Z1], [X1, F[c], Z1], [X1, F[d], Z0], fc);
        // The roof, unlit. A downward-facing quad gets nothing from a key light
        // overhead and only the hemisphere's ground colour from below, and there
        // are no shadow maps here - so a "correctly" lit ceiling over the car
        // comes out very nearly black, which is the most obvious thing in the
        // cave. `bright` is unlit and renders at full value, so the colour it
        // gets is picked two stops under the floor's.
        const cx = (X0 + X1) * 0.5, cz = (Z0 + Z1) * 0.5, k7 = a * 7 + z;
        if (Math.hypot(cx - shaftC[0], cz - shaftC[1]) < SHAFT_R) continue;
        bright.quad([X0, C[a], Z0], [X1, C[d], Z0], [X1, C[c], Z1], [X0, C[b], Z1],
                    mix(ROOF_LOW, ROOF, nz_[(k7 + 41) % N]));
      }
    }

    // --- the daylight shaft -------------------------------------------------
    // The hole the roof was skipped for, and the only thing on the track that
    // is not lit by a work lamp. Eight sides, open at the top, drawn both
    // windings because you only ever see it from inside; through it is the sky
    // dome itself rather than a painted disc, which is what makes the sun in it
    // the same sun everything else is shaded by.
    // Warm, and **graded up the bore**, which is the whole difference between a
    // shaft of daylight and a pale mound in a dark cave. Flat `shade(rock, 0.14)`
    // rendered as a sand-coloured outcrop beside the vault: the eye reads a light
    // shaft off the *gradient*, not off the brightness. `quadV` carries a colour
    // per corner, so this costs the same two triangles.
    const SH_LOW = 0x241d18, SH_HIGH = 0xd9a463;
    for (let s = 0; s < 8; s++) {
      const a0 = (s / 8) * Math.PI * 2, a1 = ((s + 1) / 8) * Math.PI * 2;
      const p0 = [shaftC[0] + Math.cos(a0) * SHAFT_R, shaftC[1] + Math.sin(a0) * SHAFT_R];
      const p1 = [shaftC[0] + Math.cos(a1) * SHAFT_R, shaftC[1] + Math.sin(a1) * SHAFT_R];
      // Splayed outward as it rises, so from under it you see wall rather than
      // a straight bore with the sky as a small disc at the end.
      const q0 = [shaftC[0] + Math.cos(a0) * (SHAFT_R + 9), shaftC[1] + Math.sin(a0) * (SHAFT_R + 9)];
      const q1 = [shaftC[0] + Math.cos(a1) * (SHAFT_R + 9), shaftC[1] + Math.sin(a1) * (SHAFT_R + 9)];
      const lo = shade(SH_LOW, (s % 3) * 0.04), hi = shade(SH_HIGH, (s % 3) * -0.06);
      const A = [p0[0], shaftY - 1.5, p0[1]], B = [p1[0], shaftY - 1.5, p1[1]];
      const Cq = [q1[0], shaftY + SHAFT_UP, q1[1]], D = [q0[0], shaftY + SHAFT_UP, q0[1]];
      solid.quadV(A, B, Cq, D, lo, lo, hi, hi);
      solid.quadV(A, D, Cq, B, lo, hi, hi, lo);
    }
    // What the shaft lands on. The floor is one flat-ish sheet in one colour and
    // half of every frame down here is that sheet, so the pool of daylight on it
    // is worth more than the same effort spent on anything standing up. Sat well
    // clear of the floor quads underneath it.
    for (let s = 0; s < 10; s++) {
      const a0 = (s / 10) * Math.PI * 2, a1 = ((s + 1) / 10) * Math.PI * 2;
      const R = SHAFT_R + 12;
      const p0 = [shaftC[0] + Math.cos(a0) * R, shaftC[1] + Math.sin(a0) * R];
      const p1 = [shaftC[0] + Math.cos(a1) * R, shaftC[1] + Math.sin(a1) * R];
      bright.quad([shaftC[0], floorAt(shaftC[0], shaftC[1]) + 0.30, shaftC[1]],
                  [p0[0], floorAt(p0[0], p0[1]) + 0.30, p0[1]],
                  [p1[0], floorAt(p1[0], p1[1]) + 0.30, p1[1]],
                  [shaftC[0], floorAt(shaftC[0], shaftC[1]) + 0.30, shaftC[1]],
                  0x4a3620);
    }

    // --- timbering, and the lamps on it -------------------------------------
    // Two posts and a lintel over the road wherever the roof is low. The
    // underside is held at LINT, well over the chase camera's 4.3, and every
    // frame is square across the road: the camera trails the car by up to 11.6
    // units, so it comes through an opening about half a second later and a
    // frame the car turned in would put a post between the two.
    const timber = pal.prop, beamCol = pal.prop2;
    for (let i = 4; i < n - 4; i++) {
      const e = line[i];
      if (e.air || e.pf) continue;
      const f = i / (n - 1);
      if (!flat(e)) continue;
      const straightish = Math.abs(e.curv || 0) < FRAME_CURV;
      // **Timbering is only where the roof is low; the lamps are everywhere.**
      // The first pass gated both on the same test, which left the gallery and
      // the vault - four hundred and seventy units and four hundred and forty -
      // with no lit thing anywhere in them. That is not just dark: a lamp is the
      // only braking reference on a road with no horizon, no trackside furniture
      // and a corner every few seconds. The two are different jobs and only one
      // of them is about what a mine looks like.
      const frame = straightish && headAt(f) <= TIMBER_HEAD && i % FRAME_EVERY === 0;
      const lamp = i % LAMP_EVERY === 0;
      if (!frame && !lamp) continue;
      const o = e.hw + 1.7;
      const L = [e.p[0] - e.lat[0] * o, e.p[1] - 1.2, e.p[2] - e.lat[2] * o];
      const R = [e.p[0] + e.lat[0] * o, e.p[1] - 1.2, e.p[2] + e.lat[2] * o];
      if (frame) {
        const Lt = [L[0], e.p[1] + LINT, L[2]], Rt = [R[0], e.p[1] + LINT, R[2]];
        collide(bar(L, [Lt[0], Lt[1] + 0.9, Lt[2]], 0.52, 0.52, timber));
        collide(bar(R, [Rt[0], Rt[1] + 0.9, Rt[2]], 0.52, 0.52, timber));
        bar([Lt[0], Lt[1] + 0.55, Lt[2]], [Rt[0], Rt[1] + 0.55, Rt[2]], 0.5, 0.5, beamCol);
        // The corner braces, which are most of what makes a rectangle read as
        // pit timbering rather than as a motorway gantry - the reference is
        // more diagonal than upright. Short, so they stay well outside the road.
        const B = 2.4;
        const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
                                  a[2] + (b[2] - a[2]) * t];
        const inL = mix(Lt, Rt, B / (2 * o)), inR = mix(Rt, Lt, B / (2 * o));
        bar([L[0], Lt[1] - B, L[2]], [inL[0], Lt[1] + 0.4, inL[2]], 0.36, 0.36, timber);
        bar([R[0], Rt[1] - B, R[2]], [inR[0], Rt[1] + 0.4, inR[2]], 0.36, 0.36, timber);
      }
      if (lamp) {
        // A lamp is a bracket, a lit face, and - the half that earns it - the
        // pool it throws on the deck. Offset along the station's own normal, so
        // it leans with a banked road instead of sinking into one.
        // Alternating sides, so a run of drift is lit from both and the deck
        // never has one dark edge all the way down it.
        const sd = (i / LAMP_EVERY) % 2 ? -1 : 1;
        const lx = e.p[0] + e.lat[0] * o * sd, lz = e.p[2] + e.lat[2] * o * sd;
        const ly = e.p[1] + 4.6;
        // Where there is a portal frame the lamp hangs off it; where there is
        // not, it needs a post of its own down to the deck or it is a light
        // floating in the dark.
        if (!frame) collide(bar([lx, e.p[1] - 1.2, lz], [lx, ly - 1.2, lz], 0.3, 0.3, timber));
        bar([lx, ly - 1.4, lz], [lx - e.lat[0] * 1.8 * sd, ly, lz - e.lat[2] * 1.8 * sd],
            0.24, 0.24, timber);
        // The lit face, hung square across the drift rather than across the
        // world - an axis-aligned quad is edge-on to the road half the time.
        const gx = lx - e.lat[0] * 2.1 * sd, gz = lz - e.lat[2] * 2.1 * sd;
        // Small, amber, and **hooded**. At 1.7 x 1.4 in near-white this was a
        // blank cream panel on a post - a road sign, not a lamp, and the largest
        // lit thing on the track. What makes a lamp read as a lamp is the shade
        // over it: the lit face has to be small enough to be a source and have
        // something dark directly above it to be a source *of*.
        const fw = [-e.lat[2], 0, e.lat[0]], W = 0.5, H = 0.42;
        bright.quad([gx - fw[0] * W, ly - H, gz - fw[2] * W],
                    [gx + fw[0] * W, ly - H, gz + fw[2] * W],
                    [gx + fw[0] * W, ly + H, gz + fw[2] * W],
                    [gx - fw[0] * W, ly + H, gz - fw[2] * W], 0xffb055);
        bar([gx - fw[0] * (W + 0.35), ly + H + 0.22, gz - fw[2] * (W + 0.35)],
            [gx + fw[0] * (W + 0.35), ly + H + 0.22, gz + fw[2] * (W + 0.35)],
            0.34, 0.16, beamCol);
        // The spill, laid across the deck between this station and the one
        // three along. `0.14` off the surface along the station's own normal:
        // 0.05 is not enough to win the depth test and a fixed world-up offset
        // sinks into a banked road on one side.
        const deck = (st, u) => [st.p[0] + st.lat[0] * u + st.n[0] * 0.14,
                                 st.p[1] + st.lat[1] * u + st.n[1] * 0.14,
                                 st.p[2] + st.lat[2] * u + st.n[2] * 0.14];
        const e2 = line[Math.min(n - 1, i + 3)];
        const w = e.hw * 0.82, w2 = e2.hw * 0.82;
        bright.quad(deck(e, -w), deck(e, w), deck(e2, w2), deck(e2, -w2), 0x2a1e0e);
      }
    }

    // --- crystal ------------------------------------------------------------
    // The one saturated thing in the place, and the only reason it is here is
    // that everything else is brown. Stood on the cavern wall rather than
    // scattered on the grid, so it is always in a place with a sightline from
    // the road - and gated on `ds` so a cluster can never land on a leg of the
    // railway the placement had no idea was there.
    const crystal = 0x8552e8, crystalDim = 0x4a2b8c;
    for (let i = 6; i < n - 6; i += 5) {
      const f = i / (n - 1);
      const vault = f > 0.545 && f < 0.685;
      if (!vault && rnd() > 0.16) continue;
      if (vault && rnd() > 0.62) continue;
      const e = line[i];
      if (e.air || !flat(e)) continue;
      const side = rnd() < 0.5 ? -1 : 1;
      const o = side * (24 + rnd() * (vault ? 30 : 12));
      const q = spot(i, o);
      if (distAt(q[0], q[1]) < 21) continue;
      const cnt = 2 + ((rnd() * 3) | 0);
      for (let c = 0; c < cnt; c++) {
        const px = q[0] + (rnd() - 0.5) * 11, pz = q[1] + (rnd() - 0.5) * 11;
        const py = floorAt(px, pz);
        const h = (vault ? 7.5 : 3.0) + rnd() * (vault ? 11 : 3.4);
        const r = 0.9 + rnd() * (vault ? 2.6 : 0.8);
        const tip = [px + (rnd() - 0.5) * 2.2, py + h, pz + (rnd() - 0.5) * 2.2];
        for (let s = 0; s < 4; s++) {
          const a0 = (s / 4) * Math.PI * 2 + 0.4, a1 = ((s + 1) / 4) * Math.PI * 2 + 0.4;
          bright.tri([px + Math.cos(a0) * r, py - 0.6, pz + Math.sin(a0) * r],
                     [px + Math.cos(a1) * r, py - 0.6, pz + Math.sin(a1) * r],
                     tip, s % 2 ? crystal : crystalDim);
        }
      }
    }

    // --- pillars, and rubble ------------------------------------------------
    // Rock columns floor to roof, in the vault only - it is the one room big
    // enough that the eye needs something between it and the far wall.
    for (let i = at(0.555); i < at(0.685); i += 11) {
      if (!flat(line[i])) continue;
      const side = (i % 22 === 0) ? -1 : 1;
      const o = side * (46 + rnd() * 26);
      const q = spot(i, o);
      if (distAt(q[0], q[1]) < 34) continue;
      const y0 = floorAt(q[0], q[1]), y1 = roofAt(q[0], q[1]);
      if (y1 - y0 < 12) continue;
      const r0 = 5 + rnd() * 4, r1 = r0 * (0.55 + rnd() * 0.3);
      for (let s = 0; s < 6; s++) {
        const a0 = (s / 6) * Math.PI * 2, a1 = ((s + 1) / 6) * Math.PI * 2;
        face([q[0] + Math.cos(a0) * r0, y0 - 1, q[1] + Math.sin(a0) * r0],
             [q[0] + Math.cos(a1) * r0, y0 - 1, q[1] + Math.sin(a1) * r0],
             [q[0] + Math.cos(a1) * r1, y1 + 1, q[1] + Math.sin(a1) * r1],
             [q[0] + Math.cos(a0) * r1, y1 + 1, q[1] + Math.sin(a0) * r1],
             shade(rock, 0.05 + (s % 2) * 0.06));
      }
    }
    // --- the trestle -------------------------------------------------------
    // **The bents this track stands on, and they replace two things.** The
    // engine draws a slim leg under every station of a groundless track, but
    // `base` is a flat `p[1] - 16`, so with the floor forty units down those
    // legs stop twenty-four units short and hang in the air - which is the
    // "geometry floating" defect, drawn by the engine rather than by this file.
    // And the first pass scattered rubble boxes on the floor, which at DROP 26
    // were lit and read as a yard of brown crates.
    //
    // A bent is what a mine-cart trestle actually stands on: two raking legs
    // from the deck edge down to the ground, with a cross-brace. It is the
    // silhouette in both reference shots, and over a ravine that goes black it
    // is the only thing telling you how far down the bottom is.
    //
    // **Not collidable.** They are under the deck, so nothing that reaches them
    // is still on the track - and a car that has left the trestle should fall.
    const legCol = pal.prop2, braceCol = shade(pal.prop, -0.18);
    for (let i = 2; i < n - 2; i += 12) {
      const e = line[i];
      if (e.air || !flat(e)) continue;
      const o = e.hw * 0.86;
      const foot = [];
      for (const sd of [-1, 1]) {
        const tx = e.p[0] + e.lat[0] * o * sd, tz = e.p[2] + e.lat[2] * o * sd;
        const ty = e.p[1] - 1.0;
        // Raked outward as they go down, which is both what a bent looks like
        // and what stops two legs of the same bent reading as one post.
        const fx = tx + e.lat[0] * 3.4 * sd, fz = tz + e.lat[2] * 3.4 * sd;
        let fy = floorAt(fx, fz);
        // Over the winze the floor falls away entirely; a leg chasing it there
        // would be a ninety-unit pole. Past `MAX_LEG` the trestle simply stops,
        // which is what a span over a hole looks like anyway.
        const MAX_LEG = 46.0;
        if (ty - fy > MAX_LEG) fy = ty - MAX_LEG;
        bar([fx, fy, fz], [tx, ty, tz], 0.42, 0.42, legCol);
        foot.push([[fx, fy, fz], [tx, ty, tz]]);
      }
      // One cross-brace per bent, at a third of the way up, and a second higher
      // one on the tall bents only - a short bent with two braces is a ladder.
      const at_ = (leg, t) => [leg[0][0] + (leg[1][0] - leg[0][0]) * t,
                               leg[0][1] + (leg[1][1] - leg[0][1]) * t,
                               leg[0][2] + (leg[1][2] - leg[0][2]) * t];
      const tall = Math.abs(foot[0][1][1] - foot[0][0][1]) > 22;
      bar(at_(foot[0], 0.34), at_(foot[1], 0.34), 0.26, 0.22, braceCol);
      if (tall) bar(at_(foot[0], 0.70), at_(foot[1], 0.70), 0.26, 0.22, braceCol);
    }
  }
})();
