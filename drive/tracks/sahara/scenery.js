// Sahara: the pyramid, the temple inside it, and the desert round it.
//
// One vocabulary throughout, which is what makes it read as one place:
//   outside   sandstone in blocks, gold at the top, and the processional way
//   inside    dark stone, gold trim, turquoise and gold glyphs, and fire
//   the pier  a square column with a gold band, which carries every raised
//             road, lines the hall and stands in the King's chamber
//   the flame a brazier: a gold bowl and a fire, wherever there is light
//
// The plan is authored in tracks/pyramid/track.py and arrives on `cfg`
// (pal.building). Everything that has to sit where the road is - the doors, the
// crawlway, the tunnels, the piers, the parapets, the King's chamber - is found
// off the ribbon here.
//
// **The chamber, the base wall, the tunnels, the parapets, the piers and the
// gateway are in the collider**, so a lap re-driven by verify.py meets the same
// stone.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.sahara = { props: props };

  const station = (line, f) =>
    line[Math.max(0, Math.min(line.length - 1, Math.round(f * (line.length - 1))))];

  // A quad or a triangle drawn with its front toward `N`, whatever order the
  // corners came in - the trap with `solid` is a face wound the wrong way, which
  // is drawn, costed, and invisible.
  function quadN(buf, a, b, c, d, color, N) {
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    if (nx * N[0] + ny * N[1] + nz * N[2] >= 0) buf.quad(a, b, c, d, color);
    else buf.quad(a, d, c, b, color);
  }
  function triN(buf, a, b, c, color, N) {
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    if (nx * N[0] + ny * N[1] + nz * N[2] >= 0) buf.tri(a, b, c, color);
    else buf.tri(a, c, b, color);
  }

  /** What every part of this file needs to know, worked out once. */
  function plan(ctx) {
    const { track, cfg } = ctx;
    const line = track.line, n = line.length;
    const G = track.ground != null ? track.ground : -1.2;
    const CX = cfg.x, CZ = cfg.z, B = cfg.b, H = cfg.h;
    const SLOPE = H / B;
    const depth = (x, z) => B - Math.max(Math.abs(x - CX), Math.abs(z - CZ));
    const insidePyr = (p) => (p[1] - G) < SLOPE * depth(p[0], p[2]) - 2;
    // The King's chamber is the one room you see: the widest road at the top of
    // the climb. Every other road inside the pyramid is in a tunnel - the open
    // hollow of the pyramid was the ugliest thing on the lap, so you never see it.
    let kingTop = -Infinity;
    for (const e of line) if (insidePyr(e.p) && !e.air) kingTop = Math.max(kingTop, e.p[1]);
    const isKing = (e) => insidePyr(e.p) && !e.air && e.p[1] > kingTop - 0.5 && e.hw > 7.6;
    const isTunnel = (e) => !e.air && insidePyr(e.p) && !isKing(e);
    // Plan distance to the nearest station.
    const toRoad = (x, z) => {
      let best = Infinity;
      for (let i = 0; i < n; i++) {
        const p = line[i].p;
        const dx = p[0] - x, dz = p[2] - z;
        const d = dx * dx + dz * dz;
        if (d < best) best = d;
      }
      return Math.sqrt(best);
    };
    // Whether some road lower than `y` passes within `pad` of its kerb of (x, z).
    const roadBelow = (x, z, y, pad) => {
      for (let i = 0; i < n; i++) {
        const e = line[i];
        if (e.p[1] > y - 3) continue;
        const dx = e.p[0] - x, dz = e.p[2] - z, r = e.hw + pad;
        if (dx * dx + dz * dz < r * r) return true;
      }
      return false;
    };
    const lane = { a: station(line, cfg.lane[0]).p, b: station(line, cfg.lane[1]).p };
    const lz = (x) => {
      const t = (x - lane.a[0]) / ((lane.b[0] - lane.a[0]) || 1);
      return lane.a[2] + (lane.b[2] - lane.a[2]) * Math.max(0, Math.min(1, t));
    };
    // Doors: wherever the ribbon (or a flight over a gap) passes through the
    // shell, and **cut to the tunnel's own section**, not to a generous box -
    // the first doors were whole wall blocks knocked out round a much narrower
    // tunnel, which read as a ragged hole with the dark showing round it.
    //
    // A tunnel keeps its full height right up to its door (`nearDoor`), because
    // the headroom cap below would otherwise squash it to nothing just as the
    // face comes down to meet it; the door is cut as tall as the tallest roof
    // in that stretch, so nothing in it comes out through the steps.
    const TW = 1.4;
    const roofH = (e) => e.p[1] > 5 ? 17 : 10.5;
    const nearDoor = new Uint8Array(n);
    const doors = [];
    for (let i = 1; i < n; i++) {
      const a = line[i - 1].p, b = line[i].p;
      const ia = insidePyr(a), ib = insidePyr(b);
      if (ia === ib) continue;
      const p = ia ? a : b;
      const ii = ia ? i - 1 : i, step = ia ? -1 : 1;
      const dx = p[0] - CX, dz = p[2] - CZ;
      const axis = Math.abs(dx) > Math.abs(dz) ? 0 : 2;
      const s = Math.sign(axis === 0 ? dx : dz);
      let top = p[1] + roofH(line[ii]);
      for (let j = ii; j >= 0 && j < n; j += step) {
        const e = line[j];
        if (e.air || !insidePyr(e.p)) break;
        const reach = (e.p[1] - G + roofH(e) + 1) / SLOPE + cfg.thick + 2;
        if (depth(e.p[0], e.p[2]) > reach) break;
        nearDoor[j] = 1;
        top = Math.max(top, e.p[1] + roofH(e));
      }
      doors.push({ axis: axis, s: s, along: axis === 0 ? dz : dx, y: Math.min(a[1], b[1]),
                   bot: Math.min(a[1], b[1]) - 1.2, top: top,
                   hw: line[ii].hw + TW + 0.15 });
    }
    // Curvature, smoothed over a few stations, for how far the outside wall of
    // a bend stands off: the chase camera trails the car by 11.6 and swings
    // wide, by about 11.6^2 / 2R, so a tight bend's outer wall moves out to keep
    // it inside - and the smoothing is what keeps that from being a step.
    const kap = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      let sum = 0, c = 0;
      for (let j = Math.max(0, i - 5); j <= Math.min(n - 1, i + 5); j++) { sum += line[j].curv || 0; c++; }
      kap[i] = sum / c;
    }
    const wallOff = (i, s) => {
      const e = line[i], q = kap[i];
      const wide = q && s === -Math.sign(q) ? Math.min(7, 67 * Math.abs(q)) : 0;
      return e.hw + TW + wide;
    };
    const surf = (e, u, lift) => [e.p[0] + e.lat[0] * u + e.n[0] * lift,
                                  e.p[1] + e.lat[1] * u + e.n[1] * lift,
                                  e.p[2] + e.lat[2] * u + e.n[2] * lift];
    // A point `off` out from the centre along a face's axis, `along` across it.
    const P = (axis, s, off, along, y) => axis === 0
      ? [CX + s * off, y, CZ + along] : [CX + along, y, CZ + s * off];
    return { line, n, G, CX, CZ, B, H, SLOPE, depth, insidePyr, isTunnel, isKing, toRoad,
             roadBelow, lane, lz, doors, surf, P, TH: cfg.thick, TIER: cfg.tier,
             TW, roofH, nearDoor, wallOff };
  }

  function props(ctx) {
    const { solid, bright, soft, col, pal, cfg, KIND, shade, mulberry } = ctx;
    const k = plan(ctx);
    const { line, n, G, CX, CZ, B, SLOPE, insidePyr, isTunnel, isKing, toRoad, roadBelow,
            lz, doors, surf, P, TH, TIER, TW, roofH, nearDoor, wallOff } = k;
    const rnd = mulberry(0x5a11d0);
    const UP = [0, 1, 0];
    const [c0, c1, c2, c3, ctop] = cfg.chamber;

    // ---- the shared vocabulary -------------------------------------------------
    // A box that is drawn and collided.
    const wallBox = (cx, cy, cz, hx, hy, hz, kc) => {
      solid.box(cx, cy, cz, hx, hy, hz, kc);
      const Q = (sx, sy, sz) => [cx + sx * hx, cy + sy * hy, cz + sz * hz];
      const v = [Q(-1, -1, -1), Q(1, -1, -1), Q(1, -1, 1), Q(-1, -1, 1),
                 Q(-1, 1, -1), Q(1, 1, -1), Q(1, 1, 1), Q(-1, 1, 1)];
      col.addQuad(v[4], v[7], v[6], v[5], KIND.WALL);
      col.addQuad(v[0], v[4], v[5], v[1], KIND.WALL);
      col.addQuad(v[1], v[5], v[6], v[2], KIND.WALL);
      col.addQuad(v[2], v[6], v[7], v[3], KIND.WALL);
      col.addQuad(v[3], v[7], v[4], v[0], KIND.WALL);
    };
    // The pier: base, shaft, a glyph band, a gold band and a capital. `top` is
    // the underside of whatever it carries.
    const pier = (x, z, y0, top, w, stone, collide) => {
      const h = top - y0;
      if (h < 2) return;
      if (collide) wallBox(x, y0 + h / 2, z, w, h / 2, w, stone);
      else solid.box(x, y0 + h / 2, z, w, h / 2, w, stone);
      solid.box(x, y0 + 0.6, z, w + 0.6, 0.6, w + 0.6, shade(stone, -0.18));
      solid.box(x, top - 0.55, z, w + 0.7, 0.55, w + 0.7, shade(stone, -0.18));
      solid.box(x, top - 1.6, z, w + 0.2, 0.45, w + 0.2, cfg.cap);
      if (h > 9 && insidePyr([x, top, z])) bright.box(x, y0 + Math.min(5.5, h * 0.35), z, w + 0.18, 0.55, w + 0.18, cfg.glyph);
    };
    // The brazier: a gold bowl on a short stand, and its fire.
    const brazier = (x, y, z) => {
      solid.box(x, y + 0.7, z, 0.22, 0.7, 0.22, 0x1a120a);
      solid.box(x, y + 1.55, z, 0.75, 0.22, 0.75, cfg.cap);
      bright.box(x, y + 2.05, z, 0.5, 0.42, 0.5, cfg.flame);
      bright.box(x, y + 2.6, z, 0.26, 0.3, 0.26, cfg.flame2);
    };
    // An oriented box from a centre, a forward unit vector in plan and three
    // half-sizes - for anything that has to face a road that is not on an axis.
    const obox = (o, f, lf, lr, y, hf, hr, hy, kc) => {
      const r = [f[1], -f[0]];
      const at = (a, b2, yy) => [o[0] + f[0] * a + r[0] * b2, yy, o[1] + f[1] * a + r[1] * b2];
      const c = [];
      for (const sy of [-1, 1]) for (const sf of [-1, 1]) for (const sr of [-1, 1]) {
        c.push(at(lf + sf * hf, lr + sr * hr, y + sy * hy));
      }
      const Q = (a, b2, cc, d, N) => quadN(solid, c[a], c[b2], c[cc], c[d], kc, N);
      Q(4, 5, 7, 6, [0, 1, 0]); Q(0, 1, 3, 2, [0, -1, 0]);
      Q(2, 3, 7, 6, [f[0], 0, f[1]]); Q(0, 1, 5, 4, [-f[0], 0, -f[1]]);
      Q(1, 3, 7, 5, [r[0], 0, r[1]]); Q(0, 2, 6, 4, [-r[0], 0, -r[1]]);
    };
    // A lion lying down with a man's head-dress, facing `f` - the guardian at
    // the scale of a landmark, and at a third of it down the processional way.
    const sphinx = (o, f, S) => {
      const st = cfg.stone, st2 = cfg.stone2, blue = cfg.lapis;
      obox(o, f, -6 * S, 0, G + 6 * S, 18 * S, 7 * S, 6 * S, st);
      obox(o, f, -22 * S, 0, G + 3.5 * S, 4.5 * S, 6.2 * S, 3.5 * S, st2);
      obox(o, f, 14 * S, -4 * S, G + 1.6 * S, 9 * S, 2.2 * S, 1.6 * S, st2);
      obox(o, f, 14 * S, 4 * S, G + 1.6 * S, 9 * S, 2.2 * S, 1.6 * S, st2);
      obox(o, f, 7 * S, 0, G + 14 * S, 5 * S, 5.5 * S, 5 * S, st);
      obox(o, f, 9 * S, 0, G + 22 * S, 4.2 * S, 4 * S, 4.2 * S, st);
      obox(o, f, 7 * S, 0, G + 23 * S, 4.6 * S, 5 * S, 4.9 * S, blue);
      for (let q = 0; q < 4; q++) obox(o, f, 7 * S, 0, G + (19.5 + q * 2.2) * S, 4.75 * S, 0.35 * S, 5.05 * S, cfg.cap);
      obox(o, f, 12.9 * S, 0, G + 22.6 * S, 0.4 * S, 2.6 * S, 2.6 * S, shade(st, 0.08));
      obox(o, f, 11.5 * S, 0, G + 15 * S, 1.2 * S, 4.5 * S, 1.6 * S, blue);
    };
    // An obelisk on its plinth, with a gold tip and a band of gold glyphs.
    const obelisk = (x, z, h) => {
      wallBox(x, G + 1.4, z, 2.8, 1.4, 2.8, cfg.stone2);
      for (let q = 0; q < 6; q++) {
        const w = 1.8 - q * 0.09;
        solid.box(x, G + 2.8 + h / 6 * (q + 0.5), z, w, h / 12, w, q % 2 ? cfg.stone : shade(cfg.stone, -0.04));
      }
      bright.box(x, G + 2.8 + h * 0.55, z, 1.42, h * 0.2, 1.42, cfg.glyph2);
      const ty = G + 2.8 + h;
      for (const [a, b2] of [[[-1, -1], [1, -1]], [[1, -1], [1, 1]], [[1, 1], [-1, 1]], [[-1, 1], [-1, -1]]]) {
        triN(solid, [x + a[0] * 1.3, ty, z + a[1] * 1.3], [x + b2[0] * 1.3, ty, z + b2[1] * 1.3],
             [x, ty + 3.6, z], cfg.cap, [(a[0] + b2[0]), 0.5, (a[1] + b2[1])]);
      }
    };

    // ---- the pyramid -------------------------------------------------------------
    // Stepped outside, in blocks; coursed and dark inside. A face is its axis
    // (0 = x, 2 = z) and its sign.
    const faces = [[0, -1], [0, 1], [2, -1], [2, 1]];
    const doorAt = (axis, s, a0, a1, y0, y1) => {
      for (const d of doors) {
        if (d.axis !== axis || d.s !== s) continue;
        if (a1 <= d.along - d.hw || a0 >= d.along + d.hw) continue;
        if (y1 <= d.bot || y0 >= d.top) continue;
        return d;
      }
      return null;
    };
    const holed = (axis, s, a0, a1, y0, y1) => !!doorAt(axis, s, a0, a1, y0, y1);
    const cl = (t, w) => Math.max(-w, Math.min(w, t));
    const stepped = (cx, cz, b, h, tier, seg, inner, holes) => {
      const slope = h / b;
      const NT = Math.ceil(h / tier);
      const Pp = (axis, s, off, along, y) => axis === 0
        ? [cx + s * off, y, cz + along] : [cx + along, y, cz + s * off];
      for (const [axis, s] of faces) {
        const N = axis === 0 ? [s, 0, 0] : [0, 0, s];
        const NIN = [-N[0], 0.6, -N[2]];
        for (let t = 0; t < NT; t++) {
          const y0 = G + t * tier, y1 = G + Math.min(h, (t + 1) * tier);
          const w0 = b - (t * tier) / slope, w1 = Math.max(0.5, b - ((t + 1) * tier) / slope);
          const cap = t >= NT - 3;
          const segs = Math.max(1, Math.ceil(2 * w0 / seg));
          // Blocks: each course offset half a block from the last, each block
          // its own shade - which is what stops a face reading as stripes from
          // a distance and as a cardboard cut-out up close.
          const off = (t % 2) * 0.5;
          for (let q = -1; q < segs; q++) {
            const t0 = cl(-w0 + (2 * w0) * (q + off) / segs, w0);
            const t1 = cl(-w0 + (2 * w0) * (q + 1 + off) / segs, w0);
            if (t1 - t0 < 0.05) continue;
            const base = cap ? cfg.cap : cfg.stone;
            const kc = shade(base, (rnd() - 0.5) * (cap ? 0.05 : 0.09));
            const riser = (a0, a1, ya, yb) => quadN(solid, Pp(axis, s, w0, a0, ya), Pp(axis, s, w0, a1, ya),
              Pp(axis, s, w0, a1, yb), Pp(axis, s, w0, a0, yb), shade(kc, -0.08), N);
            const tread = (a0, a1) => quadN(solid, Pp(axis, s, w0, a0, y1), Pp(axis, s, w0, a1, y1),
              Pp(axis, s, w1, cl(a1, w1), y1), Pp(axis, s, w1, cl(a0, w1), y1), shade(kc, 0.07), UP);
            const d = holes ? doorAt(axis, s, t0, t1, y0, y1) : null;
            if (!d) {
              riser(t0, t1, y0, y1);
              tread(t0, t1);
            } else {
              // Cut exactly: the block either side of the door whole, and over
              // and under it only the part of the block that is not door.
              const hl = d.along - d.hw, hr = d.along + d.hw;
              if (t0 < hl) { riser(t0, hl, y0, y1); tread(t0, hl); }
              if (t1 > hr) { riser(hr, t1, y0, y1); tread(hr, t1); }
              const m0 = Math.max(t0, hl), m1 = Math.min(t1, hr);
              if (y1 > d.top) riser(m0, m1, Math.max(y0, d.top), y1);
              if (y0 < d.bot) riser(m0, m1, y0, Math.min(y1, d.bot));
              if (y1 >= d.top || y1 <= d.bot) tread(m0, m1);
              continue;
            }
            if (inner) {
              const i0 = w0 - TH, i1 = Math.max(0.5, w1 - TH);
              if (i0 > 1) {
                quadN(solid, Pp(axis, s, i0, cl(t0, i0), y0), Pp(axis, s, i0, cl(t1, i0), y0),
                      Pp(axis, s, i1, cl(t1, i1), y1), Pp(axis, s, i1, cl(t0, i1), y1),
                      t % 2 ? cfg.inner : cfg.inner2, NIN);
              }
            }
          }
        }
      }
    };
    stepped(CX, CZ, B, k.H, TIER, 9, true, true);

    // A portal round every door: two jambs and a lintel, standing proud of the
    // steps and running back through the shell to the inside face, so the
    // thickness of the pyramid is stone you can see and never a gap into the
    // dark. Gold on the edge facing out.
    for (const d of doors) {
      const oOut = B - Math.max(0, d.bot - G) / SLOPE + 1.6;
      const oIn = B - (d.top - G) / SLOPE - TH - 2.5;
      const mid = (oOut + oIn) / 2, half = (oOut - oIn) / 2;
      const JW = 1.6, LH = 3.2;
      const boxAt = (along, ha, y0, y1, kc, hit) => {
        const c = P(d.axis, d.s, mid, along, 0);
        const hx = d.axis === 0 ? half : ha, hz = d.axis === 0 ? ha : half;
        (hit ? wallBox : (a1, b1, c1, d1, e1, f1, g1) => solid.box(a1, b1, c1, d1, e1, f1, g1))(
          c[0], (y0 + y1) / 2, c[2], hx, (y1 - y0) / 2, hz, kc);
      };
      for (const side of [-1, 1]) {
        boxAt(d.along + side * (d.hw + JW), JW, d.bot, d.top + LH, cfg.stone2, true);
        // The gold edge on the jamb's face.
        const f = P(d.axis, d.s, oOut + 0.12, d.along + side * (d.hw + 0.35), 0);
        solid.box(f[0], (d.bot + d.top) / 2, f[2], d.axis === 0 ? 0.12 : 0.35, (d.top - d.bot) / 2, d.axis === 0 ? 0.35 : 0.12, cfg.cap);
      }
      boxAt(d.along, d.hw + 2 * JW, d.top, d.top + LH, cfg.stone, false);
      const g = P(d.axis, d.s, oOut + 0.12, d.along, 0);
      solid.box(g[0], d.top + 0.35, g[2], d.axis === 0 ? 0.12 : d.hw + 2 * JW, 0.35, d.axis === 0 ? d.hw + 2 * JW : 0.12, cfg.cap);
      quadN(bright, P(d.axis, d.s, oOut + 0.13, d.along - d.hw * 0.7, d.top + 1.2), P(d.axis, d.s, oOut + 0.13, d.along + d.hw * 0.7, d.top + 1.2),
            P(d.axis, d.s, oOut + 0.13, d.along + d.hw * 0.7, d.top + 2.4), P(d.axis, d.s, oOut + 0.13, d.along - d.hw * 0.7, d.top + 2.4),
            cfg.glyph, d.axis === 0 ? [d.s, 0, 0] : [0, 0, d.s]);
    }

    // The base wall: one collided band round the foot of the shell, broken at
    // the doors, so the only ways in and out are the ways the road goes.
    {
      const BW = B - TH / 2, h = 7;
      for (const [axis, s] of faces) {
        const segs = Math.ceil(2 * BW / 6);
        for (let q = 0; q < segs; q++) {
          const t0 = -BW + 2 * BW * q / segs, t1 = -BW + 2 * BW * (q + 1) / segs;
          if (holed(axis, s, t0, t1, G, G + h)) continue;
          col.addQuad(P(axis, s, BW, t0, G), P(axis, s, BW, t1, G),
                      P(axis, s, BW, t1, G + h), P(axis, s, BW, t0, G + h), KIND.WALL);
        }
      }
    }

    // ---- the gateway ----------------------------------------------------------------
    // At the ground-level door: two pylons, a lintel with the winged sun, two
    // seated colossi and a pair of obelisks. The door is found, so all of this
    // is built round wherever the road goes in.
    for (const d of doors) {
      if (d.y > 2) continue;
      const N = d.axis === 0 ? [d.s, 0] : [0, d.s];          // outward, in plan
      const T = d.axis === 0 ? [0, 1] : [1, 0];              // across the face
      const at = (out, along) => d.axis === 0
        ? [CX + d.s * (B + out), CZ + d.along + along]
        : [CX + d.along + along, CZ + d.s * (B + out)];
      const PH = 34, PW = 10, PD = 8;                        // pylon height, half-width, half-depth
      for (const side of [-1, 1]) {
        const c = at(PD - 1, side * (d.hw + PW + 1));
        // A pylon is battered - narrower at the top - so it is built as a stack.
        for (let q = 0; q < 6; q++) {
          const y = G + PH * (q + 0.5) / 6, taper = 1 - q * 0.05;
          const hx = (d.axis === 0 ? PD : PW) * taper, hz = (d.axis === 0 ? PW : PD) * taper;
          const kc = shade(cfg.stone, q % 2 ? 0.02 : -0.03);
          if (q < 2) wallBox(c[0], y, c[1], hx, PH / 12, hz, kc);
          else solid.box(c[0], y, c[1], hx, PH / 12, hz, kc);
        }
        const tx = d.axis === 0 ? PD * 0.72 : PW * 0.72, tz = d.axis === 0 ? PW * 0.72 : PD * 0.72;
        solid.box(c[0], G + PH + 0.8, c[1], tx + 0.6, 0.8, tz + 0.6, cfg.cap);
        // Glyph panels down the pylon's face.
        for (let q = 0; q < 3; q++) {
          const y = G + 7 + q * 8.5;
          const taper = 1 - Math.floor((y - G) / (PH / 6)) * 0.05;
          const fo = PD * taper + 0.12;
          const fx = c[0] + N[0] * fo, fz = c[1] + N[1] * fo;
          const w = PW * 0.5;
          quadN(bright, [fx - T[0] * w, y, fz - T[1] * w], [fx + T[0] * w, y, fz + T[1] * w],
                [fx + T[0] * w, y + 4.5, fz + T[1] * w], [fx - T[0] * w, y + 4.5, fz - T[1] * w],
                q === 1 ? cfg.glyph : cfg.glyph2, [N[0], 0, N[1]]);
        }
        // The colossus: seated, facing out down the approach.
        const s0 = at(PD * 2 + 12, side * (d.hw + PW + 1));
        const f = N;
        obox(s0, f, 0, 0, G + 3, 6, 5, 3, cfg.stone2);               // throne base
        obox(s0, f, -3, 0, G + 12, 2.5, 5, 6, cfg.stone2);           // throne back
        obox(s0, f, 2, 0, G + 8, 4, 3.6, 2, cfg.stone);              // lap
        obox(s0, f, 5, -1.8, G + 4.5, 1, 1.4, 4, cfg.stone);         // shins
        obox(s0, f, 5, 1.8, G + 4.5, 1, 1.4, 4, cfg.stone);
        obox(s0, f, -0.5, 0, G + 14, 2.2, 3.4, 4.5, cfg.stone);      // torso
        obox(s0, f, 0, 0, G + 20.5, 2, 2, 2.2, cfg.stone);           // head
        obox(s0, f, -0.4, 0, G + 21, 2.4, 2.8, 2.8, cfg.lapis);      // head-dress
        for (let q = 0; q < 3; q++) obox(s0, f, -0.4, 0, G + 19.2 + q * 1.6, 2.5, 2.9, 0.25, cfg.cap);
        obox(s0, f, 2.1, 0, G + 20.3, 0.2, 1.6, 1.8, shade(cfg.stone, 0.06));
        col.addQuad([s0[0] - 6, G, s0[1] - 6], [s0[0] + 6, G, s0[1] - 6], [s0[0] + 6, G + 12, s0[1] - 6], [s0[0] - 6, G + 12, s0[1] - 6], KIND.WALL);
        col.addQuad([s0[0] + 6, G, s0[1] - 6], [s0[0] + 6, G, s0[1] + 6], [s0[0] + 6, G + 12, s0[1] + 6], [s0[0] + 6, G + 12, s0[1] - 6], KIND.WALL);
        col.addQuad([s0[0] + 6, G, s0[1] + 6], [s0[0] - 6, G, s0[1] + 6], [s0[0] - 6, G + 12, s0[1] + 6], [s0[0] + 6, G + 12, s0[1] + 6], KIND.WALL);
        col.addQuad([s0[0] - 6, G, s0[1] + 6], [s0[0] - 6, G, s0[1] - 6], [s0[0] - 6, G + 12, s0[1] - 6], [s0[0] - 6, G + 12, s0[1] + 6], KIND.WALL);
        // The obelisk in front of it.
        const o = at(PD * 2 + 34, side * (d.hw + 3));
        obelisk(o[0], o[1], 30);
      }
      // The lintel between the pylons, high over the door: the winged sun.
      const LY = d.top + 3.2, LW = d.hw + 2;
      const lc = at(PD - 1, 0);
      solid.box(lc[0], LY + 2.5, lc[1], d.axis === 0 ? PD * 0.8 : LW, 2.5, d.axis === 0 ? LW : PD * 0.8, cfg.stone);
      const fx = lc[0] + N[0] * (PD * 0.8 + 0.1), fz = lc[1] + N[1] * (PD * 0.8 + 0.1);
      quadN(bright, [fx - T[0] * LW * 0.9, LY + 2.1, fz - T[1] * LW * 0.9], [fx + T[0] * LW * 0.9, LY + 2.1, fz + T[1] * LW * 0.9],
            [fx + T[0] * LW * 0.9, LY + 2.9, fz + T[1] * LW * 0.9], [fx - T[0] * LW * 0.9, LY + 2.9, fz - T[1] * LW * 0.9],
            cfg.glyph, [N[0], 0, N[1]]);
      for (let a = 0; a < 10; a++) {
        const t0 = a / 10 * Math.PI * 2, t1 = (a + 1) / 10 * Math.PI * 2, R = 2.2;
        const pc = [fx + N[0] * 0.05, LY + 2.5, fz + N[1] * 0.05];
        triN(solid, pc, [pc[0] + T[0] * Math.cos(t0) * R, pc[1] + Math.sin(t0) * R, pc[2] + T[1] * Math.cos(t0) * R],
             [pc[0] + T[0] * Math.cos(t1) * R, pc[1] + Math.sin(t1) * R, pc[2] + T[1] * Math.cos(t1) * R],
             cfg.cap, [N[0], 0, N[1]]);
      }
    }
    // ---- the hall floor and the burial chamber -------------------------------------
    {
      const W = B - TH - 2, C = 12;
      for (let x = CX - W; x < CX + W; x += C) {
        for (let z = CZ - W; z < CZ + W; z += C) {
          const mx = x + C / 2, mz = z + C / 2;
          if (mx > c0 && mx < c1 && mz > c2 && mz < c3) continue;
          const inLane = mx > k.lane.a[0] - 4 && mx < k.lane.b[0] + 4 && Math.abs(mz - lz(mx)) < cfg.laneHW + 3;
          const kc = inLane ? shade(cfg.sand, -0.25 + 0.05 * rnd())
            : (((x - CX) / C + (z - CZ) / C) & 1 ? cfg.floor : shade(cfg.floor, -0.1));
          quadN(solid, [x, G + 0.12, z], [x + C, G + 0.12, z], [x + C, G + 0.12, z + C],
                [x, G + 0.12, z + C], kc, UP);
        }
      }
    }
    {
      const zs = (lz(c0) + lz(c1)) / 2;
      const SW = cfg.laneHW + 0.6;
      const hy = (ctop - G) / 2, cy = G + hy;
      wallBox((c0 + c1) / 2, cy, (c2 + zs - SW) / 2, (c1 - c0) / 2, hy, (zs - SW - c2) / 2, cfg.dark);
      wallBox((c0 + c1) / 2, cy, (zs + SW + c3) / 2, (c1 - c0) / 2, hy, (c3 - zs - SW) / 2, cfg.dark);
      // The roof over the crawlway: low, so it is a crack and not a corridor.
      const RY = G + 8.5;
      solid.box((c0 + c1) / 2, (RY + ctop) / 2, zs, (c1 - c0) / 2, (ctop - RY) / 2, SW + 0.05, cfg.dark);
      // A gold cornice, and a carved frieze round the outside.
      solid.box((c0 + c1) / 2, ctop + 0.5, (c2 + c3) / 2, (c1 - c0) / 2 + 0.6, 0.5, (c3 - c2) / 2 + 0.6, cfg.cap);
      const FY = G + 10, FH = 3.2;
      const frieze = (a, b2, N) => {
        quadN(solid, [a[0], FY, a[1]], [b2[0], FY, b2[1]], [b2[0], FY + FH, b2[1]], [a[0], FY + FH, a[1]], cfg.dark2, N);
        const L = Math.hypot(b2[0] - a[0], b2[1] - a[1]), ux = (b2[0] - a[0]) / L, uz = (b2[1] - a[1]) / L;
        for (let t = 1.2; t < L - 1.2; t += 2.0) {
          const g = rnd() < 0.3 ? cfg.glyph : cfg.glyph2;
          const h = 0.7 + rnd() * 1.4, y0 = FY + 0.4 + rnd() * (FH - 0.8 - h);
          const x = a[0] + ux * t + N[0] * 0.15, z = a[1] + uz * t + N[2] * 0.15;
          quadN(bright, [x, y0, z], [x + ux * 0.9, y0, z + uz * 0.9], [x + ux * 0.9, y0 + h, z + uz * 0.9],
                [x, y0 + h, z], g, N);
        }
      };
      frieze([c0, c2 - 0.15], [c1, c2 - 0.15], [0, 0, -1]);
      frieze([c0, c3 + 0.15], [c1, c3 + 0.15], [0, 0, 1]);
      frieze([c1 + 0.15, c2], [c1 + 0.15, zs - SW], [1, 0, 0]);
      frieze([c1 + 0.15, zs + SW], [c1 + 0.15, c3], [1, 0, 0]);
      frieze([c0 - 0.15, c2], [c0 - 0.15, zs - SW], [-1, 0, 0]);
      frieze([c0 - 0.15, zs + SW], [c0 - 0.15, c3], [-1, 0, 0]);
      // The crack's mouth: a lit gold edge either side, so it can be found.
      for (const x of [c0 - 0.1, c1 + 0.1]) {
        for (const side of [-1, 1]) {
          bright.box(x, G + 4.5, zs + side * (SW + 0.4), 0.15, 4.2, 0.35, cfg.glyph2);
        }
      }
      // Inside the crack: glyphs at eye height, the only light in there.
      for (let x = c0 + 3; x < c1 - 3; x += 6) {
        for (const s of [-1, 1]) {
          const z = zs + s * (SW - 0.18);
          quadN(bright, [x, G + 2.4, z], [x + 2.0, G + 2.4, z], [x + 2.0, G + 4.0, z],
                [x, G + 4.0, z], (x / 6 | 0) % 2 ? cfg.glyph : cfg.glyph2, [0, 0, -s]);
        }
      }
    }

    // ---- the road indoors ------------------------------------------------------------
    // One road colour is all the engine paints, and in here it has to be dark -
    // there is no lighting per region, so darkness indoors is albedo. A skin over
    // the engine's road, lifted clear of its kerbs, with kerbs of its own. Pads
    // are left alone to glow.
    for (let i = 0; i < n - 1; i++) {
      const e = line[i], f = line[i + 1];
      if (e.air || f.air || e.bp || f.bp) continue;
      if (!insidePyr(e.p) || !insidePyr(f.p)) continue;
      const L = 0.12, K = 0.8;
      const band = (u0, u1, kc) => quadN(solid, surf(e, u0 * e.hw, L), surf(e, u1 * e.hw, L),
        surf(f, u1 * f.hw, L), surf(f, u0 * f.hw, L), kc, e.n);
      band(-1 + K / e.hw, 1 - K / e.hw, i % 8 < 4 ? cfg.road : shade(cfg.road, 0.07));
      const kc = (i >> 1) % 2 ? cfg.cap : cfg.oxblood;
      band(-1, -1 + K / e.hw, kc);
      band(1 - K / e.hw, 1, kc);
    }

    // ---- the tunnels -----------------------------------------------------------------
    // Every road inside the pyramid but the King's chamber. Low and close on the
    // hall floor; tall and corbelled once the road is up in the air.
    //
    // The walls are continuous. Where the secret lane leaves the road and where
    // it comes back, the wall becomes a doorway - gold posts, a lintel and wall
    // over it - because a tunnel with no opening there is a shortcut nobody can
    // take, and a raw gap in a wall reads as a mistake.
    const laneD = (x, z) => {
      const ax = k.lane.a[0], az = k.lane.a[2], bx = k.lane.b[0], bz = k.lane.b[2];
      const dx = bx - ax, dz = bz - az, L2 = dx * dx + dz * dz || 1;
      const t = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / L2));
      return Math.hypot(x - (ax + dx * t), z - (az + dz * t));
    };
    const tallAt = (e) => e.p[1] > 5;
    // **Nothing built in here may come out through the shell.** A tunnel's roof
    // is capped by the headroom the pyramid actually has over each kerb, so a
    // ramp that runs close to a sloping face gets a lower ceiling rather than a
    // roof poking out of the outside of the pyramid - which is what the first
    // version did, on the south face, from every view of the start.
    const headroom = (e) => {
      let h = Infinity;
      for (const s of [-1, 1]) {
        const o = e.hw + TW + 0.5;
        const x = e.p[0] + e.lat[0] * s * o, z = e.p[2] + e.lat[2] * s * o;
        h = Math.min(h, SLOPE * (k.depth(x, z) - TH) - (e.p[1] - G) - 1.0);
      }
      return h;
    };
    const roofOf = (e, f, i) => (nearDoor[i] || nearDoor[i + 1]) ? roofH(e)
      : Math.max(5.5, Math.min(roofH(e), headroom(e), headroom(f)));
    const LINTEL = 8.5;                     // the lane's doorway, over the hall floor
    // The corridor the lane runs in, road to road: the crack's own section.
    const LZ = (lz(c0) + lz(c1)) / 2, LW = cfg.laneHW + 0.6;
    // The parts of a wall segment outside the corridor, as [t0, t1] pairs.
    const outsideLane = (a, b) => {
      const dz = b[2] - a[2];
      if (Math.abs(dz) < 1e-6) return Math.abs(a[2] - LZ) < LW ? [] : [[0, 1]];
      let t1 = (LZ - LW - a[2]) / dz, t2 = (LZ + LW - a[2]) / dz;
      if (t1 > t2) [t1, t2] = [t2, t1];
      const out = [];
      if (t1 > 0) out.push([0, Math.min(1, t1)]);
      if (t2 < 1) out.push([Math.max(0, t2), 1]);
      return out.filter(([u, v]) => v - u > 1e-4);
    };
    const inLane = (i, s) => {
      const e = line[i], f = line[i + 1];
      if (e.p[1] > 1) return false;
      const oa = wallOff(i, s), ob = wallOff(i + 1, s);
      const x = (e.p[0] + e.lat[0] * s * oa + f.p[0] + f.lat[0] * s * ob) / 2;
      const z = (e.p[2] + e.lat[2] * s * oa + f.p[2] + f.lat[2] * s * ob) / 2;
      return laneD(x, z) < cfg.laneHW + 3;
    };
    for (let i = 0; i < n - 1; i++) {
      const e = line[i], f = line[i + 1];
      if (!isTunnel(e) || !isTunnel(f)) continue;
      const H1 = roofOf(e, f, i);
      const tall = H1 >= 15;
      // The floor between the kerb and the wall. Without it a raised tunnel is a
      // road with a slot down each side - a car-width slot on the outside of
      // every bend, where the wall stands off for the camera - and running wide
      // on a ramp dropped you through it into the dark. On the hall floor the
      // ground plate is already there.
      if (e.p[1] > 1 || f.p[1] > 1) {
        for (const s of [-1, 1]) {
          const ea = surf(e, s * e.hw, 0), eb = surf(f, s * f.hw, 0);
          const oa = wallOff(i, s) + 0.3, ob = wallOff(i + 1, s) + 0.3;
          const wa = [e.p[0] + e.lat[0] * s * oa, ea[1], e.p[2] + e.lat[2] * s * oa];
          const wb = [f.p[0] + f.lat[0] * s * ob, eb[1], f.p[2] + f.lat[2] * s * ob];
          quadN(solid, ea, eb, wb, wa, cfg.dark2, UP);
          col.addQuad(ea, eb, wb, wa, KIND.OFFROAD);
          col.addQuad(ea, wa, wb, eb, KIND.OFFROAD);
        }
      }
      for (const s of [-1, 1]) {
        const oa = wallOff(i, s), ob = wallOff(i + 1, s);
        const a = [e.p[0] + e.lat[0] * s * oa, e.p[1] - 1.2, e.p[2] + e.lat[2] * s * oa];
        const b = [f.p[0] + f.lat[0] * s * ob, f.p[1] - 1.2, f.p[2] + f.lat[2] * s * ob];
        const up = (q, h) => [q[0], q[1] + 1.2 + h, q[2]];
        const NI = [-e.lat[0] * s, 0, -e.lat[2] * s];
        if (inLane(i, s)) {
          // The doorway: wall over the lintel only, a gold band under it, and a
          // gold post where the opening starts and ends.
          const LL = LINTEL - 1.2;
          quadN(solid, up(a, LL), up(b, LL), up(b, H1), up(a, H1), cfg.dark, NI);
          quadN(solid, up(a, LL), up(b, LL), up(b, H1), up(a, H1), cfg.dark2, [-NI[0], 0, -NI[2]]);
          const off = (q, h) => [q[0] + NI[0] * 0.15, q[1] + 1.2 + h, q[2] + NI[2] * 0.15];
          quadN(solid, off(a, LL), off(b, LL), off(b, LL + 0.5), off(a, LL + 0.5), cfg.cap, NI);
          quadN(solid, up(a, LL), up(b, LL), [b[0] - NI[0] * 1.4, b[1] + 1.2 + LL, b[2] - NI[2] * 1.4],
                [a[0] - NI[0] * 1.4, a[1] + 1.2 + LL, a[2] - NI[2] * 1.4], cfg.dark2, [0, -1, 0]);
          // Below it, the opening is only as wide as the corridor behind it.
          const at = (t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
          for (const [u, v] of outsideLane(a, b)) {
            const pu = at(u), pv = at(v);
            quadN(solid, pu, pv, up(pv, LL), up(pu, LL), cfg.dark, NI);
            quadN(solid, pu, pv, up(pv, LL), up(pu, LL), cfg.dark2, [-NI[0], 0, -NI[2]]);
            col.addQuad(pu, pv, up(pv, LL), up(pu, LL), KIND.WALL);
            for (const t of [u, v]) {
              if (t <= 0 || t >= 1) continue;
              const q = at(t);
              wallBox(q[0] - NI[0] * 0.5, q[1] + 1.2 + LL / 2, q[2] - NI[2] * 0.5, 0.7, LL / 2 + 0.6, 0.7, cfg.cap);
            }
          }
          continue;
        }
        quadN(solid, a, b, up(b, H1), up(a, H1), (i >> 2) % 2 ? cfg.dark : shade(cfg.dark, -0.06), NI);
        quadN(solid, a, b, up(b, H1), up(a, H1), cfg.dark2, [-NI[0], 0, -NI[2]]);
        col.addQuad(a, b, up(b, H1), up(a, H1), KIND.WALL);
        // A gold dado line and a glyph frieze above it, the whole length. Each
        // layer stands clear of the one behind it - wall, band, glyph - by more
        // than the depth buffer can lose at the far end of a tunnel; at 0.06
        // they took turns being in front and the whole frieze flickered.
        const ia = oa - 0.15, ib = ob - 0.15;
        const ga = oa - 0.3, gb = ob - 0.3;
        const qa = (h) => [e.p[0] + e.lat[0] * s * ga, e.p[1] + h, e.p[2] + e.lat[2] * s * ga];
        const qb = (h) => [f.p[0] + f.lat[0] * s * gb, f.p[1] + h, f.p[2] + f.lat[2] * s * gb];
        const pa = (h) => [e.p[0] + e.lat[0] * s * ia, e.p[1] + h, e.p[2] + e.lat[2] * s * ia];
        const pb = (h) => [f.p[0] + f.lat[0] * s * ib, f.p[1] + h, f.p[2] + f.lat[2] * s * ib];
        quadN(solid, pa(1.6), pb(1.6), pb(1.95), pa(1.95), cfg.cap, NI);
        quadN(solid, pa(2.2), pb(2.2), pb(4.1), pa(4.1), cfg.dark2, NI);
        if (i % 2 === 0) {
          const h = 0.5 + ((i * 7) % 4) * 0.3, y0 = 2.4 + ((i * 3) % 3) * 0.3;
          const m = (hh) => [(qa(hh)[0] + qb(hh)[0]) / 2, (qa(hh)[1] + qb(hh)[1]) / 2, (qa(hh)[2] + qb(hh)[2]) / 2];
          quadN(bright, qa(y0), m(y0), m(y0 + h), qa(y0 + h),
                (i >> 1) % 3 === 0 ? cfg.glyph : cfg.glyph2, NI);
        }
        // Corbels: the gallery's walls step in as they rise.
        if (tall) {
          for (let c = 0; c < 4; c++) {
            const yy = 7.5 + c * 2.3, inset = 0.85 * (c + 1);
            const ca = [e.p[0] + e.lat[0] * s * (oa - inset), e.p[1] + yy, e.p[2] + e.lat[2] * s * (oa - inset)];
            const cb = [f.p[0] + f.lat[0] * s * (ob - inset), f.p[1] + yy, f.p[2] + f.lat[2] * s * (ob - inset)];
            const wa = [a[0], e.p[1] + yy, a[2]], wb = [b[0], f.p[1] + yy, b[2]];
            quadN(solid, wa, wb, cb, ca, cfg.dark2, [0, -1, 0]);
            quadN(solid, ca, cb, [cb[0], cb[1] + 2.3, cb[2]], [ca[0], ca[1] + 2.3, ca[2]],
                  c % 2 ? cfg.dark : shade(cfg.dark, -0.08), NI);
          }
        }
        // Braziers on the walls, alternating sides.
        if (i % 12 === (s > 0 ? 0 : 6)) {
          const t = oa - 0.9;
          brazier(e.p[0] + e.lat[0] * s * t, e.p[1] + 3.2, e.p[2] + e.lat[2] * s * t);
        }
      }
      const corner = (j, s, h) => {
        const q = line[j], o = wallOff(j, s);
        return [q.p[0] + q.lat[0] * s * o, q.p[1] + h, q.p[2] + q.lat[2] * s * o];
      };
      quadN(solid, corner(i, -1, H1), corner(i + 1, -1, H1), corner(i + 1, 1, H1), corner(i, 1, H1), cfg.dark2, [0, -1, 0]);
      quadN(solid, corner(i, -1, H1), corner(i + 1, -1, H1), corner(i + 1, 1, H1), corner(i, 1, H1), cfg.dark2, UP);
    }
    // Where a tunnel opens into the King's chamber, it opens out of a wall: a
    // gable across the whole room, the tunnel's mouth cut in it and framed in
    // gold - so the room has ends, and the tunnel does not just stop in the air.
    for (let i = 0; i < n - 1; i++) {
      const a = line[i], b = line[i + 1];
      if (isTunnel(a) === isTunnel(b)) continue;
      const room = isKing(a) ? a : isKing(b) ? b : null;
      if (!room) continue;
      const e = isTunnel(a) ? a : b;
      const H1 = roofOf(e, e), WW = room.hw + 24, TOP = H1 + 14;
      const at = (u, h) => [e.p[0] + e.lat[0] * u, e.p[1] + h, e.p[2] + e.lat[2] * u];
      const fw = [b.p[0] - a.p[0], 0, b.p[2] - a.p[2]];
      const fl = Math.hypot(fw[0], fw[2]) || 1;
      const into = isKing(b) ? [fw[0] / fl, 0, fw[2] / fl] : [-fw[0] / fl, 0, -fw[2] / fl];
      const proud = (q, d) => [q[0] + into[0] * d, q[1], q[2] + into[2] * d];
      const open = e.hw + TW;
      for (const s of [-1, 1]) {
        const u0 = s * open, u1 = s * WW;
        for (const N of [into, [-into[0], 0, -into[2]]]) {
          quadN(solid, at(u0, -3), at(u1, -3), at(u1, TOP), at(u0, TOP), cfg.dark, N);
        }
        col.addQuad(at(u0, -1.5), at(u1, -1.5), at(u1, TOP), at(u0, TOP), KIND.WALL);
        const g0 = proud(at(s * (open + 0.1), -0.5), 0.15), g1 = proud(at(s * (open + 1.4), -0.5), 0.15);
        quadN(solid, g0, g1, [g1[0], g1[1] + H1 + 2, g1[2]], [g0[0], g0[1] + H1 + 2, g0[2]], cfg.cap, into);
      }
      for (const N of [into, [-into[0], 0, -into[2]]]) {
        quadN(solid, at(-open, H1), at(open, H1), at(open, TOP), at(-open, TOP), cfg.dark, N);
      }
      quadN(solid, proud(at(-open - 1.4, H1), 0.15), proud(at(open + 1.4, H1), 0.15),
            proud(at(open + 1.4, H1 + 1.5), 0.15), proud(at(-open - 1.4, H1 + 1.5), 0.15), cfg.cap, into);
      // A band of glyphs across the gable, and a brazier either side of the mouth.
      for (let u = -WW + 2; u < WW - 2; u += 2.2) {
        if (Math.abs(u) < open + 2) continue;
        const p0 = at(u, H1 + 4), q0 = at(u + 1, H1 + 4);
        const d = [into[0] * 0.25, into[2] * 0.25];
        quadN(bright, [p0[0] + d[0], p0[1], p0[2] + d[1]], [q0[0] + d[0], q0[1], q0[2] + d[1]],
              [q0[0] + d[0], q0[1] + 1.4, q0[2] + d[1]], [p0[0] + d[0], p0[1] + 1.4, p0[2] + d[1]],
              (Math.round(u / 2.2) % 3) ? cfg.glyph2 : cfg.glyph, into);
      }
    }

    // ---- the lane's corridor across the hall ------------------------------------------
    // From each doorway to the crack, walls at the crack's width and a roof at
    // the lintel, so the shortcut is one tunnel from road to road rather than a
    // dash across the open hall. Each wall runs to where it meets the road's.
    {
      const roadWallX = (zl, fromChamber) => {
        let best = null;
        for (let i = 0; i < n - 1; i++) {
          const e = line[i], f = line[i + 1];
          if (e.p[1] > 1 || !isTunnel(e) || !isTunnel(f)) continue;
          for (const s of [-1, 1]) {
            const oa = wallOff(i, s), ob = wallOff(i + 1, s);
            const ax = e.p[0] + e.lat[0] * s * oa, az = e.p[2] + e.lat[2] * s * oa;
            const bx = f.p[0] + f.lat[0] * s * ob, bz = f.p[2] + f.lat[2] * s * ob;
            if ((az - zl) * (bz - zl) > 0 || az === bz) continue;
            const x = ax + (bx - ax) * (zl - az) / (bz - az);
            if (laneD(x, zl) > LW + 1) continue;
            if (fromChamber < 0 ? x < c0 && (best === null || x > best)
                                : x > c1 && (best === null || x < best)) best = x;
          }
        }
        return best;
      };
      const RY = G + LINTEL;
      for (const end of [-1, 1]) {
        let lo = Infinity, hi = -Infinity;
        for (const sd of [-1, 1]) {
          const zl = LZ + sd * LW;
          const x = roadWallX(zl, end);
          if (x === null) continue;
          const xa = end < 0 ? x : c1, xb = end < 0 ? c0 : x;
          lo = Math.min(lo, xa); hi = Math.max(hi, xb);
          wallBox((xa + xb) / 2, (G + RY + 1) / 2, zl + sd * 0.5, (xb - xa) / 2, (RY + 1 - G) / 2, 0.5, cfg.dark);
          for (let x2 = xa + 3; x2 < xb - 3; x2 += 6) {
            const z = zl - sd * 0.18;
            quadN(bright, [x2, G + 2.4, z], [x2 + 2.0, G + 2.4, z], [x2 + 2.0, G + 4.0, z],
                  [x2, G + 4.0, z], (x2 / 6 | 0) % 2 ? cfg.glyph : cfg.glyph2, [0, 0, -sd]);
          }
        }
        if (lo < hi) solid.box((lo + hi) / 2, RY + 0.5, LZ, (hi - lo) / 2, 0.5, LW + 1, cfg.dark);
      }
    }

    // ---- what the raised road stands on --------------------------------------------
    // A pier at each kerb every few stations, down to the floor - inside and
    // out, one design. Skipped wherever another road passes underneath.
    for (let i = 0; i < n; i += 5) {
      const e = line[i];
      if (e.air || e.p[1] < 3) continue;
      const inside = insidePyr(e.p);
      if (!inside) continue;                  // outside, the sand holds it up
      for (const s of [-1, 1]) {
        const o = e.hw - 1.6;
        const x = e.p[0] + e.lat[0] * s * o, z = e.p[2] + e.lat[2] * s * o;
        if (roadBelow(x, z, e.p[1], 3.5) || laneD(x, z) < cfg.laneHW + 3) continue;
        // Not collided. Nothing can reach one - the tunnel walls are between it
        // and the hall floor - and a collided top, flat at its own station's
        // height under a road that climbs, came within a car's sag of the
        // surface on the downhill side: a wall face pointing straight up, which
        // launched anybody driving off-centre up the ramps.
        pier(x, z, G, e.p[1] - 0.9, inside ? 1.5 : 2.2, inside ? cfg.dark : cfg.stone2, false);
      }
    }

    // ---- the hall ------------------------------------------------------------------------
    // Piers down both sides of the ground-level road, set back off the kerb, a
    // brazier at each. The same pier that carries the ramps.
    for (let i = 0; i < n; i += 8) {
      const e = line[i];
      if (e.air || e.p[1] > 0.5 || !insidePyr(e.p) || isTunnel(e)) continue;
      for (const s of [-1, 1]) {
        const off = e.hw + 8;
        const x = e.p[0] + e.lat[0] * s * off, z = e.p[2] + e.lat[2] * s * off;
        if (x > c0 - 4 && x < c1 + 4 && z > c2 - 4 && z < c3 + 4) continue;
        if (toRoad(x, z) < e.hw + 5 || laneD(x, z) < cfg.laneHW + 8) continue;
        const ceil = G + SLOPE * (k.depth(x, z) - TH) - 4;
        const top = Math.min(ceil, G + 30);
        if (top < G + 12) continue;
        pier(x, z, G, top, 2.2, cfg.dark, true);
        brazier(x - e.lat[0] * s * 3.4, G, z - e.lat[2] * s * 3.4);
      }
    }
    // Sand pouring from cracks in the roof - in the open dark, off the road.
    for (let q = 0, tries = 0; q < 6 && tries < 300; tries++) {
      const x = CX + (rnd() * 2 - 1) * (B - 50), z = CZ + (rnd() * 2 - 1) * (B - 50);
      if (x > c0 - 6 && x < c1 + 6 && z > c2 - 6 && z < c3 + 6) continue;
      if (toRoad(x, z) < 20 || laneD(x, z) < 20) continue;
      const top = G + SLOPE * (k.depth(x, z) - TH);
      if (top < G + 40) continue;
      soft.box(x, (G + top) / 2, z, 0.7, (top - G) / 2, 0.7, cfg.sandfall);
      for (let a = 0; a < 10; a++) {
        const t0 = a / 10 * Math.PI * 2, t1 = (a + 1) / 10 * Math.PI * 2;
        triN(solid, [x, G + 3, z], [x + Math.cos(t0) * 8, G + 0.15, z + Math.sin(t0) * 8],
             [x + Math.cos(t1) * 8, G + 0.15, z + Math.sin(t1) * 8], shade(cfg.sand, -0.3), UP);
      }
      q++;
    }

    // ---- the King's chamber ----------------------------------------------------------
    // The widest road at the top of the climb. A gold floor either side of it,
    // collided so running wide is gold and not a fall; piers holding up nothing
    // but the dark, pharaohs on guard, the sarcophagus and the treasure.
    {
      const room = [];
      for (let i = 0; i < n; i++) if (isKing(line[i])) room.push(i);
      if (room.length > 4) {
        const D = 22;
        for (let q = 0; q + 1 < room.length; q++) {
          const e = line[room[q]], f = line[room[q + 1]];
          for (const s of [-1, 1]) {
            const a0 = surf(e, s * e.hw, -0.05), b0 = surf(f, s * f.hw, -0.05);
            const a1 = surf(e, s * (e.hw + D), -0.05), b1 = surf(f, s * (f.hw + D), -0.05);
            quadN(solid, a0, b0, b1, a1, q % 2 ? cfg.cap : shade(cfg.cap, -0.1), UP);
            // Both windings: the ground query only counts a face that points
            // up, and which way this one points depends on the side.
            col.addQuad(a0, b0, b1, a1, KIND.OFFROAD);
            col.addQuad(a0, a1, b1, b0, KIND.OFFROAD);
            const d0 = [a1[0], a1[1] - 2.5, a1[2]], d1 = [b1[0], b1[1] - 2.5, b1[2]];
            solid.quad(a1, b1, d1, d0, cfg.dark2);
            solid.quad(a1, d0, d1, b1, cfg.dark2);
            col.addQuad(a1, b1, [b1[0], b1[1] + 1.2, b1[2]], [a1[0], a1[1] + 1.2, a1[2]], KIND.WALL);
          }
        }
        for (let q = 2; q < room.length - 2; q += 4) {
          const e = line[room[q]];
          for (const s of [-1, 1]) {
            const o = e.hw + 16;
            const x = e.p[0] + e.lat[0] * s * o, z = e.p[2] + e.lat[2] * s * o, y = e.p[1];
            const f = [-e.lat[0] * s, -e.lat[2] * s];
            solid.box(x, y + 1, z, 2.4, 1, 2.4, cfg.dark2);
            obox([x, z], f, 0, 0, y + 5.5, 1.2, 1.5, 3.5, cfg.cap);
            obox([x, z], f, 0, 0, y + 10.2, 1.0, 1.1, 1.2, cfg.cap);
            obox([x, z], f, -0.1, 0, y + 10.4, 1.3, 1.5, 1.6, cfg.lapis);
            for (let b2 = 0; b2 < 3; b2++) obox([x, z], f, -0.1, 0, y + 9.2 + b2 * 1.1, 1.35, 1.55, 0.18, cfg.cap);
            bright.box(x + f[0] * 1.05, y + 10.3, z + f[1] * 1.05, 0.2, 0.15, 0.2, cfg.glyph);
            pier(x - f[0] * 5, z - f[1] * 5, y, y + 22, 1.6, cfg.dark, false);
            brazier(x + f[0] * 4.5, y, z + f[1] * 4.5);
          }
        }
        const e = line[room[Math.floor(room.length / 2)]];
        const x = e.p[0] - e.lat[0] * (e.hw + 10), z = e.p[2] - e.lat[2] * (e.hw + 10), y = e.p[1];
        solid.box(x, y + 1.8, z, 4.2, 1.8, 2.2, cfg.cap);
        solid.box(x, y + 4.0, z, 3.8, 0.45, 2.0, shade(cfg.cap, -0.2));
        solid.box(x, y + 4.6, z, 1.1, 0.25, 1.3, cfg.lapis);
        for (let q = 0; q < 50; q++) {
          const qq = room[Math.floor(rnd() * room.length)], ee = line[qq];
          const s = rnd() < 0.5 ? -1 : 1, o = ee.hw + 4 + rnd() * 16;
          const tx = ee.p[0] + ee.lat[0] * s * o, tz = ee.p[2] + ee.lat[2] * s * o;
          const w = 0.35 + rnd() * 0.8;
          solid.box(tx, ee.p[1] + w, tz, w, w, w, rnd() < 0.8 ? cfg.cap : cfg.lapis);
        }
      }
    }

    // ---- the desert ------------------------------------------------------------------------
    const clearOf = (x, z, r) => toRoad(x, z) > r && k.depth(x, z) < -r * 0.6;
    // Where the dunes must lie flat: anything standing on the desert away from
    // the road records itself here, and the sand is built last, round them.
    const flats = [];

    // The sand runs to the horizon. The engine's plate stops a few cells past
    // the road, and past it is sky - which read as a white line round the world.
    quadN(solid, [CX - 7000, G - 0.4, CZ - 7000], [CX + 7000, G - 0.4, CZ - 7000],
          [CX + 7000, G - 0.4, CZ + 7000], [CX - 7000, G - 0.4, CZ + 7000], shade(pal.ground, -0.04), UP);

    // ---- the sand itself ---------------------------------------------------------
    // The engine's ground is one flat colour, and half of every frame is it.
    // There are no image textures in scenery, so the texture is in the
    // vertices: a sheet over the whole lap, coloured by smooth noise and by
    // long wind streaks, and shaped into dunes away from the road (see
    // `buildSand`, which runs last). Ripple lines near the road were tried and
    // rejected - the colour and the shape are what read as sand; drawn lines
    // read as marks on it.
    const hash = (ix, iz) => {
      let h = (ix * 374761393 + iz * 668265263) | 0;
      h = (h ^ (h >>> 13)) * 1274126177 | 0;
      return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
    };
    const vnoise = (x, z) => {
      const ix = Math.floor(x), iz = Math.floor(z), fx = x - ix, fz = z - iz;
      const sx = fx * fx * (3 - 2 * fx), sz = fz * fz * (3 - 2 * fz);
      const a = hash(ix, iz), b = hash(ix + 1, iz), c = hash(ix, iz + 1), d = hash(ix + 1, iz + 1);
      return (a + (b - a) * sx) + ((c + (d - c) * sx) - (a + (b - a) * sx)) * sz;
    };
    const WIND = [Math.cos(0.6), Math.sin(0.6)];         // the way the dunes lie
    const lerpC = (c1, c2, t) => {
      const r = ((c1 >> 16) & 255) + (((c2 >> 16) & 255) - ((c1 >> 16) & 255)) * t;
      const g = ((c1 >> 8) & 255) + (((c2 >> 8) & 255) - ((c1 >> 8) & 255)) * t;
      const bl = (c1 & 255) + ((c2 & 255) - (c1 & 255)) * t;
      return (Math.round(r) << 16) | (Math.round(g) << 8) | Math.round(bl);
    };
    const sandAt = (x, z) => {
      const n1 = vnoise(x / 90, z / 90), n2 = vnoise(x / 23 + 7.1, z / 23 - 3.3);
      // Streaks: long bands across the wind, bent by the noise so they wander.
      const along = x * WIND[0] + z * WIND[1];
      const streak = 0.5 + 0.5 * Math.sin(along / 19 + n1 * 5.0);
      const t = Math.min(1, Math.max(0, n1 * 0.6 + n2 * 0.45 + streak * 0.2 - 0.12));
      const base = lerpC(cfg.sandDeep, cfg.sandLight, t);
      return base;
    };
    // Grain: every vertex its own small step lighter or darker, and now and
    // then a darker fleck - noise at the scale of the grid, which from the car
    // reads as texture rather than as a flat colour.
    const grain = (c, x, z) => {
      const g = hash(Math.round(x * 3.7) + 7919, Math.round(z * 5.3) - 104729);
      return shade(c, g < 0.06 ? -0.13 : (g - 0.5) * 0.11);
    };
    const buildSand = () => {
      let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
      for (const e of line) {
        x0 = Math.min(x0, e.p[0]); x1 = Math.max(x1, e.p[0]);
        z0 = Math.min(z0, e.p[2]); z1 = Math.max(z1, e.p[2]);
      }
      // Drawn at 6, collided at 12 - every other vertex of the same heights. The
      // fine grid is what the grain needs; the collider does not need it, and
      // the anti-cheat builds the collider on every lap it re-drives.
      const M = 420, C = 6;
      x0 = Math.floor((x0 - M) / 12) * 12; z0 = Math.floor((z0 - M) / 12) * 12;
      const NX = Math.ceil((x1 + M - x0) / C) + 1, NZ = Math.ceil((z1 + M - z0) / C) + 1;
      // Distance to the nearest kerb, per grid vertex, stamped outward from the
      // stations rather than asked per vertex - the per-vertex question is a
      // million distance tests and runs on every lap the anti-cheat re-drives.
      const R = 110, dist = new Float32Array(NX * NZ).fill(R);
      for (const e of line) {
        if (e.air) continue;
        const ci = Math.round((e.p[0] - x0) / C), cj = Math.round((e.p[2] - z0) / C), rr = Math.ceil(R / C);
        for (let a = Math.max(0, ci - rr); a <= Math.min(NX - 1, ci + rr); a++) {
          for (let b2 = Math.max(0, cj - rr); b2 <= Math.min(NZ - 1, cj + rr); b2++) {
            const d = Math.hypot(x0 + a * C - e.p[0], z0 + b2 * C - e.p[2]) - e.hw;
            if (d < dist[a * NZ + b2]) dist[a * NZ + b2] = d;
          }
        }
      }
      const sm = (t) => { t = Math.max(0, Math.min(1, t)); return t * t * (3 - 2 * t); };
      // Dunes: ridges lying across the wind, a long gentle windward face and a
      // short steep lee, wandering, and taller the further from the road -
      // flat within reach of a car on the road, and flat under anything
      // standing on the sand and round the pyramid.
      const relief = (x, z, d) => {
        let g = sm((d - 12) / 30) * sm((-k.depth(x, z) - 24) / 50);
        for (const [fx, fz, fr] of flats) g *= sm((Math.hypot(x - fx, z - fz) - fr) / 30);
        if (g <= 0) return 0;
        const along = x * WIND[0] + z * WIND[1];
        const ph = along / 74 + vnoise(x / 130, z / 130) * 2.2;
        const f = ph - Math.floor(ph);
        const ridge = f < 0.72 ? sm(f / 0.72) : sm((1 - f) / 0.28);
        const env = 0.35 + 0.65 * vnoise(x / 170 + 3.1, z / 170 - 1.7);
        const tall = 5 + 16 * sm((d - 40) / 280);
        return g * (tall * ridge * env + 3 * vnoise(x / 47, z / 47));
      };
      const H = new Float32Array(NX * NZ);
      for (let a = 0; a < NX; a++) {
        for (let b2 = 0; b2 < NZ; b2++) H[a * NZ + b2] = relief(x0 + a * C, z0 + b2 * C, dist[a * NZ + b2]);
      }
      const col0 = (x, z, h) => grain(lerpC(sandAt(x, z), cfg.sandLight, Math.min(1, h / 16) * 0.5), x, z);
      const Y = G + 0.08;
      const at = (a, b2) => [x0 + a * C, Y + H[a * NZ + b2], z0 + b2 * C];
      for (let a = 0; a + 1 < NX; a++) {
        for (let b2 = 0; b2 + 1 < NZ; b2++) {
          const x = x0 + a * C, z = z0 + b2 * C;
          // Not under the pyramid: it has a floor of its own.
          if (k.depth(x + C / 2, z + C / 2) > -C) continue;
          const p00 = at(a, b2), p01 = at(a, b2 + 1), p11 = at(a + 1, b2 + 1), p10 = at(a + 1, b2);
          solid.quadV(p00, p01, p11, p10, col0(p00[0], p00[2], p00[1] - Y), col0(p01[0], p01[2], p01[1] - Y),
                      col0(p11[0], p11[2], p11[1] - Y), col0(p10[0], p10[2], p10[1] - Y));
        }
      }
      // Solid wherever it is off the plate, so running wide climbs a dune
      // instead of driving through the picture of one. On the 12 grid.
      for (let a = 0; a + 2 < NX; a += 2) {
        for (let b2 = 0; b2 + 2 < NZ; b2 += 2) {
          if (k.depth(x0 + a * C + C, z0 + b2 * C + C) > -2 * C) continue;
          const p00 = at(a, b2), p01 = at(a, b2 + 2), p11 = at(a + 2, b2 + 2), p10 = at(a + 2, b2);
          if (p00[1] + p01[1] + p11[1] + p10[1] - 4 * Y > 0.4) col.addQuad(p00, p01, p11, p10, KIND.OFFROAD);
        }
      }
    };
    // Out on the desert the road sits in the sand: a berm down each side at a
    // slope sand would hold, coloured like the ground it runs into, and solid
    // as off-road. **Everywhere, not only where the road is raised.** The road
    // stands 1.2 over the ground plate, and that step is what kicked the car
    // up every time a wheel came back on from the sand - a bot never leaves its
    // line, so only a person found it. A ramp off the kerb is no step at all.
    // Where it meets the pyramid, the pyramid wins.
    {
      const SL = 3.5;                          // run per unit of height: a drift, lit like the flat
      // Which segments got a berm, per side, and where its foot landed - so a
      // berm that stops (at the jump, at the pyramid) can be closed off.
      const drawn = { [-1]: new Array(n).fill(null), [1]: new Array(n).fill(null) };
      for (let i = 0; i < n - 1; i++) {
        const e = line[i], f = line[i + 1];
        if (e.air || f.air || insidePyr(e.p) || insidePyr(f.p)) continue;
        const he = e.p[1] - G, hf = f.p[1] - G;
        for (const s of [-1, 1]) {
          // From the road's own edge at the road's own height - a lip or a slot
          // of even a twentieth of a unit is a bump at fifty units a second.
          const ta = surf(e, s * e.hw, 0), tb = surf(f, s * f.hw, 0);
          // At least eight units of run, so even the flat road's 1.2 is a
          // slope a car rolls over rather than a lip it hits.
          const da = e.hw + Math.max(8, (he - 0.1) * SL), db = f.hw + Math.max(8, (hf - 0.1) * SL);
          const fa = [e.p[0] + e.lat[0] * s * da, G + 0.1, e.p[2] + e.lat[2] * s * da];
          const fb = [f.p[0] + f.lat[0] * s * db, G + 0.1, f.p[2] + f.lat[2] * s * db];
          if (k.depth(fa[0], fa[2]) > -2 || k.depth(fb[0], fb[2]) > -2) continue;
          // Drawn as strips two units wide, each vertex grained, because this is
          // the sand right under the camera; collided as one quad below.
          const S4 = Math.max(2, Math.round((da - e.hw) / 2));
          const lerp3 = (p, q, t) => [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, p[2] + (q[2] - p[2]) * t];
          for (let q = 0; q < S4; q++) {
            const a0 = lerp3(ta, fa, q / S4), a1 = lerp3(ta, fa, (q + 1) / S4);
            const b0 = lerp3(tb, fb, q / S4), b1 = lerp3(tb, fb, (q + 1) / S4);
            const c = (p) => grain(sandAt(p[0], p[2]), p[0], p[2]);
            const ca0 = c(a0), cb0 = c(b0), cb1 = c(b1), ca1 = c(a1);
            solid.quadV(a0, b0, b1, a1, ca0, cb0, cb1, ca1);
            solid.quadV(a0, a1, b1, b0, ca0, ca1, cb1, cb0);
          }
          // Both windings: the ground query only counts a face that points up,
          // and on the right-hand side this one pointed down - the berm was
          // drawn and not there, and every wheel off the right kerb fell to the
          // plate and kicked back up onto the road edge.
          col.addQuad(ta, tb, fb, fa, KIND.OFFROAD);
          col.addQuad(ta, fa, fb, tb, KIND.OFFROAD);
          drawn[s][i] = [ta, fa, tb, fb];
        }
      }
      // **The ends.** A berm is an open slope, so where it stops - each side of
      // the jump out of the pyramid - it showed its own underside and the dark
      // under the road, a hole in the dune seen from the air. Close each end
      // with its cross-section: road edge, foot, and down the middle of the road.
      const cut = (e, top, foot) => {
        const c0 = [e.p[0], e.p[1] - 0.05, e.p[2]], c1 = [e.p[0], G + 0.1, e.p[2]];
        const kc = grain(shade(sandAt(e.p[0], e.p[2]), -0.12), e.p[0], e.p[2]);
        solid.quad(c0, top, foot, c1, kc);
        solid.quad(c0, c1, foot, top, kc);
        // Not collided: its top edge is the road's own, and a wall face there
        // kicked every car rolling over the pyramid's doors.
      };
      const closed = !!ctx.track.closed;
      const wrap = (i) => closed ? (i + n - 1) % (n - 1) : i;
      for (const s of [-1, 1]) {
        const d = drawn[s];
        for (let i = 0; i < n - 1; i++) {
          if (!d[i]) continue;
          const before = i > 0 || closed ? d[wrap(i - 1)] : null;
          const after = i < n - 2 || closed ? d[wrap(i + 1)] : null;
          if (!before) cut(line[i], d[i][0], d[i][1]);
          if (!after) cut(line[i + 1], d[i][2], d[i][3]);
        }
      }
    }


    // Pyramids on the horizon: the same stepped build, bigger blocks, far.
    for (const [ang, dist, b] of [[2.7, 1500, 210], [3.05, 1800, 150], [2.25, 1700, 120], [-0.7, 1650, 170]]) {
      stepped(CX + Math.cos(ang) * dist, CZ + Math.sin(ang) * dist, b, b * SLOPE, 10, 30, false, false);
    }

    // The processional way: sphinxes either side of the approach, facing in,
    // from the last bend to the gateway, and the great sphinx out on the sand.
    {
      let door = -1;
      for (let i = 0; i < n; i++) if (insidePyr(line[i].p)) { door = i; break; }
      if (door > 0) {
        let first = door;
        while (first > 0 && !line[first - 1].curv) first--;
        for (let i = first + 6; i < door - 24; i += 9) {
          const e = line[i];
          for (const s of [-1, 1]) {
            const o = e.hw + 9;
            const x = e.p[0] + e.lat[0] * s * o, z = e.p[2] + e.lat[2] * s * o;
            sphinx([x, z], [-e.lat[0] * s, -e.lat[2] * s], 0.3);
            wallBox(x, G + 2.5, z, 3.5, 2.5, 3.5, cfg.stone2);
          }
        }
        const e = line[Math.max(0, first - 6)];
        let placed = false;
        for (const off of [90, 110, 130, 160]) {
          for (const s of [-1, 1]) {
            const x = e.p[0] + e.lat[0] * s * off, z = e.p[2] + e.lat[2] * s * off;
            if (!placed && clearOf(x, z, 45)) {
              sphinx([x, z], [-e.lat[0] * s, -e.lat[2] * s], 1); placed = true; flats.push([x, z, 34]);
            }
          }
          if (placed) break;
        }
      }
    }

    // Obelisks in pairs down the longest desert straight.
    {
      let bi = 0, bl = 0, i = 0;
      while (i < n) {
        if (line[i].curv || line[i].air || insidePyr(line[i].p)) { i++; continue; }
        let j = i; while (j + 1 < n && !line[j + 1].curv && !line[j + 1].air) j++;
        if (j - i > bl) { bl = j - i; bi = i; }
        i = j + 1;
      }
      for (let q = bi + 6; q < bi + bl - 6; q += 14) {
        const e = line[q];
        for (const s of [-1, 1]) {
          const o = e.hw + 11;
          const x = e.p[0] + e.lat[0] * s * o, z = e.p[2] + e.lat[2] * s * o;
          if (toRoad(x, z) < e.hw + 8) continue;
          obelisk(x, z, 24);
        }
      }
    }

    // The oasis: a pool and its palms, wherever the desert has the room.
    {
      let best = null;
      for (let t = 0; t < 500; t++) {
        const ang = rnd() * Math.PI * 2, dist = B + 120 + rnd() * 300;
        const x = CX + Math.cos(ang) * dist, z = CZ + Math.sin(ang) * dist;
        const d = toRoad(x, z);
        if (d > 46 && d < 70 && k.depth(x, z) < -40 && (!best || d < best[2])) best = [x, z, d];
      }
      if (best) {
        const [ox, oz] = best, R = 26;
        flats.push([ox, oz, R + 22]);
        for (let q = 0; q < 16; q++) {
          const t0 = q / 16 * Math.PI * 2, t1 = (q + 1) / 16 * Math.PI * 2;
          const r0 = R * (0.9 + 0.1 * Math.sin(q * 2.1)), r1 = R * (0.9 + 0.1 * Math.sin((q + 1) * 2.1));
          triN(solid, [ox, G + 0.5, oz], [ox + Math.cos(t0) * r0, G + 0.5, oz + Math.sin(t0) * r0 * 0.75],
               [ox + Math.cos(t1) * r1, G + 0.5, oz + Math.sin(t1) * r1 * 0.75], cfg.water, UP);
          quadN(solid, [ox + Math.cos(t0) * r0, G + 0.35, oz + Math.sin(t0) * r0 * 0.75],
                [ox + Math.cos(t1) * r1, G + 0.35, oz + Math.sin(t1) * r1 * 0.75],
                [ox + Math.cos(t1) * (r1 + 7), G + 0.35, oz + Math.sin(t1) * (r1 + 7) * 0.75],
                [ox + Math.cos(t0) * (r0 + 7), G + 0.35, oz + Math.sin(t0) * (r0 + 7) * 0.75],
                cfg.grass, UP);
        }
        for (let q = 0; q < 11; q++) {
          const a = q / 11 * Math.PI * 2 + rnd() * 0.3, r = R + 3 + rnd() * 10;
          palm(ox + Math.cos(a) * r, oz + Math.sin(a) * r * 0.75, 11 + rnd() * 8);
        }
      }
    }
    function palm(x, z, h) {
      const lean = (rnd() - 0.5) * 0.3, lz2 = (rnd() - 0.5) * 0.3;
      const segs = 7;
      for (let q = 0; q < segs; q++) {
        const y = G + h * (q + 0.5) / segs;
        solid.box(x + lean * h * q / segs, y, z + lz2 * h * q / segs, 0.45 - q * 0.03, h / segs / 2,
                  0.45 - q * 0.03, q % 2 ? cfg.trunk : shade(cfg.trunk, -0.1));
      }
      const tx = x + lean * h, ty = G + h, tz = z + lz2 * h;
      for (let f = 0; f < 8; f++) {
        const a = f / 8 * Math.PI * 2 + rnd() * 0.3;
        const mx = tx + Math.cos(a) * 3.6, mz = tz + Math.sin(a) * 3.6;
        const ex = tx + Math.cos(a) * 7, ez = tz + Math.sin(a) * 7;
        const px = -Math.sin(a) * 1.2, pz = Math.cos(a) * 1.2;
        const kc = shade(cfg.palm, (rnd() - 0.5) * 0.1);
        for (const sgn of [1, -1]) {
          triN(solid, [tx, ty + 0.4, tz], [mx + px, ty + 0.3, mz + pz], [mx - px, ty + 0.3, mz - pz], kc, [0, sgn, 0]);
          triN(solid, [mx + px, ty + 0.3, mz + pz], [ex, ty - 2.6, ez], [mx - px, ty + 0.3, mz - pz], kc, [0, sgn, 0]);
        }
      }
    }

    // Ruined colonnades, a few, out on the sand.
    for (let q = 0, tries = 0; q < 6 && tries < 300; tries++) {
      const ang = rnd() * Math.PI * 2, dist = B + 80 + rnd() * 380;
      const x = CX + Math.cos(ang) * dist, z = CZ + Math.sin(ang) * dist;
      if (!clearOf(x, z, 34)) continue;
      flats.push([x, z, 26]);
      for (let c = 0; c < 6; c++) {
        const cx = x + c * 7 - 17, h = c === 2 || c === 4 ? 3 + rnd() * 3 : 12 + rnd() * 10;
        solid.box(cx, G + h / 2, z, 1.5, h / 2, 1.5, shade(cfg.stone, -0.05));
        if (h > 8) solid.box(cx, G + h + 0.6, z, 2.1, 0.6, 2.1, cfg.stone2);
      }
      solid.box(x + 7, G + 0.8, z + 4.5, 4.5, 0.8, 1.5, cfg.stone2);
      solid.box(x - 6, G + 0.6, z - 4, 1.5, 0.6, 3.5, cfg.stone2);
      q++;
    }

    buildSand();
  }

})();
