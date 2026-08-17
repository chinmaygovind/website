// Silverstone: the airfield it was, and the two barriers the layout needs.
//
// Four things, and only the last one is load-bearing for how the track drives:
//
//  * **the three runways** of RAF Silverstone, which are the reason this place
//    exists. Wikipedia is explicit that the airfield's three runways, in classic
//    WWII triangle format, lie *within the outline of the present track* - so the
//    infield gets them back, as cracked concrete crossing the grass. It is a few
//    hundred flat quads and it is the highest-value thing here: a ground track's
//    plate is one colour and half of every frame, and `docs/track-defects.md` is
//    blunt about it - *the floor is dead*, and anything laid on it buys more than
//    the same effort spent on things standing up;
//  * **the two hangars** beside the Hangar Straight, which is named after them;
//  * **the Wing's roof** over the pit garages, because `addFurniture`'s `pits`
//    draws exactly one shape and that shape is Spa's row of low sheds;
//  * **a barrier on the inside of the arena and of Luffield**, which is the only
//    part of this file the stopwatch can see. See `insideBarrier`.
//
// Everything here is derived from the ribbon. Nothing carries a literal world
// coordinate, because anything that does is a thing that will be wrong after the
// next layout change - and this layout gets re-solved for closure on every import.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.silverstone = { props: props };

  // How far the run-off sits under the tarmac. The same `GRASS_DROP` trackmesh
  // uses; inside the apron the ground is the road's own height less this, and
  // sampling `terrain.height` there instead is what makes a barrier zigzag
  // between two legs wherever the circuit folds back on itself.
  const DROP = 1.2;

  function props(ctx) {
    const { solid, bright, col, track, pal, bbox, CELL, terrain } = ctx;
    const { KIND, shade, mulberry } = ctx;
    const line = track.line, n = line.length;
    if (!terrain) return;              // this track always has one; be honest anyway
    const cfg = pal.terrain || {};
    const APRON = cfg.apron != null ? cfg.apron : 34;

    // Both faces on everything. The world mesh is `MeshLambertMaterial`, which is
    // `FrontSide`, and anything here placed by a signed side has its winding
    // reversed when that sign flips - which is how Spa's pit building spent an
    // afternoon as an invisible shed with a roof floating in the sky.
    const face = (a, b, c, d, colr) => {
      solid.quad(a, b, c, d, colr);
      solid.quad(a, d, c, b, colr);
    };
    // Distance along the lap, so a fraction can be turned into a station.
    const at = (f) => Math.max(0, Math.min(n - 1, Math.round(f * (n - 1))));
    const spot = (i, o) => {
      const e = line[i];
      return [e.p[0] + e.lat[0] * o, e.p[2] + e.lat[2] * o];
    };
    // Ground beside station i. Inside the apron that is the road's own height less
    // the drop, NOT `terrain.height` - the field returns whatever road is nearest,
    // so beside a fold it flips from one leg to the other and anything standing on
    // it jumps with it.
    const ground = (i, o) => (Math.abs(o) <= APRON
      ? line[i].p[1] - DROP : terrain.height.apply(null, spot(i, o)));

    // ---- the barriers ------------------------------------------------------
    //
    // **This is the one part of the file that changes lap times, and it exists
    // because the layout has two corners you could simply miss out.** Measured on
    // the built ribbon, against what the checkpoints already defend:
    //
    //   Village entry -> Aintree exit   chord  88, road 206   (2.35x)
    //   Brooklands exit -> Woodcote     chord  81, road 279   (3.42x)
    //   Luffield entry -> its own exit  chord  50, road 110   (2.21x)
    //
    // Grass tops out near half the road's top speed (`OFFROAD_DRAG`), so a cut
    // pays somewhere past about 2x - and all three of those clear it. The
    // checkpoints cannot help: the arena sits entirely between the gate on the
    // Farm Straight and the gate on the Wellington Straight, and Luffield sits
    // entirely between that one and the gate on the National Straight. So both are
    // legal laps that skip a third of a corner sequence each.
    //
    // **It cannot be a ribbon `rail`.** This is a ground track and
    // `test_barriers_are_opt_in` requires a ground track to carry *no* walled
    // stations at all - so, like the Costco's rooftop parapet, it is collider
    // geometry standing beside the road rather than a flag on the road's edge.
    // Which is also better here: it stays outside the kerb, so the racing line
    // never touches it and the medal times do not move.
    //
    // It goes on the **inside** of each corner, which is the unusual side for a
    // race track and the only side a chord across a hairpin can be blocked from.
    // The side is read off the station's own `curv` rather than authored, so a
    // sequence that changes direction - Brooklands' left into Luffield's right -
    // gets its barrier on the correct side of each without being told. **The strip
    // has to break when that sign flips**, or one quad spans the road and the
    // barrier becomes a wall across the track.
    //
    // The real arena has barrier and debris fence exactly here, for the same
    // reason: Village, The Loop and Aintree pass within twenty-odd units of each
    // other and there is infield between them, not run-off.
    const BAR_H = 1.5;
    const railC = pal.rail != null ? pal.rail : 0xd8dde2;
    const insideBarrier = (f0, f1, opts) => {
      const i0 = at(f0), i1 = at(f1);
      const gap = (opts && opts.gap != null) ? opts.gap : 4.5;
      let prev = null, prevSide = 0;
      for (let i = i0; i <= i1; i++) {
        const e = line[i];
        const k = e.curv || 0;
        // Straight enough to have no inside: carry the last side through a short
        // link rather than dropping the barrier for it, or a chicane's barrier is
        // in two pieces with the shortcut running between them.
        const side = Math.abs(k) < 1 / 200 ? prevSide : (k > 0 ? 1 : -1);
        if (!side) { prev = null; continue; }
        if (side !== prevSide) prev = null;      // never span the road
        prevSide = side;
        const o = (e.hw + gap) * side;
        const g = ground(i, o);
        const [x, z] = spot(i, o);
        const p = [x, g, z];
        const q = prev;
        prev = p;
        if (!q) continue;
        const up = (v) => [v[0], v[1] + BAR_H, v[2]];
        face(q, p, up(p), up(q), railC);
        col.addQuad(q, p, up(p), up(q), KIND.WALL);
        // A kerb-height foot under it, so it reads as standing on the ground
        // rather than hovering a hair over it wherever the sweep and the field
        // disagree.
        const dn = (v) => [v[0], v[1] - 0.55, v[2]];
        face(dn(q), dn(p), p, q, shade(railC, -0.35));
      }
    };
    // Village through The Loop and Aintree - the whole arena - and Brooklands
    // through Luffield into the entry of Woodcote. Fractions rather than station
    // indices, for the same reason the furniture uses them: the ribbon is
    // re-solved for closure and that changes how many stations there are.
    insideBarrier(0.122, 0.203);
    insideBarrier(0.296, 0.392);

    // ---- the runways -------------------------------------------------------
    //
    // Three strips in the classic WWII "A" pattern - one main and two
    // subsidiaries at sixty degrees to it, which is what a Class A bomber station
    // was built to and what RAF Silverstone was.
    //
    // **The bearings are derived, not surveyed.** The exact headings of
    // Silverstone's runways are not in OpenStreetMap (only the modern heliport
    // is), so rather than invent three plausible-looking numbers this takes its
    // main axis from the Hangar Straight - the longest leg on the lap, and a leg
    // that really does lie along the old airfield - and swings the other two off
    // it. The *pattern* is the real one; the alignment is the circuit's own. That
    // also means it survives a layout change, which three literal bearings would
    // not.
    //
    // Every cell is skipped where the road is near, so a runway stops at the
    // run-off instead of being painted over the track - which is what the real
    // concrete does, being under the circuit rather than across it. And they are
    // clamped to the ground the height field actually draws (`bbox` plus
    // `CELL * 10`): the plate is far smaller than it looks from inside the track,
    // and anything past it stands over the void.
    const rnd = mulberry(0x51157);            // fixed, so the weathering is shared
    const hangarStart = at(0.72), hangarEnd = at(0.80);
    const hs = line[hangarStart], he = line[hangarEnd];
    const mainBrg = Math.atan2(he.p[2] - hs.p[2], he.p[0] - hs.p[0]);
    const cx = (bbox.x0 + bbox.x1) / 2, cz = (bbox.z0 + bbox.z1) / 2;
    const PAD = CELL * 10 - 12;               // stay inside the drawn ground
    const gx0 = bbox.x0 - PAD, gx1 = bbox.x1 + PAD;
    const gz0 = bbox.z0 - PAD, gz1 = bbox.z1 + PAD;
    // Concrete laid in 1943 and left: pale, and mottled per slab rather than flat,
    // because one colour over a thousand units reads as a painted stripe.
    const CONC = 0xa8aaa0;
    // Runway markings, and they are what make the whole idea land. Without them a
    // runway is a flat grey strip on green, which from a car at ground level is
    // nearly invisible however wide it is - the first render had all three of them
    // in and you had to be told they were there. A broken centreline is the one
    // mark everybody reads as *runway* rather than as path or hardstanding.
    const PAINT = 0xe6e7e0;
    const runway = (brg, half, hw, slab) => {
      const dx = Math.cos(brg), dz = Math.sin(brg);
      const px = -dz, pz = dx;                // across the strip
      const steps = Math.ceil((half * 2) / slab);
      // At least three across, or the joint shading below darkens every lane there
      // is and the strip comes out flat.
      const lanes = Math.max(3, Math.round((hw * 2) / (slab * 0.7)));
      // Declared out here rather than in the inner loop, because the centreline
      // below needs it too - and a `const` is in its temporal dead zone until its
      // own line runs, so a helper used by two sections has to sit above both.
      const pt = (t, u) => [cx + dx * t + px * u, cz + dz * t + pz * u];
      for (let s = 0; s < steps; s++) {
        const t0 = -half + s * slab, t1 = Math.min(half, t0 + slab);
        for (let l = 0; l < lanes; l++) {
          const u0 = -hw + (l * hw * 2) / lanes, u1 = -hw + ((l + 1) * hw * 2) / lanes;
          const mid = pt((t0 + t1) / 2, (u0 + u1) / 2);
          if (mid[0] < gx0 || mid[0] > gx1 || mid[1] < gz0 || mid[1] > gz1) continue;
          // Stop at the run-off. Tested at the cell's middle: erring a whole cell
          // wide is what lays a ring of the wrong surface round the whole circuit,
          // which is the note `drawTerrain` makes about the gravel band.
          if (terrain.toRoad(mid[0], mid[1]) < APRON - 2) continue;
          const c = [pt(t0, u0), pt(t0, u1), pt(t1, u1), pt(t1, u0)];
          // Weathered, and a shade darker along the joints between slabs.
          const w = (rnd() - 0.5) * 0.07 - (l === 0 || l === lanes - 1 ? 0.05 : 0);
          const y = (q) => terrain.height(q[0], q[1]) + 0.16;
          solid.quad([c[0][0], y(c[0]), c[0][1]], [c[1][0], y(c[1]), c[1][1]],
                     [c[2][0], y(c[2]), c[2][1]], [c[3][0], y(c[3]), c[3][1]],
                     shade(CONC, w));
        }
        // The broken centreline, on every other slab, a hair above the concrete
        // for the same reason the concrete sits above the ground: two surfaces at
        // one height is a depth-buffer coin toss, and the note about the Costco's
        // roof puts the gap nearer 0.15 than 0.05.
        if (s % 2 === 0) {
          const mw = hw * 0.075, in0 = t0 + slab * 0.16, in1 = t1 - slab * 0.16;
          const mid = pt((in0 + in1) / 2, 0);
          if (in1 > in0 && !(mid[0] < gx0 || mid[0] > gx1 || mid[1] < gz0 || mid[1] > gz1)
              && terrain.toRoad(mid[0], mid[1]) >= APRON - 2) {
            const m = [pt(in0, -mw), pt(in0, mw), pt(in1, mw), pt(in1, -mw)];
            const my = (q) => terrain.height(q[0], q[1]) + 0.24;
            solid.quad([m[0][0], my(m[0]), m[0][1]], [m[1][0], my(m[1]), m[1][1]],
                       [m[2][0], my(m[2]), m[2][1]], [m[3][0], my(m[3]), m[3][1]],
                       PAINT);
          }
        }
      }
    };
    // 2000 yards and 1400 yards at this track's 0.4586 units per metre, which is
    // the standard main-and-two-subsidiaries a Class A airfield was laid out to.
    runway(mainBrg, 839 / 2, 10.5, 9.0);
    runway(mainBrg + Math.PI / 3, 587 / 2, 9.0, 9.0);
    runway(mainBrg - Math.PI / 3, 587 / 2, 9.0, 9.0);

    // ---- the hangars -------------------------------------------------------
    //
    // Two of them, out past the barrier on the far side of the Hangar Straight,
    // which is what the straight is named after. A Type T2 has a curved roof, so
    // the roof is a few stepped quads rather than a ridge - at this distance that
    // is the whole difference between a hangar and a barn.
    //
    // Guarded on `toRoad` like everything else here: if the footprint turns out to
    // be near another leg of the circuit the hangar is dropped rather than drawn
    // through it. It is collided, because a building you can drive through is
    // worse than one that is not there.
    const HANG = 0xa8ada6;
    const hangar = (f, side, L, D, H) => {
      const i = at(f);
      const e = line[i];
      const out = (cfg.armco != null ? cfg.armco : 26) + 22 + D / 2;
      const o = out * side;
      const [bx, bz] = spot(i, o);
      if (terrain.toRoad(bx, bz) < out - 6) return;      // somebody else is here
      const fx = e.lat[2], fz = -e.lat[0];               // along the road
      const sx = e.lat[0], sz = e.lat[2];                // across it
      const base = terrain.height(bx, bz) - 0.3;
      const P = (u, v, y) => [bx + fx * u + sx * v, y, bz + fz * u + sz * v];
      // walls
      const corners = [[-L / 2, -D / 2], [L / 2, -D / 2], [L / 2, D / 2], [-L / 2, D / 2]];
      for (let k = 0; k < 4; k++) {
        const a = corners[k], b = corners[(k + 1) % 4];
        const A = P(a[0], a[1], base), B = P(b[0], b[1], base);
        const At = P(a[0], a[1], base + H), Bt = P(b[0], b[1], base + H);
        face(A, B, Bt, At, shade(HANG, k % 2 ? -0.08 : 0));
        col.addQuad(A, B, Bt, At, KIND.WALL);
      }
      // the barrel roof, in steps across the depth
      const RIB = 7, RISE = H * 0.42;
      for (let k = 0; k < RIB; k++) {
        const v0 = -D / 2 + (k * D) / RIB, v1 = -D / 2 + ((k + 1) * D) / RIB;
        const arc = (v) => base + H + Math.cos((v / (D / 2)) * Math.PI / 2) * RISE;
        const y0 = arc(v0), y1 = arc(v1);
        face(P(-L / 2, v0, y0), P(L / 2, v0, y0), P(L / 2, v1, y1), P(-L / 2, v1, y1),
             shade(HANG, 0.10 - k * 0.012));
        // the gable end under each rib, so the roof is not a floating shell
        for (const u of [-L / 2, L / 2]) {
          face(P(u, v0, base + H), P(u, v1, base + H), P(u, v1, y1), P(u, v0, y0),
               shade(HANG, -0.16));
        }
      }
      // The doors: two dark full-height bays, which is what you actually read a
      // hangar by rather than by its shape.
      //
      // **They have to go on the face the road is on**, and working out which that
      // is takes one step of thought. The building is centred at `lat * o` with
      // `o = out * side`, and the road is at `lat * 0` - so from the hangar the
      // road lies in the `-sign(o)` direction along `lat`, which is `-side`. The
      // first pass put them at `-D/2` regardless and both hangars faced the wrong
      // way: from the car they were two blank grey walls, which is exactly what the
      // render showed and exactly what a wrong sign always looks like here.
      const vd = -side * (D / 2 + 0.12);
      for (const u of [-L / 2 + L * 0.24, L / 2 - L * 0.24]) {
        const w = L * 0.17;
        face(P(u - w, vd, base), P(u + w, vd, base),
             P(u + w, vd, base + H * 0.82), P(u - w, vd, base + H * 0.82), 0x3b4048);
      }
      // Concrete hardstanding in front of the doors. One quad, and it is what
      // stops the hangar reading as a barn dropped in a field - and the defects
      // list is right that a few quads laid on the floor buy more than the same
      // effort spent on the thing standing up.
      // `face` rather than `solid.quad`, because which way this winds depends on
      // the sign of `side` and a quad wound the wrong way here is not an error, it
      // is simply not there. Same trap as the doors above, one layer down.
      const ap = vd - side * 17;
      const apQ = [P(-L / 2 - 4, vd, 0), P(L / 2 + 4, vd, 0), P(L / 2 + 4, ap, 0),
                   P(-L / 2 - 4, ap, 0)]
        .map((q) => [q[0], terrain.height(q[0], q[2]) + 0.14, q[2]]);
      face(apQ[0], apQ[1], apQ[2], apQ[3], shade(CONC, -0.04));
    };
    hangar(0.735, -1, 62, 34, 13);
    hangar(0.790, -1, 62, 34, 13);

    // ---- the Wing ----------------------------------------------------------
    //
    // Silverstone's pit building is a 2011 sweep of white roof, and `addFurniture`
    // draws the pits as a long shed with a garage stripe - which is right for Spa
    // and is Spa. So the garages and the pit wall still come from the palette and
    // this lays the roof over them: a canopy that starts low at the pit lane and
    // lifts away from the track, carried on masts.
    //
    // Same fraction range as `furniture.pits`, read off the palette rather than
    // repeated here, so the two cannot drift apart.
    const pits = (pal.furniture || {}).pits;
    if (pits) {
      const side = pits.side || 1;
      const i0 = at(pits.at[0]), i1 = at(pits.at[1]);
      const armco = (pal.furniture.armco != null ? pal.furniture.armco : 26);
      const oF = (armco + 6) * side, oB = (armco + 26) * side;
      const WHITE = 0xeef0ee;
      let prev = null;
      for (let i = i0; i <= i1; i++) {
        const e = line[i];
        const yF = e.p[1] + 9.5, yB = e.p[1] + 15.0;
        const [fx, fz] = spot(i, oF), [bx2, bz2] = spot(i, oB);
        const cur = [[fx, yF, fz], [bx2, yB, bz2]];
        if (prev) {
          face(prev[0], cur[0], cur[1], prev[1], WHITE);
          // a shadow line along the leading edge, so the sweep has a thickness
          const dn = (v) => [v[0], v[1] - 0.7, v[2]];
          face(dn(prev[0]), dn(cur[0]), cur[0], prev[0], shade(WHITE, -0.30));
        }
        prev = cur;
        // masts, every few stations, down to whatever the ground is doing
        if ((i - i0) % 6 === 0) {
          const g = ground(i, oB);
          solid.box(bx2, (g + yB) / 2, bz2, 0.5, (yB - g) / 2, 0.5, shade(WHITE, -0.45));
        }
      }
    }
  }
})();
