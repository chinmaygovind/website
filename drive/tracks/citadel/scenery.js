(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.citadel = { props: props, movers: movers };

  const STEPS = 120;               // physics steps a second
  const LAVA_DECK = 7.0;           // track.py's, which the palette also reads
  // How far short of the Hall's end its geyser stands. Far enough back that it
  // is under the *start* of the rampart's hole, so a launched car has the whole
  // hole ahead of it to rise through before the far lip.
  const HALL_LEAD = 30;
  // Hazard geysers per grate run after the Hall, in lap order: the forge, the
  // Geyser Run, the S-bend home. See `sites`.
  const GEYSERS_PER_RUN = [0, 2, 1, 0];

  const IRON = 0x2b2422;
  const IRON_HOT = 0x5a2a1a;
  const STONE = 0x3a3436;
  const STONE_DARK = 0x262123;
  const FLAME = 0xffb03a;
  const CRUST = 0x26232b;

  // Runs of consecutive stations with a flag, as [first, last] index pairs.
  function runs(line, test) {
    const out = [];
    let a = -1;
    for (let i = 0; i < line.length; i++) {
      if (test(line[i])) { if (a < 0) a = i; }
      else if (a >= 0) { out.push([a, i - 1]); a = -1; }
    }
    if (a >= 0) out.push([a, line.length - 1]);
    return out;
  }

  // Which way the road is bending at station i: +1 right, -1 left, 0 straight.
  function bend(line, i) {
    const a = line[Math.max(0, i - 2)].p, b = line[i].p, c = line[Math.min(line.length - 1, i + 2)].p;
    const cr = (b[0] - a[0]) * (c[2] - b[2]) - (b[2] - a[2]) * (c[0] - b[0]);
    return Math.abs(cr) < 1e-3 ? 0 : Math.sign(cr);
  }

  const off = (e, side, d, up) => [
    e.p[0] + e.lat[0] * side * d + e.n[0] * (up || 0),
    e.p[1] + e.lat[1] * side * d + e.n[1] * (up || 0),
    e.p[2] + e.lat[2] * side * d + e.n[2] * (up || 0)];

  /**
   * Where the geysers stand, found off the ribbon so a re-solved lap carries
   * them with it. Three kinds of place:
   *
   * - **The Hall's end.** `HALL_LEAD` short of the first grate run's last
   *   station, on the right-hand half of the road - the outside of the hairpin
   *   that follows, which is where the racing line already is. This is the
   *   shortcut: it throws a car up through the hole in the rampart overhead.
   * - **The apex of grate corners after it**, `GEYSERS_PER_RUN` of them per
   *   run. On the inside line, where a car is turning hardest; launched there
   *   it flies on straight and lands in the lake. Those are the hazards.
   */
  function sites(track, minY) {
    const line = track.line;
    const lava = minY - LAVA_DECK;
    const grates = runs(line, (e) => e.skin);
    const out = [];
    if (!grates.length) return out;
    const hall = grates[0];
    let hi = hall[1], back = 0;
    while (hi > hall[0] && back < HALL_LEAD) {
      back += Math.hypot(line[hi].p[0] - line[hi - 1].p[0], line[hi].p[2] - line[hi - 1].p[2]);
      hi--;
    }
    const h = line[hi];
    const hp = off(h, 1, h.hw * 0.42);
    out.push({ x: hp[0], z: hp[2], y: lava, road: h.p[1], vel: 50, r: 6.5, height: 60,
               phase: 0 });
    let n = 0;
    for (let g = 1; g < grates.length; g++) {
      const [a, b] = grates[g];
      // Each arc on the run: a contiguous stretch bending one way.
      const arcs = [];
      let i = a;
      while (i <= b) {
        const s = bend(line, i);
        let j = i;
        while (j + 1 <= b && bend(line, j + 1) === s) j++;
        if (s !== 0 && j - i >= 4) arcs.push([i, j, s]);
        i = j + 1;
      }
      // **How many apexes get one, run by run.** A geyser on every grate bend
      // was seven in the back half and too hard to drive: the forge keeps both,
      // the Geyser Run keeps its long middle bend, and the S on the way home
      // has none. Longest bends first, so a cap of one is the middle bend.
      const cap = GEYSERS_PER_RUN[g] != null ? GEYSERS_PER_RUN[g] : 0;
      arcs.sort((p, q) => (q[1] - q[0]) - (p[1] - p[0]));
      for (const [i0, j0, s] of arcs.slice(0, cap)) {
        const e = line[(i0 + j0) >> 1];
        const p = off(e, s, e.hw * 0.4);
        out.push({ x: p[0], z: p[2], y: lava, road: e.p[1], vel: 30, r: 5.5, height: 34,
                   phase: 130 * ++n });
      }
    }
    return out;
  }

  function movers(ctx) {
    return sites(ctx.track, ctx.minY).map((s) => ({
      geyser: true, x: s.x, y: s.y, z: s.z, r: s.r, vel: s.vel, height: s.height,
      top: s.road,
      // Up from the lava to just over the road it comes through, and no
      // further: a car on the rampart jumping the hole flies over the Hall's
      // column untouched.
      reach: s.road - s.y + 3,
      period: 3 * STEPS, burst: STEPS, warn: STEPS, phase: s.phase,
      hot: 0xff6a14, core: 0xffd890,
    }));
  }

  function props(ctx) {
    const { solid, bright, track, minY, shade } = ctx;
    const line = track.line, n = line.length;
    const lava = minY - LAVA_DECK;

    const quad2 = (buf, a, b, c, d, k) => { buf.quad(a, b, c, d, k); buf.quad(a, d, c, b, k); };
    // Whether a post standing from height `y` down to the lake would come
    // through some lower stretch of road on the way. The rampart is laid
    // straight over the Hall, so its columns went down through the grate -
    // stone you could see and drive through. Such a post is simply left out.
    const overRoad = (x, y, z, half) => {
      for (let j = 0; j < n; j++) {
        const r = line[j];
        if (r.p[1] > y - 1.5) continue;
        if (Math.hypot(r.p[0] - x, r.p[2] - z) < r.hw + half + 1) return true;
      }
      return false;
    };

    // --- the grates --------------------------------------------------------
    // Iron over the lake: a bar across at every station, bars along at a
    // fixed pitch, a heavier rail at each edge. Nothing under them, so the
    // fire shows through every gap - which is the point of a grate.
    for (let i = 1; i < n; i++) {
      const a = line[i - 1], b = line[i];
      if (!a.skin || !b.skin) continue;
      const w = Math.min(a.hw, b.hw);
      for (let u = -w; u <= w + 1e-6; u += 2.5) {
        const t = Math.abs(u) > w - 1.3 ? 0.55 : 0.22;
        quad2(solid, off(a, 1, u - t, 0.03), off(b, 1, u - t, 0.03),
              off(b, 1, u + t, 0.03), off(a, 1, u + t, 0.03),
              Math.abs(u) > w - 1.3 ? IRON_HOT : IRON);
      }
      quad2(solid, off(a, -1, w, 0.04), off(a, 1, w, 0.04),
            off(a, 1, w, 0.04 + 0), off(a, -1, w, 0.04), IRON);
      // The crossbar, as a thin box so it has a face from the side as well.
      const m = [(a.p[0] + b.p[0]) / 2, (a.p[1] + b.p[1]) / 2, (a.p[2] + b.p[2]) / 2];
      const dx = b.p[0] - a.p[0], dz = b.p[2] - a.p[2];
      const L = Math.hypot(dx, dz) || 1;
      const fx = dx / L * 0.25, fz = dz / L * 0.25;
      const A = off(a, -1, w, 0.04), B = off(a, 1, w, 0.04);
      quad2(solid, [A[0] - fx, A[1], A[2] - fz], [B[0] - fx, B[1], B[2] - fz],
            [B[0] + fx, B[1], B[2] + fz], [A[0] + fx, A[1], A[2] + fz], IRON);
      // The beams the grate hangs off, under each edge, down into the lake.
      if (i % 6 === 0) {
        for (const side of [-1, 1]) {
          const p = off(a, side, w + 0.4);
          if (overRoad(p[0], p[1], p[2], 0.6)) continue;
          solid.box(p[0], (p[1] + lava) / 2, p[2], 0.6, (p[1] - lava) / 2, 0.6, STONE_DARK);
        }
      }
      void m;
    }

    // --- the curtain wall, towers and torches -----------------------------
    // **Kept well back from the road, on purpose.** A wall at the kerb reads
    // as a barrier, and this track is `exposed` with none: a parapet you could
    // see and not hit would be the one lie on the lap. So the wall stands out
    // in the lake, `WALL_OFF` past the edge, and the edge itself is the drop.
    // Anywhere it would come within `CLEAR` of another piece of road - the
    // Hall and its climb run thirty units apart - it is simply left out.
    const WALL_OFF = 16, CLEAR = 6;
    const clearOfRoad = (x, y, z, half) => {
      for (let j = 0; j < n; j += 2) {
        const r = line[j];
        if (Math.abs(r.p[1] - y) > 40) continue;
        if (Math.hypot(r.p[0] - x, r.p[2] - z) - half < r.hw + CLEAR) return false;
      }
      return true;
    };
    const torch = (x, y, z) => {
      solid.box(x, y - 0.6, z, 0.25, 0.6, 0.25, IRON);
      bright.quad([x - 0.6, y, z], [x + 0.6, y, z], [x, y + 1.6, z], [x, y + 1.6, z], FLAME);
      bright.quad([x, y, z - 0.6], [x, y, z + 0.6], [x, y + 1.6, z], [x, y + 1.6, z], FLAME);
    };
    const flat = (e) => !e.air && (e.n[1] || 0) > 0.95;
    let k = 0;
    for (let i = 0; i < n; i += 2) {
      const e = line[i];
      // Only near the lake. Up on a causeway the fire is far enough down that
      // a wall level with the road hides it, and the columns say enough.
      if (!flat(e) || e.p[1] - lava > 9) continue;
      k++;
      for (const side of [-1, 1]) {
        if (bend(line, i) === side) continue;           // not on the inside of a bend
        const p = off(e, side, e.hw + WALL_OFF);
        if (!clearOfRoad(p[0], e.p[1], p[2], 3)) continue;
        // Low: the lake between the road and the wall is the subject, and a
        // wall over eye height turns it into a canyon.
        const top = e.p[1] + 1.5;
        solid.box(p[0], (top + lava) / 2, p[2], 1.8, (top - lava) / 2, 1.8,
                  shade(STONE, ((i * 7) % 5 - 2) * 0.03));
        if (k % 2 === 0) solid.box(p[0], top + 0.9, p[2], 1.1, 0.9, 1.1, STONE);
        if (k % 6 === 0) {
          const q = off(e, side, e.hw + WALL_OFF - 2.1, 2.6);
          torch(q[0], q[1], q[2]);
        }
      }
    }

    // **The crust, and it is most of the lake.** The Gauntlet's lava reads as
    // molten because it is nearly all covered: dark plates with the fire showing
    // only in the cracks. Bare lava is a flat orange floor. These are this
    // track's own rather than `below`'s, because the engine's are placed with no
    // regard for the road and one stood up through the Hall's grate - and kept
    // `MOAT` clear of every road, so the fire glows right along each edge,
    // which is where the danger is.
    const MOAT = 2.0;
    const nearRoad = (x, z, half, margin) => {
      for (let j = 0; j < n; j += 2) {
        const r = line[j];
        if (Math.hypot(r.p[0] - x, r.p[2] - z) - half < r.hw + margin) return true;
      }
      return false;
    };
    const rnd = ctx.mulberry(4021);
    const bb = ctx.bbox, CR = 12;
    for (let x = bb.x0 - 160; x < bb.x1 + 160; x += CR) {
      for (let z = bb.z0 - 160; z < bb.z1 + 160; z += CR) {
        if (rnd() > 0.88) continue;
        const px = x + (rnd() - 0.5) * 3, pz = z + (rnd() - 0.5) * 3;
        const hx = CR * (0.36 + rnd() * 0.12), hz = CR * (0.36 + rnd() * 0.12);
        if (nearRoad(px, pz, Math.max(hx, hz), MOAT)) continue;
        const h = 0.5 + rnd() * 2.2;
        solid.box(px, lava + h / 2, pz, hx, h / 2, hz, shade(CRUST, (rnd() - 0.45) * 0.5));
      }
    }
    // **Out to the edge of the lava**, where there is no road to keep clear
    // of: bigger plates the further out, so the far lake is crust to the
    // horizon like The Gauntlet's instead of a band of bare orange past the
    // last plate - which is what it was, and from the road it is most of what
    // you see of the lake.
    const IN = 160, OUT = (ctx.pal.below && ctx.pal.below.reach) || 500;
    for (let x = bb.x0 - OUT; x < bb.x1 + OUT; x += 24) {
      for (let z = bb.z0 - OUT; z < bb.z1 + OUT; z += 24) {
        if (x > bb.x0 - IN - 24 && x < bb.x1 + IN && z > bb.z0 - IN - 24 && z < bb.z1 + IN) continue;
        if (rnd() > 0.9) continue;
        const hx = 24 * (0.38 + rnd() * 0.1), hz = 24 * (0.38 + rnd() * 0.1);
        const h = 0.6 + rnd() * 2.4;
        solid.box(x + 12 + (rnd() - 0.5) * 4, lava + h / 2, z + 12 + (rnd() - 0.5) * 4,
                  hx, h / 2, hz, shade(CRUST, (rnd() - 0.45) * 0.5));
      }
    }
    // Hotter streaks in the cracks, so the fire is not one flat colour: thin
    // unlit strips a hair over the lava, mostly hidden under the crust and
    // showing yellow where they cross a crack.
    for (let i = 0; i < 900; i++) {
      const px = bb.x0 - IN + rnd() * (bb.x1 - bb.x0 + 2 * IN);
      const pz = bb.z0 - IN + rnd() * (bb.z1 - bb.z0 + 2 * IN);
      const a = rnd() * Math.PI, L = 6 + rnd() * 16, w = 0.5 + rnd() * 0.9;
      const ux = Math.cos(a) * L / 2, uz = Math.sin(a) * L / 2, vx = -Math.sin(a) * w / 2, vz = Math.cos(a) * w / 2;
      const y = lava + 0.06;
      bright.quad([px - ux - vx, y, pz - uz - vz], [px - ux + vx, y, pz - uz + vz],
                  [px + ux + vx, y, pz + uz + vz], [px + ux - vx, y, pz + uz - vz],
                  rnd() < 0.5 ? 0xffb43c : 0xff8a1e);
    }

    // Spires of black rock standing in the lake, well away from the road, for
    // the skyline the Gauntlet has and an empty lake does not.
    for (let i = 0; i < 70; i++) {
      const px = bb.x0 - 220 + rnd() * (bb.x1 - bb.x0 + 440);
      const pz = bb.z0 - 220 + rnd() * (bb.z1 - bb.z0 + 440);
      const w0 = 5 + rnd() * 9;
      if (nearRoad(px, pz, w0, 30)) continue;
      const hgt = 30 + rnd() * 80, tiers = 3 + Math.floor(rnd() * 3), lean = (rnd() - 0.5) * 0.5;
      let y = lava;
      for (let t = 0; t < tiers; t++) {
        const u = t / tiers, th = hgt / tiers;
        const w = w0 * (1 - u * 0.75);
        solid.box(px + lean * u * w0, y + th / 2, pz + lean * u * w0 * 0.6, w / 2, th / 2, w * 0.8 / 2,
                  shade(CRUST, -0.2 + u * 0.25));
        y += th;
      }
    }

    // A tower on the outside of every corner, where the eye goes on the way in.
    let ci = 0;
    while (ci < n) {
      const s = bend(line, ci);
      let cj = ci;
      while (cj + 1 < n && bend(line, cj + 1) === s) cj++;
      if (s !== 0 && cj - ci >= 6) {
        const e = line[(ci + cj) >> 1];
        if (flat(e)) {
          const p = off(e, -s, e.hw + WALL_OFF + 4);
          if (clearOfRoad(p[0], e.p[1], p[2], 6)) {
            const top = e.p[1] + 16;
            solid.box(p[0], (top + lava) / 2, p[2], 5, (top - lava) / 2, 5, STONE_DARK);
            solid.box(p[0], top + 1, p[2], 6, 1, 6, STONE);
            for (const [mx, mz] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
              solid.box(p[0] + mx * 5, top + 3, p[2] + mz * 5, 1.2, 1.2, 1.2, STONE);
            }
            const q = off(e, -s, e.hw + WALL_OFF - 1.2, 5);
            torch(q[0], q[1], q[2]);
          }
        }
      }
      ci = cj + 1;
    }

    // Stone columns under both edges of the raised road, so nothing floats:
    // the causeway stands in the lake.
    for (let i = 0; i < n; i += 4) {
      const e = line[i];
      if (e.air || e.skin || (e.n[1] || 0) < 0.9) continue;
      if (e.p[1] - lava < 1) continue;
      for (const side of [-1, 1]) {
        const c = off(e, side, e.hw - 1.0, -0.6);
        if (overRoad(c[0], c[1], c[2], 1.0)) continue;
        solid.box(c[0], (c[1] + lava) / 2, c[2], 1.0, (c[1] - lava) / 2, 1.0, STONE_DARK);
      }
    }

    // The keep: a tower in the middle of the wall of death. Its centre is the
    // circle through the banked run's first, middle and last stations - not
    // the average of the steep ones, which only cover the middle of the arc and
    // put the first tower off to one side of it.
    const banked = runs(line, (e) => !e.air && Math.abs(e.n[1]) < 0.9)
      .sort((p, q) => (q[1] - q[0]) - (p[1] - p[0]))[0];
    if (banked && banked[1] - banked[0] > 12) {
      const A = line[banked[0]].p, B = line[(banked[0] + banked[1]) >> 1].p, C = line[banked[1]].p;
      const d = 2 * (A[0] * (B[2] - C[2]) + B[0] * (C[2] - A[2]) + C[0] * (A[2] - B[2]));
      const a2 = A[0] * A[0] + A[2] * A[2], b2 = B[0] * B[0] + B[2] * B[2], c2 = C[0] * C[0] + C[2] * C[2];
      const cx = (a2 * (B[2] - C[2]) + b2 * (C[2] - A[2]) + c2 * (A[2] - B[2])) / d;
      const cz = (a2 * (C[0] - B[0]) + b2 * (A[0] - C[0]) + c2 * (B[0] - A[0])) / d;
      let cy = 0, top = -1e9, rad = 1e9;
      for (let i = banked[0]; i <= banked[1]; i++) {
        const e = line[i];
        cy += e.p[1]; top = Math.max(top, e.p[1]);
        rad = Math.min(rad, Math.hypot(e.p[0] - cx, e.p[2] - cz));
      }
      cy /= banked[1] - banked[0] + 1;
      // **Solid, and as wide as the wall lets it be.** It used to be scenery a
      // third this size, and the inside of the wall of death was open air - so
      // you could jump straight across the circle from one side of the wall to
      // the other and skip it. Now any line across the middle hits stone; what
      // is left are chords near the wall, which save nothing over driving it.
      // `rad - 14` keeps it clear of the ramps' inner kerb (`hw` 10.5 inside
      // the centreline, where the roll is still shallow).
      const r = Math.max(6, rad - 14);
      const h = top + 46;
      const SIDES = 16;
      const ring = (rr, y) => {
        const out = [];
        for (let i = 0; i < SIDES; i++) {
          const a = (i + 0.5) / SIDES * Math.PI * 2;
          out.push([cx + Math.cos(a) * rr, y, cz + Math.sin(a) * rr]);
        }
        return out;
      };
      const lo = ring(r, lava), hi = ring(r, h);
      for (let i = 0; i < SIDES; i++) {
        const j = (i + 1) % SIDES;
        const k = shade(STONE, (i % 2) * 0.05);
        solid.quad(lo[i], hi[i], hi[j], lo[j], k);
        solid.quad(lo[i], lo[j], hi[j], hi[i], k);
        ctx.col.addQuad(lo[i], hi[i], hi[j], lo[j], ctx.KIND.WALL);
      }
      const cap = ring(r + 1.5, h), cap2 = ring(r + 1.5, h + 3);
      for (let i = 0; i < SIDES; i++) {
        const j = (i + 1) % SIDES;
        solid.quad(cap[i], cap2[i], cap2[j], cap[j], STONE_DARK);
        solid.quad(cap[i], cap[j], cap2[j], cap2[i], STONE_DARK);
        solid.quad(cap2[i], [cx, h + 3, cz], cap2[j], cap2[j], STONE_DARK);
        solid.quad(cap2[j], [cx, h + 3, cz], cap2[i], cap2[i], STONE_DARK);
        if (i % 2 === 0) {
          const m = ring(r + 0.8, h + 4.5)[i];
          solid.box(m[0], m[1], m[2], 1.6, 1.5, 1.6, STONE);
        }
      }
      // **The bastion: the open quarter of the wall, filled with stone.** The
      // wall of death turns 270 degrees, so between where it starts (just past
      // the second checkpoint) and where it comes out there is a quarter-circle
      // of air - and the rampart above and the exit road below both run past
      // it. Jumping across that quarter from one to the other skipped the
      // keep. So it is solid, in the collider, out to well past both roads and
      // up to well over the rampart, stopping half a unit short of every edge.
      let s0 = banked[0], s1 = banked[1];
      while (s0 > 0 && Math.abs(line[s0 - 1].n[1]) < 0.999 && !line[s0 - 1].air) s0--;
      while (s1 < n - 1 && Math.abs(line[s1 + 1].n[1]) < 0.999 && !line[s1 + 1].air) s1++;
      const ang = (q) => Math.atan2(q[2] - cz, q[0] - cx);
      const aS = ang(line[s0].p), aM = ang(B), aE = ang(line[s1].p);
      const TAU = Math.PI * 2, norm = (x) => ((x % TAU) + TAU) % TAU;
      const dir = norm(aM - aS) < Math.PI ? 1 : -1;      // which way round the wall goes
      const gap = norm((aS - aE) * dir);
      const hB = top + 18, BH = 2.6;
      for (let rr = r + 1; rr < rad + 34; rr += 4) {
        const steps = Math.max(1, Math.ceil(gap * rr / 4));
        for (let q = 0; q <= steps; q++) {
          const a = aE + dir * gap * (q / steps);
          const px = cx + Math.cos(a) * rr, pz = cz + Math.sin(a) * rr;
          let clear = true;
          for (let j = 0; j < n && clear; j++) {
            const e = line[j];
            if (Math.hypot(e.p[0] - px, e.p[2] - pz) < e.hw + BH + 0.5) clear = false;
          }
          if (!clear) continue;
          const y0 = lava, y1 = hB;
          solid.box(px, (y0 + y1) / 2, pz, BH, (y1 - y0) / 2, BH, shade(STONE, ((q * 3 + rr) % 5 - 2) * 0.025));
          const P = (sx, sz, y) => [px + sx * BH, y, pz + sz * BH];
          ctx.col.addQuad(P(-1, -1, y0), P(1, -1, y0), P(1, -1, y1), P(-1, -1, y1), ctx.KIND.WALL);
          ctx.col.addQuad(P(1, -1, y0), P(1, 1, y0), P(1, 1, y1), P(1, -1, y1), ctx.KIND.WALL);
          ctx.col.addQuad(P(1, 1, y0), P(-1, 1, y0), P(-1, 1, y1), P(1, 1, y1), ctx.KIND.WALL);
          ctx.col.addQuad(P(-1, 1, y0), P(-1, -1, y0), P(-1, -1, y1), P(-1, 1, y1), ctx.KIND.WALL);
        }
      }

      // Windows lit from inside.
      for (let y = cy; y < h - 6; y += 12) {
        const ap = r * Math.cos(Math.PI / SIDES) + 0.05;
        for (const [dx, dz] of [[ap, 0], [-ap, 0], [0, ap], [0, -ap]]) {
          const px = cx + dx, pz = cz + dz;
          const ax = dz !== 0 ? 1.2 : 0, az = dx !== 0 ? 1.2 : 0;
          bright.quad([px - ax, y, pz - az], [px + ax, y, pz + az],
                      [px + ax, y + 3.5, pz + az], [px - ax, y + 3.5, pz - az], FLAME);
        }
      }
    }
  }
})();
