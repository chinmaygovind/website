// Dino Park: the jungle, the gorge it is cut into, and the animal across it.
//
// **The three set pieces are found, not told.** Nothing in here is a fraction of
// the lap copied out of `track.py` - the pair-of-constants-in-two-languages this
// repo has been bitten by. Each one is the extreme of something the ribbon
// already carries, and `track.py` says so and promises to keep it true:
//
//     the ledge    the stations at the lap's highest point
//     the herd     the stations on the widest road
//     the animal   the stations flagged `skin` - the ones the engine draws no
//                  road on at all, because this file draws the surface instead
//     the jump     the `air` stations, which the ribbon marks for itself
//
// So a re-cut layout drags all four with it, and the failure mode if somebody
// breaks the promise is a set piece in the wrong place - loud - rather than a
// waterfall hanging over ordinary road, which is quiet.
//
// **The floor is Mount Joy's rule.** One height field, a lower envelope of
// upward cones:
//
//     floor(x,z) = min over solid stations of ( y - DROP + rise(d) )
//
// At most `y - DROP` at every station, so it is arithmetically incapable of
// coming up through the road - not by construction of this layout but for any
// layout. Built as a **chamfer sweep**, two raster passes taking
// `min(here, neighbour + G*step)`, which is the same field in O(cells) and, the
// part that matters, with no reach cutoff: there is no distance at which it
// gives up and falls to a plane.
//
// **The gorge only ever subtracts**, which is the whole reason it is safe:
//
//     gorge(x,z) = floor(x,z) - depth * (1 - smoothstep(d / HALF))
//
// It is zero at the rim with zero slope, so it joins the field tangentially
// instead of creasing it (`docs/track-defects.md`: a carve switched on at a
// threshold instead of blended), and it is never positive, so no amount of it
// can lift ground into a road. Its course is derived too - a straight line from
// the falls to the animal, which measures 45 units clear of every station that
// is not one of those two - and its depth is faded out near any road that is
// not a crossing, so the guarantee holds even if a re-cut brings the two closer.
//
// **The jump's `air` stations are excluded from the envelope and only from it.**
// Include them and the floor fills in under the flight, which is Shroom Street's
// logged mistake; exclude them and the stream you jump has somewhere to be.
//
// Collided as `KIND.OFFROAD` within `COL_REACH` of the road and drawn well past
// it. That is what makes running wide here a slow scramble through undergrowth
// rather than a respawn, and it is why `track.py` is `exposed` with barriers in
// only two places - the ledge and the animal, the two places the floor genuinely
// is not there.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.dino = { props: props, movers: movers };

  // --- the floor ------------------------------------------------------------
  // Shallow, because this is a dirt road lying on the jungle rather than a deck
  // over it. Four and a half units is about a kerb and a verge.
  const DROP = 4.5;
  // **Nearly flat, and that is the correction rather than the first guess.**
  // The envelope's gradient is the *floor* of how fast the ground may rise away
  // from the road, and at the 0.42/1.15 this started at, the jungle came out as
  // a V-shaped trench with the road in the bottom of it and a brown wall on the
  // horizon in every direction - 340 units out is 356 units up. A jungle floor
  // is flat. The relief comes from `hill` below instead, which is *added* and so
  // has to earn its safety separately, rather than from a gradient, which is
  // subtractive-safe and therefore tempting and wrong.
  const G_UP = 0.10, SOFT = 55.0, STEEP_UP = 0.20;
  const CELLM = 12.0;        // grid pitch
  const PAD = 300.0;         // how far past the ribbon's bbox the grid runs
  const COL_REACH = 120.0;   // collided this far from the road, drawn past it
  const DRAW_REACH = 340.0;
  // **What is planted, and how far out.** These are a triangle budget rather
  // than a taste: at the first pass's "everywhere the floor is drawn" the
  // understory alone came to about a million triangles and the shooter timed
  // out taking a screenshot of it. A jungle only has to be dense where you can
  // see into it - past PLANT_FAR the canopy is a silhouette on a hillside, and
  // past FERN_REACH you are looking over the top of the undergrowth anyway.
  const PLANT_NEAR = 90.0, PLANT_FAR = 250.0, FERN_REACH = 110.0;
  const ROUGH = 2.4;         // floor noise, in units
  // The rolling relief, which is *added* to the field and so is the one thing in
  // here that could reach a road. It is multiplied by a ramp that is exactly
  // zero within HILL_NEAR of every station, so it cannot - and HILL_NEAR is
  // comfortably past the widest road plus its apron.
  const HILL = 34.0, HILL_WAVE = 210.0, HILL_NEAR = 46.0, HILL_FAR = 150.0;

  // --- the gorge ------------------------------------------------------------
  // Deep enough that the bottom is out of the key light and reads as distance
  // rather than as a ditch, and wide enough that the animal spanning it is
  // doing something.
  // **Bounded at both ends, and that is the correction.** The first pass ran the
  // downstream reach 900 units past the animal at a half-width that grew to 81,
  // and from above that is a bare rock scar straight across the middle of the
  // track - through road it happened to clear by 76. A canyon is a *place*, not
  // a river system: it starts in the plunge pool, crosses under the animal, and
  // closes into wooded valley TAIL units later.
  // Deeper than it is half wide, which is the difference between a canyon and a
  // dip. At 58 deep and 116 across, the far rim sat just under eye level from a
  // camera four units over the road and the whole crossing read as an
  // embankment: you look *across* a bowl and *into* a slot.
  const GORGE = 72.0;
  const HALF_HEAD = 30.0, HALF_SPAN = 46.0, TAIL = 260.0;
  // The falls' end sits this far off the ledge road, on the side away from the
  // rest of the track - so the road runs along the rim with the drop on one
  // side, rather than down the middle of its own canyon.
  const LEDGE_OFF = 15.0;
  // ...and the depth is faded to nothing this close to any road that is not one
  // of the crossings. A ramp, not a threshold. NEAR is about a road width, which
  // is what the guarantee actually needs; the first pass had it at 24 with FAR
  // at 56 and that is wide enough to strangle the crossings themselves - the
  // creek you jump came out 4% of its depth, which is to say invisible.
  const KEEP_NEAR = 16.0, KEEP_FAR = 44.0;
  // How far either side of a crossing the road is allowed to be undercut, in
  // stations. The banks of a jumped creek are by definition close to it.
  const JUMP_MARGIN = 14;

  // --- the herd -------------------------------------------------------------
  // How many walk the open floor, how far each one paces across it, and how many
  // physics steps a there-and-back takes. The periods are **deliberately not
  // multiples of each other**: equal ones make a chorus line, and a set with a
  // common factor re-forms the same wall every few laps. At 120 steps a second
  // these are between five and eight seconds a crossing.
  const HERD_N = 5;
  const OPEN_N = 3;           // ...and how many walk the opening flick section
  const HERD_PERIODS = [703, 811, 601, 907, 757, 653, 863, 571];
  const HERD_PACE = 0.62;     // how much of the road's width one of them covers

  // The stream you jump, which is its own watercourse: it runs along the jump's
  // own lateral axis, which is by definition across the road. Narrower than the
  // gap is long, so the take-off and the landing are on the banks rather than
  // over the water.
  const CREEK = 34.0, CREEK_HALF = 22.0;
  // Where the river bends. It leaves the falls, swings round, and crosses under
  // the animal **square to the road** - which is the whole reason it bends at
  // all: run straight from the falls to the animal and the road meets it at 35
  // degrees, so the neck lands in the water instead of on the far bank. A bend
  // is also what a river does, and this one buys 76 units of clearance to the
  // rest of the track where the straight line bought 45.
  const BEND = 200.0;

  /**
   * The herd: five solid, moving obstacles across the widest road on the track.
   *
   * **Numbers, not meshes.** `buildTrack` turns each of these into both the
   * group it draws and the box it collides, so there is exactly one description
   * of where a dinosaur is - see `Movers` in trackmesh.js for why that matters
   * and why the clock is an integer.
   *
   * Two things about *where* they are put:
   *
   * **They walk across the road rather than along it.** A mover on the racing
   * line is a wall you cannot pass; a mover crossing a road that is four units
   * wider than the rest of the track is a gap you have to read. That extra width
   * is why `track.py` widens the road here at all, and it is also how this
   * function finds the place - the herd is the widest run of stations, the same
   * way the falls are the highest and the animal the narrowest.
   *
   * **Each one's pace is bounded by the road it is on**, so a re-cut that
   * narrows the herd's floor narrows their walk with it instead of leaving them
   * marching off into the trees.
   */
  function movers(ctx) {
    const { track, pal, shade, cfg } = ctx;
    const line = track.line, n = line.length;
    const C = cfg || {};
    const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
    let wMax = -Infinity;
    for (const e of line) if (e.hw > wMax) wMax = e.hw;
    let bi = -1, bj = -2, i = 0;
    while (i < n) {
      if (line[i].hw < wMax - 0.01) { i++; continue; }
      let j = i; while (j + 1 < n && line[j + 1].hw >= wMax - 0.01) j++;
      if (j - i > bj - bi) { bi = i; bj = j; }
      i = j + 1;
    }
    if (bj <= bi) return [];

    const hideC = C.herd != null ? C.herd : 0x9c5a3c;
    const hide2 = C.herd2 != null ? C.herd2 : 0x6e3d28;
    const eyeC = C.eye != null ? C.eye : 0x141018;
    const out = [];

    // Where they are: the herd's own floor, and the opening. The opening is the
    // road before the jump - the ribbon marks the jump for itself with `air`, so
    // "before the first gap" needs no number - and it is there because that
    // stretch is the fastest and easiest on the track, which is exactly where
    // something walking out in front of you is worth the most.
    let ji = n;
    for (let i = 0; i < n; i++) if (line[i].air) { ji = i; break; }
    const bands = [[bi, bj, HERD_N, 0.12, 0.76], [14, Math.max(20, ji - 18), OPEN_N, 0.18, 0.66]];

    let q = 0;
    for (const [lo, hi, count, pad0, span] of bands) {
      if (hi - lo < 20) continue;
      for (let c = 0; c < count; c++, q++) {
        // Spread along the run, and never on its very ends - the entry and the
        // exit of a section are where a car is already committed.
        const t = (c + 0.5) / count;
        const idx = Math.round(lo + (pad0 + span * t) * (hi - lo));
        const e = line[clamp(idx, 0, n - 1)];
        const reach = e.hw * HERD_PACE;
        const side = q % 2 ? 1 : -1;
        const ax = e.p[0] + e.lat[0] * reach * side;
        const az = e.p[2] + e.lat[2] * reach * side;
        const bx2 = e.p[0] - e.lat[0] * reach * side;
        const bz2 = e.p[2] - e.lat[2] * reach * side;
        // **A hadrosaur, and built as one.** The first pass was a stack of boxes
        // in roughly the right places at roughly the same size, and every one of
        // them came out reading as a wooden crate standing in the road - which
        // on a track whose scatter is boulders and whose palette is brown is the
        // worst thing it could have been mistaken for. What fixes it is
        // proportion, not detail: a long low body, a neck at an angle, a head
        // held above it and a tail as long again behind.
        //
        // Tall enough to stop a car and short enough to see the next corner
        // over, which is the whole brief for an obstacle you are meant to read
        // and drive around rather than be surprised by.
        const S1 = 2.3 * (0.86 + (q % 3) * 0.13);
        const HX = 0.95 * S1, HY = 1.55 * S1, HZ = 2.1 * S1;
        const mid = hideC, dark = hide2, pale = shade(hideC, 0.16);
        out.push({
          ax: ax, az: az, bx: bx2, bz: bz2, y: e.p[1] + HY - 0.5,
          hx: HX, hy: HY, hz: HZ,
          period: HERD_PERIODS[q % HERD_PERIODS.length],
          phase: q * 137,
          // Boxes in the mover's own frame: +z is the way it walks, and y is
          // measured from the middle of the collision box.
          parts: [
            [0, -0.10 * S1, -0.55 * S1, 0.68 * S1, 0.62 * S1, 0.78 * S1, mid],
            [0, 0.02 * S1, 0.45 * S1, 0.52 * S1, 0.50 * S1, 0.72 * S1, mid],
            [0, -0.30 * S1, 0.10 * S1, 0.46 * S1, 0.34 * S1, 1.10 * S1, pale],
            [0, 0.62 * S1, 1.02 * S1, 0.34 * S1, 0.52 * S1, 0.34 * S1, mid],
            [0, 1.18 * S1, 1.34 * S1, 0.30 * S1, 0.28 * S1, 0.58 * S1, mid],
            [0, 1.30 * S1, 1.82 * S1, 0.22 * S1, 0.18 * S1, 0.26 * S1, pale],
            [0, 1.60 * S1, 1.00 * S1, 0.12 * S1, 0.34 * S1, 0.44 * S1, dark],
            [0.28 * S1, 1.30 * S1, 1.48 * S1, 0.10 * S1, 0.10 * S1, 0.13 * S1, eyeC],
            [-0.28 * S1, 1.30 * S1, 1.48 * S1, 0.10 * S1, 0.10 * S1, 0.13 * S1, eyeC],
            [0, -0.12 * S1, -1.55 * S1, 0.40 * S1, 0.40 * S1, 0.62 * S1, mid],
            [0, -0.34 * S1, -2.45 * S1, 0.26 * S1, 0.26 * S1, 0.62 * S1, dark],
            [0, -0.56 * S1, -3.20 * S1, 0.14 * S1, 0.14 * S1, 0.50 * S1, dark],
            [0.60 * S1, -0.78 * S1, -0.45 * S1, 0.22 * S1, 0.70 * S1, 0.30 * S1, dark],
            [-0.60 * S1, -0.78 * S1, -0.45 * S1, 0.22 * S1, 0.70 * S1, 0.30 * S1, dark],
            [0.44 * S1, -0.86 * S1, 0.70 * S1, 0.14 * S1, 0.56 * S1, 0.18 * S1, dark],
            [-0.44 * S1, -0.86 * S1, 0.70 * S1, 0.14 * S1, 0.56 * S1, 0.18 * S1, dark],
          ],
        });
      }
    }
    return out;
  }

  function props(ctx) {
    const { solid, bright, soft, col, track, pal, bbox, KIND, shade, mulberry,
            cfg } = ctx;
    const line = track.line, n = line.length;
    const C = cfg || {};

    // --- the grammar, declared before anything uses it ---------------------
    // A `const` in a long function is in its temporal dead zone until its own
    // line runs, so anything two sections share goes up here with the rest.
    const rnd = mulberry(0xd1a05a);
    const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
    const smooth = (t) => { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); };
    const spot = (i, o) => {
      const e = line[clamp(i | 0, 0, n - 1)];
      return [e.p[0] + e.lat[0] * o, e.p[2] + e.lat[2] * o];
    };
    // Both windings on everything that is not the floor. `solid` is
    // MeshLambertMaterial, which is FrontSide, so a quad wound away from you is
    // drawn, costed and invisible - and an invisible wall is not an error in
    // either language.
    const face = (a, b, c, d, k) => { solid.quad(a, b, c, d, k); solid.quad(a, d, c, b, k); };
    // Two octaves of smooth value noise, for the rolling ground far from the
    // road. Deterministic in world space rather than per-cell, so the hills do
    // not change shape when the grid pitch does.
    const vn = (x, z, w) => {
      const fx = x / w, fz = z / w;
      const ix = Math.floor(fx), iz = Math.floor(fz);
      const tx = smooth(fx - ix), tz = smooth(fz - iz);
      const h = (a, b) => {
        let t = Math.imul(a * 374761393 + b * 668265263 ^ 0x5bf03635, 1274126177);
        t = t ^ t >>> 13;
        return ((t >>> 0) % 65536) / 65536;
      };
      const a = h(ix, iz), b = h(ix + 1, iz), c = h(ix, iz + 1), d = h(ix + 1, iz + 1);
      return (a + (b - a) * tx) + ((c + (d - c) * tx) - (a + (b - a) * tx)) * tz;
    };
    const hill = (x, z) => (vn(x, z, HILL_WAVE) * 0.72
                          + vn(x + 911, z - 733, HILL_WAVE * 0.42) * 0.28) * HILL;
    // Between two packed colours. `shade` moves toward white by a fraction of
    // what is left, which is the wrong curve for picking between two darks.
    const mix = (a, b, t) => {
      const l = (sh) => ((a >> sh) & 255) + (((b >> sh) & 255) - ((a >> sh) & 255)) * clamp(t, 0, 1);
      return (Math.round(l(16)) << 16) | (Math.round(l(8)) << 8) | Math.round(l(0));
    };

    // --- finding the four set pieces --------------------------------------
    // Each is the longest run of stations at the extreme of one quantity. Taken
    // as a *run* rather than as a set, so a stray station that happens to tie
    // cannot smear a set piece across half the lap.
    const runOf = (ok) => {
      let bi = -1, bj = -2, i = 0;
      while (i < n) {
        if (!ok(i)) { i++; continue; }
        let j = i; while (j + 1 < n && ok(j + 1)) j++;
        if (j - i > bj - bi) { bi = i; bj = j; }
        i = j + 1;
      }
      return [bi, bj];
    };
    let hiY = -Infinity, wMax = -Infinity, wMin = Infinity;
    for (const e of line) {
      if (e.p[1] > hiY) hiY = e.p[1];
      if (e.hw > wMax) wMax = e.hw;
      if (e.hw < wMin) wMin = e.hw;
    }
    const LEDGE = runOf((i) => line[i].p[1] >= hiY - 1.0);
    const HERD = runOf((i) => line[i].hw >= wMax - 0.01);
    // The animal is the stations with no road on them: `Builder.skin` says so,
    // and it is the same flag `trackmesh.js` reads to draw nothing there. One
    // statement, read by both halves - the width is a consequence, not the cue.
    const BRACH = runOf((i) => !!line[i].skin);
    const JUMP = runOf((i) => !!line[i].air);
    const midOf = (r) => (r[0] + r[1]) >> 1;

    // Which side of the ledge the canyon is on: the one with more room. Derived
    // rather than read off the corner's sign, because "outside of the corner"
    // and "away from the rest of the track" are the same thing here and only
    // the second one stays true if the layout is re-cut.
    const clearance = (i, o) => {
      const q = spot(i, o);
      let best = Infinity;
      for (let j = 0; j < n; j++) {
        if (j >= LEDGE[0] && j <= LEDGE[1]) continue;
        const e = line[j];
        const d = Math.hypot(q[0] - e.p[0], q[1] - e.p[2]);
        if (d < best) best = d;
      }
      return best;
    };
    const lm = midOf(LEDGE), bm = midOf(BRACH), jm = midOf(JUMP);
    const OUT = clearance(lm, 60) >= clearance(lm, -60) ? 1 : -1;

    // The canyon, as a three-point polyline: the plunge pool under the falls, a
    // bend, then a reach that runs through the animal along the *road's own
    // lateral axis* - which is what makes the crossing square - and on off the
    // map. Not extended past the falls: that end *is* the headwall, and the
    // water coming over it is the reason the canyon is there.
    const be = line[bm];
    const bl = Math.hypot(be.lat[0], be.lat[2]) || 1;
    const blx = be.lat[0] / bl, blz = be.lat[2] / bl;
    const GC = [be.p[0], be.p[2]];
    const RIV = [spot(lm, OUT * LEDGE_OFF),
                 [GC[0] - blx * BEND, GC[1] - blz * BEND],
                 [GC[0] + blx * (BEND + TAIL + 40), GC[1] + blz * (BEND + TAIL + 40)]];
    // Cumulative length to the head of each segment, and the distance at which
    // the river reaches the animal - the two numbers the water surface is
    // sloped between.
    const RS = [0];
    for (let i = 1; i < RIV.length; i++) {
      RS.push(RS[i - 1] + Math.hypot(RIV[i][0] - RIV[i - 1][0], RIV[i][1] - RIV[i - 1][1]));
    }
    const gL = RS[1] + BEND;               // river distance from the falls to the animal
    const gorgeAt = (x, z) => {
      let bd = Infinity, bt = 0;
      for (let i = 0; i + 1 < RIV.length; i++) {
        const a = RIV[i], c = RIV[i + 1];
        const dx = c[0] - a[0], dz = c[1] - a[1];
        const L2 = dx * dx + dz * dz || 1;
        const t = clamp(((x - a[0]) * dx + (z - a[1]) * dz) / L2, 0, 1);
        const d = Math.hypot(x - (a[0] + t * dx), z - (a[1] + t * dz));
        if (d < bd) { bd = d; bt = RS[i] + t * Math.sqrt(L2); }
      }
      // Widening from the plunge pool to the span the animal has to cross, then
      // closing again - so the canyon has two ends rather than one.
      const g = clamp(bt / gL, 0, 1);
      const half = HALF_HEAD + (HALF_SPAN - HALF_HEAD) * smooth(g);
      const close = 1 - smooth((bt - gL) / TAIL);
      return { u: (1 - smooth(bd / half)) * close, t: bt };
    };

    // The creek under the jump, along the jump's own lateral axis.
    const ce = line[jm];
    const cA = [ce.p[0], ce.p[2]];
    const cl = Math.hypot(ce.lat[0], ce.lat[2]) || 1;
    const cux = ce.lat[0] / cl, cuz = ce.lat[2] / cl;
    const creekAt = (x, z) => {
      const t = Math.abs((x - cA[0]) * cux + (z - cA[1]) * cuz);
      const d = Math.abs((x - cA[0]) * cuz - (z - cA[1]) * cux);
      // Bounded along its own axis for the canyon's reason: an unbounded channel
      // is a scar across the map rather than a stream in a clearing.
      return (1 - smooth(d / CREEK_HALF)) * (1 - smooth((t - 150) / 130));
    };

    // --- the field ---------------------------------------------------------
    const gx0 = bbox.x0 - PAD, gz0 = bbox.z0 - PAD;
    const nx = Math.ceil((bbox.x1 + PAD - gx0) / CELLM) + 1;
    const nz = Math.ceil((bbox.z1 + PAD - gz0) / CELLM) + 1;
    const N = nx * nz;
    const fl = new Float64Array(N).fill(Infinity);   // the envelope, gentle
    const ds = new Float64Array(N).fill(Infinity);   // distance to any road
    const dk = new Float64Array(N).fill(Infinity);   // ...to road that is not a crossing
    const ry = new Float64Array(N);                 // y of the nearest road station
    const nzf = new Float64Array(N);
    for (let k = 0; k < N; k++) nzf[k] = rnd();

    // A station the canyon is allowed to undercut: the two crossings, and the
    // ledge, which is a shelf over it on purpose.
    const crossing = (i) => (i >= JUMP[0] - JUMP_MARGIN && i <= JUMP[1] + JUMP_MARGIN)
                         || (i >= BRACH[0] && i <= BRACH[1])
                         || (i >= LEDGE[0] && i <= LEDGE[1]);
    for (let i = 0; i < n; i++) {
      const e = line[i], p = e.p;
      const cx = clamp(Math.round((p[0] - gx0) / CELLM), 0, nx - 1);
      const cz = clamp(Math.round((p[2] - gz0) / CELLM), 0, nz - 1);
      const k = cz * nx + cx;
      // Solid stations only, or the floor fills in under the jump.
      if (!e.air && fl[k] > p[1] - DROP) fl[k] = p[1] - DROP;
      ds[k] = 0; ry[k] = p[1];
      if (!crossing(i)) dk[k] = 0;
    }
    const D1 = CELLM, D2 = CELLM * Math.SQRT2;
    const relax = (k, x, z, d) => {
      if (x < 0 || z < 0 || x >= nx || z >= nz) return;
      const j = z * nx + x;
      const f = fl[j] + G_UP * d; if (f < fl[k]) fl[k] = f;
      const s = ds[j] + d; if (s < ds[k]) { ds[k] = s; ry[k] = ry[j]; }
      const q = dk[j] + d; if (q < dk[k]) dk[k] = q;
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

    // The drawn surface. `extra` is the steep half of the gradient and is zero
    // within SOFT of any station, so it cannot lift the floor into a road - the
    // guarantee the envelope gives survives it. The noise is likewise only ever
    // taken away.
    const F = new Float64Array(N);
    const WET = new Float64Array(N);      // 0..1, how much of this cell is river
    for (let k = 0; k < N; k++) {
      const x = gx0 + (k % nx) * CELLM, z = gz0 + ((k / nx) | 0) * CELLM;
      const d = ds[k];
      const eu = d <= SOFT ? 0 : (STEEP_UP - G_UP) * (d - SOFT);
      let y = fl[k] + eu - nzf[k] * ROUGH
            + hill(x, z) * smooth((d - HILL_NEAR) / (HILL_FAR - HILL_NEAR));
      // Both carves subtract and only subtract.
      const keep = smooth((dk[k] - KEEP_NEAR) / (KEEP_FAR - KEEP_NEAR));
      const g = gorgeAt(x, z), c = creekAt(x, z);
      const cut = Math.max(GORGE * g.u, CREEK * c) * keep;
      y -= cut;
      F[k] = y;
      WET[k] = Math.max(g.u, c) * keep;
    }
    const idx = (x, z) => clamp(z, 0, nz - 1) * nx + clamp(x, 0, nx - 1);
    const cellOf = (x, z) => [Math.round((x - gx0) / CELLM), Math.round((z - gz0) / CELLM)];
    const floorAt = (x, z) => { const c = cellOf(x, z); return F[idx(c[0], c[1])]; };
    const distAt = (x, z) => { const c = cellOf(x, z); return ds[idx(c[0], c[1])]; };

    // --- the floor, drawn --------------------------------------------------
    const green = pal.ground;
    const rock = C.rock != null ? C.rock : 0x8a6a4e;
    const rock2 = C.rock2 != null ? C.rock2 : 0x5c4433;
    for (let z = 0; z < nz - 1; z++) {
      for (let x = 0; x < nx - 1; x++) {
        const a = idx(x, z), b = idx(x, z + 1), c = idx(x + 1, z + 1), d = idx(x + 1, z);
        if (ds[a] > DRAW_REACH && ds[b] > DRAW_REACH
            && ds[c] > DRAW_REACH && ds[d] > DRAW_REACH) continue;
        const X0 = gx0 + x * CELLM, X1 = X0 + CELLM;
        const Z0 = gz0 + z * CELLM, Z1 = Z0 + CELLM;
        // Wound the way the engine's own ground quad is, which is the copy
        // worth taking rather than reasoning about: (x0,z0) -> (x0,z1) ->
        // (x1,z1) -> (x1,z0) faces up.
        const A = [X0, F[a], Z0], B = [X0, F[b], Z1];
        const Cq = [X1, F[c], Z1], D = [X1, F[d], Z0];
        // Grade off the cell's own corners. Anything steep is rock: a canyon
        // wall carpeted in the same green as the floor is a green canyon, and
        // the reference's whole silhouette is bare stone under a green rim.
        const lo = Math.min(F[a], F[b], F[c], F[d]);
        const hi = Math.max(F[a], F[b], F[c], F[d]);
        const grade = (hi - lo) / CELLM;
        const nse = nzf[(a * 7 + 13) % N];
        let colr;
        if (grade > 0.95) {
          colr = mix(rock, rock2, clamp((grade - 0.95) * 0.7 + nse * 0.35, 0, 1));
        } else {
          // Wetter and darker toward the water, drier and yellower up the
          // hillside - so the floor is not one flat green from rim to rim.
          const w = WET[a];
          colr = shade(mix(green, mix(green, rock, 0.35), clamp((ds[a] - SOFT) / 300, 0, 0.42)),
                       (nse - 0.5) * 0.16 - w * 0.22);
        }
        solid.quad(A, B, Cq, D, colr);
        if (ds[a] <= COL_REACH) col.addQuad(A, B, Cq, D, KIND.OFFROAD);
      }
    }

    // --- the water ---------------------------------------------------------
    // **The surface is read off the bed the carve actually cut, not written down
    // beside it.** The level used to be two authored constants interpolated
    // along the river, which is a second description of a shape that already
    // exists - and the two disagreed the moment the carve was narrowed, leaving
    // a canyon with a puddle in the bottom and, where the road ran near, a pane
    // of blue lying across the tarmac.
    //
    // So: bucket every cell by how far down the river it is, take the lowest
    // floor in each bucket, and put the water a few units over that. Then sweep
    // downstream taking a running minimum, because a river may not flow uphill
    // and a per-bucket answer has no reason on its own not to.
    const water = C.water != null ? C.water : 0x2f7f8c;
    const deep = C.deepWater != null ? C.deepWater : 0x14495c;
    const DEPTH = 5.0;                     // how far the water stands over the bed
    const BUCK = 24.0;                     // river distance per bucket
    const NB = Math.ceil((gL + TAIL + 80) / BUCK) + 2;
    const bed = new Float64Array(NB).fill(Infinity);
    let creekBed = Infinity;
    for (let k = 0; k < N; k++) {
      if (WET[k] < 0.55) continue;         // the channel, not its banks
      const x = gx0 + (k % nx) * CELLM, z = gz0 + ((k / nx) | 0) * CELLM;
      const g = gorgeAt(x, z), c = creekAt(x, z);
      if (g.u >= c) {
        const bq = clamp(Math.round(g.t / BUCK), 0, NB - 1);
        if (F[k] < bed[bq]) bed[bq] = F[k];
      } else if (F[k] < creekBed) creekBed = F[k];
    }
    // Fill the empty buckets from their neighbours, then make it run downhill.
    for (let i = 1; i < NB; i++) if (!isFinite(bed[i])) bed[i] = bed[i - 1];
    for (let i = NB - 2; i >= 0; i--) if (!isFinite(bed[i])) bed[i] = bed[i + 1];
    for (let i = 1; i < NB; i++) if (bed[i] > bed[i - 1]) bed[i] = bed[i - 1];
    const surfaceAt = (t) => bed[clamp(Math.round(t / BUCK), 0, NB - 1)] + DEPTH;
    const creekY = (isFinite(creekBed) ? creekBed : 0) + DEPTH;
    for (let z = 0; z < nz - 1; z++) {
      for (let x = 0; x < nx - 1; x++) {
        const a2 = idx(x, z);
        if (ds[a2] > DRAW_REACH || WET[a2] < 0.12) continue;
        const X0 = gx0 + x * CELLM, X1 = X0 + CELLM;
        const Z0 = gz0 + z * CELLM, Z1 = Z0 + CELLM;
        const g = gorgeAt(X0, Z0), c = creekAt(X0, Z0);
        const wy = (g.u >= c) ? surfaceAt(g.t) : creekY;
        if (F[a2] > wy - 0.6) continue;    // only where there is a bed under it
        // ...and never at the height of a road that is near. Where the canyon
        // passes *under* the animal this is no constraint at all - the river is
        // sixty units down - but at the mouth, where the road comes back to
        // ground beside the water, a surface within a few units of the tarmac
        // is a pane of blue lying across it. Which is what it did.
        if (ds[a2] < 46 && wy > ry[a2] - 9) continue;
        solid.quad([X0, wy, Z0], [X0, wy, Z1], [X1, wy, Z1], [X1, wy, Z0],
                   mix(water, deep, clamp((wy - F[a2]) / 22, 0, 1)));
      }
    }

    // --- where the head stands ----------------------------------------------
    // Worked out here rather than in the animal block below, because the pass
    // that plants the jungle runs first and has to know: an animal with its head
    // down on the bank has trodden its own clearing, and without one the trees
    // grow through it. `HEAD_SPOT` is the one place this position exists - the
    // animal reads it back rather than recomputing it, so the glade and the head
    // cannot drift apart.
    //
    // **The clearing is also a hole in the canopy**, and that is the half that
    // matters to a picture. The head is only six units off the floor while the
    // crowns are twenty-five, so there is no camera height that both sees it and
    // is above the leaves: from under the canopy the near trunks fill the frame
    // and from over it you are looking at the roof. A gap in the roof is the
    // only thing that gives the shot somewhere to look through, and it is why
    // this is 34 units rather than the 12 the head itself occupies.
    const HEAD_CLEAR = 34.0;
    const HEAD_SPOT = (() => {
      const hi = clamp(BRACH[1] + 9, 0, n - 1);
      const pA = spot(hi, 22), pB = spot(hi, -22);
      const sd = floorAt(pA[0], pA[1]) >= floorAt(pB[0], pB[1]) ? 1 : -1;
      return { i: hi, side: sd, p: spot(hi, sd * 21.0) };
    })();

    // --- what grows on it --------------------------------------------------
    // The engine's own scatter stops at `if (!onGround) continue` - there is
    // nothing to stand a tree on in the void - so a floating track plants its
    // own, reading the same two palette keys so that `pal.props` still means
    // what it means everywhere else.
    const mixw = pal.props || { palm: 0.6, rock: 0.4 };
    const kinds = Object.keys(mixw);
    const tot = kinds.reduce((s, k) => s + mixw[k], 0);
    const pick = (r) => { let acc = 0; for (const k of kinds) { acc += mixw[k] / tot; if (r <= acc) return k; } return kinds[kinds.length - 1]; };
    const density = pal.density != null ? pal.density : 0.2;
    const trunk = 0x6b4a2e;
    const leaf = pal.prop, leaf2 = pal.prop2 != null ? pal.prop2 : shade(pal.prop, -0.2);
    const cone = (cx, cy, cz, r, h, k) => {
      const S = 6, top = [cx, cy + h, cz];
      for (let s = 0; s < S; s++) {
        const a0 = s / S * Math.PI * 2, a1 = (s + 1) / S * Math.PI * 2;
        solid.tri([cx + Math.cos(a0) * r, cy, cz + Math.sin(a0) * r],
                  [cx + Math.cos(a1) * r, cy, cz + Math.sin(a1) * r], top, k);
      }
    };
    for (let z = 1; z < nz - 1; z++) {
      for (let x = 1; x < nx - 1; x++) {
        const a = idx(x, z);
        if (ds[a] > PLANT_FAR) continue;
        // Thinning with distance, so the near jungle is thick and the far one is
        // a horizon rather than a million triangles of it.
        if (rnd() > density * (1 - 0.55 * smooth((ds[a] - PLANT_NEAR) / (PLANT_FAR - PLANT_NEAR)))) continue;
        // Off the road, out of the water, and off anything too steep to stand
        // on. `ds` is the road distance the field already computed, so a tree
        // can never grow out of the kerb.
        if (ds[a] < 16) continue;
        if (WET[a] > 0.25) continue;
        const lo = Math.min(F[a], F[idx(x + 1, z)], F[idx(x, z + 1)]);
        const hi = Math.max(F[a], F[idx(x + 1, z)], F[idx(x, z + 1)]);
        if ((hi - lo) / CELLM > 0.75) continue;
        const px = gx0 + x * CELLM + (rnd() - 0.5) * CELLM * 0.7;
        const pz = gz0 + z * CELLM + (rnd() - 0.5) * CELLM * 0.7;
        if (Math.hypot(px - HEAD_SPOT.p[0], pz - HEAD_SPOT.p[1]) < HEAD_CLEAR) continue;
        const by = floorAt(px, pz) - 0.4;
        // How far a crown may spread from this trunk. A canopy over the road is
        // the point, so the foliage is *meant* to overhang - what it may not do
        // is meet in the middle, because this track is photographed from up high
        // for the switcher and the share card and the cover of a fully roofed
        // road is a picture of leaves. So a crown may reach three units short of
        // the centre line and no further, which leaves a slot about six wide
        // down a thirteen-wide road: from the seat that is a green tunnel with a
        // strip of sky in it, which is what a road cut through jungle actually
        // looks like, and from above it is still a road. Out past about 35 units
        // nothing clamps and the crowns close over each other properly.
        //
        // **This clamp is the whole difficulty and it took two passes to get
        // right.** The trees that fill the frame are the ones nearest the road,
        // so a clamp that is too tight bites hardest exactly where the canopy
        // has to read: at the `ds - 13` it started at, a 30-unit trunk carried a
        // 10-unit crown and the jungle was the field of bare poles this file has
        // been warned about since its first version. At `ds - 7` the tips landed
        // on the near kerb, which is a lined avenue rather than a canopy - the
        // road still had its own full-width strip of sky over it.
        const reach = Math.max(6.5, ds[a] - 3);
        const kind = pick(rnd());
        if (kind === 'rock') {
          // A boulder, not a crate. Three overlapping boxes at three angles is
          // the cheapest thing that stops reading as furniture, and the first
          // pass - one axis-aligned box in a colour off the palette - carpeted
          // the jungle in what looked like dropped luggage.
          const s0 = 1.6 + rnd() * 2.8;
          const rc = mix(rock, rock2, 0.3 + rnd() * 0.5);
          solid.box(px, by + s0 * 0.42, pz, s0, s0 * 0.46, s0 * 0.86, rc);
          solid.box(px + s0 * 0.35, by + s0 * 0.7, pz - s0 * 0.2,
                    s0 * 0.5, s0 * 0.34, s0 * 0.44, shade(rc, 0.08));
          solid.box(px - s0 * 0.3, by + s0 * 0.3, pz + s0 * 0.3,
                    s0 * 0.44, s0 * 0.26, s0 * 0.5, shade(rc, -0.1));
          continue;
        }
        if (kind === 'deadtree') {
          // A snag, and its job changed when the canopy went up: at 7 to 15 it
          // was a stick in the undergrowth, and the only thing a bare trunk is
          // good for is standing *through* the leaves. So it is tall enough to
          // break the ceiling and thick enough to read against it.
          const h = 16 + rnd() * 14;
          solid.box(px, by + h / 2, pz, 0.56, h / 2, 0.56, shade(trunk, -0.2));
          continue;
        }
        if (kind === 'conifer') {
          // The tall dark tree ferns of the reference: a bare stem and three
          // whorls, which is all that reads at this scale. The whorls sit at
          // fractions of `h`, so they follow the trunk up on their own; only
          // their spread and depth are absolute and had to be scaled by hand.
          const h = 20 + rnd() * 15;
          solid.box(px, by + h * 0.5, pz, 0.52, h * 0.5, 0.52, trunk);
          const cr = Math.min(1.0, reach / 6.5);
          cone(px, by + h * 0.50, pz, (5.6 + rnd() * 1.5) * cr, 8.5, leaf2);
          cone(px, by + h * 0.72, pz, (4.3 + rnd() * 1.3) * cr, 7.0, leaf);
          cone(px, by + h * 0.90, pz, (2.8 + rnd() * 1.0) * cr, 5.0, leaf2);
          continue;
        }
        // A palm: a lean, and a splay of long drooping fronds. **The fronds are
        // the tree.** At the first pass's 4-unit blades on a 0.62-unit trunk
        // the whole jungle read as a field of bare poles - a frond has to be
        // most of the silhouette, which at this scale means about as long as
        // the trunk is tall and wide enough to survive being seen edge-on.
        //
        // **A canopy is a layer, not a spread of heights.** At the 11-to-21 this
        // started at, every crown was inside the arc the camera looks through
        // and the jungle read as scrub the car sees over the top of - a hedge
        // with a road in it. What makes a canopy is a *ceiling*: crowns at
        // roughly one height, well above the sight line, with the trunks holding
        // it up and only the odd emergent standing clear. So the height band is
        // deliberately narrow, and the variation that used to be in `h` is in
        // `emergent` instead, where it reads as one tree above the roof rather
        // than as a hillside of assorted shrubs.
        const emergent = rnd() < 0.15;
        const h = (23 + rnd() * 7) * (emergent ? 1.35 : 1.0);
        // Thicker with height, or a forty-unit trunk is a wire. And the lean is
        // smaller than it was for the same reason `bx` limbs are: the trunk's
        // boxes are axis-aligned, so the lean is a staircase, and the taller the
        // trunk the more steps there are to notice - hence the fourth segment.
        const tw = 0.34 + h * 0.013;
        const lean = (rnd() - 0.5) * 0.18, la = rnd() * Math.PI * 2;
        const tx = px + Math.cos(la) * lean * h, tz = pz + Math.sin(la) * lean * h;
        const seg = 4;
        for (let sg = 0; sg < seg; sg++) {
          const u0 = sg / seg, u1 = (sg + 1) / seg;
          solid.box(px + (tx - px) * (u0 + u1) * 0.5, by + h * (u0 + u1) * 0.5,
                    pz + (tz - pz) * (u0 + u1) * 0.5,
                    tw * (1 - u0 * 0.3), h * (u1 - u0) * 0.5, tw * (1 - u0 * 0.3),
                    shade(trunk, (rnd() - 0.5) * 0.12));
        }
        // **Crowns wide enough to touch their neighbours**, which is the other
        // half of a ceiling and the half that took a second pass. The grid is 12
        // units and the thinned density stands a tree about every 25, so a crown
        // has to be about 35 across before the gaps between them close and the
        // eye stops reading sky through a colonnade. More blades too: a wider
        // splay off the same seven fronds is a starfish, and it is the count
        // that fills a crown rather than the length.
        const NF = 8 + ((rnd() * 4) | 0);
        const spin = rnd() * Math.PI * 2;
        for (let f = 0; f < NF; f++) {
          const a2 = spin + (f / NF) * Math.PI * 2 + (rnd() - 0.5) * 0.35;
          const rl = Math.min(14.0 + rnd() * 7.0, reach);
          const cx = tx + Math.cos(a2) * rl * 0.55, cz = tz + Math.sin(a2) * rl * 0.55;
          const ex = tx + Math.cos(a2) * rl, ez = tz + Math.sin(a2) * rl;
          // Two panels with a knee in the middle, so the frond droops instead of
          // sticking out flat - which is what tells a palm from an umbrella.
          // The droop and the blade's width both scale off the frond's own
          // length - a twenty-unit frond held at the old 1.55 half-width is a
          // ribbon, and one that falls the old 2.6 is dead flat.
          const cy = by + h + 0.9, ey = by + h - rl * 0.30 - rnd() * 3.0;
          const w0 = 0.38, w1 = rl * 0.15, w2 = rl * 0.05;
          const ox = -Math.sin(a2), oz = Math.cos(a2);
          const kf = f % 2 ? leaf : leaf2;
          face([tx - ox * w0, by + h, tz - oz * w0], [tx + ox * w0, by + h, tz + oz * w0],
               [cx + ox * w1, cy, cz + oz * w1], [cx - ox * w1, cy, cz - oz * w1], kf);
          face([cx - ox * w1, cy, cz - oz * w1], [cx + ox * w1, cy, cz + oz * w1],
               [ex + ox * w2, ey, ez + oz * w2], [ex - ox * w2, ey, ez - oz * w2], kf);
        }
      }
    }

    // --- shared shapes ------------------------------------------------------
    // The forward direction at a station, in the ground plane. Taken from the
    // neighbours rather than from `n`, which is the surface normal.
    const fwd = (i) => {
      const a = line[clamp(i - 1, 0, n - 1)].p, b = line[clamp(i + 1, 0, n - 1)].p;
      const dx = b[0] - a[0], dz = b[2] - a[2];
      const L = Math.hypot(dx, dz) || 1;
      return [dx / L, dz / L];
    };
    // A box in a station's own frame: along the road, across it, and up.
    // Everything on the animal is built with this, so the body follows the road
    // round the arch instead of being a row of world-aligned crates.
    const bx = (c, f, hf, hl, hv, k) => {
      const l = [-f[1], f[0]];
      const P = (sf, sl, sv) => [c[0] + f[0] * sf * hf + l[0] * sl * hl,
                                 c[1] + sv * hv,
                                 c[2] + f[1] * sf * hf + l[1] * sl * hl];
      const v = [P(-1, -1, -1), P(1, -1, -1), P(1, 1, -1), P(-1, 1, -1),
                 P(-1, -1, 1), P(1, -1, 1), P(1, 1, 1), P(-1, 1, 1)];
      face(v[0], v[3], v[2], v[1], k); face(v[4], v[5], v[6], v[7], k);
      face(v[0], v[1], v[5], v[4], k); face(v[2], v[3], v[7], v[6], k);
      face(v[1], v[2], v[6], v[5], k); face(v[3], v[0], v[4], v[7], k);
      return v;
    };

    // --- the falls ----------------------------------------------------------
    // What makes the lap's highest stations a *shelf*: a cliff standing on the
    // inside of the road, leaning out over it as it rises, and the water leaving
    // that lip **outboard of the road's outer edge** - so the curtain is between
    // you and the canyon and you drive behind it, which is what was asked for
    // and is also the only arrangement that does not put a waterfall on the
    // racing line.
    //
    // The lean starts at LEAN_Y and not at the road, and that is the one number
    // here with a reason rather than a taste behind it: a face leaning the whole
    // way from the verge crosses the road's own airspace about three units in,
    // which is a rock wall through the middle of the corner. Above the car and
    // above the chase camera, it is scenery; below that it is geometry, and this
    // file adds none of it to the collider.
    const HAS_FALLS = LEDGE[0] >= 0 && LEDGE[1] > LEDGE[0];
    if (HAS_FALLS) {
      const IN = -OUT;
      const L0 = clamp(LEDGE[0] - 7, 0, n - 1), L1 = clamp(LEDGE[1] + 7, 0, n - 1);
      // Where the lean starts, where the lip is, and where the cliff tops out.
      // The first pass leaned from 9 to 34 and roofed the road over so completely
      // that the ledge read as a tunnel with a window - the whole point is that
      // you can see the canyon through the water. Starting higher and topping out
      // lower leaves the overhang a shelf rather than a lid.
      const LEAN_Y = 15.0, TOP_Y = 21.0, CAP_Y = 26.0;
      const rockA = mix(rock, rock2, 0.35), rockB = mix(rock, rock2, 0.7);
      // The four levels of the face, as offsets from the road centre on the
      // inside/outside axis. Level 2 is out past the road's own edge, which is
      // what puts the lip - and the water off it - outboard of the kerb.
      // The bottom level is taken down to whatever the ground beside it is, and
      // not to a flat offset: on the inside the ledge is a hillside and on the
      // outside it is the canyon, so a fixed `-12` leaves the cliff a slab
      // floating over the drop with daylight under it.
      const prof = (e) => [
        [IN * (e.hw + 1.0), e.p[1] - 12.0],
        [IN * (e.hw + 1.0), e.p[1] + LEAN_Y],
        [OUT * (e.hw + 2.0), e.p[1] + TOP_Y],
        [OUT * (e.hw + 0.5), e.p[1] + CAP_Y],
      ];
      const lipPts = [];
      for (let i = L0; i < L1; i++) {
        const ea = line[i], eb = line[i + 1];
        const pa = prof(ea), pb = prof(eb);
        const ptA = (k) => {
          const q = spot(i, pa[k][0]);
          return [q[0], k === 0 ? Math.min(pa[0][1], floorAt(q[0], q[1]) - 4) : pa[k][1], q[1]];
        };
        const ptB = (k) => {
          const q = spot(i + 1, pb[k][0]);
          return [q[0], k === 0 ? Math.min(pb[0][1], floorAt(q[0], q[1]) - 4) : pb[k][1], q[1]];
        };
        for (let k = 0; k < 3; k++) {
          face(ptA(k), ptA(k + 1), ptB(k + 1), ptB(k),
               shade(k === 2 ? rockB : rockA,
                     (nzf[(i * 13 + k * 91) % N] - 0.5) * 0.2));
        }
        lipPts.push(ptA(2));
        // The cliff has a back as well as a face, or the ledge is a fin you can
        // see the sky through from the descent below it.
        const bk = (k, j) => { const q = spot(j, IN * (line[j].hw + 15.0)); return [q[0], line[j].p[1] + (k ? CAP_Y : -12.0), q[1]]; };
        face(bk(0, i), bk(1, i), bk(1, i + 1), bk(0, i + 1), shade(rockB, -0.06));
        face(ptA(3), ptB(3), bk(1, i + 1), bk(1, i), shade(rockA, 0.1));
      }
      lipPts.push((() => { const q = spot(L1, prof(line[L1])[2][0]); return [q[0], prof(line[L1])[2][1], q[1]]; })());
      // Both ends closed, or the cliff is a fin you can see the sky through from
      // the road below it.
      for (const [j, sgn] of [[L0, 1], [L1, -1]]) {
        const pj = prof(line[j]);
        const face4 = pj.map((lv, k) => {
          const q = spot(j, lv[0]);
          return [q[0], k === 0 ? Math.min(lv[1], floorAt(q[0], q[1]) - 4) : lv[1], q[1]];
        });
        const bq0 = spot(j, IN * (line[j].hw + 15.0));
        const b0 = [bq0[0], face4[0][1], bq0[1]], b1 = [bq0[0], face4[3][1], bq0[1]];
        face(face4[0], face4[1], b1, b0, shade(rockB, -0.03));
        face(face4[1], face4[2], b1, b1, shade(rockB, -0.03));
        face(face4[1], face4[2], face4[3], b1, shade(rockA, -0.02));
      }

      // The water. Drawn in `soft`, which is the game's one translucent mesh -
      // it is what `rain` uses, and a curtain you can see the canyon through is
      // the whole difference between a waterfall and a white wall. Three sheets
      // at slightly different offsets, because one sheet at 0.82 opacity reads
      // as a pane of glass and three overlapping ones accumulate into something
      // dense in the middle and thin at the edges.
      const foam = C.foam != null ? C.foam : 0xd8f0f2;
      const wsurf = surfaceAt(0);
      // **A fringe, not a wall, and only over the middle of the shelf.** The
      // first pass hung five continuous sheets down the whole railed stretch,
      // and with rock leaning in on one side that is a corridor with a pane of
      // glass for one wall - which is the opposite of the thing being built.
      // You are supposed to be able to see the canyon through it, so the water
      // starts a third of the way along, ends before the shelf does, and is
      // ragged: each sheet skips columns, so there are gaps between the falls
      // and the sky and the gorge come through them.
      const W0 = L0 + Math.round((L1 - L0) * 0.18);
      const W1 = L1 - Math.round((L1 - L0) * 0.12);
      for (let sIdx = 0; sIdx < 2; sIdx++) {
        const off = (sIdx - 0.5) * 3.0, drape = sIdx * 1.3;
        for (let k = 0; k + 1 < lipPts.length; k++) {
          const j = L0 + k;
          if (j < W0 || j >= W1) continue;
          // Ragged: about a third of the columns of each sheet are simply not
          // there, and no two sheets skip the same ones.
          if (nzf[(j * 53 + sIdx * 311) % N] < 0.50) continue;
          const a = lipPts[k], b = lipPts[k + 1];
          const oa = spot(j, OUT * (line[j].hw + 2.2 + off));
          const ob = spot(j + 1, OUT * (line[j + 1].hw + 2.2 + off));
          const ta = [oa[0], a[1] - drape, oa[1]], tb = [ob[0], b[1] - drape, ob[1]];
          const fa = spot(j, OUT * (line[j].hw + 8.5 + off));
          const fb = spot(j + 1, OUT * (line[j + 1].hw + 8.5 + off));
          const kc = shade(mix(foam, C.water != null ? C.water : 0x2f7f8c, 0.06 + sIdx * 0.07),
                           (nzf[(j * 31 + sIdx * 7) % N] - 0.5) * 0.20);
          soft.quad(ta, tb, [fb[0], wsurf, fb[1]], [fa[0], wsurf, fa[1]], kc);
          soft.quad(ta, [fa[0], wsurf, fa[1]], [fb[0], wsurf, fb[1]], tb, kc);
        }
      }
      // **The white in it is `bright` and the body of it is `soft`, and both
      // halves are needed.** `soft` is the game's one translucent mesh, which is
      // what lets you see the canyon through the water - but it is a
      // *MeshLambertMaterial*, and a vertical sheet under a near-overhead sun
      // gets almost nothing from the key light, so a curtain picked at the
      // colour of water comes out a flat dark panel. The sheets above are
      // therefore picked nearly white and let the lighting take them down to
      // water; these are unlit, which is honest here, because falling water
      // really is the one thing in a scene that is its own light source.
      for (let k = 0; k + 1 < lipPts.length; k++) {
        const j = L0 + k;
        if (j < W0 || j >= W1) continue;
        const a = lipPts[k], b = lipPts[k + 1];
        const oa = spot(j, OUT * (line[j].hw + 9.0));
        const ob = spot(j + 1, OUT * (line[j + 1].hw + 9.0));
        bright.quad([a[0], a[1] + 0.4, a[2]], [b[0], b[1] + 0.4, b[2]],
                    [ob[0], b[1] - 9.0, ob[1]], [oa[0], a[1] - 9.0, oa[1]], foam);
        // Vertical streaks down the face of it, which is most of what says
        // *falling* rather than *hanging*. Thin, unlit, and at three depths, so
        // the curtain has some thickness to look into.
        for (let q2 = 0; q2 < 3; q2++) {
          if ((k + q2) % 3) continue;
          const w2 = 0.5 + rnd() * 0.9, off2 = (q2 - 1) * 2.0;
          const ta = spot(j, OUT * (line[j].hw + 3.4 + off2));
          const tb = spot(j + 1, OUT * (line[j + 1].hw + 3.4 + off2));
          const fa2 = spot(j, OUT * (line[j].hw + 9.4 + off2));
          const y0 = a[1] - rnd() * 6, y1 = wsurf + rnd() * 12;
          bright.quad([ta[0], y0, ta[1]], [tb[0] + (tb[0] - ta[0]) * w2, y0, tb[1] + (tb[1] - ta[1]) * w2],
                      [fa2[0] + (tb[0] - ta[0]) * w2, y1, fa2[1] + (tb[1] - ta[1]) * w2],
                      [fa2[0], y1, fa2[1]], shade(foam, -0.02));
        }
        if (k % 2) {
          const r = 5.0 + rnd() * 5.0;
          soft.box(oa[0], wsurf + 1.6 + rnd() * 5.0, oa[1], r, 2.2 + rnd() * 2.4, r,
                   shade(foam, -0.04));
        }
      }
    }

    // --- the animal ---------------------------------------------------------
    // **You drive on the creature, not over it.** The stations across the canyon
    // are flagged `skin`, so `trackmesh.js` draws no road on them at all - no
    // surface, no kerb, no slab - and this builds the back that replaces it,
    // through those same station points. The crown is *flat across the road's
    // own width* and then rolls away to a rounded flank, so the surface the car
    // stands on and the surface you can see are the same one, and the ribbon's
    // collider quad down the middle is a floor under both of them that does not
    // depend on this file being right.
    //
    // The upper half of the flank goes into the collider as `KIND.ROAD` too, so
    // the back is three times the width of the road it replaced and running wide
    // is a slide down a shoulder rather than a wall. There are no barriers here
    // for that reason: a handrail down both sides of an animal's spine is a
    // bridge with a paint job.
    //
    // **The body is derived from the road over it and never the other way
    // round**, so a re-cut spine drags the creature with it and the two cannot
    // disagree - the failure that would be invisible from every angle except the
    // one you drive.
    if (BRACH[1] > BRACH[0]) {
      const hide = C.hide != null ? C.hide : 0x3160cc;
      const belly = C.belly != null ? C.belly : 0xe4d6a8;
      const eyeC = C.eye != null ? C.eye : 0x141018;
      const B0 = BRACH[0], B1 = BRACH[1], BN = B1 - B0;
      const RMAX = 13.0, RMIN = 1.2;
      // Tail, torso, neck. A single sine bulge gives a football; a plateau is
      // what makes the middle a body with a tail off one end and a neck off the
      // other.
      const girth = (u) => RMIN + (RMAX - RMIN)
        * smooth((u - 0.14) / 0.20) * (1 - smooth((u - 0.58) / 0.22));
      // Half a cross-section, from the edge of the flat crown round to the belly:
      // [how far out past the road, how far down], both in girths. Only the first
      // three steps are shallow enough to be a surface; past that it is a flank.
      const CS = [[0.00, 0.00], [0.42, 0.10], [0.80, 0.42], [1.00, 0.92],
                  [0.96, 1.46], [0.66, 1.90], [0.24, 2.12], [0.00, 2.20]];
      const DRIVE = 3;                       // steps collided as road, per side
      // One side of one station, as world points.
      const rib = (i, sd) => {
        const e = line[clamp(i, 0, n - 1)];
        const u = (clamp(i, B0, B1) - B0) / BN;
        const r = girth(u);
        return CS.map((c) => {
          const o = sd * (e.hw + c[0] * r);
          return [e.p[0] + e.lat[0] * o, e.p[1] - c[1] * r, e.p[2] + e.lat[2] * o];
        });
      };
      const axisOf = (i) => {
        const e = line[clamp(i, B0, B1)];
        const u = (clamp(i, B0, B1) - B0) / BN;
        const r = girth(u);
        return { p: [e.p[0], e.p[1] - r * 1.1, e.p[2]], r: r, u: u, e: e };
      };
      const hideAt = (k, i, sd) => {
        // Pale throat and belly underneath, hide on top, blended rather than
        // switched - a hard line round the flank reads as a painted stripe.
        const dn = clamp((CS[k][1] - 0.5) / 1.5, 0, 1);
        return shade(mix(hide, belly, dn), (nzf[(i * 17 + k * 53 + (sd > 0 ? 7 : 0)) % N] - 0.5) * 0.06);
      };
      let prevL = rib(B0, -1), prevR = rib(B0, 1);
      for (let i = B0 + 1; i <= B1; i++) {
        const curL = rib(i, -1), curR = rib(i, 1);
        // The crown: three quads across the road's own width, exactly where the
        // engine's undrawn collider quad is. Three rather than one, and shaded,
        // because a single flat quad 37 units wide and 240 long reads as a blue
        // lake - a spine lighter down the middle and the shoulders falling into
        // shadow is what says *back* from the one seat that can only ever see
        // this much of the animal.
        {
          const cL = hideAt(0, i, -1), cM = shade(hide, 0.10);
          const q = (A, B2, Cc, D, k) => solid.quad(A, B2, Cc, D, k);
          const mixp = (a3, b3, t) => [a3[0] + (b3[0] - a3[0]) * t, a3[1] + (b3[1] - a3[1]) * t,
                                       a3[2] + (b3[2] - a3[2]) * t];
          const pl = mixp(prevL[0], prevR[0], 0.30), pr = mixp(prevL[0], prevR[0], 0.70);
          const kl = mixp(curL[0], curR[0], 0.30), kr = mixp(curL[0], curR[0], 0.70);
          q(prevL[0], pl, kl, curL[0], shade(cL, -0.06));
          q(pl, pr, kr, kl, cM);
          q(pr, prevR[0], curR[0], kr, shade(cL, -0.06));
        }
        for (const [prev, cur, sd] of [[prevL, curL, -1], [prevR, curR, 1]]) {
          for (let k = 0; k + 1 < CS.length; k++) {
            const A = prev[k], Bp = prev[k + 1], Cq = cur[k + 1], D = cur[k];
            face(A, Bp, Cq, D, hideAt(k, i, sd));
            if (k < DRIVE) {
              // Wound to match the road's own quads, so the ground query finds
              // the shoulder the same way it finds tarmac.
              if (sd > 0) col.addQuad(A, Bp, Cq, D, KIND.ROAD);
              else col.addQuad(D, Cq, Bp, A, KIND.ROAD);
            }
          }
        }
        // A row of low plates along each flank, spaced out. They sit past the
        // shoulder the collider covers, so they are never in the way of a car
        // that is on the animal - and they are the other half of what says the
        // surface is alive rather than paved.
        if (i % 4 === 0 && girth((i - B0) / BN) > RMAX * 0.45) {
          for (const side of [prevL, prevR]) {
            const base = side[2], tip = side[1];
            const c2 = [(base[0] + tip[0]) / 2, (base[1] + tip[1]) / 2 + 1.9,
                        (base[2] + tip[2]) / 2];
            bx(c2, fwd(i), 2.2, 1.0, 2.1, shade(mix(hide, belly, 0.1), 0.14));
          }
        }
        prevL = curL; prevR = curR;
      }
      // Caps, so neither end is a hole you can see the sky through.
      for (const [j, sg] of [[B0, -1], [B1, 1]]) {
        const L = rib(j, -1), R = rib(j, 1);
        for (let k = 0; k + 1 < CS.length; k++) {
          face(L[k], R[k], R[k + 1], L[k + 1], hideAt(k, j, sg));
        }
      }
      // Four legs, down to whatever the canyon floor is under each foot.
      for (const lu of [0.26, 0.32, 0.52, 0.58]) {
        const i = Math.round(B0 + lu * BN);
        const a2 = axisOf(i), e = a2.e, f = fwd(i);
        for (const sd of [-1, 1]) {
          const hipX = a2.p[0] + e.lat[0] * sd * (e.hw + a2.r * 0.5);
          const hipZ = a2.p[2] + e.lat[2] * sd * (e.hw + a2.r * 0.5);
          const hipY = a2.p[1] - a2.r * 0.55;
          const footY = Math.min(floorAt(hipX, hipZ) + 0.8, hipY - 8);
          const SEGS = 4;
          for (let q = 0; q < SEGS; q++) {
            const y0 = hipY + (footY - hipY) * (q / SEGS);
            const y1 = hipY + (footY - hipY) * ((q + 1) / SEGS);
            const w = a2.r * (0.30 - q * 0.038);
            bx([hipX, (y0 + y1) * 0.5, hipZ], f, w, w, (y0 - y1) * 0.5,
               shade(mix(hide, belly, 0.10 + q * 0.05), -q * 0.03));
          }
          bx([hipX, footY + 1.1, hipZ], f, a2.r * 0.28, a2.r * 0.24, 1.1,
             shade(hide, -0.12));
        }
      }
      // The tail, swept out onto the near bank past where the road climbs on -
      // the one part of the animal you meet before you are standing on it, and
      // therefore the one that says what you are about to drive over.
      {
        const i0 = Math.round(B0 + 0.16 * BN);
        const a0 = axisOf(i0), f0 = fwd(i0);
        let px = a0.p[0], py = a0.p[1], pz = a0.p[2];
        let dx = -f0[0], dz = -f0[1];
        const curve = OUT * 0.5, TS = 12;
        for (let q = 0; q < TS; q++) {
          const t = q / TS, step = 9.0;
          const r = a0.r * (1 - t) * 0.72 + 0.5;
          const ang = curve * t * 1.1;
          const nx2 = dx * Math.cos(ang) - dz * Math.sin(ang);
          const nz2 = dx * Math.sin(ang) + dz * Math.cos(ang);
          dx = nx2; dz = nz2;
          const qx = px + dx * step, qz = pz + dz * step;
          const qy = Math.max(floorAt(qx, qz) + r * 0.8, py - 2.4 - t * 2.0);
          bx([(px + qx) / 2, (py + qy) / 2, (pz + qz) / 2], [dx, dz],
             step * 0.62, r, r, shade(mix(hide, belly, 0.2), -0.02));
          px = qx; py = qy; pz = qz;
        }
      }
      // The head. **Beside the road at the foot of the neck, and below it.** Both
      // the head and the neck hang off a body whose middle is already under the
      // deck, so as long as the head is under the deck too the neck between them
      // cannot cross the surface - which is what it did, as five blue slabs
      // standing through the tarmac. An animal at the bottom of its own neck has
      // its head turned anyway, so it sits on the bank and watches you leave.
      {
        const hi2 = HEAD_SPOT.i;
        const he = line[hi2];
        const q = HEAD_SPOT.p;
        const gy = floorAt(q[0], q[1]);
        const hc = [q[0], Math.min(gy + 6.2, he.p[1] - 1.6), q[1]];
        const na = axisOf(B1);
        for (let k = 0; k < 5; k++) {
          const t0 = k / 5, t1 = (k + 1) / 5;
          const m0 = [na.p[0] + (hc[0] - na.p[0]) * t0, na.p[1] + (hc[1] - na.p[1]) * t0,
                      na.p[2] + (hc[2] - na.p[2]) * t0];
          const m1 = [na.p[0] + (hc[0] - na.p[0]) * t1, na.p[1] + (hc[1] - na.p[1]) * t1,
                      na.p[2] + (hc[2] - na.p[2]) * t1];
          const dxz = [m1[0] - m0[0], m1[2] - m0[2]];
          const dl = Math.hypot(dxz[0], dxz[1]) || 1;
          const r = na.r * (1 - t0) * 0.7 + 1.9;
          bx([(m0[0] + m1[0]) / 2, (m0[1] + m1[1]) / 2, (m0[2] + m1[2]) / 2],
             [dxz[0] / dl, dxz[1] / dl],
             Math.hypot(m1[0] - m0[0], m1[1] - m0[1], m1[2] - m0[2]) * 0.55, r, r,
             shade(mix(hide, belly, 0.25), 0.02));
        }
        const gf = [(na.p[0] - hc[0]), (na.p[2] - hc[2])];
        const gl = Math.hypot(gf[0], gf[1]) || 1;
        const hfw = [-gf[0] / gl, -gf[1] / gl];
        bx(hc, hfw, 6.0, 4.1, 3.5, hide);
        const sn2 = [hc[0] + hfw[0] * 8.2, hc[1] - 1.2, hc[2] + hfw[1] * 8.2];
        bx(sn2, hfw, 3.5, 2.7, 2.3, shade(hide, 0.06));
        bx([sn2[0] + hfw[0] * 3.1, sn2[1] + 0.7, sn2[2] + hfw[1] * 3.1],
           hfw, 1.2, 2.0, 1.4, belly);
        for (const es of [-1, 1]) {
          const lx = -hfw[1] * es, lz = hfw[0] * es;
          bx([hc[0] + hfw[0] * 2.6 + lx * 3.8, hc[1] + 2.0, hc[2] + hfw[1] * 2.6 + lz * 3.8],
             hfw, 1.2, 0.8, 1.2, eyeC);
        }
      }
    }

    // --- the landmarks --------------------------------------------------------
    // Two more of them, a long way off the road, standing over the canopy.
    //
    // They are here for one reason: **the jungle is otherwise empty of anything
    // alive that you are not about to hit.** The herd is on the road because
    // that is what makes it an obstacle, and the big one is under the road
    // because that is what makes it a bridge - so from the driving seat the park
    // has dinosaurs in it only at the two moments they are in your way, and
    // between those it is trees. These are the ones that are simply *there*.
    //
    // Placed far enough out to be scenery and near enough to be inside the
    // drawn floor: past DRAW_REACH there is no ground under them, which is the
    // logged mistake of scenery standing on nothing past the plate's edge.
    // Their spots are found rather than written down - a walk outward from a
    // station until the ground is flat, dry and clear of the road.
    {
      const hide = C.hide != null ? C.hide : 0x3160cc;
      const belly = C.belly != null ? C.belly : 0xe4d6a8;
      const eyeC = C.eye != null ? C.eye : 0x141018;
      // A big sauropod standing on the floor, facing `yaw`. All boxes, because
      // at 200 units and through fog a silhouette is the whole of it.
      // A big sauropod standing on the floor, facing `yaw`. All boxes, because
      // at two hundred units and through fog a silhouette is the whole of it -
      // but **many small boxes rather than few long ones**, because `bx` orients
      // in yaw only and a neck built as five stretched boxes climbing to one
      // side is a staircase in the sky, which is exactly what the first pass
      // put over the trees.
      const sauropod = (px, pz, yaw, sc) => {
        const f = [Math.sin(yaw), Math.cos(yaw)];
        const gy = floorAt(px, pz);
        const legH = 13 * sc, bodyR = 6.5 * sc;
        const by = gy + legH + bodyR * 0.7;
        const skin = (t) => mix(hide, belly, t);
        bx([px, by, pz], f, 12 * sc, bodyR, bodyR * 0.95, skin(0.05));
        bx([px, by - bodyR * 0.72, pz], f, 10 * sc, bodyR * 0.8, bodyR * 0.35, skin(0.55));
        for (const a2 of [-1, 1]) for (const b2 of [-1, 1]) {
          const lx = px + f[0] * a2 * 7 * sc + (-f[1]) * b2 * bodyR * 0.72;
          const lz = pz + f[1] * a2 * 7 * sc + (f[0]) * b2 * bodyR * 0.72;
          const fy = floorAt(lx, lz);
          bx([lx, (fy + by - bodyR * 0.4) / 2, lz], f,
             1.9 * sc, 1.9 * sc, Math.max(1, (by - bodyR * 0.4 - fy) / 2), skin(0.2));
        }
        // A tapering tube along a path, as a run of small unstretched boxes -
        // fine enough that the steps are the creature's own scales.
        const limb = (x0, y0, z0, dx, dy, dz, steps, r0, r1, t0) => {
          for (let k = 0; k <= steps; k++) {
            const t = k / steps;
            const r = r0 + (r1 - r0) * t;
            bx([x0 + dx * t, y0 + dy * t, z0 + dz * t], f, r, r, r, skin(t0 + t * 0.18));
          }
        };
        // Neck: forward and up, then a head.
        const nx0 = px + f[0] * 11 * sc, nz0 = pz + f[1] * 11 * sc, ny0 = by + bodyR * 0.4;
        const NL = 26 * sc, NU = 26 * sc;
        limb(nx0, ny0, nz0, f[0] * NL, NU, f[1] * NL, 16, bodyR * 0.44, bodyR * 0.20, 0.10);
        const hx2 = nx0 + f[0] * NL, hz2 = nz0 + f[1] * NL, hy2 = ny0 + NU;
        bx([hx2 + f[0] * 2.4 * sc, hy2 + 0.9 * sc, hz2 + f[1] * 2.4 * sc],
           f, 2.6 * sc, 1.7 * sc, 1.5 * sc, skin(0.08));
        for (const es of [-1, 1]) {
          bx([hx2 + f[0] * 2.4 * sc + (-f[1]) * es * 1.5 * sc, hy2 + 1.6 * sc,
              hz2 + f[1] * 2.4 * sc + (f[0]) * es * 1.5 * sc],
             f, 0.6 * sc, 0.45 * sc, 0.6 * sc, eyeC);
        }
        // Tail: back and down.
        const tx0 = px - f[0] * 11 * sc, tz0 = pz - f[1] * 11 * sc;
        limb(tx0, by, tz0, -f[0] * 40 * sc, -(legH + bodyR * 0.3), -f[1] * 40 * sc,
             18, bodyR * 0.42, 0.5, 0.28);
      };
      // Somewhere out there worth standing: walk outward from a station until the
      // ground is flat, dry, well clear of the road and still inside the drawn
      // floor. Returns null rather than guessing if there is no such place.
      //
      // **`near` is what the far bank's seat uses.** The two in the jungle want
      // to be far - they are scenery, and a landmark you could reach is not one.
      // The third is in a photograph, and the crop is sixty-four units wide, so
      // it has to stand about thirty-six off the road or it is not in the shot.
      // That does put it where you can see it from the car, which the two far
      // ones deliberately are not: the trade is deliberate, and the place it
      // lands - the bank at the foot of the neck, where the big one already has
      // its head down - is the one spot on the track where a second animal
      // standing there is the scene rather than an intrusion into it.
      const clearing = (i, sign, near) => {
        const o0 = near ? 30 : 150, dsMin = near ? 28 : 110;
        for (let o = o0; o <= 300; o += 14) {
          const q2 = spot(i, sign * o);
          const c = cellOf(q2[0], q2[1]);
          const k = idx(c[0], c[1]);
          if (ds[k] > DRAW_REACH - 40 || ds[k] < dsMin) continue;
          if (WET[k] > 0.08) continue;
          const h0 = F[k], h1 = F[idx(c[0] + 3, c[1])], h2 = F[idx(c[0], c[1] + 3)];
          if (Math.abs(h1 - h0) > 9 || Math.abs(h2 - h0) > 9) continue;
          return q2;
        }
        return null;
      };
      // Two out in the empty jungle, and **one standing over the crossing**,
      // which is the one that is here for the picture. Every shot of this track
      // - the switcher card, the share card, the portal cover - is the animal's
      // back with a field of cars on it, and the animal's own head cannot be in
      // that shot: the road *is* its neck, so the head is at the foot of it, six
      // units off the floor, on a bank the canopy closes over. A landmark is the
      // only head on this track that stands above the leaves, so one of them
      // watches the crossing from the far side and gets into every picture the
      // game takes of the place.
      //
      // **The third one stands on the far bank, and where it stands is measured
      // off the frame rather than off the map.** Every picture this game takes
      // of Dino Park is the crossing at `pad=0.26`, which at `fov=50` is about
      // sixty-four units wide where the animal is: a landmark at the 150-to-300
      // the other two use cannot be in it at any azimuth, and the first three
      // attempts at this put one at 90, 150 and 200 units out and photographed
      // none of them. So this seat is pinned just past the end of the neck, on
      // the same side as the head's own glade and a little outside it - close
      // enough to be in the crop, on ground that is already cleared, and with
      // its head fifty units up where nothing grows.
      //
      // Two fallbacks behind it because the far bank is not guaranteed flat:
      // the other side, then a little further along the run-out.
      const seats = [[[Math.round(n * 0.10), OUT, false]],
                     [[Math.round(n * 0.62), -OUT, false]],
                     [[BRACH[1] + 12, HEAD_SPOT.side, true],
                      [BRACH[1] + 12, -HEAD_SPOT.side, true],
                      [BRACH[1] + 34, HEAD_SPOT.side, true]]];
      // Yaw and scale per seat, because the third one is doing a different job:
      // the two in the jungle are silhouettes and can be the smaller build, and
      // the one over the crossing is a hundred and fifty units past the subject
      // of every photograph of this track, so it gets the full size or it is a
      // speck. Facing roughly across the valley and not at the camera - three of
      // them pointing the same way reads as a display rather than as a place.
      const POSE = [[-1.1, 1.25], [2.4, 1.05], [3.6, 1.35]];
      for (let k = 0; k < seats.length; k++) {
        let q2 = null;
        for (const [si2, sg, near] of seats[k]) {
          q2 = clearing(clamp(si2, 0, n - 1), sg, near);
          if (q2) break;
        }
        if (!q2) continue;
        sauropod(q2[0], q2[1], POSE[k][0], POSE[k][1]);
      }
    }

    // --- the ranger station -------------------------------------------------
    // The one built thing in the park, on the descent below the falls, and the
    // only warm light in the scene. It stands on stilts because everything in a
    // jungle does, and its windows are `bright` - unlit geometry - so they read
    // as lit from inside rather than as yellow paint, which is what a lit
    // material at this hour would have given.
    //
    // Placed a fixed distance past the falls rather than at a fraction of the
    // lap: the falls are already derived, so measuring from them is one anchor
    // rather than two, and a re-cut layout moves the hut with the thing it is
    // meant to be below.
    {
      const si = clamp(LEDGE[1] + 74, 0, n - 1);
      const e = line[si], f = fwd(si);
      // Whichever side has room, by the same measure the canyon's side is picked.
      const sd = clearance(si, 44) >= clearance(si, -44) ? 1 : -1;
      const q = spot(si, sd * 30.0);
      const gy = floorAt(q[0], q[1]);
      const timber = 0x7a5334, timber2 = 0x5c3d26;
      const deckY = gy + 7.0;
      const HW = 11.0, HL = 8.0;
      // Stilts.
      for (const a of [-1, 1]) for (const b of [-1, 1]) {
        const px = q[0] + f[0] * a * (HL - 1.2) + (-f[1]) * b * (HW - 1.2);
        const pz = q[1] + f[1] * a * (HL - 1.2) + (f[0]) * b * (HW - 1.2);
        const fy = floorAt(px, pz);
        bx([px, (fy + deckY) / 2, pz], f, 0.7, 0.7, (deckY - fy) / 2, timber2);
      }
      bx([q[0], deckY, q[1]], f, HL, HW, 0.5, timber);                  // deck
      bx([q[0], deckY + 4.4, q[1]], f, HL - 1.6, HW - 1.6, 4.0, shade(timber, 0.08));
      // A hipped roof, as two slabs, with the eaves proud of the walls.
      bx([q[0], deckY + 9.0, q[1]], f, HL + 1.4, HW + 1.4, 0.55, timber2);
      bx([q[0], deckY + 10.2, q[1]], f, HL - 2.6, HW - 2.6, 0.8, timber2);
      // The windows, and the light in them.
      const lamp = pal.deco;
      for (const b of [-1, 1]) {
        const wx = q[0] + (-f[1]) * b * (HW - 1.5);
        const wz = q[1] + (f[0]) * b * (HW - 1.5);
        for (const a of [-0.5, 0.5]) {
          const cx = wx + f[0] * a * (HL - 2.0), cz = wz + f[1] * a * (HL - 2.0);
          const l = [-f[1], f[0]];
          const P = (sf, sv) => [cx + f[0] * sf * 2.6, deckY + 4.6 + sv * 1.7,
                                 cz + f[1] * sf * 2.6];
          bright.quad(P(-1, -1), P(1, -1), P(1, 1), P(-1, 1), lamp);
          bright.quad(P(-1, -1), P(-1, 1), P(1, 1), P(1, -1), lamp);
        }
      }
      // A lamp on a post at the road's edge, which is what actually puts the
      // park's own colour where you drive past it.
      const lp = spot(si, sd * (e.hw + 3.0));
      const ly = floorAt(lp[0], lp[1]);
      bx([lp[0], ly + 4.0, lp[1]], f, 0.35, 0.35, 4.0, timber2);
      bright.quad([lp[0] - 1.0, ly + 8.4, lp[1] - 1.0], [lp[0] + 1.0, ly + 8.4, lp[1] - 1.0],
                  [lp[0] + 1.0, ly + 8.4, lp[1] + 1.0], [lp[0] - 1.0, ly + 8.4, lp[1] + 1.0], lamp);
      bx([lp[0], ly + 9.0, lp[1]], f, 1.3, 1.3, 0.4, timber2);
    }

    // --- the understory ----------------------------------------------------
    // A second, much denser pass of low broad-leaf clumps. Without it the floor
    // between the trees is bare green and the place reads as parkland: a jungle
    // is a *floor* you cannot see, and this is the cheapest version of that.
    // Kept low enough to see the next corner over, and off the road by the same
    // `ds` the field already computed.
    const FERN_N = 3;
    for (let z = 1; z < nz - 1; z++) {
      for (let x = 1; x < nx - 1; x++) {
        const a = idx(x, z);
        if (ds[a] > FERN_REACH || ds[a] < 11 || WET[a] > 0.3) continue;
        const lo = Math.min(F[a], F[idx(x + 1, z)], F[idx(x, z + 1)]);
        const hi = Math.max(F[a], F[idx(x + 1, z)], F[idx(x, z + 1)]);
        if ((hi - lo) / CELLM > 0.8) continue;
        for (let q = 0; q < FERN_N; q++) {
          if (rnd() > 0.34) continue;
          const px = gx0 + x * CELLM + (rnd() - 0.5) * CELLM;
          const pz = gz0 + z * CELLM + (rnd() - 0.5) * CELLM;
          const by = floorAt(px, pz) - 0.2;
          const r = 1.5 + rnd() * 2.2, hh = 1.2 + rnd() * 1.8;
          const B = 4;
          const spin = rnd() * Math.PI * 2;
          const kf = rnd() < 0.5 ? leaf : leaf2;
          for (let bq = 0; bq < B; bq++) {
            const a2 = spin + bq / B * Math.PI * 2;
            const ox = -Math.sin(a2) * 0.55, oz = Math.cos(a2) * 0.55;
            face([px - ox, by, pz - oz], [px + ox, by, pz + oz],
                 [px + Math.cos(a2) * r + ox, by + hh, pz + Math.sin(a2) * r + oz],
                 [px + Math.cos(a2) * r - ox, by + hh, pz + Math.sin(a2) * r - oz],
                 shade(kf, (rnd() - 0.5) * 0.14));
          }
        }
      }
    }
  }
})();
