// Monza: the Sopraelevata, the Alps, and the Rettifilo escape-road barrier.
//
// **The banking is the reason this track exists.** The 1955 Pista di Alta
// Velocita - two 38-degree banked curves, raced on until 1969, abandoned since,
// and still standing in the park - crosses directly over the modern circuit. It
// makes Monza the fourth track in the pool with solid geometry over the road,
// after the Costco's roof, Monaco's tunnel and Rickety Rails' cave, and the only
// one where the thing overhead is a road nobody has driven in sixty years.
// **Nothing else in Drive is derelict**: the Costco is new, Monaco's city is
// lived in, Spa's grandstands are maintained. A ruin is new vocabulary, and it
// is most of what stops this being a third fast circuit with Spa's kit on it.
//
// **There were braking boards here and they are gone.** Four `200 / 150 / 100 /
// 50` boards stood before each pad's corner, found off the `bp` flag so they
// moved with the pads, and the argument for them was good: a pad that hands you
// speed into a braking zone is a corner you otherwise learn by failing, and
// nothing else in the game tells you how far the corner is. They were cut after
// Chinmay drove it, because they looked bad - which is the only test that
// matters for something whose whole job is to be read at a glance. Worth knowing
// if anyone tries this again: `signs.push({text, ...})` takes arbitrary text and
// the fallback board is a dark plate with a red border, so the mechanism is
// easy; it is the look that failed, not the plumbing.
//
// **Nothing here is in the collider except the chicane barrier.** The deck
// crosses 16 units over the road, the piers stand outside the armco at 44, and
// the Alps are 1300 units out - so there is nothing else a car can reach, and
// unreachable triangles would only cost `verify.py` time on every submitted
// lap. The cost is that `test_scenery.py` pins collider triangles per track, so
// a throw in the parts that add none would leave the suite green:
// `tools/validate_track.py` is what actually checks this file ran.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.monza = { props: props };

  // Weathered 1950s concrete. **Not `pal.prop2`** - that is the big pine's
  // foliage (see `palette.py`), which is exactly the mistake this track made
  // first. It is cooler and bluer than the asphalt it crosses, which is the one
  // colour fact the reference photograph of the real banking gave up.
  const CONCRETE = 0x8d9aa2;
  const CONCRETE_D = 0x6f7b84;   // the shaded underside and the retaining face
  const RUST = 0x7a4a32;         // the iron guardrail along the lip
  const SAPLING = 0x3f5c26;      // what grows out of a surface nobody sweeps

  // Where it crosses, as a fraction of the lap *by distance* - which is not the
  // same thing as `ctx.at`, and the difference is visible. `at` maps a fraction
  // onto the station **index**, and stations are not evenly spaced: a corner
  // lays them much closer together than a straight does. The first pass put the
  // crossing at `at(0.661)` and the render came back with the banking overhead
  // at 0.645 and gone by 0.661, roughly forty units from where it was asked
  // for. Everything here is placed off arc length instead.
  const CROSS_AT = 0.655;
  const CLEAR = 17.0;    // deck underside over the road. The camera rides ~4.3
                         // over the car and trails ~11.6 behind, so this is the
                         // Costco's 15 with room to spare, and the crossing is
                         // square on a straight for the same reason.
  const R = 200.0;       // the old curve's radius, near enough
  const SPAN = 0.80;     // radians each side of the crossing before it is lost
                         // in the wood - at fogFar 1150 the ends never resolve
  const W = 30.0;        // the banked surface, inner lip to outer lip
  // **How much the outer edge stands above the inner one, and the first pass
  // was half this.** At 12.5 over 26 units the surface is a 26-degree slope,
  // which from the road below reads as a flat bridge deck with a kink in it -
  // and a bridge is exactly what this must not look like. The real Sopraelevata
  // is banked at 38 degrees; 21 over 30 is 35, and the difference between the
  // two renders is the difference between a ruin and an overpass.
  const BANK = 21.0;
  const PIER = 46.0;     // piers this far off the road centre: outside the
                         // armco at 30, so nothing here is reachable

  function props(ctx) {
    const { solid, track, pal, terrain, groundY, shade, mulberry, KIND } = ctx;
    const col_ = ctx.col;
    const { at, face } = ctx;
    const line = track.line;
    const rnd = mulberry(20260911);

    const gY = (x, z) => (terrain ? terrain.height(x, z) : (groundY != null ? groundY : 0));
    const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
    const cross = (a, b) => [a[1] * b[2] - a[2] * b[1],
                             a[2] * b[0] - a[0] * b[2],
                             a[0] * b[1] - a[1] * b[0]];
    const norm = (v) => {
      const l = Math.hypot(v[0], v[1], v[2]) || 1;
      return [v[0] / l, v[1] / l, v[2] / l];
    };
    // The ribbon stores up and right; forward is what is left, and this is the
    // same expression `Builder._gate` uses so a gate and a prop agree.
    const fwdAt = (e) => norm(cross(e.n, e.lat));

    // Distance along the ribbon to every station, built once and used by both
    // halves of this file. Everything here is placed by arc length rather than
    // by station index, because stations bunch up in corners - see the note on
    // `CROSS_AT`.
    const SD = [0];
    for (let i = 1; i < line.length; i++) {
      SD.push(SD[i - 1] + Math.hypot(line[i].p[0] - line[i - 1].p[0],
                                     line[i].p[2] - line[i - 1].p[2]));
    }
    const totalLen = () => SD[SD.length - 1];
    const idxAtDist = (d) => {
      let lo = 0, hi = line.length - 1;
      while (lo < hi) { const m = (lo + hi) >> 1; if (SD[m] < d) lo = m + 1; else hi = m; }
      return lo;
    };

    banking();
    alps();
    chicaneWall();

    // ---- the Sopraelevata -------------------------------------------------
    function banking() {
      const i0 = idxAtDist(CROSS_AT * totalLen());
      const e0 = line[i0];
      const p0 = e0.p, f0 = fwdAt(e0);
      // Curve about a centre directly ahead of the road, so at the crossing the
      // banking runs across it rather than along it - which is what the two
      // roads actually do, and also the only arrangement where a fixed deck
      // height clears the whole width of the road.
      const cx = p0[0] + f0[0] * R, cz = p0[2] + f0[2] * R;
      const deckTop = p0[1] + CLEAR;

      // The point on the arc at angle t, and how far it is from the road's
      // centreline measured across the road (which is what decides whether it
      // needs a pier or a retaining wall under it).
      const arc = (t) => {
        // At t=0 this is the crossing point: the radius vector is -forward.
        const c = Math.cos(t), s = Math.sin(t);
        const dx = -f0[0] * c - (-f0[2]) * s;      // rotate -f0 by t about y
        const dz = -f0[2] * c + (-f0[0]) * s;
        return [cx + dx * R, cz + dz * R, dx, dz];
      };
      // How high the structure stands at t. Full height over the road, easing
      // down to the ground at both ends - a ruin running out into the trees.
      // Full height over the road and still most of its height well out into
      // the wood, so what you see on the approach is a wall of concrete rather
      // than a ramp. Only the last fifth comes down to the ground.
      const hAt = (t) => {
        const u = Math.min(1, Math.abs(t) / SPAN);
        return u < 0.62 ? 1 - 0.14 * (u / 0.62)
                        : 0.86 * (0.5 + 0.5 * Math.cos(Math.PI * (u - 0.62) / 0.38));
      };

      const N = 72;
      let prev = null;
      for (let k = 0; k <= N; k++) {
        const t = -SPAN + (2 * SPAN) * (k / N);
        const [ax, az, dx, dz] = arc(t);
        const inX = ax - dx * (W / 2), inZ = az - dz * (W / 2);
        const outX = ax + dx * (W / 2), outZ = az + dz * (W / 2);
        const g = hAt(t);
        // The ground under this slice, and the height the deck sits at.
        const base = gY(ax, az);
        const yIn = base + (deckTop - base) * g;
        const yOut = yIn + BANK * (0.35 + 0.65 * g);
        // How far this slice is from the road, along the road's own heading.
        const along = Math.abs((ax - p0[0]) * f0[0] + (az - p0[2]) * f0[2]);
        const cur = { inX, inZ, outX, outZ, yIn, yOut, base, along, g, t };
        if (prev) slice(prev, cur);
        prev = cur;
      }

      function slice(a, b) {
        // The banked surface itself.
        const col = shade(CONCRETE, (rnd() - 0.5) * 0.10);
        face([a.inX, a.yIn, a.inZ], [b.inX, b.yIn, b.inZ],
             [b.outX, b.yOut, b.outZ], [a.outX, a.yOut, a.outZ], col);
        // The outer retaining face, down to the ground. Where the structure is
        // over the road this is left open and carried on piers instead, which
        // is what makes it read as a viaduct rather than as a dam.
        const overRoad = a.along < PIER && b.along < PIER;
        if (!overRoad) {
          face([a.outX, a.yOut, a.outZ], [b.outX, b.yOut, b.outZ],
               [b.outX, b.base, b.outZ], [a.outX, a.base, a.outZ],
               shade(CONCRETE_D, (rnd() - 0.5) * 0.08));
          face([a.inX, a.yIn, a.inZ], [b.inX, b.yIn, b.inZ],
               [b.inX, b.base, b.inZ], [a.inX, a.base, a.inZ],
               shade(CONCRETE_D, (rnd() - 0.5) * 0.08));
        } else {
          // The underside of the deck, and **it is authored far lighter than it
          // should look**. This is Rickety Rails' lesson: the key light points
          // down, there are no shadow maps, and so the only thing lighting a
          // downward face is `hemi.ground` - which on this track is a
          // desaturated leaf green at 0.98. At `shade(CONCRETE_D, 0.16)` the
          // whole span came out near-black and read as a hole in the sky rather
          // than as the thing you are driving under. This is the face you
          // actually look at from the car, so it gets the lift.
          face([a.inX, a.yIn - 1.4, a.inZ], [b.inX, b.yIn - 1.4, b.inZ],
               [b.outX, b.yOut - 1.4, b.outZ], [a.outX, a.yOut - 1.4, a.outZ],
               shade(CONCRETE, 0.46));
          face([a.inX, a.yIn, a.inZ], [b.inX, b.yIn, b.inZ],
               [b.inX, a.yIn - 1.4, b.inZ], [a.inX, a.yIn - 1.4, a.inZ],
               shade(CONCRETE, 0.10));
          face([a.outX, a.yOut, a.outZ], [b.outX, b.yOut, b.outZ],
               [b.outX, b.yOut - 1.4, b.outZ], [a.outX, a.yOut - 1.4, a.outZ],
               shade(CONCRETE, 0.10));
        }
        // The guardrail along the lip: rusted iron on short posts, and the most
        // recognisable thing in any photograph of the abandoned banking.
        const postEvery = 3;
        if ((Math.round(a.t * 1000) % postEvery) === 0) {
          solid.box(a.outX, a.yOut + 0.55, a.outZ, 0.16, 0.55, 0.16, RUST);
        }
        face([a.outX, a.yOut + 0.95, a.outZ], [b.outX, b.yOut + 0.95, b.outZ],
             [b.outX, b.yOut + 0.62, b.outZ], [a.outX, a.yOut + 0.62, a.outZ],
             shade(RUST, (rnd() - 0.5) * 0.22));
        // What grows out of a surface nobody has swept since 1969. Only on the
        // low, shallow part - the top of a 38-degree bank sheds everything.
        if (a.g < 0.55 && rnd() < 0.30) {
          const u = 0.15 + rnd() * 0.5;
          const sx = a.inX + (a.outX - a.inX) * u;
          const sz = a.inZ + (a.outZ - a.inZ) * u;
          const sy = a.yIn + (a.yOut - a.yIn) * u;
          const h = 0.8 + rnd() * 1.8;
          solid.box(sx, sy + h * 0.5, sz, 0.12, h * 0.5, 0.12, 0x4c3a29);
          solid.box(sx, sy + h, sz, 0.55 + rnd() * 0.5, 0.45, 0.55 + rnd() * 0.5,
                    shade(SAPLING, (rnd() - 0.5) * 0.25));
        }
      }

      // The piers, and the first pass got these wrong in the way the render
      // makes obvious: four thin slabs standing in a row beside the road, which
      // read as menhirs rather than as a viaduct holding something up. Two
      // chunky columns a side now, set under the deck's own edges, tapering the
      // way a 1950s concrete pier does, and each one actually reaching the
      // ground under it rather than a height computed for somewhere else.
      for (const sgn of [-1, 1]) {
        const t = sgn * (PIER / R);
        const [ax, az, dx, dz] = arc(t);
        const g = hAt(t);
        const base = gY(ax, az);
        const yIn = base + (deckTop - base) * g;
        for (const u of [-0.34, 0.34]) {
          const px = ax + dx * W * u, pz = az + dz * W * u;
          const top = yIn + BANK * (0.35 + 0.65 * g) * (u + 0.5) - 1.5;
          const pb = gY(px, pz);
          if (top - pb < 2) continue;
          // A shaft, and a wider pad at the foot. Two boxes is the whole of it
          // and it is the difference between a column and a post.
          solid.box(px, (pb + top) / 2 + 0.8, pz, 2.2, (top - pb) / 2, 2.2,
                    shade(CONCRETE_D, 0.06));
          solid.box(px, pb + 1.1, pz, 3.4, 1.1, 3.4, shade(CONCRETE_D, -0.04));
        }
      }
    }

    // ---- the Alps ---------------------------------------------------------
    // A faint blue ridge on the horizon, which is what is behind the treeline in
    // the road-level reference of the real place. It is two jagged double-sided
    // walls and nothing more: at this distance the fog does almost all the work,
    // and anything with real geometry on it would be detail nobody can resolve.
    //
    // **Placed down the pit straight's own heading rather than to the north.**
    // The built world has no compass - the ribbon starts at the origin at yaw
    // zero, so the survey's bearings are gone by the time anything is drawn -
    // and the honest version of "where are the mountains" here is "where they
    // can be seen from", which is along the longest straight in the game.
    //
    // **Measured from the track's own centre, and clear of its own radius.**
    // The first pass put the near rank 820 units along that heading from
    // *station 0* - and station 0 is on the edge of the circuit, not in the
    // middle of it, so a range 3000 units wide was dropped through the middle of
    // the lap. At the Lesmos the car was a couple of hundred units from an
    // unfogged 150-unit wall and half the frame was black. The track reaches 676
    // units from its centre; the near rank stands at that plus CLEARANCE, so it
    // is outside the circuit wherever you are on it.
    function alps() {
      const e0 = line[0], f = fwdAt(e0), lat = e0.lat;
      let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
      for (const e of line) {
        if (e.p[0] < x0) x0 = e.p[0];
        if (e.p[0] > x1) x1 = e.p[0];
        if (e.p[2] < z0) z0 = e.p[2];
        if (e.p[2] > z1) z1 = e.p[2];
      }
      const mx = (x0 + x1) / 2, mz = (z0 + z1) / 2;
      let rad = 0;
      for (const e of line) {
        const d = Math.hypot(e.p[0] - mx, e.p[2] - mz);
        if (d > rad) rad = d;
      }
      const CLEARANCE = 620;          // past the far kerb, inside `fogFar` 1150
      const HALF = 2600;              // wide enough that the ends are off-frame
      const baseY = (groundY != null ? groundY : 0) - 8;
      // Two ranks. The far one is taller, paler and pushed further out, which is
      // the cheapest thing that reads as depth rather than as a cut-out.
      for (const [push, lo, hi, col] of [[430, 86, 168, 0x8398b0],
                                         [0,   52, 104, 0x6f8498]]) {
        const d = rad + CLEARANCE + push;
        const ox = mx + f[0] * d, oz = mz + f[2] * d;
        const N = 72;
        let prev = null;
        for (let k = 0; k <= N; k++) {
          const u = k / N;
          const off = (u - 0.5) * 2 * HALF;
          const x = ox + lat[0] * off, z = oz + lat[2] * off;
          // Sum of a few waves, so the skyline has both big peaks and the
          // shoulders between them rather than one repeating tooth.
          const w = Math.sin(u * 21.7) * 0.5 + Math.sin(u * 9.1 + 1.3) * 0.32
                  + Math.sin(u * 47.3 + 2.7) * 0.18;
          const h = lo + (hi - lo) * (0.5 + 0.5 * w);
          const cur = [x, z, baseY + h];
          if (prev) {
            face([prev[0], baseY, prev[1]], [cur[0], baseY, cur[1]],
                 [cur[0], cur[2], cur[1]], [prev[0], prev[2], prev[1]],
                 shade(col, (((k * 37) % 11) / 11 - 0.5) * 0.12));
          }
          prev = cur;
        }
      }
    }

    // ---- the barriers at the three chicanes -------------------------------
    // **Every chicane, found rather than listed.** A chicane here is a maximal
    // run of real corner (radius under 75) that contains a *sign change* - which
    // is precisely the three Variantes and nothing else on the lap. It does not
    // catch Lesmo 1 (isolated, no flip), Lesmo 2 (two arcs the same way), the
    // Parabolica (same way again) or Curva Grande and the Serraglio (both too
    // gentle to be corners by this measure). So there is no list of lap
    // fractions to fall out of step with a re-solved ribbon.
    //
    // **Both kerbs, continuously, through every chicane.** No side changes and
    // no gap: a chicane you can only run off the outside of is half a chicane.
    //
    // The inside wall of a tight element is a tight arc - on the radius-19
    // Rettifilo the road's inside edge is already at radius 12.5 and the wall
    // sits at 10.6 - so it wraps hard round the apex and from the car it reads
    // as a mound. **An earlier pass called that a blocked corner and it was
    // wrong.** The offset is `hw + GAP`, and `hw` is the road's own half-width,
    // so the wall is beyond the road edge at every station by construction; the
    // measured worst case across all three chicanes is **+1.30 units** of
    // clearance, so the racing line cannot reach it. A render says how something
    // looks, not whether the car fits - that one takes offsetting the stations
    // and measuring, and it should have been done before the claim.
    //
    // **The escape road's wall is on the Rettifilo only.** It carries straight on
    // along the entry tangent while the road turns away, which is the line a car
    // that missed its braking point takes. The Roggia and Ascari get gravel
    // instead, which is what they have.
    //
    // Neither is a shortcut fix: `tools/cut_check.py` reports no open chord on
    // this lap with or without them - the backstop at 30 already blocks every
    // one. They are here because the corners looked bare.
    //
    // All of it is `addArmco`'s construction, because the first pass invented a
    // wall of red and white blocks and it read as a painted kerb stood on end: a
    // `pal.rail` face at the pool's own 1.7 with a dark plinth 0.55 under it, and
    // in the collider the same way.
    function chicaneWall() {
      const CORNER = 1 / 75;     // radius under 75 is a corner here
      const H = 1.7, PLINTH = 0.55, GAP = 1.9;
      const rail = pal.rail != null ? pal.rail : 0xc3c7bd;

      const seg = (p, q) => {
        const pt = [p[0], p[1] + H, p[2]], qt = [q[0], q[1] + H, q[2]];
        face(p, q, qt, pt, rail);
        face([p[0], p[1], p[2]], [q[0], q[1], q[2]],
             [q[0], q[1] - PLINTH, q[2]], [p[0], p[1] - PLINTH, p[2]],
             shade(rail, -0.55));
        col_.addQuad(p, q, qt, pt, KIND.WALL);
        col_.addQuad(p, pt, qt, q, KIND.WALL);
      };

      // Every run of corner, bridging up to six slack stations - which is where
      // one element of a chicane hands over to the next and the curvature passes
      // through zero. Without the bridge each element is its own run and no run
      // ever contains a sign change, so nothing is a chicane.
      const runs = [];
      let start = -1, last = -1, slack = 0;
      for (let i = 0; i < line.length; i++) {
        if (Math.abs(line[i].curv || 0) >= CORNER) {
          if (start < 0) start = i;
          last = i; slack = 0;
        } else if (start >= 0 && ++slack > 6) {
          runs.push([start, last]);
          start = -1; slack = 0;
        }
      }
      if (start >= 0) runs.push([start, last]);

      // A chicane is a run that changes direction inside itself.
      const chicanes = runs.filter(([p, q]) => {
        let pos = false, neg = false;
        for (let i = p; i <= q; i++) {
          const k = line[i].curv || 0;
          if (Math.abs(k) < CORNER) continue;
          if (k > 0) pos = true; else neg = true;
        }
        return pos && neg;
      });

      chicanes.forEach(([a0, b0], n) => {
        // **Both kerbs, continuously, from the braking zone to the exit.** The
        // barrier does not change sides and there is no gap at the flip: a
        // chicane you can only run off the outside of is half a chicane, and
        // what this corner wants is a walled corridor.
        //
        // The inside wall of a tight element is a tight arc - on the Rettifilo
        // the road's inside edge is already at radius 12.5 and the wall sits at
        // 10.6 - so it wraps hard round the apex. That is what a barrier on the
        // inside kerb of a first-gear chicane actually looks like, and it is
        // *outside* the road at every station by construction: the offset is
        // `hw + GAP`, and `hw` is the road's own half-width, so the racing line
        // cannot reach it. `tools/chicane_clearance` in this folder's notes is
        // the check - see `track.py`.
        const i0 = Math.max(0, a0 - 10);
        const i1 = Math.min(line.length - 1, b0 + 8);
        for (const side of [-1, 1]) {
          let prevP = null;
          for (let i = i0; i <= i1; i++) {
            const e = line[i];
            const o = side * (e.hw + GAP);
            const x = e.p[0] + e.lat[0] * o, z = e.p[2] + e.lat[2] * o;
            // Another part of the circuit closer than our own offset means
            // there is no room - the guard `addArmco` uses.
            if (terrain && terrain.toRoad(x, z) < e.hw - 0.5) { prevP = null; continue; }
            const cur = [x, e.p[1] - 0.2, z];
            if (prevP) seg(prevP, cur);
            prevP = cur;
          }
        }

        // The escape road, at the first chicane only.
        if (n !== 0) return;
        const turn = (line[a0].curv || 0) > 0 ? 1 : -1;
        const eS = line[Math.max(0, a0 - 7)];
        const f = fwdAt(eS);
        const sx = eS.p[0] + eS.lat[0] * -turn * (eS.hw + GAP);
        const sz = eS.p[2] + eS.lat[2] * -turn * (eS.hw + GAP);
        const y = eS.p[1] - 0.2;
        let prev = null;
        for (let d = 0; d <= 96.0; d += 4.0) {
          const x = sx + f[0] * d, z = sz + f[2] * d;
          if (terrain && terrain.toRoad(x, z) < eS.hw + 1.0) break;
          const cur = [x, y, z];
          if (prev) seg(prev, cur);
          prev = cur;
        }
      });
    }
  }
})();