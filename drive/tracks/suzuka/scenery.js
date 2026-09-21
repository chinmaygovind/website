// Suzuka: the crossover bridge, the wall across the Casio Triangle, and the
// Ferris wheel.
//
// Everything else this circuit stands up - the grandstands, the pit building,
// the start gantry, the hoardings, the armco, the blossom - is `trackmesh.js`
// drawing off the ribbon with the rest of the terrain kit, configured in
// `palette.py`. This file is the three things that kit cannot say.
//
// **The bridge is the only one of the three that had to exist.** Suzuka is a
// figure-eight: the back straight crosses over the run down from Degner, and
// `tracks/checks.py` already guarantees the twelve units of air between them.
// But air is all it guarantees - without something built in the gap the upper
// road is a ribbon hanging over a field, and from underneath you drive beneath
// a floating strip of tarmac. What is added here is what makes it read as a
// bridge: two bents standing either side of the crossing, a soffit under the
// deck between them, and a parapet along both edges.
//
// **None of the bridge is in the collider except the parapet.** The bents stand
// well clear of both roads - they are placed off the *upper* ribbon at
// fractions either side of the crossing, where the ground beneath is open
// infield rather than the lower road - so a car cannot reach them, and a
// collider quad a car cannot reach is triangles nobody drives into. The parapet
// is different: it is at the edge of a road twelve units in the air, and the
// one place on this circuit where going off is a fall rather than a trip into
// the gravel. It cannot be a ribbon `rail` - `test_barriers_are_opt_in` allows
// a ground-level track no walled stations at all - so it is collider geometry
// standing beside the road, which is Spa's answer and the Costco's parapet.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.suzuka = { props: props };

  // trackmesh's own `GRASS_DROP`: how far the swept run-off sits under the
  // tarmac. Inside the apron the ground is the road's height less this, and
  // sampling `terrain.height` instead is what makes a barrier zigzag wherever
  // the circuit folds back on itself.
  const DROP = 1.2;
  const BAR_H = DROP + 1.6;          // 1.6 above the road, the armco's height

  // Where the ribbon crosses itself, as fractions of the lap. Fractions and not
  // station indices for the reason the furniture uses them: the ribbon is
  // re-solved for closure on every import and that changes how many stations
  // there are. `OVER` is the back straight, `UNDER` is the run out of Degner.
  const OVER = 0.809;
  const UNDER = 0.358;
  // How far either side of the crossing the bridge runs, as a fraction of the
  // lap. **This has to match where the height field stops**, not just look
  // right: `buildTerrain` drops every station with road underneath it and then
  // grows that set by `apron + 8` along the ribbon, which here is about 62
  // units either side of the crossing - so that is exactly the stretch with no
  // ground, no run-off and no armco under it, and exactly the stretch that
  // needs a deck and a parapet instead. Shorter and there is a length of road
  // with neither; longer and the parapet runs on past the abutment into road
  // that has ordinary run-off beside it.
  const SPAN = 0.018;

  function props(ctx) {
    const { solid, col, track, pal, terrain, KIND, shade, mulberry,
            bbox, minY } = ctx;
    const line = track.line, n = line.length;
    if (!terrain) return;            // this track always has one; be honest anyway
    const APRON = (pal.terrain && pal.terrain.apron != null) ? pal.terrain.apron : 34;

    // Both faces on everything: the world mesh is `MeshLambertMaterial`, which
    // is `FrontSide`, and geometry placed by a signed side has its winding
    // reversed when that sign flips.
    const face = (a, b, c, d, colr) => {
      solid.quad(a, b, c, d, colr);
      solid.quad(a, d, c, b, colr);
    };
    const at = (f) => Math.max(0, Math.min(n - 1, Math.round(f * (n - 1))));
    const spot = (i, o) => {
      const e = line[i];
      return [e.p[0] + e.lat[0] * o, e.p[2] + e.lat[2] * o];
    };
    const ground = (i, o) => (Math.abs(o) <= APRON
      ? line[i].p[1] - DROP : terrain.height.apply(null, spot(i, o)));

    const railC = pal.rail != null ? pal.rail : 0xd6dbe0;
    const conc = (pal.furniture && pal.furniture.concrete != null)
      ? pal.furniture.concrete : 0xb9b6ae;

    // ---- a wall beside the road, collided ---------------------------------
    // Silverstone's `insideBarrier` with the side told rather than read off the
    // curvature, which is Spa's version of it. Told, because the Casio Triangle
    // changes direction twice inside the span being walled and the "inside" of
    // the cut is one side of the road for all of it.
    const wall = (f0, f1, side, gap, h, colr) => {
      let prev = null;
      for (let i = at(f0); i <= at(f1); i++) {
        const e = line[i];
        const o = (e.hw + gap) * side;
        const [x, z] = spot(i, o);
        const p = [x, ground(i, o), z];
        const q = prev;
        prev = p;
        if (!q) continue;
        const up = (v) => [v[0], v[1] + h, v[2]];
        face(q, p, up(p), up(q), colr);
        col.addQuad(q, p, up(p), up(q), KIND.WALL);
        const dn = (v) => [v[0], v[1] - 0.55, v[2]];
        face(dn(q), dn(p), p, q, shade(colr, -0.35));
      }
    };

    // ---- the corners you could otherwise leave out --------------------------
    // All three were found with `tools/cut_check.py`, which walks every chord
    // across the infield and reports the ones that pay - a chord pays when the
    // road it skips is over twice its own length, and grass is about half road
    // speed. Two of them Chinmay found first by driving, which is the reminder
    // that the tool scores chords and a driver scores corners.
    //
    // **The hairpin**, and it is Spa's La Source exactly: 175 degrees on a 22
    // radius, so the entry and the exit run about forty units apart and the
    // quick line ignores the corner and crosses straight between them. 56 units
    // of chord against 175 units of road, 3.1x, and it skips no checkpoint. The
    // backstop armco cannot close it - that sits 26 units out past the gravel
    // and the cut runs inside it, which is the armco doing its job rather than
    // failing at this one. It starts just past the gate before it, so a car
    // that leaves the road earlier has already missed that gate.
    wall(0.413, 0.471, -1, 4.5, BAR_H, railC);

    // **Both of these are on the road's left, and the side is not eyeballable.**
    // Reading it off `lat` at the chord's start says "the exit is to the right"
    // for Spoon and is simply wrong: through 205 degrees the station frame
    // rotates faster than the chord moves, so a per-station lateral offset
    // swings from one sign to the other while the chord sits still in the
    // world. The only test that answers it is a real segment-segment crossing
    // between the chord and the wall's own polyline, in world coordinates, and
    // the same test is what says how far the wall has to run: the first spans
    // tried here were both a few hundredths short and blocked nothing at all.
    //
    // **Spoon**, which is the same shape and worse: 181 units of chord against
    // 458 units of road, 4.8x, and the biggest open cut on the circuit. Nobody
    // spotted this one from the seat - the road it skips is most of a corner
    // you cannot see the far side of - which is the case for running the tool
    // even when the track feels right.
    wall(0.578, 0.722, -1, 4.5, BAR_H, railC);

    // **The run down from 130R to the chicane**, where the circuit comes back
    // alongside the Degner descent: 22 units apart in plan with the older road
    // seven above, which is a car trap rather than a shortcut - the ground
    // probe has no good answer for which surface you are on. `addArmco` already
    // declines to build here, because it skips any segment whose post is nearer
    // some other part of the track than its own offset, so the gap this closes
    // is one the automatic barrier deliberately leaves.
    wall(0.838, 0.897, 1, 4.5, BAR_H, railC);

    // ---- the Casio Triangle ------------------------------------------------
    // The chicane doubles back on itself: entry and exit run about thirty units
    // apart and the quick way through is to ignore both corners and drive
    // straight between them. The backstop armco cannot close that - it is 26
    // units out past the gravel and the cut runs inside it - which is the armco
    // doing its job, catching a car before it reaches the trees rather than
    // stopping it cutting. The real circuit has a wall in exactly this gap.
    wall(0.856, 0.896, 1, 4.5, BAR_H, railC);

    // ---- the crossover bridge ----------------------------------------------
    // The parapet, on both edges of the upper road, and the only part of the
    // bridge a car can touch. Slightly taller than the armco because it is the
    // lip of a twelve-unit drop and has to read as one from the seat.
    for (const s of [-1, 1]) wall(OVER - SPAN, OVER + SPAN, s, 0.5, DROP + 2.3, conc);

    // The soffit: a flat underside swept along the deck, so from the road below
    // you drive under a bridge rather than under a floating strip of tarmac.
    // Not collided - it is directly under the road's own surface, which already
    // is, and a second quad there is a surface the ground probe could pick.
    {
      const i0 = at(OVER - SPAN), i1 = at(OVER + SPAN);
      let prev = null;
      for (let i = i0; i <= i1; i++) {
        const e = line[i], w = e.hw + 1.6;
        const [lx, lz] = spot(i, -w), [rx, rz] = spot(i, w);
        const y = e.p[1] - 1.5;
        const cur = [[lx, y, lz], [rx, y, rz]];
        if (prev) {
          face(prev[0], prev[1], cur[1], cur[0], shade(conc, -0.18));
          // and a fascia down each side, so the deck has a thickness
          for (const k of [0, 1]) {
            const a = prev[k], b = cur[k];
            face([a[0], a[1] + 1.5, a[2]], [b[0], b[1] + 1.5, b[2]], b, a,
                 shade(conc, -0.06));
          }
        }
        prev = cur;
      }
    }

    // The two bents. Placed off the upper ribbon just outside the span, where
    // the ground below is open infield - never off the *lower* road, which is
    // what would stand a pier in the middle of the track you drive under.
    for (const f of [OVER - SPAN, OVER + SPAN]) {
      const i = at(f), e = line[i];
      for (const s of [-1, 1]) {
        const o = (e.hw + 1.2) * s;
        const [x, z] = spot(i, o);
        const g = terrain.height(x, z);
        const top = e.p[1] - 1.5;
        if (top - g < 2) continue;              // nothing to stand on
        solid.box(x, (g + top) / 2, z, 1.5, (top - g) / 2, 1.5, conc);
      }
      // a cross-beam under the deck so the pair reads as one trestle
      const [ax, az] = spot(i, -(e.hw + 1.2)), [bx, bz] = spot(i, e.hw + 1.2);
      solid.box((ax + bx) / 2, e.p[1] - 2.6, (az + bz) / 2,
                Math.abs(bx - ax) / 2 + 1.5, 0.8, Math.abs(bz - az) / 2 + 1.5,
                shade(conc, -0.12));
    }

    // ---- the horizon: a skirt, and the Suzuka mountains ----------------------
    // **The ground used to stop.** `drawTerrain` covers the circuit's bounding
    // box plus ten cells of padding and nothing beyond it, so down the longest
    // straights the world ended at a hard green edge with sky under it. That is
    // most of what "the background is boring" actually was - not the sky's
    // colour but the fact that there was nothing between the last tree and the
    // dome.
    //
    // So: a skirt out to twice the circuit, and three ranks of ridges standing
    // on it. Suzuka is a circuit under the Suzuka mountains and they are in
    // every photograph of the place, which is the other half of why this is
    // here rather than a taller tree count.
    //
    // Nothing is collided and nothing is lit specially. The ranks are drawn
    // paler and bluer with distance and then the scene's own fog finishes the
    // job - `fogFar` is 1500, so the far rank is mostly haze, which is what
    // makes three ranks read as depth instead of as three fences.
    {
      const cx0 = (bbox.x0 + bbox.x1) / 2, cz0 = (bbox.z0 + bbox.z1) / 2;
      const reach = Math.max(bbox.x1 - bbox.x0, bbox.z1 - bbox.z0) / 2;
      const baseY = minY - 6;
      // The skirt. Drawn as a ring rather than one huge quad so it can sit just
      // under the terrain's own edge without z-fighting it across the middle.
      const RING = 64, inner = reach + 40, outer = reach * 3.2;
      for (let k = 0; k < RING; k++) {
        const a = (k / RING) * Math.PI * 2, b = ((k + 1) / RING) * Math.PI * 2;
        const P = (ang, r, y) => [cx0 + Math.cos(ang) * r, y, cz0 + Math.sin(ang) * r];
        face(P(a, inner, baseY), P(b, inner, baseY),
             P(b, outer, baseY), P(a, outer, baseY),
             shade(pal.ground != null ? pal.ground : 0x5c8042, -0.10));
      }
      // Three ranks of ridges. Each is a silhouette: one quad per segment from
      // the skirt up to a peak, so the only thing that reads is the top line.
      const ranks = [
        { r: reach * 1.35, h: 86,  n: 46, col: 0x5f7a63, seed: 0x1a7d },
        { r: reach * 1.95, h: 132, n: 38, col: 0x7d93a8, seed: 0x2b3c },
        { r: reach * 2.60, h: 186, n: 30, col: 0x9fb2c4, seed: 0x5e91 },
      ];
      for (const rk of ranks) {
        const rn = mulberry(rk.seed);
        const hs = [];
        for (let k = 0; k < rk.n; k++) hs.push(0.42 + rn() * 0.58);
        for (let k = 0; k < rk.n; k++) {
          const a = (k / rk.n) * Math.PI * 2, b = ((k + 1) / rk.n) * Math.PI * 2;
          const ha = baseY + rk.h * hs[k], hb = baseY + rk.h * hs[(k + 1) % rk.n];
          const A = [cx0 + Math.cos(a) * rk.r, baseY, cz0 + Math.sin(a) * rk.r];
          const B = [cx0 + Math.cos(b) * rk.r, baseY, cz0 + Math.sin(b) * rk.r];
          face(A, B, [B[0], hb, B[2]], [A[0], ha, A[2]], rk.col);
        }
      }
    }

    // ---- the paddock, behind the pits ---------------------------------------
    // The opening stretch was the blandest part of the lap: pit building on one
    // side, grandstand on the other, and then flat green for two hundred units
    // in every direction. A real circuit's start/finish is the most built-up
    // place on the site, so this is what stands behind the pit wall - a row of
    // team buildings, a rank of hospitality marquees and acar park.
    //
    // **Everything here is placed by `toRoad` rather than by eye.** The field
    // returns the distance to the *nearest* road centre, so at a point `o` out
    // from our own road it reads back `o` exactly when we are the nearest thing
    // and less when some other leg is - which is the same test `addApron` uses
    // to clip the run-off, and it is what stops a hospitality unit being built
    // on the exit of the last corner. Nothing is collided: it all stands beyond
    // the armco, where a car cannot reach it.
    {
      const rnd = mulberry(0x51ce17);
      // An oriented box. `solid.box` is axis-aligned, so anything built with it
      // beside a road that is not axis-aligned comes out as its own bounding
      // volume - the same trap the Ferris wheel's spokes fell into. Six quads
      // off the road's own frame instead.
      const slab = (i, off, along, w, h, d, colr) => {
        const e = line[i];
        const f = [e.lat[2], 0, -e.lat[0]];
        const [x, z] = spot(i, off);
        const cx2 = x + f[0] * along, cz2 = z + f[2] * along;
        if (terrain.toRoad(cx2, cz2) < Math.abs(off) - 6) return false;
        const g = terrain.height(cx2, cz2);
        const P = (sw, sh, sd) => [cx2 + e.lat[0] * sw * w + f[0] * sd * d,
                                   g + sh * h,
                                   cz2 + e.lat[2] * sw * w + f[2] * sd * d];
        const c = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
        for (let k = 0; k < 4; k++) {           // four walls
          const a = c[k], b = c[(k + 1) % 4];
          face(P(a[0], 0, a[1]), P(b[0], 0, b[1]),
               P(b[0], 2, b[1]), P(a[0], 2, a[1]), colr);
        }
        face(P(-1, 2, -1), P(1, 2, -1), P(1, 2, 1), P(-1, 2, 1),
             shade(colr, 0.12));               // roof
        return true;
      };
      // Team buildings down the back of the pit lane, and a taller one at the
      // end of the row so the skyline is not a single flat ridge.
      for (let k = 0; k < 7; k++) {
        const i = at(0.006 + k * 0.0092);
        slab(i, 62, 0, 9, 4.2 + (k === 6 ? 3.4 : 0), 17,
             k % 2 ? 0xdfe3e6 : 0xcdd3d8);
      }
      // Hospitality marquees, smaller and set further back.
      for (let k = 0; k < 9; k++) {
        const i = at(0.004 + k * 0.0076);
        slab(i, 92 + (k % 2) * 9, 0, 5.5, 3.0, 6.5,
             k % 3 === 0 ? 0xf2f4f5 : (k % 3 === 1 ? 0xe6dfe8 : 0xdfe8e2));
      }
      // The car park: rows of parked cars, which is most of what makes a
      // paddock read as busy rather than as a shed.
      for (let row = 0; row < 5; row++) {
        for (let k = 0; k < 13; k++) {
          const i = at(0.010 + k * 0.0042);
          const col = [0xb03a32, 0x2f4f7a, 0xdfe1e3, 0x3c3f45, 0x6f7a53,
                       0xc8a63a][Math.floor(rnd() * 6) % 6];
          slab(i, 118 + row * 7, 0, 1.6, 0.85, 3.2, col);
        }
      }
    }

    // ---- the Ferris wheel --------------------------------------------------
    // Suzuka is a circuit inside an amusement park and the wheel is the thing
    // everybody photographs it past, so it is placed to be *seen* rather than
    // to be near anything: outside the S Curves, far enough back that it clears
    // the trees, and tall enough to stand over them from the far side of the
    // lap. That is also why `density` in the palette is the lowest of any
    // wooded track here - a 0.34 pine forest would hide it completely.
    //
    // Nothing about it is collided. It is 120 units off the road with a wood in
    // between, so a car cannot reach it, and collider quads a car cannot reach
    // are triangles that only ever cost the anti-cheat time.
    {
      const i = at(0.185);
      const R = 36, legH = 16;
      const [cx, cz] = spot(i, -120);
      const baseY = terrain.height(cx, cz);
      // **Which way it faces is the whole of whether it reads as a wheel.**
      // Edge-on it is a vertical line and reads as a pylon, and the first
      // version aimed it along the S Curves' own forward direction on the
      // reasoning that it should face the circuit there. That was wrong about
      // *where it is looked at from*: at the esses the camera is beside it and
      // pointing along the road, so it is out of frame - and from the back
      // straight, which is 480 units of full throttle pointed straight at it
      // and the longest look anybody gets, it was exactly edge-on. A sliver.
      //
      // So it is aimed at the back straight instead: the face normal is the
      // horizontal bearing from the wheel to a station half way down it, and
      // the wheel is built in the plane perpendicular to that. From the esses
      // it is then three-quarters on, which is the better of the two to lose.
      const vp = line[at(0.74)].p;
      let nx = vp[0] - cx, nz = vp[2] - cz;
      const nl = Math.hypot(nx, nz) || 1;
      nx /= nl; nz /= nl;
      const f = [nz, 0, -nx];                 // across the face, in plan
      const hubY = baseY + legH + R;
      const rim = (a) => [cx + f[0] * Math.cos(a) * R, hubY + Math.sin(a) * R,
                          cz + f[2] * Math.cos(a) * R];
      const STEEL = 0xe9eef2;
      // **A member is a run of small boxes, never one box from end to end.**
      // `solid.box` is axis-aligned, so a box asked to span a diagonal comes out
      // as that diagonal's whole bounding volume - a spoke at 45 degrees became
      // a 25-unit slab, and twelve of them made the wheel a pile of grey
      // monoliths that ate the entire cover shot. It is the axis-aligned note in
      // `docs/track-defects.md`, met on a structure that is nothing but
      // diagonals. Stepping along the segment costs boxes and is the only thing
      // here that draws a strut rather than a block.
      const strut = (a, b, r, colr) => {
        const dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
        const n = Math.max(1, Math.ceil(Math.hypot(dx, dy, dz) / (r * 2.6)));
        for (let k = 0; k <= n; k++) {
          const t = k / n;
          solid.box(a[0] + dx * t, a[1] + dy * t, a[2] + dz * t, r, r, r, colr);
        }
      };
      const SEG = 48;
      for (let k = 0; k < SEG; k++) {
        strut(rim((k / SEG) * Math.PI * 2), rim(((k + 1) / SEG) * Math.PI * 2),
              0.55, STEEL);
      }
      // spokes and hub
      const hub = [cx, hubY, cz];
      for (let k = 0; k < 12; k++) {
        strut(hub, rim((k / 12) * Math.PI * 2), 0.42, shade(STEEL, -0.1));
      }
      solid.box(cx, hubY, cz, 2.0, 2.0, 2.0, shade(STEEL, -0.25));
      // the gondolas, one per spoke, hanging under the rim. Coloured off the
      // palette's `deco` and `kerb2` so the wheel belongs to this track's
      // scheme rather than being a second palette nobody declared.
      const rnd = mulberry(0x5a2c17);
      const pods = [pal.deco != null ? pal.deco : 0xe8b93c,
                    pal.kerb2 != null ? pal.kerb2 : 0xc9372f,
                    pal.prop != null ? pal.prop : 0xdba8bc, STEEL];
      for (let k = 0; k < 12; k++) {
        const a = (k / 12) * Math.PI * 2, p = rim(a);
        solid.box(p[0], p[1] - 2.6, p[2], 1.5, 1.3, 1.5,
                  pods[Math.floor(rnd() * pods.length) % pods.length]);
      }
      // two A-frames carrying the hub - struts for the same reason as the spokes
      for (const sgn of [-1, 1]) {
        for (const t of [-1, 1]) {
          const fx = cx + f[0] * sgn * R * 0.55 + nx * t * 5;
          const fz = cz + f[2] * sgn * R * 0.55 + nz * t * 5;
          strut([fx, terrain.height(fx, fz), fz], hub, 0.75, shade(STEEL, -0.18));
        }
      }
    }
  }
})();
