// Harvest: the maple tunnel, the barn you drive through, the farm round it and
// a post-and-rail fence round the whole lap.
//
// Everything is found off the ribbon rather than placed by fraction:
//   the tunnel  the longest straight on the lap
//   the barn    the longest *flat* straight that is not the start straight,
//               at its far end, so its checkpoint gate is behind you first
//
// **In the collider:** the maple trunks, the barn's walls and doors, and the
// fence. The fence is drawn here instead of by the engine's armco (`armco: 0`
// in the palette) because an armco is one solid strip and this is posts and
// rails; it keeps the armco's one collision quad per span.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.harvest = { props: props, movers: movers };

  const TRUNK = 0x4a3324;
  const CROWNS = [0xb8241a, 0xd0401c, 0xe0661c, 0xc8321e, 0xf0a020];
  const RED = 0x9e2a1e, TRIM = 0xf0ebe0, ROOF = 0x585c60, DARK = 0x3a2414;
  const HAY = 0xd9a440, HAY_END = 0xe8c070, BEAM = 0x5a3e28;
  const SILO = 0x9aa4ac, SILO_BAND = 0x6f7880;
  const POST = 0x5e4630, PLANK = 0x8a6a48;
  const STONE = 0x8a847a, IRON = 0x2c2a28, GLASS = 0xffc670, LAMP = 0xffd27a;
  const PUMPKIN = 0xc83000, STEM = 0x2a5010;

  const TREE_EVERY = 10, SPILL = 30;
  const FENCE = 20, POST_EVERY = 3.6;
  const BARN_LEN = 44, BARN_W = 16, BARN_H = 11, BARN_MARGIN = 26;

  function props(ctx) {
    const { solid, bright, col, KIND, track, ground, face, terrain, mulberry, shade } = ctx;
    const line = track.line, n = line.length;
    const rnd = mulberry(0x68617276);
    const { tun, barnRun } = layout(line);

    tunnel(spill(line, tun));
    const barn = barnRun ? barnAt(barnRun) : null;
    fence(barn);
    fields(barn);
    if (barn) herd(barn);

    // -- helpers -----------------------------------------------------------
    function add(p, v, k) { return [p[0] + v[0] * k, p[1] + v[1] * k, p[2] + v[2] * k]; }
    function hgt(x, z, fall) { return terrain ? terrain.height(x, z) - 0.3 : fall; }

    // A box in a frame (origin O, forward F, across Lt, world up), so a box
    // stands square to a diagonal road. `solid.box` is axis aligned.
    function boxF(fr, s0, s1, l0, l1, h0, h1, c, buf) {
      const P = (s, l, h) => fr.pt(s, l, h);
      const q = buf ? (a, b, cc, d, k) => { buf.quad(a, b, cc, d, k); buf.quad(a, d, cc, b, k); } : face;
      q(P(s0, l0, h1), P(s1, l0, h1), P(s1, l1, h1), P(s0, l1, h1), c);
      q(P(s0, l0, h0), P(s1, l0, h0), P(s1, l0, h1), P(s0, l0, h1), shade(c, -0.08));
      q(P(s0, l1, h0), P(s1, l1, h0), P(s1, l1, h1), P(s0, l1, h1), shade(c, -0.08));
      q(P(s0, l0, h0), P(s0, l1, h0), P(s0, l1, h1), P(s0, l0, h1), shade(c, -0.14));
      q(P(s1, l0, h0), P(s1, l1, h0), P(s1, l1, h1), P(s1, l0, h1), shade(c, -0.14));
    }
    function frame(O, F, Lt) {
      return { O, F, Lt, pt: (s, l, h) => [O[0] + F[0] * s + Lt[0] * l, O[1] + h,
                                           O[2] + F[2] * s + Lt[2] * l] };
    }
    // A cylinder about a horizontal or vertical axis, as a ring of quads.
    function cyl(c, ax, r, len, color, end, sides = 12) {
      const up = Math.abs(ax[1]) > 0.5;
      const u = up ? [1, 0, 0] : [0, 1, 0];
      const v = up ? [0, 0, 1] : [ax[2], 0, -ax[0]];
      const ring = (k) => {
        const pts = [];
        for (let j = 0; j < sides; j++) {
          const a = j / sides * Math.PI * 2;
          pts.push(add(add(add(c, ax, k * len / 2), u, Math.cos(a) * r), v, Math.sin(a) * r));
        }
        return pts;
      };
      const A = ring(-1), B = ring(1);
      for (let j = 0; j < sides; j++) {
        const k = (j + 1) % sides;
        if (color != null) face(A[j], B[j], B[k], A[k], shade(color, (j % 2 ? -0.05 : 0.03)));
        if (end != null) {
          face(A[j], A[k], add(c, ax, -len / 2), add(c, ax, -len / 2), end);
          face(B[j], B[k], add(c, ax, len / 2), add(c, ax, len / 2), end);
        }
      }
    }

    // -- the maple tunnel ----------------------------------------------------
    function tunnel([a, b]) {
      let d = 0, next = 0;
      for (let i = a; i <= b; i++) {
        if (i > a) d += dist(line[i - 1].p, line[i].p);
        if (d < next) continue;
        next = d + TREE_EVERY * (0.8 + rnd() * 0.4);
        for (const s of [-1, 1]) maple(i, s);
      }
    }

    function maple(i, s) {
      const e = line[i];
      const off = s * (e.hw + 4 + rnd() * 1.5);
      const x = e.p[0] + e.lat[0] * off, z = e.p[2] + e.lat[2] * off;
      const g = ground(i, off), road = e.p[1];
      const tw = 0.45 + rnd() * 0.15;
      const top = road + 9 + rnd() * 1.5;
      solid.box(x, (g + top) / 2, z, tw, (top - g) / 2, tw, TRUNK);
      const lo = [x - tw, g, z - tw], hi = [x + tw, top, z + tw];
      col.addQuad([lo[0], lo[1], lo[2]], [hi[0], lo[1], lo[2]], [hi[0], hi[1], lo[2]], [lo[0], hi[1], lo[2]], KIND.WALL);
      col.addQuad([hi[0], lo[1], lo[2]], [hi[0], lo[1], hi[2]], [hi[0], hi[1], hi[2]], [hi[0], hi[1], lo[2]], KIND.WALL);
      col.addQuad([hi[0], lo[1], hi[2]], [lo[0], lo[1], hi[2]], [lo[0], hi[1], hi[2]], [hi[0], hi[1], hi[2]], KIND.WALL);
      col.addQuad([lo[0], lo[1], hi[2]], [lo[0], lo[1], lo[2]], [lo[0], hi[1], lo[2]], [lo[0], hi[1], hi[2]], KIND.WALL);
      // The crown sits on the trunk and leans in over the road: its centre is
      // at most three units in from the trunk and every lobe is wider than
      // that, so the trunk always runs up into leaves.
      const inward = 1.5 + rnd() * 1.5;
      const cx = x - e.lat[0] * s * inward, cz = z - e.lat[2] * s * inward;
      // A limb from the trunk top to the crown, in steps, so the lean is held up.
      for (let k = 1; k <= 3; k++) {
        const t = k / 3;
        solid.box(x + (cx - x) * t, top - 0.6 + t * 0.8, z + (cz - z) * t,
                  tw * 0.75, 0.35, tw * 0.75, TRUNK);
      }
      const crown = CROWNS[Math.floor(rnd() * CROWNS.length)];
      for (let k = 0, m = 5 + Math.floor(rnd() * 3); k < m; k++) {
        const a = rnd() * Math.PI * 2, r = rnd() * 2.2;
        const w = 2.3 + rnd() * 1.1;
        solid.box(cx + Math.cos(a) * r, top + 0.6 + rnd() * 3.2, cz + Math.sin(a) * r,
                  w, 1.1 + rnd() * 0.9, w * (0.8 + rnd() * 0.4),
                  shade(crown, (rnd() - 0.5) * 0.22));
      }
    }

    // -- the barn ------------------------------------------------------------
    // A wide gambrel barn the road runs down the middle of. Each gable end is
    // a wall with a doorway in the middle and the two sliding doors run back
    // across the wall either side of it, the way a real barn's are.
    function barnAt(r) {
      let b = r.b, s = 0;
      while (b > r.a && s < BARN_MARGIN) { s += dist(line[b - 1].p, line[b].p); b--; }
      let a = b; s = 0;
      while (a > r.a && s < BARN_LEN) { s += dist(line[a - 1].p, line[a].p); a--; }
      const O = line[a].p, E = line[b].p;
      const L = dist(O, E);
      const F = [(E[0] - O[0]) / L, 0, (E[2] - O[2]) / L];
      const fr = frame(O, F, line[a].lat);
      const W = BARN_W, H = BARN_H, D = -1.6, OPEN = 8.5, DOOR_H = 10;
      const P = fr.pt;
      const wallQ = (a1, b1, c1, d1) => col.addQuad(a1, b1, c1, d1, KIND.WALL);
      const strip = (se, la, ha, lb, hb, t, c) => {
        const dl = lb - la, dh = hb - ha, m = Math.hypot(dl, dh);
        const nl = -dh / m * t, nh = dl / m * t;
        face(P(se, la - nl, ha - nh), P(se, lb - nl, hb - nh),
             P(se, lb + nl, hb + nh), P(se, la + nl, ha + nh), c);
      };
      // An X-braced door or panel on the plane s = se, between l0..l1, h0..h1.
      const door = (se, l0, l1, h0, h1, c) => {
        face(P(se, l0, h0), P(se, l1, h0), P(se, l1, h1), P(se, l0, h1), c);
        const so = se + (se > L / 2 ? 0.06 : -0.06), t = 0.32;
        strip(so, l0, h0 + t, l1, h0 + t, t, TRIM); strip(so, l0, h1 - t, l1, h1 - t, t, TRIM);
        strip(so, l0 + t * Math.sign(l1 - l0), h0, l0 + t * Math.sign(l1 - l0), h1, t, TRIM);
        strip(so, l1 - t * Math.sign(l1 - l0), h0, l1 - t * Math.sign(l1 - l0), h1, t, TRIM);
        strip(so, l0, h0, l1, h1, t * 0.8, TRIM); strip(so, l1, h0, l0, h1, t * 0.8, TRIM);
      };

      // Stone footing all round, so it stands on the ground rather than on a line.
      for (const sd of [-1, 1]) {
        boxF(fr, -0.3, L + 0.3, sd > 0 ? W - 0.3 : -W - 0.3, sd > 0 ? W + 0.3 : -W + 0.3, D, 0.9, STONE);
        boxF(fr, -0.3, 0.3, sd * OPEN, sd * (W + 0.3), D, 0.9, STONE);
        boxF(fr, L - 0.3, L + 0.3, sd * OPEN, sd * (W + 0.3), D, 0.9, STONE);
      }

      // Long walls: board-and-batten, a white band under the eave, white
      // corner boards, and a row of windows.
      for (const sd of [-1, 1]) {
        const l = sd * W, lo = sd * (W + 0.07);
        const boards = 20;
        for (let k = 0; k < boards; k++) {
          const s0 = L * k / boards, s1 = L * (k + 1) / boards;
          face(P(s0, l, 0.9), P(s1, l, 0.9), P(s1, l, H), P(s0, l, H), shade(RED, k % 2 ? -0.05 : 0.02));
        }
        face(P(-0.1, lo, 0.9), P(0.9, lo, 0.9), P(0.9, lo, H), P(-0.1, lo, H), TRIM);
        face(P(L - 0.9, lo, 0.9), P(L + 0.1, lo, 0.9), P(L + 0.1, lo, H), P(L - 0.9, lo, H), TRIM);
        face(P(0, lo, H - 0.7), P(L, lo, H - 0.7), P(L, lo, H), P(0, lo, H), TRIM);
        for (let k = 1; k < 5; k++) {
          const sm = L * k / 5;
          face(P(sm - 1.5, lo, 3.4), P(sm + 1.5, lo, 3.4), P(sm + 1.5, lo, 6.6), P(sm - 1.5, lo, 6.6), TRIM);
          const gl = sd * (W + 0.12);
          bright.quad(P(sm - 1.1, gl, 3.8), P(sm + 1.1, gl, 3.8), P(sm + 1.1, gl, 6.2), P(sm - 1.1, gl, 6.2), GLASS);
          bright.quad(P(sm - 1.1, gl, 3.8), P(sm - 1.1, gl, 6.2), P(sm + 1.1, gl, 6.2), P(sm + 1.1, gl, 3.8), GLASS);
          const gm = sd * (W + 0.16);
          face(P(sm - 0.1, gm, 3.8), P(sm + 0.1, gm, 3.8), P(sm + 0.1, gm, 6.2), P(sm - 0.1, gm, 6.2), TRIM);
          face(P(sm - 1.1, gm, 4.9), P(sm + 1.1, gm, 4.9), P(sm + 1.1, gm, 5.1), P(sm - 1.1, gm, 5.1), TRIM);
        }
        wallQ(P(0, l, D), P(L, l, D), P(L, l, H), P(0, l, H));
      }

      // The gable ends.
      const K = 0.62, KH = H + 5.5, RH = H + 9;
      for (const [se, out] of [[0, -1], [L, 1]]) {
        const o = (k) => se + out * k;
        // The wall either side of the doorway, and above it up to the eave.
        for (const sd of [-1, 1]) {
          face(P(se, sd * OPEN, 0.9), P(se, sd * W, 0.9), P(se, sd * W, H), P(se, sd * OPEN, H), RED);
          wallQ(P(se, sd * OPEN, D), P(se, sd * W, D), P(se, sd * W, H), P(se, sd * OPEN, H));
          // The door, slid open across that wall.
          door(o(0.12), sd * (OPEN + 0.2), sd * (OPEN + 8), 0.9, DOOR_H - 0.3, shade(RED, -0.06));
          // Its track, a dark rail over the doorway and the door.
          boxF(fr, Math.min(se, o(0.3)), Math.max(se, o(0.3)), sd > 0 ? -OPEN - 1 : -(W - 0.5),
               sd > 0 ? W - 0.5 : OPEN + 1, DOOR_H - 0.2, DOOR_H + 0.2, IRON);
        }
        face(P(se, -OPEN, DOOR_H), P(se, OPEN, DOOR_H), P(se, OPEN, H), P(se, -OPEN, H), RED);
        // The gable itself.
        face(P(se, -W, H), P(se, -W * K, KH), P(se, W * K, KH), P(se, W, H), RED);
        face(P(se, -W * K, KH), P(se, 0, RH), P(se, 0, RH), P(se, W * K, KH), RED);
        // White trim up the roofline and round the doorway.
        strip(o(0.07), -W, H, -W * K, KH, 0.3, TRIM); strip(o(0.07), -W * K, KH, 0, RH, 0.3, TRIM);
        strip(o(0.07), W, H, W * K, KH, 0.3, TRIM); strip(o(0.07), W * K, KH, 0, RH, 0.3, TRIM);
        strip(o(0.07), -OPEN, 0.9, -OPEN, DOOR_H, 0.3, TRIM);
        strip(o(0.07), OPEN, 0.9, OPEN, DOOR_H, 0.3, TRIM);
        strip(o(0.07), -W, H - 0.35, W, H - 0.35, 0.35, TRIM);
        // The hayloft door, with the hoist beam over it.
        door(o(0.1), -2.4, 2.4, H + 1.2, H + 5.6, shade(RED, -0.1));
        boxF(fr, Math.min(se, o(3.2)), Math.max(se, o(3.2)), -0.3, 0.3, H + 6.6, H + 7.2, BEAM);
        boxF(fr, Math.min(o(2.9), o(3.1)), Math.max(o(2.9), o(3.1)), -0.06, 0.06, H + 4.6, H + 6.6, IRON);
      }

      // The gambrel roof, with a fascia so it has thickness, overhanging the
      // walls and both gables.
      const s0 = -1.6, s1 = L + 1.6;
      const eave = W + 1.6, eh = H - 0.6;
      for (const sd of [-1, 1]) {
        face(P(s0, sd * eave, eh), P(s1, sd * eave, eh), P(s1, sd * W * K, KH), P(s0, sd * W * K, KH), ROOF);
        face(P(s0, sd * W * K, KH), P(s1, sd * W * K, KH), P(s1, 0, RH), P(s0, 0, RH), shade(ROOF, 0.07));
        face(P(s0, sd * eave, eh - 0.5), P(s1, sd * eave, eh - 0.5), P(s1, sd * eave, eh), P(s0, sd * eave, eh), TRIM);
        for (const se of [s0, s1]) {
          strip(se, sd * eave, eh - 0.25, sd * W * K, KH - 0.25, 0.25, TRIM);
          strip(se, sd * W * K, KH - 0.25, 0, RH - 0.25, 0.25, TRIM);
        }
      }
      boxF(fr, s0, s1, -0.4, 0.4, RH - 0.1, RH + 0.35, shade(ROOF, -0.12));
      // A cupola with a weathervane.
      boxF(fr, L / 2 - 1.8, L / 2 + 1.8, -1.8, 1.8, RH - 0.5, RH + 2.8, TRIM);
      boxF(fr, L / 2 - 1.2, L / 2 + 1.2, -1.85, 1.85, RH + 0.4, RH + 2.2, DARK);
      boxF(fr, L / 2 - 2.3, L / 2 + 2.3, -2.3, 2.3, RH + 2.8, RH + 3.3, ROOF);
      boxF(fr, L / 2 - 0.06, L / 2 + 0.06, -0.06, 0.06, RH + 3.3, RH + 5.5, IRON);
      boxF(fr, L / 2 - 1.1, L / 2 + 1.1, -0.05, 0.05, RH + 4.8, RH + 5.2, IRON);

      // Inside: posts down both sides of the drive, tie beams across, hay in
      // the bays behind the posts, and lanterns.
      for (let k = 1; k < 5; k++) {
        const sm = L * k / 5;
        for (const sd of [-1, 1]) boxF(fr, sm - 0.35, sm + 0.35, sd * 8.2, sd * 8.9, D, H, BEAM);
        boxF(fr, sm - 0.35, sm + 0.35, -W, W, H - 1.1, H - 0.4, BEAM);
        for (const sd of [-1, 1]) {
          boxF(fr, sm - 0.3, sm + 0.3, sd * 8.1, sd * 8.25, 5.6, 6.6, LAMP, bright);
        }
      }
      for (const sd of [-1, 1]) {
        for (let s = 1.5; s < L - 2.5; s += 2.7) {
          if (rnd() < 0.15 || stall(s, sd, L)) continue;
          const l0 = sd * 9.5, l1 = sd * (W - 0.3);
          const lo = Math.min(l0, l1), hi = Math.max(l0, l1);
          const tiers = 1 + Math.floor(rnd() * 3);
          for (let t = 0; t < tiers; t++) {
            boxF(fr, s + 0.1, s + 2.5, lo, hi, D + 1.6 + t * 1.3, D + 2.9 + t * 1.3, shade(HAY, (rnd() - 0.5) * 0.1));
          }
        }
      }

      // Cows in the two stalls the hay leaves empty, facing the drive.
      const moo = mulberry(0x636f7773);
      for (const sd of [-1, 1]) {
        for (let s = 1.5; s < L - 2.5; s += 2.7) {
          if (stall(s, sd, L)) cow(fr.pt(s + 1.3, sd * 13.5, 0), Math.atan2(-fr.Lt[2] * sd, -fr.Lt[0] * sd), moo);
        }
      }

      // The silo beside it, past the fence.
      const sc = P(L * 0.3, W + 20, 0);
      const sg = hgt(sc[0], sc[2], O[1] - 1.2);
      cyl([sc[0], sg + 13, sc[2]], [0, 1, 0], 4.6, 26, SILO, null, 18);
      for (const bh of [4, 10, 16, 22]) cyl([sc[0], sg + bh, sc[2]], [0, 1, 0], 4.7, 0.5, SILO_BAND, null, 18);
      for (let k = 0; k < 5; k++) {
        const t0 = k / 5 * Math.PI / 2, t1 = (k + 1) / 5 * Math.PI / 2;
        const rr = 4.6 * Math.cos((t0 + t1) / 2), hh = 4.6 * Math.sin((t0 + t1) / 2);
        cyl([sc[0], sg + 26 + hh, sc[2]], [0, 1, 0], rr, 4.6 * (Math.sin(t1) - Math.sin(t0)) + 0.05,
            SILO_BAND, k === 4 ? SILO_BAND : null, 18);
      }

      return { a: a - 6, b: b + 6, fr, L };
    }

    // -- the fence -----------------------------------------------------------
    // Post and rail, chest high on a car: posts every few units and three
    // rails between them, each rail a plank with a face both ways and a top.
    function fence(barn) {
      for (const sd of [-1, 1]) {
        let prev = null;
        for (let i = 0; i < n; i++) {
          if (barn && i >= barn.a && i <= barn.b) { prev = null; continue; }
          const e = line[i], off = sd * FENCE;
          const x = e.p[0] + e.lat[0] * off, z = e.p[2] + e.lat[2] * off;
          if (terrain && terrain.toRoad(x, z) < FENCE - 2.5) { prev = null; continue; }
          if (prev && Math.hypot(x - prev[0], z - prev[2]) < POST_EVERY) continue;
          const g = ground(i, off);
          solid.box(x, g + 1.05, z, 0.3, 1.25, 0.3, POST);
          solid.box(x, g + 2.35, z, 0.36, 0.08, 0.36, shade(POST, -0.1));
          if (prev && Math.hypot(x - prev[0], z - prev[2]) < 7) {
            const dx = x - prev[0], dz = z - prev[2], m = Math.hypot(dx, dz);
            const nx = -dz / m * 0.09, nz = dx / m * 0.09;
            for (const h of [0.75, 1.45, 2.1]) {
              const A = [prev[0], prev[1] + h, prev[2]], B = [x, g + h, z];
              const t = 0.2;
              face([A[0] + nx, A[1] - t, A[2] + nz], [B[0] + nx, B[1] - t, B[2] + nz],
                   [B[0] + nx, B[1] + t, B[2] + nz], [A[0] + nx, A[1] + t, A[2] + nz], PLANK);
              face([A[0] - nx, A[1] - t, A[2] - nz], [B[0] - nx, B[1] - t, B[2] - nz],
                   [B[0] - nx, B[1] + t, B[2] - nz], [A[0] - nx, A[1] + t, A[2] - nz], shade(PLANK, -0.08));
              face([A[0] - nx, A[1] + t, A[2] - nz], [B[0] - nx, B[1] + t, B[2] - nz],
                   [B[0] + nx, B[1] + t, B[2] + nz], [A[0] + nx, A[1] + t, A[2] + nz], shade(PLANK, 0.1));
            }
            col.addQuad([prev[0], prev[1] - 0.5, prev[2]], [x, g - 0.5, z],
                        [x, g + 2.4, z], [prev[0], prev[1] + 2.4, prev[2]], KIND.WALL);
          }
          prev = [x, g, z];
        }
      }
    }

    // -- the fields ------------------------------------------------------------
    function fields(barn) {
      const clear = (x, z, d) => !terrain || terrain.toRoad(x, z) > d;
      const spot = (i, off) => {
        const e = line[Math.max(0, Math.min(n - 1, i))];
        return [e.p[0] + e.lat[0] * off, e.p[2] + e.lat[2] * off, e];
      };
      // A round bale lying on its side, its rolled end facing out.
      const bale = (x, z, y, a) => {
        cyl([x, y + 1.6, z], [Math.cos(a), 0, Math.sin(a)], 1.6, 2.2, HAY, HAY_END, 16);
        cyl([x, y + 1.6, z], [Math.cos(a), 0, Math.sin(a)], 0.7, 2.24, null, shade(HAY_END, -0.12), 10);
      };
      // A stack of them, three on the ground and two on top, just past the
      // fence where you see it from the road.
      const stack = (i, sd) => {
        const e = line[i];
        const F = [e.lat[2], 0, -e.lat[0]];
        const off = sd * (FENCE + 5);
        const [cx, cz] = spot(i, off);
        if (!clear(cx, cz, FENCE + 2)) return;
        const g = hgt(cx, cz, e.p[1] - 1.2);
        const a = Math.atan2(e.lat[2], e.lat[0]);
        for (const [k, up] of [[-1.7, 0], [0, 0], [1.7, 0], [-0.85, 1], [0.85, 1]]) {
          bale(cx + F[0] * k * 2, cz + F[2] * k * 2, g + up * 2.6, a);
        }
      };
      for (const f of [0.13, 0.36, 0.52, 0.64, 0.93]) stack(Math.round(f * (n - 1)), f * 100 % 2 < 1 ? 1 : -1);
      if (barn) {
        for (let k = 0; k < 6; k++) {
          const p = barn.fr.pt(-8 - k * 6, (k % 2 ? 1 : -1) * (FENCE + 4 + rnd() * 6), 0);
          if (clear(p[0], p[2], FENCE + 2)) bale(p[0], p[2], hgt(p[0], p[2], line[0].p[1] - 1.2), rnd() * 3);
        }
      }

      // The pumpkin patch: rows of them, big enough to read at speed, outside
      // the fence along the start straight, with a scarecrow keeping watch.
      const i0 = Math.round(n * 0.025), i1 = Math.round(n * 0.08);
      for (let i = i0; i < i1; i += 2) {
        for (let row = 0; row < 6; row++) {
          if (rnd() < 0.25) continue;
          const off = -(FENCE + 3 + row * 3.2 + rnd() * 1.2);
          const [x0, z0, e] = spot(i, off);
          const x = x0 + (rnd() - 0.5) * 1.5, z = z0 + (rnd() - 0.5) * 1.5;
          if (!clear(x, z, FENCE + 1.5)) continue;
          pumpkin(x, z, hgt(x, z, e.p[1] - 1.2), 1.2 + rnd() * 0.7);
        }
      }
      const [sx, sz, se] = spot(Math.round((i0 + i1) / 2), -(FENCE + 11));
      if (clear(sx, sz, FENCE + 2)) scarecrow(sx, sz, hgt(sx, sz, se.p[1] - 1.2));
    }

    // Cows out in the paddock either side of the barn, grazing.
    function herd(barn) {
      const moo = mulberry(0x6865726421);
      for (let k = 0; k < 14; k++) {
        const sd = k % 2 ? 1 : -1;
        const p = barn.fr.pt(-20 + moo() * (barn.L + 40), sd * (FENCE + 5 + moo() * 18), 0);
        if (terrain && terrain.toRoad(p[0], p[2]) < FENCE + 3) continue;
        if (sd > 0 && Math.hypot(...[0, 2].map(j => p[j] - barn.fr.pt(barn.L * 0.3, 36, 0)[j])) < 8) continue;
        p[1] = hgt(p[0], p[2], line[0].p[1] - 1.2);
        cow(p, moo() * 6.28, moo, moo() < 0.6);
      }
    }

    // A Holstein, standing still, built from the same boxes a walking one is.
    function cow(at, yaw, r, graze) {
      const fr = frame(at, [Math.cos(yaw), 0, Math.sin(yaw)], [-Math.sin(yaw), 0, Math.cos(yaw)]);
      for (const [s0, s1, l0, l1, h0, h1, c] of cowParts(r, graze)) boxF(fr, s0, s1, l0, l1, h0, h1, c);
    }

    // Ribbed: three overlapping boxes, the middle one tallest, read as a
    // pumpkin from the road where one box reads as a crate.
    function pumpkin(x, z, g, r) {
      // Unlit, so they stay orange with the low sun behind them: lit, they
      // went brown against the grass and could not be seen from the road.
      // Authored dark and red because an unlit colour is lifted hard on its
      // way to the screen: 0xe0661a came out a pale cream.
      const c = shade(PUMPKIN, (rnd() - 0.5) * 0.16);
      bright.box(x, g + r * 0.62, z, r, r * 0.6, r * 0.62, shade(c, -0.1));
      bright.box(x, g + r * 0.66, z, r * 0.62, r * 0.66, r, shade(c, -0.16));
      bright.box(x, g + r * 0.7, z, r * 0.8, r * 0.7, r * 0.8, c);
      solid.box(x, g + r * 1.5, z, r * 0.12, r * 0.22, r * 0.12, STEM);
      solid.box(x + r * 0.5, g + r * 1.42, z, r * 0.4, r * 0.06, r * 0.22, shade(STEM, 0.1));
    }

    function scarecrow(x, z, g) {
      solid.box(x, g + 2.4, z, 0.18, 2.4, 0.18, POST);
      solid.box(x, g + 3.7, z, 1.9, 0.15, 0.15, POST);
      solid.box(x, g + 3.3, z, 0.7, 1.0, 0.45, 0x5b6f9e);
      solid.box(x, g + 3.75, z, 1.5, 0.28, 0.32, 0x9b3b2a);
      solid.box(x - 1.75, g + 3.7, z, 0.22, 0.22, 0.22, HAY);
      solid.box(x + 1.75, g + 3.7, z, 0.22, 0.22, 0.22, HAY);
      solid.box(x, g + 4.75, z, 0.45, 0.48, 0.45, 0xe8c99a);
      solid.box(x, g + 5.25, z, 0.85, 0.06, 0.85, 0x8a6a3a);
      solid.box(x, g + 5.55, z, 0.45, 0.3, 0.45, 0x8a6a3a);
    }
  }

  // Where the set pieces go: the maple tunnel is the longest straight, the
  // barn the longest flat one that is not the start straight.
  function layout(line) {
    const runs = straights(line);
    const tun = runs.reduce((a, r) => (r.len > a.len ? r : a), runs[0]);
    const flat = runs.filter(r => r !== tun && r.a > 0 && r.flat);
    const barnRun = flat.reduce((a, r) => (!a || r.len > a.len ? r : a), null);
    return { tun, barnRun };
  }

  // A Holstein as boxes (s forward, l across, h up from the hooves): white
  // body, black patches, pink nose. `graze` drops the head.
  function cowParts(r, graze) {
    const W = 0xf2eee6, B = 0x1e1c1c, PINK = 0xe8a8a0;
    const out = [[-1.3, 1.3, -0.6, 0.6, 1.0, 2.2, W]];
    const p0 = -1.0 + r() * 0.8, p1 = 0.2 + r() * 0.8;
    out.push([p0, p0 + 0.9, -0.63, 0.63, 1.3 + r() * 0.3, 2.23, B]);
    out.push([p1, p1 + 0.5, -0.63, 0.2, 1.6, 2.23, B]);
    for (const s of [-1, 1]) for (const l of [-1, 1]) {
      out.push([s - 0.15, s + 0.15, l * 0.4 - 0.15, l * 0.4 + 0.15, 0.2, 1.0, W]);
      out.push([s - 0.16, s + 0.16, l * 0.4 - 0.16, l * 0.4 + 0.16, 0, 0.2, B]);
    }
    out.push([-0.7, -0.3, -0.25, 0.25, 0.8, 1.0, PINK]);
    out.push([-1.4, -1.3, -0.05, 0.05, 1.1, 2.1, W]);
    out.push([-1.45, -1.32, -0.1, 0.1, 0.9, 1.15, B]);
    const h = graze ? 0.4 : 1.7;
    if (graze) out.push([1.2, 1.7, -0.25, 0.25, 0.8, 1.9, W]);
    out.push([1.3, 2.1, -0.35, 0.35, h, h + 0.7, B]);
    out.push([2.1, 2.4, -0.3, 0.3, h, h + 0.35, PINK]);
    out.push([1.6, 1.8, -0.55, 0.55, h + 0.7, h + 0.85, W]);
    return out;
  }

  // Two cows wandering back and forth across the road, solid: one in the
  // maple tunnel, one on the way into the barn. Movers, so the anti-cheat's
  // re-drive meets them in the same place the player did (see `Movers`).
  function movers(ctx) {
    const line = ctx.track.line;
    const { tun, barnRun } = layout(line);
    const moo = ctx.mulberry ? ctx.mulberry(0x726f6164) : Math.random;
    const at = [];
    if (barnRun) {
      let i = barnRun.b, d = 0;
      while (i > barnRun.a && d < BARN_MARGIN + BARN_LEN + 30) { d += dist(line[i - 1].p, line[i].p); i--; }
      at.push(i);
    }
    at.push(Math.round((tun.a + tun.b) / 2));
    // The collision box is the cow's own extent: s -1.45..2.4, l +-0.63, h 0..2.4.
    const S = 0.475, H = 1.2;
    return at.map((i, q) => {
      const e = line[i], reach = e.hw * 0.7, side = q % 2 ? 1 : -1;
      const parts = cowParts(moo, false).map(([s0, s1, l0, l1, h0, h1, c]) =>
        [(l0 + l1) / 2, (h0 + h1) / 2 - H, (s0 + s1) / 2 - S, (l1 - l0) / 2, (h1 - h0) / 2, (s1 - s0) / 2, c]);
      return {
        ax: e.p[0] + e.lat[0] * reach * side, az: e.p[2] + e.lat[2] * reach * side,
        bx: e.p[0] - e.lat[0] * reach * side, bz: e.p[2] - e.lat[2] * reach * side,
        y: e.p[1] + H, hx: 0.63, hy: H, hz: 1.925,
        period: [1409, 1201][q % 2], phase: q * 401, parts,
      };
    });
  }

  // Two runs of stalls, one each side, given over to cows instead of hay.
  function stall(s, sd, L) {
    return sd < 0 ? s > L * 0.25 && s < L * 0.5 : s > L * 0.55 && s < L * 0.8;
  }

  function dist(p, q) {
    return Math.hypot(q[0] - p[0], q[1] - p[1], q[2] - p[2]);
  }

  // Every straight on the lap as a station range. A station's `lat` is rounded
  // to three places, so a straight on a diagonal only dots to 0.99996 with
  // itself; the widest arc here is 0.9996.
  function straights(line) {
    const out = [];
    let a = 0, len = 0;
    const close = (b) => {
      if (len > 40) {
        let lo = Infinity, hi = -Infinity;
        for (let k = a; k <= b; k++) { lo = Math.min(lo, line[k].p[1]); hi = Math.max(hi, line[k].p[1]); }
        out.push({ a, b, len, flat: hi - lo < 0.3 });
      }
    };
    for (let i = 1; i < line.length; i++) {
      const u = line[i - 1].lat, v = line[i].lat;
      if (u[0] * v[0] + u[2] * v[2] > 0.9999) len += dist(line[i - 1].p, line[i].p);
      else { close(i - 1); a = i; len = 0; }
    }
    close(line.length - 1);
    return out;
  }

  // A straight widened by SPILL into the corners either end.
  function spill(line, r) {
    let a = r.a, b = r.b, s = 0;
    while (a > 0 && s < SPILL) { s += dist(line[a - 1].p, line[a].p); a--; }
    s = 0;
    while (b < line.length - 1 && s < SPILL) { s += dist(line[b].p, line[b + 1].p); b++; }
    return [a, b];
  }
})();
