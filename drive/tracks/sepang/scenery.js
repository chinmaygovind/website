// Sepang: the umbrella grandstand, the control tower, the flag-striped run-off
// at Turn 15, the palm oil, and the hills.
//
// Everything a circuit has in common - the corner stands, the pit garages, the
// start gantry, the teal boards, the armco and the flags - is the furniture kit
// configured in `palette.py`. This file is what that kit cannot say, and every
// piece of it is in the reference photographs:
//
//  * **the main grandstand is between the two straights and faces both.** It is
//    the thing anybody who has seen Sepang remembers: a long double-sided stand
//    under a row of fabric umbrellas - Hibiscus-leaf canopies, tan on top and
//    cream underneath on white ribs - with a taller tower in the middle
//    carrying two bigger ones, a wire globe and the flag. Kit `stands` are one
//    side of one straight and cannot be this.
//  * **the race control tower** at the line, on the pit side: a slim white
//    shaft with dark glass strips and a glazed cab.
//  * **Turn 15's run-off is painted in the flag's colours**, red, white, yellow
//    and blue bands round the outside of the hairpin. It is the most
//    photographed bit of paint on the circuit.
//  * **palm oil in rows.** The scatter plants loose palms and rainforest near
//    the road; out past it every aerial shows plantation, palms on a grid,
//    blocks of it with gaps between.
//  * **green hills round the horizon, and blue mountains behind them**, which is
//    what is behind the pit straight in every photograph taken from the stand.
//
// Three things are in the collider: the front of the grandstand (see `FRONT`),
// the fence beside the Turn 9 straight, and the wall round the inside of Turns 1
// and 2 - the last two are both there to stop a shortcut. The tower
// stands outside the armco, the paint is a colour on run-off that is already
// OFFROAD, and the palms and the hills are past `clear`. A throw in any of the
// rest leaves the suite green - `tools/validate_track.py` is what checks it ran.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.sepang = { props: props };

  const FABRIC = 0xd7bd84;      // the canopy, sun side
  const FABRIC_U = 0xb9ae94;    // ...and its underside, unlit, so picked darker
  const STEEL = 0xf2f2ee;       // ribs, masts, the tower
  const CONC = 0xd3d0c8;
  const SEAT = 0x2d7a46, SEAT2 = 0x24663a;
  const GLASS = 0x26313b;

  function props(ctx) {
    const { solid, bright, col, KIND, track, pal, bbox, CELL, terrain, shade, mulberry } = ctx;
    const { at, face, DROP } = ctx;
    const line = track.line, n = line.length;
    if (!terrain) return;
    const cfg = pal.terrain || {};
    const ARMCO = cfg.armco != null ? cfg.armco : 24;
    const CLEAR = cfg.clear != null ? cfg.clear : 34;

    // ---- a frame on the start line ----------------------------------------
    // u along the start straight, v across it towards the back straight (the
    // road's left, side -1), y up. Derived from the ribbon, never a literal: the
    // lap is re-solved for closure on every import.
    const i0 = at(0.0), e0 = line[i0], e1 = line[Math.min(n - 1, i0 + 4)];
    const fl = Math.hypot(e1.p[0] - e0.p[0], e1.p[2] - e0.p[2]) || 1;
    const F = [(e1.p[0] - e0.p[0]) / fl, (e1.p[2] - e0.p[2]) / fl];
    const G = [-e0.lat[0], -e0.lat[2]];
    const O = [e0.p[0], e0.p[2]];
    const W = (u, v) => [O[0] + F[0] * u + G[0] * v, O[1] + F[1] * u + G[1] * v];
    const P = (u, v, y) => { const w = W(u, v); return [w[0], y, w[1]]; };
    // How far across the back straight is: the nearest station of the back
    // half of the lap, measured along G.
    let D = 1e9;
    for (let i = at(0.80); i <= at(0.92); i++) {
      const dx = line[i].p[0] - O[0], dz = line[i].p[2] - O[1];
      const v = dx * G[0] + dz * G[1], u = dx * F[0] + dz * F[1];
      if (Math.abs(u) < 60 && v > 0) D = Math.min(D, v);
    }
    if (D > 400) return;
    const floorY = e0.p[1] - DROP;

    // ---- the umbrella grandstand ------------------------------------------
    // **The two straights are 48 units apart centre to centre** (105 m, which
    // is the real gap), so between two 19-wide roads there are 29 units for a
    // stand facing both - and the armco cannot be in there at all: the kit cuts
    // it wherever another road is nearer than its own offset. So the front of
    // the stand is the barrier, three units past each kerb, and it is in the
    // collider. That is also what the real one is: a wall and a fence, then
    // seats, with no run-off between the pit straight and the crowd.
    const VM = D / 2;                              // the spine
    const FRONT = e0.hw + 3;
    const DEEP = Math.max(5, VM - FRONT - 1.2);    // each side's seating depth
    // Run the stand along the straight until its footprint finds other road -
    // which at the T15 end is the hairpin itself.
    const okAt = (u) => [FRONT, VM, D - FRONT].every((v) => {
      const w = W(u, v);
      return terrain.toRoad(w[0], w[1]) >= FRONT - 1;
    });
    let uA = 0, uB = 0;
    while (uA > -170 && okAt(uA - 4)) uA -= 4;
    while (uB < 120 && okAt(uB + 4)) uB += 4;
    if (uB - uA > 40) {
      const TIERS = 7, RISE = 1.3, PLINTH = 2.4;
      const TEAL = 0x00a19a;
      const crowdRnd = mulberry(0xc40d);
      const SHIRTS = [0xd94f3d, 0xe8e3d6, 0x2f4f7a, 0xf2c94c, 0x3d6b4a,
                      0x8a4fa0, 0xdd7f2e, 0x33383f, 0xb8443a, 0xcfd4d8];
      const step = DEEP / TIERS;
      // Each half faces its own straight: `dir` -1 is the half facing the start
      // straight (front at v = FRONT), +1 the half facing the back straight.
      for (const dir of [-1, 1]) {
        const vF = dir < 0 ? FRONT : D - FRONT;
        for (let t = 0; t < TIERS; t++) {
          const va = vF - dir * t * step, vb = vF - dir * (t + 1) * step;
          const y = floorY + PLINTH + t * RISE;
          // The tread, and the row of seats on it - which from the road is the
          // riser, since you see a stand from below its front edge.
          face(P(uA, va, y), P(uB, va, y), P(uB, vb, y), P(uA, vb, y), CONC);
          face(P(uA, vb, y), P(uB, vb, y), P(uB, vb, y + RISE), P(uA, vb, y + RISE),
               t % 2 ? SEAT2 : SEAT);
        }
        // the front wall down to the ground, and the two ends
        // The crowd: the kit's recipe for its own stands (`stand` in
        // trackmesh.js) - one box a person, two seats in three filled, shirts
        // dealt at random - so this stand and the corner ones read as one
        // circuit's crowd. Without it, the biggest stand at the track was the
        // only empty one.
        for (let t = 0; t < TIERS; t++) {
          const vS = vF - dir * (t * step + step * 0.55);
          const y = floorY + PLINTH + t * RISE;
          for (let u = uA + 0.6; u < uB - 0.6; u += 0.85) {
            if (crowdRnd() > 0.66) continue;
            const [x, z] = W(u, vS);
            const h = 0.46 + crowdRnd() * 0.2;
            solid.box(x, y + h, z, 0.25, h, 0.25, SHIRTS[(crowdRnd() * SHIRTS.length) | 0]);
          }
        }
        // the front wall: teal, as every barrier here is, with a white lip
        face(P(uA, vF, floorY), P(uB, vF, floorY), P(uB, vF, floorY + PLINTH - 0.4),
             P(uA, vF, floorY + PLINTH - 0.4), TEAL);
        face(P(uA, vF, floorY + PLINTH - 0.4), P(uB, vF, floorY + PLINTH - 0.4),
             P(uB, vF, floorY + PLINTH), P(uA, vF, floorY + PLINTH), 0xf3f1ec);
        for (let u = uA; u < uB; u += 8) {
          const u1 = Math.min(uB, u + 8);
          col.addQuad(P(u, vF, floorY - 1), P(u1, vF, floorY - 1), P(u1, vF, floorY + 3.5),
                      P(u, vF, floorY + 3.5), KIND.WALL);
        }
        const top = floorY + PLINTH + TIERS * RISE;
        for (const u of [uA, uB]) {
          face(P(u, vF, floorY), P(u, VM, floorY), P(u, VM, top), P(u, vF, floorY + PLINTH),
               shade(CONC, -0.08));
        }
      }
      // The spine: the concourse wall between the two halves, a storey higher
      // than the top rows, and the hospitality glazing along it.
      const top = floorY + PLINTH + TIERS * RISE;
      for (const dv of [-1.2, 1.2]) {
        face(P(uA, VM + dv, top), P(uB, VM + dv, top), P(uB, VM + dv, top + 4.2),
             P(uA, VM + dv, top + 4.2), STEEL);
        face(P(uA, VM + dv * 1.01, top + 1.0), P(uB, VM + dv * 1.01, top + 1.0),
             P(uB, VM + dv * 1.01, top + 3.2), P(uA, VM + dv * 1.01, top + 3.2), GLASS);
      }
      face(P(uA, VM - 1.2, top + 4.2), P(uB, VM - 1.2, top + 4.2),
           P(uB, VM + 1.2, top + 4.2), P(uA, VM + 1.2, top + 4.2), CONC);
      // and across both ends, so neither end of the gap between the straights
      // is a way in
      for (const u of [uA, uB]) {
        col.addQuad(P(u, FRONT, floorY - 1), P(u, D - FRONT, floorY - 1),
                    P(u, D - FRONT, floorY + 3.5), P(u, FRONT, floorY + 3.5), KIND.WALL);
      }

      // An umbrella: a mast, and a shallow fabric bowl on twelve ribs whose rim
      // droops and scallops between them. Seen from below - which is how it is
      // seen - the cream underside and the white ribs are the whole read.
      const umbrella = (u, v, yTop, R, mast0) => {
        const [cx, cz] = W(u, v);
        solid.box(cx, (mast0 + yTop) / 2, cz, 0.55, (yTop - mast0) / 2, 0.55, STEEL);
        const N = 12, droop = R * 0.2;
        const rim = [];
        for (let k = 0; k <= N; k++) {
          const a = (k / N) * Math.PI * 2;
          const r = k % 2 ? R * 0.93 : R;
          const y = yTop - droop + (k % 2 ? droop * 0.35 : 0);
          rim.push([cx + Math.cos(a) * r, y, cz + Math.sin(a) * r]);
        }
        const mid = [];
        for (let k = 0; k <= N; k++) {
          const a = (k / N) * Math.PI * 2;
          mid.push([cx + Math.cos(a) * R * 0.38, yTop - droop * 0.15, cz + Math.sin(a) * R * 0.38]);
        }
        const c = [cx, yTop + 0.5, cz];
        const dn = (q, d) => [q[0], q[1] - d, q[2]];
        for (let k = 0; k < N; k++) {
          // top: winding up, sun-coloured; underside a hair below, cream
          solid.tri(c, mid[k + 1], mid[k], FABRIC);
          solid.quad(mid[k], mid[k + 1], rim[k + 1], rim[k], shade(FABRIC, k % 2 ? -0.05 : 0.03));
          // The underside faces down, where the key light never reaches, so it
          // is unlit: lit, it was black.
          bright.tri(dn(c, 0.12), dn(mid[k], 0.12), dn(mid[k + 1], 0.12), FABRIC_U);
          bright.quad(dn(mid[k], 0.12), dn(rim[k], 0.12), dn(rim[k + 1], 0.12),
                      dn(mid[k + 1], 0.12), shade(FABRIC_U, k % 2 ? -0.07 : 0));
          if (k % 2 === 0) {
            // a rib under the fabric, from the mast to the rim
            const a = dn(c, 0.15), b = dn(rim[k], 0.15);
            face(a, b, dn(b, 0.5), dn(a, 0.9), STEEL);
          }
        }
      };
      const roofY = top + 9.5;
      const SPAN = 24;
      const TOWER_U = Math.max(uA + 30, Math.min(uB - 30, -18));
      for (let u = uA + SPAN / 2; u <= uB - SPAN / 2 + 1; u += SPAN) {
        if (Math.abs(u - TOWER_U) < SPAN * 0.8) continue;
        umbrella(u, VM, roofY, VM - FRONT + 5, top + 4.2);
      }

      // The tower in the middle: a white shaft, two bigger umbrellas stacked,
      // the wire globe, and the flag.
      const [tx, tz] = W(TOWER_U, VM);
      solid.box(tx, (top + 4.2 + top + 34) / 2, tz, 2.4, 15, 2.4, STEEL);
      umbrella(TOWER_U, VM, roofY + 5, VM - FRONT + 12, top + 4.2);
      umbrella(TOWER_U, VM, roofY + 14, (VM - FRONT) * 1.1, roofY + 5);
      const gy = roofY + 20;
      for (let k = 0; k < 10; k++) {
        const a = (k / 10) * Math.PI * 2;
        solid.box(tx + Math.cos(a) * 3.2, gy, tz + Math.sin(a) * 3.2, 0.25, 0.25, 0.25, STEEL);
        solid.box(tx + Math.cos(a) * 2.3, gy + 2.2, tz + Math.sin(a) * 2.3, 0.22, 0.22, 0.22, STEEL);
        solid.box(tx + Math.cos(a) * 2.3, gy - 2.2, tz + Math.sin(a) * 2.3, 0.22, 0.22, 0.22, STEEL);
      }
      solid.box(tx, gy + 6, tz, 0.2, 9, 0.2, STEEL);
      flag(tx, gy + 14.5, tz, 7.0);
    }

    // A Jalur Gemilang on a pole, flying along the start straight: fourteen
    // stripes and a navy canton with a gold star. Drawn here rather than with
    // the kit's `flagRun`, which places along the ribbon and not on a tower.
    function flag(x, yTop, z, L) {
      const H = L / 2, s = H / 14;
      const Q = (u, w) => [x + F[0] * u, yTop - w, z + F[1] * u];
      for (let k = 0; k < 14; k++) {
        const c = k % 2 ? 0xf4f4f2 : 0xcc0001;
        const u0 = k < 8 ? L / 2 : 0;
        face(Q(u0, k * s), Q(L, k * s), Q(L, (k + 1) * s), Q(u0, (k + 1) * s), c);
      }
      face(Q(0, 0), Q(L / 2, 0), Q(L / 2, 8 * s), Q(0, 8 * s), 0x010066);
      face(Q(L * 0.28, 2.6 * s), Q(L * 0.38, 2.6 * s), Q(L * 0.38, 5.4 * s),
           Q(L * 0.28, 5.4 * s), 0xffcc00);
    }

    // ---- the control tower --------------------------------------------------
    // On the pit side, just short of the line, standing behind the garages.
    {
      const v = -(ARMCO + 9 + 13 + 9), u = -26;
      const [x, z] = W(u, v);
      const g = terrain.height(x, z) - 0.3;
      const H = 36, R = 4.2;
      const corner = (a, b, y) => P(u + a, v + b, y);
      const sides = [[-R, -R, R, -R], [R, -R, R, R], [R, R, -R, R], [-R, R, -R, -R]];
      // The shaft is unlit: lit, its three faces away from the sun came out a
      // dark grey, and the real one is a white you see from half the circuit.
      // Each face gets its own value instead, so it still reads as a box.
      let fk = 0;
      for (const [a0, b0, a1, b1] of sides) {
        const A = corner(a0, b0, g), B = corner(a1, b1, g), C2 = corner(a1, b1, g + H), D2 = corner(a0, b0, g + H);
        const wc = [0xc4c7c4, 0xa9adab, 0xb6b9b6, 0x9a9e9d][fk++];
        bright.quad(A, B, C2, D2, wc); bright.quad(A, D2, C2, B, wc);
        // two dark window strips up each face
        for (const t of [0.3, 0.7]) {
          const ax = a0 + (a1 - a0) * (t - 0.08), bx = b0 + (b1 - b0) * (t - 0.08);
          const cx = a0 + (a1 - a0) * (t + 0.08), cz = b0 + (b1 - b0) * (t + 0.08);
          const o = 1.02;
          face(corner(ax * o, bx * o, g + 3), corner(cx * o, cz * o, g + 3),
               corner(cx * o, cz * o, g + H - 2), corner(ax * o, bx * o, g + H - 2), GLASS);
        }
      }
      // the cab: a glazed box overhanging the shaft, a white roof, a mast
      const C = R * 1.45, y0 = g + H, y1 = g + H + 5.5;
      const cs = [[-C, -C, C, -C], [C, -C, C, C], [C, C, -C, C], [-C, C, -C, -C]];
      for (const [a0, b0, a1, b1] of cs) {
        face(corner(a0, b0, y0), corner(a1, b1, y0), corner(a1, b1, y1), corner(a0, b0, y1), GLASS);
        face(corner(a0, b0, y1), corner(a1, b1, y1), corner(a1, b1, y1 + 1.4), corner(a0, b0, y1 + 1.4), STEEL);
      }
      face(corner(-C, -C, y0), corner(C, -C, y0), corner(C, C, y0), corner(-C, C, y0), STEEL);
      face(corner(-C, -C, y1 + 1.4), corner(C, -C, y1 + 1.4), corner(C, C, y1 + 1.4),
           corner(-C, C, y1 + 1.4), STEEL);
      solid.box(x, y1 + 6, z, 0.18, 4.6, 0.18, STEEL);
    }

    // ---- the barrier round the inside of Turns 1 and 2 -----------------------
    // **The one part of this file that changes a lap time.** Turn 1 is 203
    // degrees at radius 19 and Turn 2 turns straight back, so the pair sits
    // between the gate on the start straight and the one after Turn 3 and the
    // chord across them is 47 units of grass against 157 of road - 3.3x, and
    // grass pays past about 2x (`tools/cut_check.py`). Silverstone's answer: a
    // low wall on the inside of each corner, side read off the station's own
    // curvature, broken where the sign flips so it never spans the road. It is
    // collider geometry because a ground track may carry no ribbon `rail`.
    {
      const dist = [0];
      for (let i = 1; i < n; i++) dist.push(dist[i - 1] + Math.hypot(
        line[i].p[0] - line[i - 1].p[0], line[i].p[2] - line[i - 1].p[2]));
      const atD = (f) => { const t = f * dist[n - 1]; let i = 0; while (i < n - 1 && dist[i] < t) i++; return i; };
      const BAR_H = 2.2;
      const TEAL = 0x00a19a;
      // A low teal-and-white wall from f0 to f1 (fractions by distance), `gap`
      // past the kerb. With `force` it stays on that side; without, it follows
      // the inside of each corner and breaks where the sign flips.
      const wall = (f0, f1, gap, force) => {
        const i0 = atD(f0), i1 = atD(f1);
        let first = i0;
        while (first < i1 && Math.abs(line[first].curv || 0) < 1 / 200) first++;
        let prev = null, prevSide = force || ((line[first].curv || 0) > 0 ? 1 : -1);
        for (let i = i0; i <= i1; i++) {
          const e = line[i], k = e.curv || 0;
          const side = force || (Math.abs(k) < 1 / 200 ? prevSide : (k > 0 ? 1 : -1));
          if (side !== prevSide) prev = null;
          prevSide = side;
          const o = (e.hw + gap) * side;
          const p = [e.p[0] + e.lat[0] * o, e.p[1] - DROP, e.p[2] + e.lat[2] * o];
          const q = prev; prev = p;
          if (!q) continue;
          const up = (v) => [v[0], v[1] + BAR_H, v[2]];
          face(q, p, up(p), up(q), (i >> 1) % 2 ? TEAL : 0xf3f1ec);
          col.addQuad(q, p, up(p), up(q), KIND.WALL);
        }
      };
      // It starts 80 units back down the start straight, on the side Turn 1
      // turns to: the chord leaves the straight there, crosses the grass and
      // lands half way round Turn 2, never touching Turn 1's own inside.
      wall(0.072, 0.192, 4.0);
      // **And one on the left from the back half of Turn 1 round to Turn 2's
      // exit**, found by driving it: T1 and T2 are an S, so the outside of T1's
      // exit is the same patch of grass as T2's inside, and running wide out of
      // T1 dropped you straight onto T2's exit. Close to the kerb, because the
      // inside wall above sits too far into a radius-18 hairpin to stop it.
      wall(0.124, 0.168, 1.6, -1);
      // **And a cross wall shutting the grass strip between that inside wall
      // and the armco**, found on prod: BotTyler left the straight before the
      // inside wall starts, ran the strip and came out onto Turn 2 half way
      // round, skipping Turn 1 for 1.5s. It stands where the armco ends, so
      // the strip is a dead end rather than a way through.
      {
        const e = line[atD(0.0900)];
        const p = (v) => [e.p[0] + e.lat[0] * v, e.p[1] - DROP, e.p[2] + e.lat[2] * v];
        const q = p(e.hw + 3), r = p(e.hw + 21);
        const up = (v) => [v[0], v[1] + BAR_H, v[2]];
        face(q, r, up(r), up(q), TEAL);
        face(r, q, up(q), up(r), TEAL);
        col.addQuad(q, r, up(r), up(q), KIND.WALL);
      }
      // The other corners you could clip across the grass, found by driving
      // and then by `cut_check` run at 1.25x rather than its usual 2x: Turn 4,
      // Turns 9 into 10, Turn 14 onto the back straight, and Turn 15 - which
      // until this had a checkpoint thirty units short of the line doing this
      // job instead, and a gate that close to the finish is just noise.
      wall(0.272, 0.315, 2.0);
      wall(0.568, 0.615, 2.0);
      wall(0.742, 0.790, 2.0);
      wall(0.910, 0.985, 2.0);
    }

    // ---- the fence between the Turn 9 straight and the back straight -------
    // The run down to Turn 9 lies alongside the back straight, 22 units away
    // centre to centre at its closest - and the real circuit has a barrier and
    // a debris fence down the strip between them, because there is no run-off
    // there for either road. So a wall stands on the midline wherever the two
    // are within 36 units, armco-grey with a fence above it, and it is in the
    // collider: crossing from one to the other skips Turns 9 to 14.
    {
      const dist = [0];
      for (let i = 1; i < n; i++) dist.push(dist[i - 1] + Math.hypot(
        line[i].p[0] - line[i - 1].p[0], line[i].p[2] - line[i - 1].p[2]));
      const atD = (f) => { const t = f * dist[n - 1]; let i = 0; while (i < n - 1 && dist[i] < t) i++; return i; };
      const back = [];
      for (let i = atD(0.78); i <= atD(0.93); i++) back.push(line[i]);
      let prev = null;
      for (let i = atD(0.50); i <= atD(0.60); i++) {
        const e = line[i];
        let best = null, bd = 1e9;
        for (const q of back) {
          const d = Math.hypot(q.p[0] - e.p[0], q.p[2] - e.p[2]);
          if (d < bd) { bd = d; best = q; }
        }
        if (!best || bd > 36) { prev = null; continue; }
        const p = [(e.p[0] + best.p[0]) / 2, Math.min(e.p[1], best.p[1]) - DROP,
                   (e.p[2] + best.p[2]) / 2];
        const q = prev; prev = p;
        if (!q) continue;
        const up = (v, h) => [v[0], v[1] + h, v[2]];
        face(q, p, up(p, 1.4), up(q, 1.4), 0xb8bdc0);
        face(up(q, 1.4), up(p, 1.4), up(p, 4.6), up(q, 4.6), 0x8d969b);
        col.addQuad(q, p, up(p, 1.4), up(q, 1.4), KIND.WALL);
      }
    }

    // ---- the flag-striped run-off at Turn 15 --------------------------------
    // Red, white, yellow, blue from the kerb out, on the outside of the hairpin
    // and a little way either side of it. The hairpin is found by its
    // curvature inside the last tenth of the lap, not by a fraction alone,
    // because stations are closer together in a corner than on a straight.
    {
      const BANDS = [0xcf2a27, 0xf3f1ec, 0xf2c230, 0x1f57b5];
      let a = -1, b = -1;
      for (let i = at(0.88); i <= at(0.99); i++) {
        if (Math.abs(line[i].curv || 0) > 1 / 40) { if (a < 0) a = i; b = i; }
      }
      if (a >= 0) {
        a = Math.max(0, a - 10); b = Math.min(n - 1, b + 14);
        const out = -Math.sign(line[Math.round((a + b) / 2)].curv || 1);
        const W0 = 1.6, BW = 3.2;
        for (let i = a; i < b; i++) {
          const p = line[i], q = line[i + 1];
          const y0 = p.p[1] - DROP + 0.2, y1 = q.p[1] - DROP + 0.2;
          for (let k = 0; k < BANDS.length; k++) {
            const o0 = (p.hw + W0 + k * BW) * out, o1 = (p.hw + W0 + (k + 1) * BW) * out;
            const Q = (e, o, y) => [e.p[0] + e.lat[0] * o, y, e.p[2] + e.lat[2] * o];
            const m = Q(p, (o0 + o1) / 2, 0);
            if (terrain.toRoad(m[0], m[2]) < Math.abs(o0) - 1) continue;
            face(Q(p, o0, y0), Q(q, o0, y1), Q(q, o1, y1), Q(p, o1, y0), BANDS[k]);
          }
        }
      }
    }

    // ---- the palm oil -------------------------------------------------------
    // Rows on a grid, in blocks with gaps between. Thick near the circuit and
    // thinning out, because past a couple of hundred units a plantation is a
    // texture and nothing out there is worth a frond. Four boxes a palm: a trunk
    // and a cross of fronds, the lower pair drooping.
    // The ground plate is the height field's own grid, read off it rather than
    // re-derived: a rectangle reconstructed from `bbox` came out larger than the
    // one actually drawn, and the hills started past its edge with sky between.
    const gx0 = terrain.x0 + 10, gz0 = terrain.z0 + 10;
    const gx1 = terrain.x0 + (terrain.nx - 1) * terrain.CELL - 10;
    const gz1 = terrain.z0 + (terrain.nz - 1) * terrain.CELL - 10;
    const rnd = mulberry(0x5e9a46);
    const ROW = 9, ALONG = 8, BLOCK = 72;
    const ca = Math.cos(0.42), sa = Math.sin(0.42);
    const cxm = (gx0 + gx1) / 2, czm = (gz0 + gz1) / 2;
    const half = Math.hypot(gx1 - gx0, gz1 - gz0) / 2;
    const FROND = pal.prop, FROND2 = shade(pal.prop, -0.18), TRUNK = 0x6f5a3f;
    const planted = new Map();
    for (let a = -half; a <= half; a += ALONG) {
      for (let r = -half; r <= half; r += ROW) {
        const x = cxm + ca * a - sa * r, z = czm + sa * a + ca * r;
        if (x < gx0 || x > gx1 || z < gz0 || z > gz1) continue;
        const bk = Math.floor(a / BLOCK) + ',' + Math.floor(r / BLOCK);
        if (!planted.has(bk)) planted.set(bk, rnd() < 0.62);
        if (!planted.get(bk)) continue;
        const d = terrain.toRoad(x, z);
        if (d < CLEAR + 14) continue;
        if (d > 160 && rnd() < Math.min(0.75, (d - 160) / 260)) continue;
        const px = x + (rnd() - 0.5) * 1.2, pz = z + (rnd() - 0.5) * 1.2;
        const g = terrain.height(px, pz) - 0.2;
        const h = 6.5 + rnd() * 3.5;
        solid.box(px, g + h / 2, pz, 0.38, h / 2, 0.38, TRUNK);
        const fl2 = 2.4 + rnd() * 0.8;
        solid.box(px, g + h + 0.2, pz, fl2, 0.3, 0.95, FROND);
        solid.box(px, g + h + 0.2, pz, 0.95, 0.3, fl2, FROND);
        solid.box(px, g + h - 0.55, pz, fl2 * 1.25, 0.26, 0.8, FROND2);
        solid.box(px, g + h - 0.55, pz, 0.8, 0.26, fl2 * 1.25, FROND2);
      }
    }

    // ---- the hills, and the mountains behind them --------------------------
    // Rings round the ribbon's own centre (Monza's lesson: never round a
    // station). The first starts just under the ground plate's edge and rises,
    // so there is no strip of sky between the plate and the hills.
    const hill = (r0, r1, h0, h1, col0, col1, seed, lumps) => {
      const rr = mulberry(seed), N = 160;
      const ph = [rr() * 6.28, rr() * 6.28, rr() * 6.28];
      // `k % N`: the harmonics are not whole multiples of the circle, so the
      // profile does not come back to where it started, and at the seam the
      // last quad and the first stood at different heights with sky between.
      const prof = (k) => {
        const a = ((k % N) / N) * Math.PI * 2;
        const w = 0.5 + 0.25 * Math.sin(a * lumps + ph[0]) + 0.17 * Math.sin(a * lumps * 2.3 + ph[1])
          + 0.08 * Math.sin(a * lumps * 5.1 + ph[2]);
        return h1 * Math.max(0.15, w);
      };
      // The inner edge sits on whatever the ground is doing there (clamped onto
      // the plate), not at one height: the field is not flat, and where it
      // stood higher than `h0` there was a slot of sky between the two.
      // `r0` null means "start at the edge of the ground plate": the ray from
      // the centre to the rectangle the plate is drawn over. A circle cannot do
      // that job - inscribed, it rose over the far ends of the circuit itself
      // and buried a stretch of road; circumscribed, it leaves sky in the gaps.
      const hx = (gx1 - gx0) / 2, hz = (gz1 - gz0) / 2;
      const rad = (a) => r0 != null ? r0
        : Math.min(hx / Math.max(1e-6, Math.abs(Math.cos(a))), hz / Math.max(1e-6, Math.abs(Math.sin(a))));
      const inner = (a) => {
        if (h0 != null) return h0;
        const r = rad(a);
        return terrain.height(cxm + Math.cos(a) * r, czm + Math.sin(a) * r) - 0.4;
      };
      for (let k = 0; k < N; k++) {
        const a0 = (k / N) * Math.PI * 2, a1 = ((k + 1) / N) * Math.PI * 2;
        const A = (r, a, y) => [cxm + Math.cos(a) * r, y, czm + Math.sin(a) * r];
        const y0 = inner(a0), y1 = inner(a1), q0 = rad(a0), q1 = rad(a1);
        solid.quadV(A(q0, a0, y0), A(r1, a0, floorY + prof(k)), A(r1, a1, floorY + prof(k + 1)),
                    A(q1, a1, y1), col0, col1, col1, col0);
        solid.quadV(A(q0, a0, y0), A(q1, a1, y1), A(r1, a1, floorY + prof(k + 1)),
                    A(r1, a0, floorY + prof(k)), col0, col0, col1, col1);
      }
    };
    hill(null, half + 380, null, 46, shade(pal.ground, -0.12), 0x355f30, 0x41a5, 5);
    // The mountains start right behind the hills rather than out on their own
    // ring: with open sky between the two, every view from above - the cover
    // shot is one - showed a white band round the world.
    hill(half + 370, half + 1250, floorY + 4, 170, 0x4f6f4c, 0x8fa3b2, 0x7a11, 3);
  }
})();
