// High Roller: a toy car loose in a giant casino.
//
// Built off reference photos of real Las Vegas floors, not a mental picture:
// slot banks back to back with lit screens, LED trim, toppers and stools; domed
// ceilings with tiered crystal chandeliers in a gold coffer grid; busy carpet;
// craps under a padded rail with the real layout on the felt; a mahogany
// roulette wheel with red and black pockets and a gold turret; blackjack's
// half-moon with its gold lettering, betting circles and chairs.
//
// Every set piece is found off the ribbon rather than placed by number:
//   card ramps    `skin` stations 13 wide before the jump (the ace) and after
//                 the spiral (the queen); the ramp *is* the card
//   craps         the stations 18 wide; the felt is the road
//   roulette      the `skin` stations between the jump and the spiral are the
//                 betting layout; the wheel turns at the spiral's pivot
//   blackjack     the stations 16 wide, a half-moon round their pivot
//   slot machine  the second pad run and the 74 units after it
//   chip stacks   the inside of every radius-24 corner, and under every
//                 stretch of raised road that is not on a table
// so a re-solved lap carries its furniture with it.
//
// Pictures ride the `signs` list (`art`), painted by tools/make_casino_art.py,
// and never reach QuickJS. Solid: the chip stacks, the slot cabinets, every
// table's rail, chairs and dealer kit, the felts and card faces (as road, with
// their normals up - the ground query skips a face-down floor), the columns,
// and the dice and ball (movers). The wheel is a `ghost` mover: it turns, and
// nothing can touch it.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.casino = { props: props, movers: movers };

  const ART = '/static/img/art/casino/';
  const ROOM_MARGIN = 120;
  const CEIL = 130;

  // An unlit vertex colour is lifted sRGB-ward on the way out and a texture
  // tagged sRGB is not, so geometry that has to match a picture (the felt
  // round a printed layout, a chip's top round its face) is given the
  // picture's colour converted to linear.
  const lin = (hex) => {
    const ch = (v) => { v /= 255; return Math.round(255 * (v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4))); };
    return (ch(hex >> 16 & 255) << 16) | (ch(hex >> 8 & 255) << 8) | ch(hex & 255);
  };
  const FELT = lin(0x186036);     // the art's own felt
  const WOOD = 0x5a2a16, WOOD_D = 0x3a1a0e, LEATHER = 0x24120c;
  const GOLD = 0xb08a36, GOLD_L = 0xd8b45a;
  // Bodies are the chip faces' own colours (tools/make_casino_art.py, CHIPS).
  const CHIPS = [[0xb01420, 0xe8e2d4], [0x186e38, 0xe8e2d4], [0x16161a, 0xe8e2d4],
                 [0x602882, 0xe8e2d4], [0xd6aa28, 0x2a1a08]];
  const GLOWS = [0xff3aa0, 0x40b8ff, 0xff4a30, 0xffc030, 0x40ff80, 0xb060ff];

  const near = (a, b, eps) => Math.abs(a - b) < eps;
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const add = (a, b, s) => [a[0] + b[0] * s, a[1] + b[1] * s, a[2] + b[2] * s];
  const len = (a) => Math.hypot(a[0], a[1], a[2]);
  const norm = (a) => { const l = len(a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const fwdAt = (line, i) => {
    const n = line.length;
    const a = line[Math.max(0, i - 1)].p, b = line[Math.min(n - 1, i + 1)].p;
    const dx = b[0] - a[0], dz = b[2] - a[2], d = Math.hypot(dx, dz) || 1;
    return [dx / d, 0, dz / d];
  };
  // Horizontal right-hand vector of a horizontal forward vector.
  const latOf = (f) => [-f[2], 0, f[0]];

  // A ball as quads, for a mover's `quads`: lit and flat-shaded, which is what
  // makes it read round - an unlit one is a disc.
  function sphereQuads(cx, cy, cz, R, colr, nu, nv) {
    const q = [];
    const P = (i, j) => {
      const th = i / nu * Math.PI * 2, ph = j / nv * Math.PI;
      return [cx + R * Math.sin(ph) * Math.cos(th), cy + R * Math.cos(ph), cz + R * Math.sin(ph) * Math.sin(th)];
    };
    for (let i = 0; i < nu; i++) {
      for (let j = 0; j < nv; j++) q.push([P(i, j), P(i + 1, j), P(i + 1, j + 1), P(i, j + 1), colr]);
    }
    return q;
  }

  function runs(idx) {
    const out = [];
    for (const i of idx) {
      const r = out[out.length - 1];
      if (r && i === r[r.length - 1] + 1) r.push(i); else out.push([i]);
    }
    return out;
  }

  // The set pieces, in lap order, by structure rather than by width (the
  // table gates make the road as wide as the table, so width says nothing):
  // the first `skin` run is the ace and then the craps felt, split where it
  // reaches the table's height; the run after the jump is the roulette layout;
  // the curve after that is the spiral; the next run is the queen and then the
  // blackjack felt.
  function sections(line) {
    const n = line.length;
    let air0 = n, air1 = -1;
    for (let i = 0; i < n; i++) if (line[i].air) { air0 = Math.min(air0, i); air1 = i; }
    const skins = runs(line.map((e, i) => (e.skin ? i : -1)).filter((i) => i >= 0));
    const before = skins.find((r) => r[0] < air0) || [];
    const landing = skins.find((r) => r[0] > air1) || [];
    const after = skins.find((r) => landing.length && r[0] > landing[landing.length - 1]) || [];
    // A ramp and the table it climbs to: the card runs up to and including the
    // first station at the table's height, so card and felt meet edge to edge.
    const split = (r) => {
      let top = -Infinity;
      for (const i of r) top = Math.max(top, line[i].p[1]);
      const j = r.findIndex((i) => line[i].p[1] >= top - 0.01);
      return j < 0 ? [r, []] : [r.slice(0, j + 1), r.slice(j)];
    };
    const [card1, craps] = split(before);
    const [card2, bj] = split(after);
    const spiral = [];
    for (let i = (landing.length ? landing[landing.length - 1] + 1 : n); i < n && line[i].curv; i++) spiral.push(i);
    const chips = [], pad1 = [], late = [];
    for (let i = 0; i < n; i++) {
      const e = line[i];
      if (e.curv && near(Math.abs(e.curv), 1 / 24, 0.002) && e.p[1] < 0.5) chips.push(i);
      if (e.bp) (i < air0 ? pad1 : late).push(i);
    }
    const lr = runs(late);
    return { air0, air1, craps, spiral, chips, bj, landing, card1, card2, pad1,
             pad2: lr[0] || [], pad3: lr[1] || [] };
  }

  // Centre and radius of the circle through an arc's first, middle and last
  // stations: the pivot it was laid round.
  function pivot(line, idx) {
    const A = line[idx[0]].p, B = line[idx[idx.length >> 1]].p, C = line[idx[idx.length - 1]].p;
    const ax = A[0], az = A[2], bx = B[0], bz = B[2], qx = C[0], qz = C[2];
    const d = 2 * (ax * (bz - qz) + bx * (qz - az) + qx * (az - bz));
    const cx = ((ax * ax + az * az) * (bz - qz) + (bx * bx + bz * bz) * (qz - az) + (qx * qx + qz * qz) * (az - bz)) / d;
    const cz = ((ax * ax + az * az) * (qx - bx) + (bx * bx + bz * bz) * (ax - qx) + (qx * qx + qz * qz) * (bx - ax)) / d;
    return [cx, cz, Math.hypot(ax - cx, az - cz)];
  }

  // The rectangle the craps table stands on.
  function crapsRect(line, S) {
    let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity, y = 0;
    for (const i of S.craps) {
      const p = line[i].p;
      x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]);
      z0 = Math.min(z0, p[2]); z1 = Math.max(z1, p[2]);
      y = Math.max(y, p[1]);
    }
    const M = 9 + 12;
    x0 -= M; x1 += M; z0 -= M; z1 += M;
    // Flush with the top of the card, and with the foot of the kicker at the
    // far end: past either, the felt would stand over road that is still
    // climbing to it, and the car clips its edge.
    const trim = (i, back) => {
      const p = line[i].p, f = fwdAt(line, i), s = back ? -1 : 1;
      if (Math.abs(f[2]) > Math.abs(f[0])) { if (f[2] * s > 0) z0 = p[2]; else z1 = p[2]; }
      else if (f[0] * s > 0) x0 = p[0]; else x1 = p[0];
    };
    // The near side is the card's top edge; the far side is put as far from
    // the road's long run, so the table is centred on it and the gate (as
    // wide as the table, less the rails) is too.
    const p0 = line[S.craps[0]].p, f0 = fwdAt(line, S.craps[0]);
    let long = [];
    for (const r of runs(S.craps.filter((i) => !line[i].curv))) if (r.length > long.length) long = r;
    if (long.length) {
      let m = 0;
      for (const i of long) m += Math.abs(f0[2]) > Math.abs(f0[0]) ? line[i].p[2] : line[i].p[0];
      m /= long.length;
      if (Math.abs(f0[2]) > Math.abs(f0[0])) { if (f0[2] > 0) z1 = 2 * m - p0[2]; else z0 = 2 * m - p0[2]; }
      else if (f0[0] > 0) x1 = 2 * m - p0[0]; else x0 = 2 * m - p0[0];
    }
    trim(S.craps[0], false);
    trim(S.craps[S.craps.length - 1], true);
    return { x0, x1, z0, z1, y };
  }

  function props(ctx) {
    const { solid, bright, signs, col, track, KIND, groundY, mulberry, shade } = ctx;
    const line = track.line, n = line.length;
    const G = groundY != null ? groundY : -1.2;
    const S = sections(line);
    const rnd = mulberry(0xca5170);

    // --- primitives ------------------------------------------------------------
    const quad2 = (buf, a, b, c, d, k) => { buf.quad(a, b, c, d, k); buf.quad(a, d, c, b, k); };
    // A drivable surface, wound so its normal points up whatever order the
    // corners came in: `Collider.ground` skips a floor it is behind.
    const floorQuad = (a, b, c, d, kind) => {
      const ny = (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]);
      if (ny >= 0) col.addQuad(a, b, c, d, kind); else col.addQuad(a, d, c, b, kind);
    };
    const floorTri = (a, b, c, kind) => {
      const ny = (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]);
      if (ny >= 0) col.add(a, b, c, kind); else col.add(a, c, b, kind);
    };
    const corners = (c, f, l, hx, hy, hz) => {
      const v = [];
      for (const sy of [-1, 1]) for (const sz of [-1, 1]) for (const sx of [-1, 1]) {
        v.push([c[0] + l[0] * hx * sx + f[0] * hz * sz, c[1] + hy * sy,
                c[2] + l[2] * hx * sx + f[2] * hz * sz]);
      }
      return v;
    };
    // An upright box with its own heading; f, l horizontal unit vectors.
    const obox = (buf, c, f, l, hx, hy, hz, k) => {
      const v = corners(c, f, l, hx, hy, hz);
      quad2(buf, v[0], v[1], v[3], v[2], k);
      quad2(buf, v[4], v[5], v[7], v[6], k);
      quad2(buf, v[0], v[1], v[5], v[4], k);
      quad2(buf, v[2], v[3], v[7], v[6], k);
      quad2(buf, v[0], v[2], v[6], v[4], k);
      quad2(buf, v[1], v[3], v[7], v[5], k);
    };
    const oboxCol = (c, f, l, hx, hy, hz) => {
      const v = corners(c, f, l, hx, hy, hz);
      col.addQuad(v[0], v[1], v[5], v[4], KIND.WALL);
      col.addQuad(v[2], v[3], v[7], v[6], KIND.WALL);
      col.addQuad(v[0], v[2], v[6], v[4], KIND.WALL);
      col.addQuad(v[1], v[3], v[7], v[5], KIND.WALL);
    };
    const cyl = (buf, cx, y0, cz, r, h, k, top, sides, r1) => {
      const m = sides || 12, rt = r1 != null ? r1 : r;
      for (let i = 0; i < m; i++) {
        const a0 = i / m * Math.PI * 2, a1 = (i + 1) / m * Math.PI * 2;
        const A = [cx + Math.cos(a0) * r, y0, cz + Math.sin(a0) * r];
        const B = [cx + Math.cos(a1) * r, y0, cz + Math.sin(a1) * r];
        const C = [cx + Math.cos(a1) * rt, y0 + h, cz + Math.sin(a1) * rt];
        const D = [cx + Math.cos(a0) * rt, y0 + h, cz + Math.sin(a0) * rt];
        quad2(buf, A, B, C, D, k);
        if (top != null) {
          buf.tri([cx, y0 + h, cz], C, D, top);
          buf.tri([cx, y0 + h, cz], D, C, top);
        }
      }
    };
    const cylCol = (cx, y0, cz, r, h, sides) => {
      const m = sides || 12;
      for (let i = 0; i < m; i++) {
        const a0 = i / m * Math.PI * 2, a1 = (i + 1) / m * Math.PI * 2;
        const A = [cx + Math.cos(a0) * r, y0, cz + Math.sin(a0) * r];
        const B = [cx + Math.cos(a1) * r, y0, cz + Math.sin(a1) * r];
        col.addQuad(A, B, [B[0], y0 + h, B[2]], [A[0], y0 + h, A[2]], KIND.WALL);
      }
    };
    const ring = (buf, cx, y, cz, r0, r1, k, sides) => {
      const m = sides || 24;
      for (let i = 0; i < m; i++) {
        const u = Math.PI * 2 * i / m, v = Math.PI * 2 * (i + 1) / m;
        quad2(buf, [cx + Math.cos(u) * r0, y, cz + Math.sin(u) * r0], [cx + Math.cos(u) * r1, y, cz + Math.sin(u) * r1],
              [cx + Math.cos(v) * r1, y, cz + Math.sin(v) * r1], [cx + Math.cos(v) * r0, y, cz + Math.sin(v) * r0], k);
      }
    };
    // A picture on a panel: c centre, r right, u up, half sizes, n the way it faces.
    const art = (name, aspect, c, r, u, hw, hh, nrm) => {
      signs.push({ art: ART + name + '.png', aspect: aspect, c: c, r: r, u: u, hw: hw, hh: hh, n: nrm });
    };
    // Plan distance from (x, z) to the nearest road edge within a height band.
    const roadDist = (x, z, ylo, yhi) => {
      let best = Infinity;
      for (let i = 0; i < n; i++) {
        const p = line[i].p;
        if (p[1] < ylo || p[1] > yhi) continue;
        const d = Math.hypot(p[0] - x, p[2] - z) - line[i].hw;
        if (d < best) best = d;
      }
      return best;
    };
    // Ground already spoken for (tables, cards, the wheel), so the floor fill
    // and the chandeliers keep off it; and table tops, so the pillars do.
    const claimed = [];
    const claim = (ax, az, bx, bz) => claimed.push([Math.min(ax, bx), Math.min(az, bz), Math.max(ax, bx), Math.max(az, bz)]);
    const isClaimed = (x, z, pad) => claimed.some((c) => x > c[0] - pad && x < c[2] + pad && z > c[1] - pad && z < c[3] + pad);
    const tops = [];
    let bjExit = null;
    const onTable = (x, z) => tops.some((t) => t(x, z));

    // A stack of chips, edge spots and all, the top chip's face a picture.
    const CHIP_T = 1.25;
    const chipStack = (cx, cz, r, count, kind, solidStack, y0) => {
      const base = y0 != null ? y0 : G;
      const [body, spot] = CHIPS[kind];
      for (let c = 0; c < count; c++) {
        const y = base + c * CHIP_T;
        cyl(solid, cx, y, cz, r, CHIP_T * 0.94, body, null, 14);
        for (let s2 = 0; s2 < 6; s2++) {
          const a = (s2 + (c % 2) * 0.5) / 6 * Math.PI * 2, da = 0.16;
          const A = [cx + Math.cos(a - da) * (r + 0.04), y + 0.18, cz + Math.sin(a - da) * (r + 0.04)];
          const B = [cx + Math.cos(a + da) * (r + 0.04), y + 0.18, cz + Math.sin(a + da) * (r + 0.04)];
          quad2(solid, A, B, [B[0], y + CHIP_T * 0.78, B[2]], [A[0], y + CHIP_T * 0.78, A[2]], spot);
        }
      }
      const top = base + count * CHIP_T;
      cyl(bright, cx, top - 0.06, cz, r * 0.995, 0.05, lin(body), lin(body), 14);
      const q = r * 0.7071;
      art('chip-' + kind, 1, [cx, top + 0.02, cz], [1, 0, 0], [0, 0, -1], q, q, [0, 1, 0]);
      if (solidStack) cylCol(cx, base, cz, r, count * CHIP_T, 10);
      return top;
    };

    // --- the room -------------------------------------------------------------
    let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
    for (const e of line) {
      x0 = Math.min(x0, e.p[0]); x1 = Math.max(x1, e.p[0]);
      z0 = Math.min(z0, e.p[2]); z1 = Math.max(z1, e.p[2]);
    }
    x0 -= ROOM_MARGIN; x1 += ROOM_MARGIN; z0 -= ROOM_MARGIN; z1 += ROOM_MARGIN;
    const RX = (x0 + x1) / 2, RZ = (z0 + z1) / 2;

    // Carpet: a busy tile, laid edge to edge over the whole floor.
    const TILE = 36;
    for (let x = x0; x < x1; x += TILE) {
      for (let z = z0; z < z1; z += TILE) {
        art('carpet', 1, [x + TILE / 2, G + 0.03, z + TILE / 2], [1, 0, 0], [0, 0, -1],
            TILE / 2, TILE / 2, [0, 1, 0]);
      }
    }

    // Walls: dark panelled wainscot with a gold rail, damask above, a gold
    // crown, marble pilasters with gold capitals, and sconces between them.
    const WAIN = 14;
    const wall = (ax, az, bx, bz, nx, nz) => {
      const L = Math.hypot(bx - ax, bz - az), dx = (bx - ax) / L, dz = (bz - az) / L;
      const f = [nx, 0, nz], l = [dx, 0, dz];
      const P = (s, y, o) => [ax + dx * s + nx * o, y, az + dz * s + nz * o];
      quad2(solid, P(0, G, 0), P(L, G, 0), P(L, CEIL, 0), P(0, CEIL, 0), 0x3a0c14);
      quad2(solid, P(0, G, 0.6), P(L, G, 0.6), P(L, WAIN, 0.6), P(0, WAIN, 0.6), WOOD_D);
      for (let s = 0; s < L; s += 12) {
        quad2(solid, P(s + 1.5, 2, 0.75), P(Math.min(L, s + 10.5), 2, 0.75),
              P(Math.min(L, s + 10.5), WAIN - 2, 0.75), P(s + 1.5, WAIN - 2, 0.75), WOOD);
      }
      quad2(bright, P(0, WAIN, 0.9), P(L, WAIN, 0.9), P(L, WAIN + 1.2, 0.9), P(0, WAIN + 1.2, 0.9), GOLD);
      quad2(bright, P(0, CEIL - 6, 0.9), P(L, CEIL - 6, 0.9), P(L, CEIL - 3, 0.9), P(0, CEIL - 3, 0.9), GOLD);
      const PAN = 38;
      for (let s = 0; s + PAN <= L; s += PAN) {
        for (let y = WAIN + 1.2; y + PAN <= CEIL - 6; y += PAN) {
          art('wall', 1, P(s + PAN / 2, y + PAN / 2, 0.4), l, [0, 1, 0], PAN / 2, PAN / 2, f);
        }
      }
      for (let s = 30; s < L - 10; s += 76) {
        obox(solid, P(s, (G + CEIL) / 2, 2.2), f, l, 3.2, (CEIL - G) / 2, 2.2, 0xcfc2aa);
        obox(bright, P(s, CEIL - 9, 2.6), f, l, 4, 2, 2.6, GOLD_L);
        obox(bright, P(s, WAIN + 1, 2.6), f, l, 3.8, 1, 2.6, GOLD);
        for (const o of [-19, 19]) {
          obox(solid, P(s + o, 48, 1.2), f, l, 0.8, 2.2, 1.2, GOLD);
          const q = P(s + o, 0, 2.4);
          cyl(bright, q[0], 50.4, q[2], 1.3, 3.2, 0xfff0cc, 0xfff6e0, 8, 0.8);
        }
      }
      return { P, L, f, l };
    };
    const walls = [wall(x0, z0, x1, z0, 0, 1), wall(x1, z0, x1, z1, -1, 0),
                   wall(x1, z1, x0, z1, 0, -1), wall(x0, z1, x0, z0, 1, 0)];

    // The name on the wall the start line faces, the cashier on the opposite one.
    const startF = fwdAt(line, 0);
    let ahead = walls[0], best = -Infinity;
    for (const w of walls) {
      const s = -(w.f[0] * startF[0] + w.f[2] * startF[2]);
      if (s > best) { best = s; ahead = w; }
    }
    const behind = walls.find((w) => w.f[0] === -ahead.f[0] && w.f[2] === -ahead.f[2]);
    {
      const { P, L, f, l } = ahead;
      art('sign-high-roller', 4, P(L / 2, 72, 3.2), l, [0, 1, 0], 64, 16, f);
      art('sign-jackpot', 4, P(L / 2 - 110, 72, 3.2), l, [0, 1, 0], 32, 8, f);
      art('sign-jackpot', 4, P(L / 2 + 110, 72, 3.2), l, [0, 1, 0], 32, 8, f);
    }
    {
      // The cashier's cage: a counter, gold bars to the ceiling of the cage.
      const { P, L, f, l } = behind;
      const c = P(L / 2, 0, 8);
      obox(solid, [c[0], G + 8, c[2]], f, l, 50, 8, 8, WOOD);
      oboxCol([c[0], G + 8, c[2]], f, l, 50, 8, 8);
      obox(solid, [c[0] + f[0] * 0.2, G + 16.6, c[2] + f[2] * 0.2], f, l, 51, 0.6, 9, 0x2a1a10);
      for (let s = -48; s <= 48; s += 3) {
        obox(bright, [c[0] + l[0] * s + f[0] * 7, G + 26, c[2] + l[2] * s + f[2] * 7], f, l, 0.25, 9, 0.25, GOLD_L);
      }
      obox(bright, [c[0] + f[0] * 7, G + 35.5, c[2] + f[2] * 7], f, l, 50, 0.6, 0.4, GOLD_L);
      art('sign-cashier', 4, [c[0] + f[0] * 8.5, G + 42, c[2] + f[2] * 8.5], l, [0, 1, 0], 20, 5, f);
    }

    // Ceiling: dark, a gold coffer grid, can lights in the coffers.
    quad2(bright, [x0, CEIL, z0], [x1, CEIL, z0], [x1, CEIL, z1], [x0, CEIL, z1], 0x1c100e);
    const COF = 48;
    for (let x = x0 + COF; x < x1; x += COF) {
      obox(bright, [x, CEIL - 1.5, RZ], [0, 0, 1], [1, 0, 0], 1.2, 1.5, (z1 - z0) / 2, 0x6a4a1c);
    }
    for (let z = z0 + COF; z < z1; z += COF) {
      obox(bright, [RX, CEIL - 1.5, z], [0, 0, 1], [1, 0, 0], (x1 - x0) / 2, 1.5, 1.2, 0x6a4a1c);
    }
    for (let x = x0 + COF / 2; x < x1; x += COF) {
      for (let z = z0 + COF / 2; z < z1; z += COF) {
        ring(bright, x, CEIL - 0.4, z, 0, 1.4, 0xfff0d0, 8);
        ring(bright, x, CEIL - 0.35, z, 1.4, 2.0, 0x8a6a2a, 8);
      }
    }

    // A dome with a crystal chandelier: a lit cove set into the ceiling, gold
    // rings and tiers of hanging crystal.
    const chandelier = (x, z, size) => {
      const s = size || 1;
      ring(bright, x, CEIL - 0.6, z, 30 * s, 34 * s, 0x6a4a1c, 32);
      ring(bright, x, CEIL - 0.7, z, 26 * s, 30 * s, 0xffd890, 32);
      ring(bright, x, CEIL - 0.5, z, 0, 26 * s, 0x2a1a14, 32);
      cyl(solid, x, CEIL - 12 * s, z, 0.5, 12 * s, GOLD);
      const tiers = [[14, 16, 10], [11, 21, 9], [8, 25.5, 8], [4.5, 29, 6]];
      for (const [r, dy, drop] of tiers) {
        const R = r * s, Y = CEIL - dy * s;
        ring(bright, x, Y, z, R - 0.5 * s, R + 0.5 * s, GOLD_L, 24);
        const m = Math.max(10, Math.round(R * 2.4));
        for (let k = 0; k < m; k++) {
          const a = k / m * Math.PI * 2;
          const px = x + Math.cos(a) * R, pz = z + Math.sin(a) * R;
          const hh = drop * s * (0.55 + 0.45 * ((k % 3) / 2));
          bright.box(px, Y - hh / 2, pz, 0.32 * s, hh / 2, 0.32 * s, k % 2 ? 0xfff6e2 : 0xe2eeff);
          bright.box(px, Y - hh - 0.5 * s, pz, 0.55 * s, 0.55 * s, 0.55 * s, 0xfffaf0);
        }
        for (let k = 0; k < 6; k++) {
          const a = k / 6 * Math.PI * 2;
          quad2(solid, [x, Y + 2 * s, z], [x + Math.cos(a) * R, Y, z + Math.sin(a) * R],
                [x + Math.cos(a) * R, Y - 0.4 * s, z + Math.sin(a) * R], [x, Y + 1.6 * s, z], GOLD);
        }
      }
      bright.box(x, CEIL - 34 * s, z, 1.2 * s, 2 * s, 1.2 * s, 0xfffaf0);
    };

    // Hanging signs: double sided, on two gold chains.
    const hangSign = (name, x, z, f, w) => {
      const l = latOf(f), y = CEIL - 52, hh = w / 4;
      obox(solid, [x, y, z], f, l, w + 0.6, hh + 0.6, 0.5, 0x1a0a0e);
      art(name, 4, [x + f[0] * 0.55, y, z + f[2] * 0.55], l, [0, 1, 0], w, hh, f);
      art(name, 4, [x - f[0] * 0.55, y, z - f[2] * 0.55], l, [0, 1, 0], w, hh, [-f[0], 0, -f[2]]);
      for (const o of [-w * 0.8, w * 0.8]) {
        obox(solid, [x + l[0] * o, (y + hh + CEIL) / 2, z + l[2] * o], f, l, 0.2, (CEIL - y - hh) / 2, 0.2, GOLD);
      }
    };

    // Marble columns with gold bands, solid.
    const column = (x, z) => {
      cyl(solid, x, G, z, 5.5, CEIL - G, 0xd6cab4, null, 16);
      for (const y of [G, 12, CEIL - 14]) cyl(bright, x, y, z, 6.4, 3, GOLD, null, 16);
      cylCol(x, G, z, 5.5, CEIL - G, 10);
    };

    // --- slot machines ------------------------------------------------------------------
    // One cabinet: base with an LED kick strip, body with the screen in a
    // bezel, a button deck, glowing trim up both front edges, a topper with
    // the game's name and its progressive, a tower light, and a stool.
    let slotN = 0;
    const slotCab = (cx, cz, f, solidCab) => {
      const k = slotN++ % GLOWS.length, glow = GLOWS[k];
      const l = latOf(f);
      const at = (fo, lo, y) => [cx + f[0] * fo + l[0] * lo, y, cz + f[2] * fo + l[2] * lo];
      obox(solid, at(0, 0, G + 2.5), f, l, 3.2, 2.5, 2.6, 0x16121a);
      obox(bright, at(2.62, 0, G + 0.6), f, l, 3.0, 0.25, 0.02, glow);
      obox(solid, at(-0.3, 0, G + 10), f, l, 3.0, 5, 2.3, 0x221a26);
      obox(solid, at(1.3, 0, G + 5.4), f, l, 3.0, 0.4, 1.6, 0x2a2430);
      for (let b2 = -2; b2 <= 2; b2++) {
        obox(bright, at(1.6, b2 * 1.1, G + 5.9), f, l, 0.4, 0.12, 0.35, [0xff3030, 0xffd040, 0x40ff60, 0x40a0ff, 0xffffff][b2 + 2]);
      }
      obox(solid, at(1.98, 0, G + 10.2), f, l, 2.85, 3.9, 0.04, 0x101014);
      art('slot-' + k, 0.75, at(2.1, 0, G + 10.2), l, [0, 1, 0], 2.6, 3.47, f);
      for (const s of [-1, 1]) obox(bright, at(2.0, s * 3.05, G + 10), f, l, 0.14, 5.2, 0.14, glow);
      obox(solid, at(0.6, 0, G + 16.6), f, l, 3.1, 1.6, 1.2, 0x16121a);
      art('topper-' + k, 3, at(1.85, 0, G + 16.6), l, [0, 1, 0], 3.0, 1.0, f);
      const tw = at(-0.8, 0, 0);
      cyl(bright, tw[0], G + 18.2, tw[2], 0.5, 1.2, 0xff2a2a, null, 8);
      cyl(bright, tw[0], G + 19.4, tw[2], 0.5, 1.0, 0xfff4e0, 0xfff4e0, 8);
      // The stool: chrome column, red seat, a back.
      const st = at(5.6, 0, 0);
      cyl(solid, st[0], G, st[2], 1.5, 0.5, 0x9a9aa2, null, 10);
      cyl(solid, st[0], G + 0.5, st[2], 0.35, 3.4, 0xb4b4bc, null, 8);
      cyl(solid, st[0], G + 3.9, st[2], 1.6, 0.8, 0x8a1020, 0xa01828, 12);
      obox(solid, at(6.9, 0, G + 6.2), f, l, 1.4, 1.6, 0.3, 0x8a1020);
      if (solidCab) oboxCol(at(0, 0, G + 9), f, l, 3.2, 10, 2.7);
    };
    // A bank: two rows back to back, and lit end caps.
    const slotBank = (cx, cz, f, count) => {
      const l = latOf(f), W = 6.5;
      for (let i = 0; i < count; i++) {
        const o = (i - (count - 1) / 2) * W;
        slotCab(cx + l[0] * o + f[0] * 2.8, cz + l[2] * o + f[2] * 2.8, f, true);
        slotCab(cx + l[0] * o - f[0] * 2.8, cz + l[2] * o - f[2] * 2.8, [-f[0], 0, -f[2]], true);
      }
      const half = count * W / 2;
      for (const s of [-1, 1]) {
        const c = [cx + l[0] * (half + 1) * s, G + 9, cz + l[2] * (half + 1) * s];
        obox(solid, c, f, l, 1, 9, 5.6, 0x221a26);
        obox(bright, [c[0] + l[0] * s * 1.05, G + 9, c[2] + l[2] * s * 1.05], f, l, 0.05, 8, 4.8, GLOWS[(slotN + 1) % 6]);
      }
    };

    // Slot rows lining the slot-floor road (the weave and the home straight):
    // a single row each side facing the road, set back so they frame it.
    {
      const firstChip = S.chips.length ? S.chips[0] - 8 : 20;
      const last = {};
      for (let i = 0; i < n; i++) {
        const e = line[i];
        if (!(e.p[1] < 0.2 && !e.bp && (i < firstChip || i > n - 22))) continue;
        const f = fwdAt(line, i), l = latOf(f);
        for (const side of [-1, 1]) {
          const o = e.hw + 11;
          const cx = e.p[0] + l[0] * o * side, cz = e.p[2] + l[2] * o * side;
          if (last[side] && Math.hypot(cx - last[side][0], cz - last[side][1]) < 6.8) continue;
          if (roadDist(cx, cz, -2, 24) < 7) continue;
          slotCab(cx, cz, [-l[0] * side, 0, -l[2] * side], true);
          last[side] = [cx, cz];
        }
      }
    }

    // --- chip stacks round the slalom --------------------------------------------------
    for (const r of runs(S.chips)) {
      const i = r[r.length >> 1], e = line[i];
      const side = e.curv > 0 ? 1 : -1;
      const f = fwdAt(line, i), l = latOf(f);
      const o = e.hw + 8;
      const cx = e.p[0] + l[0] * o * side, cz = e.p[2] + l[2] * o * side;
      chipStack(cx, cz, 5.5, 14 + (i % 3) * 6, i % CHIPS.length, true);
      const nx = cx + l[0] * side * 9 + f[0] * 4, nz = cz + l[2] * side * 9 + f[2] * 4;
      if (roadDist(nx, nz, -2, 6) > 6) chipStack(nx, nz, 5.5, 5 + (i % 4), (i + 2) % CHIPS.length, true);
    }

    // --- the card ramps ----------------------------------------------------------------
    // The ramp is a playing card, and the card is wider than the road - so its
    // face is road too, collided exactly through the station edges. Drawn as
    // strips that follow the eased climb, the art cut to match.
    const cards = [];
    const cardRamp = (idx, name, strips) => {
      if (idx.length < 4) return;
      const i0 = Math.max(0, idx[0] - 1), i1 = idx[idx.length - 1];
      const dist = [0];
      for (let i = i0 + 1; i <= i1; i++) dist.push(dist[dist.length - 1] + len(sub(line[i].p, line[i - 1].p)));
      const L = dist[dist.length - 1];
      const W2 = L * 0.714 / 2;
      const at = (s) => {
        let j = 1;
        while (j < dist.length - 1 && dist[j] < s) j++;
        const a = line[i0 + j - 1], b = line[i0 + j];
        const t = Math.max(0, Math.min(1, (s - dist[j - 1]) / ((dist[j] - dist[j - 1]) || 1)));
        return { p: [a.p[0] + (b.p[0] - a.p[0]) * t, a.p[1] + (b.p[1] - a.p[1]) * t, a.p[2] + (b.p[2] - a.p[2]) * t],
                 lat: norm([a.lat[0], 0, a.lat[2]]) };
      };
      for (let k = 0; k < strips; k++) {
        const A = at(L * k / strips), B = at(L * (k + 1) / strips), M = at(L * (k + 0.5) / strips);
        const u = norm(sub(B.p, A.p));
        const nn = norm(cross(M.lat, u));
        const up = nn[1] < 0 ? [-nn[0], -nn[1], -nn[2]] : nn;
        const c = add([(A.p[0] + B.p[0]) / 2, (A.p[1] + B.p[1]) / 2, (A.p[2] + B.p[2]) / 2], up, 0.1);
        art(name + '-' + String(k).padStart(2, '0'), 512 / (716 / strips), c, M.lat, u,
            W2, len(sub(B.p, A.p)) / 2 + 0.02, up);
      }
      for (let i = i0; i < i1; i++) {
        const a = line[i], b = line[i + 1];
        for (const s of [-1, 1]) {
          const P = (e, o) => [e.p[0] + e.lat[0] * o * s, e.p[1] + e.lat[1] * o * s, e.p[2] + e.lat[2] * o * s];
          floorQuad(P(a, a.hw), P(b, b.hw), P(b, W2), P(a, W2), KIND.ROAD);
        }
      }
      // Its edges: a white rim the card's thickness, all the way round.
      for (let k = 0; k < 24; k++) {
        const A = at(L * k / 24), B = at(L * (k + 1) / 24);
        for (const s of [-1, 1]) {
          const a2 = add(A.p, A.lat, W2 * s), b2 = add(B.p, B.lat, W2 * s);
          quad2(solid, a2, b2, add(b2, [0, -1, 0], 0.45), add(a2, [0, -1, 0], 0.45), 0xe0dacc);
        }
      }
      const A = at(0), Z = at(L);
      for (const end of [A, Z]) {
        const a2 = add(end.p, end.lat, -W2), b2 = add(end.p, end.lat, W2);
        quad2(solid, a2, b2, add(b2, [0, -1, 0], 0.45), add(a2, [0, -1, 0], 0.45), 0xe0dacc);
      }
      claim(A.p[0] - W2, A.p[2] - W2, Z.p[0] + W2, Z.p[2] + W2);
      cards.push({ at: at, L: L, W2: W2 });
    };
    cardRamp(S.card1, 'ace', 12);
    cardRamp(S.card2, 'queen', 10);

    // A table rail along a polyline of (x, z): padded leather bumper, a wood
    // cap with a chip groove, gold trim, the apron below - cut in 4-unit
    // pieces so the road crossing the edge opens exactly its own gap. Solid.
    const railAlong = (pts, fy, inward) => {
      let piece = 0;
      for (let k = 0; k + 1 < pts.length; k++) {
        const P0 = pts[k], P1 = pts[k + 1];
        const m = Math.max(1, Math.ceil(Math.hypot(P1[0] - P0[0], P1[1] - P0[1]) / 4));
        for (let j = 0; j < m; j++, piece++) {
          const A = [P0[0] + (P1[0] - P0[0]) * j / m, P0[1] + (P1[1] - P0[1]) * j / m];
          const B = [P0[0] + (P1[0] - P0[0]) * (j + 1) / m, P0[1] + (P1[1] - P0[1]) * (j + 1) / m];
          const mx = (A[0] + B[0]) / 2, mz = (A[1] + B[1]) / 2;
          if (roadDist(mx, mz, fy - 6, fy + 6) < 0.5) continue;
          const inn = inward(mx, mz);
          const P = (p, o, y) => [p[0] + inn[0] * o, y, p[1] + inn[2] * o];
          quad2(solid, P(A, 0, fy), P(B, 0, fy), P(B, 0, fy + 2.2), P(A, 0, fy + 2.2), LEATHER);
          quad2(solid, P(A, 0, fy + 2.2), P(B, 0, fy + 2.2), P(B, -1.6, fy + 3.1), P(A, -1.6, fy + 3.1), 0x3a1c12);
          quad2(solid, P(A, -1.6, fy + 3.1), P(B, -1.6, fy + 3.1), P(B, -5.2, fy + 3.1), P(A, -5.2, fy + 3.1), WOOD);
          quad2(solid, P(A, -2.6, fy + 3.15), P(B, -2.6, fy + 3.15), P(B, -4.0, fy + 3.15), P(A, -4.0, fy + 3.15), 0x1a0c06);
          quad2(bright, P(A, -5.2, fy + 3.1), P(B, -5.2, fy + 3.1), P(B, -5.2, fy + 2.5), P(A, -5.2, fy + 2.5), GOLD);
          quad2(solid, P(A, -5.2, fy + 2.5), P(B, -5.2, fy + 2.5), P(B, -5.2, fy - 4.5), P(A, -5.2, fy - 4.5), WOOD_D);
          col.addQuad(P(A, 0, fy), P(B, 0, fy), P(B, 0, fy + 3.1), P(A, 0, fy + 3.1), KIND.WALL);
          if (piece % 3 === 1) {
            const g = P([mx, mz], -3.3, fy + 3.2);
            cyl(solid, g[0], g[1], g[2], 0.6, 0.35, CHIPS[piece % 5][0], CHIPS[piece % 5][1], 8);
          }
        }
      }
    };
    // A pedestal under a table top, unless it would stand on a road.
    const pedestal = (x, z, top, w, d) => {
      if (roadDist(x, z, G - 1, top) < Math.max(w, d) + 2) return;
      obox(solid, [x, (G + top) / 2, z], [0, 0, 1], [1, 0, 0], w, (top - G) / 2, d, WOOD_D);
      obox(bright, [x, top - 1.5, z], [0, 0, 1], [1, 0, 0], w + 0.3, 0.4, d + 0.3, GOLD);
      obox(solid, [x, G + 1.2, z], [0, 0, 1], [1, 0, 0], w + 1.5, 1.2, d + 1.5, 0x1a0c06);
      oboxCol([x, (G + top) / 2, z], [0, 0, 1], [1, 0, 0], w + 1.5, (top - G) / 2, d + 1.5);
    };

    // --- the craps table -------------------------------------------------------------------
    if (S.craps.length) {
      const R = crapsRect(line, S);
      const fy = R.y;
      const midX = (R.x0 + R.x1) / 2, midZ = (R.z0 + R.z1) / 2;
      const hx = (R.x1 - R.x0) / 2, hz = (R.z1 - R.z0) / 2;
      // The felt, printed: two mirrored halves along the long axis.
      const long = hx >= hz;
      const halfA = long ? [R.x0 + hx / 2, midZ] : [midX, R.z0 + hz / 2];
      const halfB = long ? [R.x1 - hx / 2, midZ] : [midX, R.z1 - hz / 2];
      const rr = long ? [1, 0, 0] : [0, 0, 1];
      const uu = long ? [0, 0, -1] : [1, 0, 0];
      const hw2 = long ? hx / 2 : hz / 2, hh2 = long ? hz : hx;
      art('craps-l', 512 / 416, [halfA[0], fy + 0.03, halfA[1]], rr, uu, hw2, hh2, [0, 1, 0]);
      art('craps-r', 512 / 416, [halfB[0], fy + 0.03, halfB[1]], rr, uu, hw2, hh2, [0, 1, 0]);
      quad2(bright, [R.x0, fy - 0.02, R.z0], [R.x1, fy - 0.02, R.z0], [R.x1, fy - 0.02, R.z1], [R.x0, fy - 0.02, R.z1], FELT);
      floorQuad([R.x0, fy, R.z0], [R.x1, fy, R.z0], [R.x1, fy, R.z1], [R.x0, fy, R.z1], KIND.ROAD);
      obox(solid, [midX, fy - 2.5, midZ], [0, 0, 1], [1, 0, 0], hx + 5.2, 2.4, hz + 5.2, WOOD_D);
      obox(solid, [midX, fy - 6, midZ], [0, 0, 1], [1, 0, 0], hx + 2, 1.2, hz + 2, LEATHER);
      const rect = [[R.x0, R.z0], [R.x1, R.z0], [R.x1, R.z1], [R.x0, R.z1], [R.x0, R.z0]];
      railAlong(rect, fy, (x, z) => {
        const dx = midX - x, dz = midZ - z;
        return Math.abs(dx) / hx > Math.abs(dz) / hz ? [Math.sign(dx), 0, 0] : [0, 0, Math.sign(dz)];
      });
      for (const s of [-0.55, 0.55]) {
        pedestal(long ? midX + hx * s : midX, long ? midZ : midZ + hz * s, fy - 7.2,
                 long ? 6 : hx * 0.6, long ? hz * 0.6 : 6);
      }
      // Players' chips on the felt by the far rail, clear of the road - solid.
      for (let k = 0; k < 9; k++) {
        const t = (k + 0.6) / 9.2;
        for (const edge of long ? [R.z0 + 6, R.z1 - 6] : [R.x0 + 6, R.x1 - 6]) {
          const cx = long ? R.x0 + (R.x1 - R.x0) * t : edge;
          const cz = long ? edge : R.z0 + (R.z1 - R.z0) * t;
          if (roadDist(cx, cz, fy - 3, fy + 3) < 5) continue;
          chipStack(cx, cz, 1.6, 2 + (k * 5) % 4, (k * 3) % 5, true, fy);
        }
      }
      tops.push((x, z) => x > R.x0 - 6 && x < R.x1 + 6 && z > R.z0 - 6 && z < R.z1 + 6);
      hangSign('sign-craps', midX, midZ, long ? [0, 0, 1] : [1, 0, 0], 22);
      chandelier(midX, midZ, 1.15);
      claim(R.x0 - 6, R.z0 - 6, R.x1 + 6, R.z1 + 6);
    }

    // --- roulette: the betting layout the jump lands on, and the wheel -----------------
    if (S.landing.length && S.spiral.length) {
      const i0 = S.landing[0], i1 = S.landing[S.landing.length - 1];
      const a = line[i0].p, b = line[i1].p, fy = a[1];
      const f = norm([b[0] - a[0], 0, b[2] - a[2]]), l = latOf(f);
      // From two units short of the landing to exactly the last station on the
      // felt: any further and the table stands over the spiral, which is
      // already dropping away under it - felt drawn over the road, and a felt
      // collider a car rides on and then falls off.
      const Lh = len(sub(b, a)) / 2 + 1, Wh = line[i0].hw + 1.5;
      const c = [(a[0] + b[0]) / 2 - f[0] * 1, fy, (a[2] + b[2]) / 2 - f[2] * 1];
      const P = (fo, lo, y) => [c[0] + f[0] * fo + l[0] * lo, y, c[2] + f[2] * fo + l[2] * lo];
      // The layout reads from the wheel's end: 0 nearest the wheel.
      art('roulette-layout', 2.5, [c[0], fy + 0.03, c[2]], [-f[0], 0, -f[2]], [l[0], 0, l[2]], Lh, Wh, [0, 1, 0]);
      quad2(bright, P(-Lh, Wh, fy - 0.02), P(Lh, Wh, fy - 0.02), P(Lh, -Wh, fy - 0.02), P(-Lh, -Wh, fy - 0.02), FELT);
      floorQuad(P(-Lh, -Wh, fy), P(Lh, -Wh, fy), P(Lh, Wh, fy), P(-Lh, Wh, fy), KIND.ROAD);
      obox(solid, [c[0], fy - 2.5, c[2]], f, l, Wh + 5.2, 2.4, Lh + 5.2, WOOD_D);
      // No rail across the end the jump lands over: a car that comes up short
      // should drop, not stall against a bumper in mid-air.
      const outline = [P(-Lh, -Wh, 0), P(Lh, -Wh, 0), P(Lh, Wh, 0), P(-Lh, Wh, 0)].map((q) => [q[0], q[2]]);
      railAlong(outline, fy, (x, z) => {
        const dx = c[0] - x, dz = c[2] - z;
        const fo = dx * f[0] + dz * f[2], lo = dx * l[0] + dz * l[2];
        return Math.abs(fo) / Lh > Math.abs(lo) / Wh ? [f[0] * Math.sign(fo), 0, f[2] * Math.sign(fo)]
                                                      : [l[0] * Math.sign(lo), 0, l[2] * Math.sign(lo)];
      });
      pedestal(c[0], c[2], fy - 4.9, 5, 5);
      tops.push((x, z) => {
        const dx = x - c[0], dz = z - c[2];
        return Math.abs(dx * f[0] + dz * f[2]) < Lh + 6 && Math.abs(dx * l[0] + dz * l[2]) < Wh + 6;
      });
      claim(c[0] - Lh - 6, c[2] - Lh - 6, c[0] + Lh + 6, c[2] + Lh + 6);

      // The wheel's bowl: mahogany, gold-trimmed rim, the ball track with its
      // gold deflectors. What turns (pockets, cone, turret, ball) is a mover.
      const [wx, wz, wr] = pivot(line, S.spiral);
      const WR = wr - line[S.spiral[0]].hw - 4;
      const top = G + 8.5;
      cyl(solid, wx, G, wz, WR, top - G, WOOD, null, 40);
      // The bowl's side, as a real wheel's: inlaid panels of lighter wood
      // between gold bands, so from the foot of the spiral it is furniture
      // rather than a brown wall.
      for (const y of [G + 0.6, top - 0.8]) cyl(bright, wx, y, wz, WR + 0.12, 0.7, GOLD, null, 40);
      for (let k = 0; k < 20; k++) {
        const u = (k + 0.12) / 20 * Math.PI * 2, v = (k + 0.88) / 20 * Math.PI * 2;
        const A = [wx + Math.cos(u) * (WR + 0.08), 0, wz + Math.sin(u) * (WR + 0.08)];
        const B = [wx + Math.cos(v) * (WR + 0.08), 0, wz + Math.sin(v) * (WR + 0.08)];
        quad2(solid, [A[0], G + 2, A[2]], [B[0], G + 2, B[2]], [B[0], top - 1.6, B[2]], [A[0], top - 1.6, A[2]], 0x8a4a22);
        const m2 = [(A[0] + B[0]) / 2, (A[2] + B[2]) / 2];
        bright.box(m2[0], (G + top) / 2 + 0.2, m2[1], 0.5, 0.5, 0.5, GOLD_L);
      }
      cyl(solid, wx, top, wz, WR, 1.2, 0x4a2010, null, 40, WR * 0.98);
      ring(bright, wx, top + 1.25, wz, WR * 0.94, WR, GOLD, 40);
      ring(solid, wx, top + 0.7, wz, WR * 0.78, WR * 0.94, 0x6a3418, 40);
      for (let k = 0; k < 8; k++) {
        const a2 = k / 8 * Math.PI * 2;
        const dx = wx + Math.cos(a2) * WR * 0.81, dz = wz + Math.sin(a2) * WR * 0.81;
        obox(bright, [dx, top + 1.0, dz], [Math.cos(a2), 0, Math.sin(a2)], [-Math.sin(a2), 0, Math.cos(a2)],
             0.5, 0.3, 1.2, GOLD_L);
      }
      hangSign('sign-roulette', wx, wz, [f[0], 0, f[2]], 22);
      chandelier(wx, wz, 1.25);
      claim(wx - WR, wz - WR, wx + WR, wz + WR);
    }

    // --- the blackjack table ---------------------------------------------------------------
    // Built off the road rather than off an ideal half-circle, because the
    // road round it is two quarter-turns with the gate's straight between: the
    // rim is the road's outer edge pushed out, the dealer's side is the straight
    // line the road comes on and goes off across, and the felt is a fan from the
    // middle of that line.
    if (S.bj.length > 4) {
      const bjI = S.bj;
      const first = line[bjI[0]], last = line[bjI[bjI.length - 1]];
      const turn = line[bjI.find((i) => line[i].curv) || bjI[0]].curv || 1;
      const out = turn > 0 ? -1 : 1;                 // lat is road-right; outside is away from the turn
      let hwB = Infinity, fy = 0;
      for (const i of bjI) { hwB = Math.min(hwB, line[i].hw); fy = Math.max(fy, line[i].p[1]); }
      const RIM = hwB + 7;
      const hl = (e) => norm([e.lat[0], 0, e.lat[2]]);
      const C = [(first.p[0] + last.p[0]) / 2, fy, (first.p[2] + last.p[2]) / 2];
      const midE = line[bjI[bjI.length >> 1]];
      const md = norm([midE.p[0] - C[0], 0, midE.p[2] - C[2]]);
      const reach = Math.hypot(midE.p[0] - C[0], midE.p[2] - C[2]);
      const rim = bjI.map((i) => add([line[i].p[0], fy, line[i].p[2]], hl(line[i]), RIM * out));
      // Felt (unlit, the art's own green), its collider, the slab under it.
      for (let k = 0; k + 1 < rim.length; k++) {
        const A = [rim[k][0], fy - 0.02, rim[k][2]], B = [rim[k + 1][0], fy - 0.02, rim[k + 1][2]];
        quad2(bright, [C[0], fy - 0.02, C[2]], A, B, [C[0], fy - 0.02, C[2]], FELT);
        floorTri([C[0], fy, C[2]], [A[0], fy, A[2]], [B[0], fy, B[2]], KIND.ROAD);
        const Ao = add(A, norm(sub(A, C)), 5.2), Bo = add(B, norm(sub(B, C)), 5.2);
        quad2(solid, [Ao[0], fy - 0.2, Ao[2]], [Bo[0], fy - 0.2, Bo[2]], [Bo[0], fy - 5, Bo[2]], [Ao[0], fy - 5, Ao[2]], WOOD_D);
        quad2(solid, [C[0], fy - 5, C[2]], [Ao[0], fy - 5, Ao[2]], [Bo[0], fy - 5, Bo[2]], [C[0], fy - 5, C[2]], WOOD_D);
      }
      railAlong(rim.map((q) => [q[0], q[2]]), fy, (x, z) => norm([C[0] - x, 0, C[2] - z]));
      bjExit = { rim: rim[rim.length - 1], last: bjI[bjI.length - 1], out: out };
      // The dealer's side: a low padded rail along the straight edge, between
      // where the road comes on and goes off.
      const df = [-md[0], 0, -md[2]], dl = latOf(df);
      // Stops short of the road at both ends, by the wider road: the first
      // station is the queen's top (7.5 each side) and the last is the exit
      // (10), and sizing it off the first left the rail's end half a unit into
      // the road on the way off the table.
      const dr = Math.hypot(first.p[0] - C[0], first.p[2] - C[2]) - Math.max(first.hw, last.hw, hwB) - 2.5;
      obox(solid, add([C[0], fy + 1.2, C[2]], df, 1.2), df, dl, dr, 1.2, 1.2, LEATHER);
      oboxCol([C[0] + df[0] * 1.2, fy + 1.2, C[2] + df[2] * 1.2], df, dl, dr, 1.2, 1.2);
      // Betting circles, one per seat along the road, the insurance line's
      // smaller ones on its inside edge, and the lettering, reading from the
      // players' side: tops of the letters toward the dealer.
      for (let s2 = 0; s2 < 7; s2++) {
        const e = line[bjI[Math.round((s2 + 0.5) / 7 * (bjI.length - 1))]];
        ring(bright, e.p[0], fy + 0.03, e.p[2], 3.6, 4.2, 0xd8d2bc, 20);
        const q = add([e.p[0], fy + 0.03, e.p[2]], hl(e), -out * (hwB - 0.5));
        ring(bright, q[0], q[1], q[2], 1.6, 1.9, 0xd8d2bc, 14);
      }
      const word = (name, aspect, r, w) => {
        art(name, aspect, add([C[0], fy + 0.035, C[2]], md, r), [-md[2], 0, md[0]], [-md[0], 0, -md[2]],
            w, w / aspect, [0, 1, 0]);
      };
      const inner = reach - hwB;
      word('bj-pays', 8, inner - 4.5, 13);
      word('bj-insurance', 8, inner - 8.5, 10);
      word('bj-dealer', 512 / 48, inner - 12, 8);
      // Dealer's chip tray, the shoe, the discard rack, the limit placard.
      const ml = latOf(md);
      const T = add(C, md, 5.5);
      obox(solid, [T[0], fy + 0.6, T[2]], md, ml, 9, 0.6, 2.6, 0x1a0c06);
      oboxCol([T[0], fy + 1.5, T[2]], md, ml, 9, 1.5, 2.6);
      for (let k = 0; k < 8; k++) {
        const o = -7.8 + k * 2.2;
        for (let j = -1; j <= 1; j++) {
          const px = T[0] + ml[0] * o + md[0] * j * 1.4, pz = T[2] + ml[2] * o + md[2] * j * 1.4;
          cyl(solid, px, fy + 0.6, pz, 0.85, 1.4 + ((k + j + 3) % 3) * 0.4, CHIPS[k % 5][0], CHIPS[k % 5][1], 10);
        }
      }
      const shoe = add(add(C, md, 7), ml, 12);
      obox(solid, [shoe[0], fy + 1.6, shoe[2]], md, ml, 1.6, 1.6, 2.4, 0x6a1a20);
      obox(bright, [shoe[0] + md[0] * 2.45, fy + 1.6, shoe[2] + md[2] * 2.45], md, ml, 1.4, 1.2, 0.04, 0xd8d2c4);
      oboxCol([shoe[0], fy + 1.6, shoe[2]], md, ml, 1.6, 1.6, 2.4);
      const disc = add(add(C, md, 7), ml, -12);
      obox(solid, [disc[0], fy + 1.4, disc[2]], md, ml, 1.5, 1.4, 1.9, 0x1a1a1e);
      oboxCol([disc[0], fy + 1.4, disc[2]], md, ml, 1.5, 1.4, 1.9);
      const plq = add(add(C, md, 6), ml, 18);
      obox(solid, [plq[0], fy + 2.2, plq[2]], md, ml, 3.2, 1.5, 0.3, 0x1a1a1e);
      art('bj-limit', 8, [plq[0] + md[0] * 0.35, fy + 2.2, plq[2] + md[2] * 0.35], ml, [0, 1, 0], 3, 0.375, md);
      // Chairs round the outside, on the floor, their backs standing over the rail.
      for (let s2 = 0; s2 < 7; s2++) {
        const e = line[bjI[Math.round((s2 + 0.5) / 7 * (bjI.length - 1))]];
        const o = norm(sub([e.p[0], 0, e.p[2]], [C[0], 0, C[2]]));
        const p = add([e.p[0], 0, e.p[2]], hl(e), out * (RIM + 11));
        if (roadDist(p[0], p[2], G - 1, fy + 8) < 5) continue;
        const ll = latOf(o), seat = G + (fy - G) * 0.6;
        cyl(solid, p[0], G, p[2], 2.6, 0.6, 0x8a8a92, null, 10);
        cyl(solid, p[0], G + 0.6, p[2], 0.6, seat - G - 1.2, 0xb0b0b8, null, 8);
        obox(solid, [p[0], seat, p[2]], o, ll, 3.2, 0.7, 3.0, 0x7a1020);
        obox(solid, [p[0] + o[0] * 3, seat + 4.2, p[2] + o[2] * 3], o, ll, 3.0, 3.8, 0.6, 0x7a1020);
        obox(bright, [p[0] + o[0] * 3, seat + 8.1, p[2] + o[2] * 3], o, ll, 3.1, 0.25, 0.65, GOLD);
        oboxCol([p[0], (G + seat + 8) / 2, p[2]], o, ll, 3.2, (seat + 8 - G) / 2, 3.6);
      }
      for (const t of [0.2, 0.5, 0.8]) {
        const e = line[bjI[Math.round(t * (bjI.length - 1))]];
        pedestal((e.p[0] + C[0]) / 2, (e.p[2] + C[2]) / 2, fy - 5, 4, 4);
      }
      const poly = rim.map((q) => [q[0], q[2]]);
      tops.push((x, z) => {
        let inside = false;
        for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
          const [xi, zi] = poly[i], [xj, zj] = poly[j];
          if ((zi > z) !== (zj > z) && x < (xj - xi) * (z - zi) / (zj - zi) + xi) inside = !inside;
        }
        return inside;
      });
      hangSign('sign-blackjack', C[0], C[2], md, 20);
      chandelier(C[0], C[2], 1.0);
      let bx0 = Infinity, bx1 = -Infinity, bz0 = Infinity, bz1 = -Infinity;
      for (const q of rim) { bx0 = Math.min(bx0, q[0]); bx1 = Math.max(bx1, q[0]); bz0 = Math.min(bz0, q[2]); bz1 = Math.max(bz1, q[2]); }
      claim(bx0 - 14, bz0 - 14, bx1 + 14, bz1 + 14);
    }

    // --- chip-stack pillars under every raised road that is not on a table ------------
    {
      let last = -Infinity, run = 0;
      for (let i = 1; i < n; i++) {
        const e = line[i];
        run += len(sub(e.p, line[i - 1].p));
        if (e.skin || e.air || e.p[1] < 3.2) continue;
        if (run - last < 22) continue;
        if (onTable(e.p[0], e.p[2])) continue;
        last = run;
        const count = Math.max(1, Math.floor((e.p[1] - 0.9 - G) / CHIP_T));
        // Not collided: under a road that climbs, a solid flat top just below
        // the deck is a launcher for a car sagging on its springs (Sahara's
        // piers), and nothing needs them solid - they are under the road.
        chipStack(e.p[0], e.p[2], 3.4, count, (i >> 2) % CHIPS.length, false);
      }
    }

    // --- rails round the cards, wherever a card's edge meets nothing ------------------
    // A card is wider than the road and its whole face is drivable, but it is
    // wider than the table it leans on too: the ace hangs thirty units past the
    // craps table's end and the queen past the blackjack table's outer side.
    // Up the card off-centre, then, was a drive off its top edge into the air -
    // a gap in the track. The same low padded bumper with a brass cap the
    // raised road has, along both long edges once they are off the floor and
    // along any stretch of the top edge with no table beyond it. Inner face
    // and top collided, so it only ever pushes a car back onto the card.
    const edgeRail = (A, B, inward) => {
      const H = 0.8, T = 0.8;
      const P = (q, o, dy) => [q[0] + inward[0] * o, q[1] + dy, q[2] + inward[2] * o];
      const v = [P(A, 0, -0.5), P(A, T, -0.5), P(A, T, H), P(A, 0, H),
                 P(B, 0, -0.5), P(B, T, -0.5), P(B, T, H), P(B, 0, H)];
      quad2(solid, v[0], v[1], v[5], v[4], LEATHER);
      quad2(solid, v[1], v[5], v[6], v[2], LEATHER);
      quad2(solid, v[3], v[7], v[4], v[0], LEATHER);
      quad2(bright, v[2], v[6], v[7], v[3], GOLD);
      col.addQuad(v[1], v[5], v[6], v[2], KIND.WALL);
      col.addQuad(v[2], v[6], v[7], v[3], KIND.WALL);
    };
    for (const cd of cards) {
      const SEG = 32;
      for (let k = 0; k < SEG; k++) {
        const A = cd.at(cd.L * k / SEG), B = cd.at(cd.L * (k + 1) / SEG);
        if (B.p[1] < 1.0) continue;                      // still on the floor
        for (const s2 of [-1, 1]) {
          edgeRail(add(A.p, A.lat, cd.W2 * s2), add(B.p, B.lat, cd.W2 * s2), [-A.lat[0] * s2, 0, -A.lat[2] * s2]);
        }
      }
      // The top edge, in pieces, wherever there is no table just past it.
      const Z = cd.at(cd.L), Y = cd.at(cd.L - 2);
      const fwd = norm([Z.p[0] - Y.p[0], 0, Z.p[2] - Y.p[2]]);
      const PIECES = Math.ceil(cd.W2 * 2 / 4);
      for (let k = 0; k < PIECES; k++) {
        const o0 = -cd.W2 + 2 * cd.W2 * k / PIECES, o1 = -cd.W2 + 2 * cd.W2 * (k + 1) / PIECES;
        const a2 = add(Z.p, Z.lat, o0), b2 = add(Z.p, Z.lat, o1);
        const m = [(a2[0] + b2[0]) / 2 + fwd[0] * 2.5, 0, (a2[2] + b2[2]) / 2 + fwd[2] * 2.5];
        if (onTable(m[0], m[2]) || roadDist(m[0], m[2], Z.p[1] - 3, Z.p[1] + 3) < 0) continue;
        edgeRail(a2, b2, [-fwd[0], 0, -fwd[2]]);
      }
    }

    // The corner off the blackjack table. The table's rail ends at the rim,
    // seven units outside the road, and the exit road's own rail starts at its
    // kerb: between them was open table edge with a nine-unit drop, and a car
    // running wide off the felt went straight over it. Angled, from the rail's
    // end to the exit's edge two stations on, so it funnels rather than stops.
    if (bjExit) {
      const e2 = line[Math.min(n - 1, bjExit.last + 2)];
      const l2 = norm([e2.lat[0], 0, e2.lat[2]]);
      const A = bjExit.rim, B = add([e2.p[0], e2.p[1], e2.p[2]], l2, (e2.hw + 1.4) * bjExit.out);
      const d = norm([B[0] - A[0], 0, B[2] - A[2]]);
      // inward: toward the road side of the segment
      let inw = [-d[2], 0, d[0]];
      const mid = [(A[0] + B[0]) / 2, 0, (A[2] + B[2]) / 2];
      if ((e2.p[0] - mid[0]) * inw[0] + (e2.p[2] - mid[2]) * inw[2] < 0) inw = [-inw[0], 0, -inw[2]];
      edgeRail([A[0], A[1], A[2]], B, inw);
    }

    // --- the road where a felt or card hands back to tarmac -------------------------------
    // `trackmesh.js` draws a road segment only when the station it starts from
    // is drawn, so the one segment from the last `skin` station to the first
    // ordinary one had no surface at all: a hole three and a half units long
    // off the end of the craps table onto the kicker, off the betting layout
    // onto the spiral, and off the blackjack table onto the exit corner. Laid
    // here at the drawn road's width (the narrower of the two), in its colour,
    // with the slab's two sides under it. The collider was never missing - only
    // the picture - so this adds no collision.
    {
      const pal = ctx.pal;
      for (let i = 0; i + 1 < n; i++) {
        const a = line[i], b = line[i + 1];
        if (!a.skin || b.skin || b.air) continue;
        const w = Math.min(a.hw, b.hw);
        const E = (e, s2, dy) => [e.p[0] + e.lat[0] * w * s2 + e.n[0] * dy, e.p[1] + e.lat[1] * w * s2 + e.n[1] * dy,
                                  e.p[2] + e.lat[2] * w * s2 + e.n[2] * dy];
        quad2(solid, E(a, -1, 0.01), E(a, 1, 0.01), E(b, 1, 0.01), E(b, -1, 0.01), i % 8 < 4 ? pal.road : shade(pal.road, 0.045));
        for (const s2 of [-1, 1]) {
          quad2(solid, E(a, s2, 0.01), E(b, s2, 0.01), E(b, s2, -1.2), E(a, s2, -1.2), shade(pal.road, -0.3));
          // the kerb the engine starts on the next station, carried back over the patch
          const K = (e, o) => [e.p[0] + e.lat[0] * (w + o) * s2, e.p[1] + e.lat[1] * (w + o) * s2 + 0.02,
                               e.p[2] + e.lat[2] * (w + o) * s2];
          quad2(solid, K(a, -0.9), K(a, 0), K(b, 0), K(b, -0.9), pal.kerb);
        }
      }
    }

    // --- an edge rail on every raised road that is not on a table ----------------------
    // The spiral and the run off the blackjack table stand nine to eleven units
    // over the carpet with nothing at their edge, so running wide was a drop
    // and a respawn. A low padded bumper with a brass cap, as on the tables:
    // Playground's shape - inner face and top collided, below the eye line, so
    // it can only ever push a car sideways - and not a ribbon `rail`, which a
    // ground track must carry none of.
    {
      const BEAM_OUT = 1.4, BEAM_H = 0.8, BEAM_T = 0.8;   // inner face half a unit past the kerb
      const raised = (e) => e.p[1] > 1.5 && !e.skin && !e.air && !onTable(e.p[0], e.p[2]);
      for (let i = 1; i < n; i++) {
        const a = line[i - 1], b = line[i];
        if (!raised(a) || !raised(b)) continue;
        for (const side of [-1, 1]) {
          const P = (e, sl, su) => {
            const o = e.hw + BEAM_OUT - sl * BEAM_T;
            return [e.p[0] + e.lat[0] * side * o + e.n[0] * su, e.p[1] + e.lat[1] * side * o + e.n[1] * su,
                    e.p[2] + e.lat[2] * side * o + e.n[2] * su];
          };
          const v = [P(a, 0, -0.6), P(a, 1, -0.6), P(a, 1, BEAM_H), P(a, 0, BEAM_H),
                     P(b, 0, -0.6), P(b, 1, -0.6), P(b, 1, BEAM_H), P(b, 0, BEAM_H)];
          quad2(solid, v[0], v[1], v[5], v[4], LEATHER);
          quad2(solid, v[1], v[5], v[6], v[2], LEATHER);
          quad2(solid, v[3], v[7], v[4], v[0], LEATHER);
          quad2(bright, v[2], v[6], v[7], v[3], GOLD);
          col.addQuad(v[1], v[5], v[6], v[2], KIND.WALL);
          col.addQuad(v[2], v[6], v[7], v[3], KIND.WALL);
        }
      }
    }

    // --- the slot machine you drive through ---------------------------------------------------
    if (S.pad2.length) {
      const i0 = S.pad2[0];
      let i1 = i0, run = 0;
      while (i1 + 1 < n && run < 74) {
        run += Math.hypot(line[i1 + 1].p[0] - line[i1].p[0], line[i1 + 1].p[2] - line[i1].p[2]);
        i1++;
      }
      const a = line[i0].p, b = line[i1].p, hw = line[i0].hw;
      const f = fwdAt(line, (i0 + i1) >> 1), l = latOf(f);
      const mid = [(a[0] + b[0]) / 2, 0, (a[2] + b[2]) / 2];
      const half = Math.hypot(b[0] - a[0], b[2] - a[2]) / 2;
      const BODY = 0x6a0e1c, CHROME = 0xc8c0a0;
      const H = 22, T = 3.5;
      const at = (fo, lo, y) => [mid[0] + f[0] * fo + l[0] * lo, y, mid[2] + f[2] * fo + l[2] * lo];
      for (const side of [-1, 1]) {
        const o = hw + 2.5 + T;
        obox(solid, at(0, o * side, G + H / 2), f, l, T, H / 2, half, BODY);
        oboxCol(at(0, o * side, G + H / 2), f, l, T, H / 2, half);
        // Giant screens on the inside faces: you drive between two games.
        const inF = [-l[0] * side, 0, -l[2] * side];
        for (let k = 0; k < 3; k++) {
          const fo = (k - 1) * half * 0.62;
          obox(solid, at(fo, (o - T - 0.02) * side, G + 10.5), f, l, 0.02, 9.2, 7.2, 0x101014);
          art('slot-' + ((k + (side > 0 ? 3 : 0)) % 6), 0.75, at(fo, (o - T - 0.09) * side, G + 10.5),
              f, [0, 1, 0], 6.5, 8.67, inF);
        }
        for (let fo = -half + 2, q = 0; fo < half; fo += 4, q++) {
          obox(bright, at(fo, (o - T - 0.1) * side, G + 1.4), f, l, 0.06, 0.6, 1.2, q % 2 ? 0xffe070 : 0xff4a30);
          obox(bright, at(fo, (o - T - 0.1) * side, G + H - 1.4), f, l, 0.06, 0.6, 1.2, q % 2 ? 0xff4a30 : 0xffe070);
        }
        obox(bright, at(0, (o + T + 0.05) * side, G + H / 2), f, l, 0.05, H / 2 - 1, 0.3, GLOWS[side > 0 ? 0 : 1]);
      }
      const span = hw + 2.5 + T * 2;
      obox(solid, at(0, 0, G + H + 3), f, l, span, 3, half, BODY);
      obox(solid, at(0, 0, G + H + 7), f, l, span - 2, 1.2, half - 2, CHROME);
      obox(solid, at(0, 0, G + H + 12), f, l, span - 3, (span - 3) / 3, half - 2.4, 0x16121a);
      for (const end of [-1, 1]) {
        const nf = [f[0] * end, 0, f[2] * end];
        art('sign-jackpot', 4, at((half + 0.15) * end, 0, G + H + 3), l, [0, 1, 0], span - 1, (span - 1) / 4 * 0.85, nf);
        art('topper-' + (end > 0 ? 0 : 3), 3, at((half - 2.4 + 0.15) * end, 0, G + H + 12), l, [0, 1, 0],
            span - 3, (span - 3) / 3, nf);
      }
      const lv = at(0, span + 1.4, 0);
      obox(solid, [lv[0], G + H + 4, lv[2]], f, l, 0.6, 10, 0.6, CHROME);
      cyl(solid, lv[0], G + H + 13.5, lv[2], 2.4, 3.6, 0xd01828, 0xe02838, 12);
      hangSign('sign-slots', mid[0], mid[2], f, 18);
      claim(mid[0] - half - 4, mid[2] - half - 4, mid[0] + half + 4, mid[2] + half + 4);
    }

    // --- the rest of the floor: banks, tables, columns, chandeliers ---------------------------
    // Filled on a grid wherever there is room - off the road, off every table,
    // clear of the walls - so the lap runs through a working casino rather
    // than across an empty carpet.
    const cell = 70;
    let kind = 0;
    for (let x = x0 + cell; x < x1 - cell / 2; x += cell) {
      for (let z = z0 + cell; z < z1 - cell / 2; z += cell) {
        const jx = x + (rnd() - 0.5) * 12, jz = z + (rnd() - 0.5) * 12;
        if (isClaimed(jx, jz, 30)) continue;
        if (roadDist(jx, jz, -3, 40) < 34) continue;
        const f = rnd() < 0.5 ? [1, 0, 0] : [0, 0, 1];
        const pick = kind++ % 5;
        if (pick === 0 || pick === 2 || pick === 4) {
          slotBank(jx, jz, f, 5 + (kind % 3));
        } else if (pick === 1) {
          // A blackjack table at rest: half-moon, felt, rail, stools.
          const fy = G + 9, Rr = 16, l = latOf(f);
          const P = (a, r, y) => [jx + (f[0] * Math.cos(a) + l[0] * Math.sin(a)) * r, y,
                                  jz + (f[2] * Math.cos(a) + l[2] * Math.sin(a)) * r];
          for (let k = 0; k < 20; k++) {
            const u = Math.PI * k / 20, v = Math.PI * (k + 1) / 20;
            quad2(bright, P(u, 0, fy), P(u, Rr, fy), P(v, Rr, fy), P(v, 0, fy), FELT);
            quad2(solid, P(u, Rr, fy), P(v, Rr, fy), P(v, Rr + 2, fy + 1.2), P(u, Rr + 2, fy + 1.2), LEATHER);
            quad2(solid, P(u, Rr + 2, fy + 1.2), P(v, Rr + 2, fy + 1.2), P(v, Rr + 2, fy - 3), P(u, Rr + 2, fy - 3), WOOD_D);
            quad2(solid, P(u, 0, fy - 3), P(u, Rr + 2, fy - 3), P(v, Rr + 2, fy - 3), P(v, 0, fy - 3), WOOD_D);
            if (k % 3 === 1) {
              const s = P((u + v) / 2, Rr + 5, 0);
              cyl(solid, s[0], G, s[2], 0.4, 4, 0xb0b0b8, null, 6);
              cyl(solid, s[0], G + 4, s[2], 1.8, 0.8, 0x7a1020, 0x8a1828, 10);
            }
          }
          obox(solid, [jx, (G + fy) / 2, jz], f, l, 6, (fy - G) / 2, 3, WOOD_D);
          cylCol(jx, G, jz, Rr + 2, fy + 1.2 - G, 12);
        } else {
          // A roulette table at rest: a small still wheel and its layout.
          const fy = G + 9, l = latOf(f);
          art('roulette-layout', 2.5, [jx + f[0] * 6, fy + 0.03, jz + f[2] * 6], [f[0], 0, f[2]], [l[0], 0, l[2]], 15, 6, [0, 1, 0]);
          obox(solid, [jx + f[0] * 6, fy - 1.5, jz + f[2] * 6], f, l, 7.5, 1.5, 16.5, WOOD_D);
          obox(solid, [jx + f[0] * 6, (G + fy) / 2 - 1.5, jz + f[2] * 6], f, l, 3, (fy - G) / 2 - 1.5, 10, WOOD_D);
          const wx = jx - f[0] * 16, wz = jz - f[2] * 16;
          cyl(solid, wx, G, wz, 7, fy - G + 1.5, WOOD, null, 24);
          for (let k = 0; k < 37; k++) {
            const u = k / 37 * Math.PI * 2, v = (k + 1) / 37 * Math.PI * 2;
            const colr = k === 0 ? 0x1a7038 : (k % 2 ? 0xa01424 : 0x16161a);
            quad2(solid, [wx + Math.cos(u) * 3.4, fy + 1.6, wz + Math.sin(u) * 3.4], [wx + Math.cos(u) * 5.6, fy + 1.6, wz + Math.sin(u) * 5.6],
                  [wx + Math.cos(v) * 5.6, fy + 1.6, wz + Math.sin(v) * 5.6], [wx + Math.cos(v) * 3.4, fy + 1.6, wz + Math.sin(v) * 3.4], colr);
          }
          cyl(solid, wx, fy + 1.5, wz, 3.4, 1.4, 0x6a3418, GOLD, 16, 1.2);
          oboxCol([jx + f[0] * 6, (G + fy) / 2, jz + f[2] * 6], f, l, 7.5, (fy - G) / 2, 16.5);
          cylCol(wx, G, wz, 7, fy - G + 1.5, 10);
        }
        if (kind % 4 === 0 && !isClaimed(jx + 30, jz, 10) && roadDist(jx + 30, jz, -3, CEIL) > 14) column(jx + 30, jz);
      }
    }
    // Chandeliers over the floor too, away from the ones over tables.
    for (let x = x0 + 96; x < x1 - 48; x += 144) {
      for (let z = z0 + 96; z < z1 - 48; z += 144) {
        if (isClaimed(x, z, 30)) continue;
        chandelier(x, z, 0.8);
      }
    }
    // Over the start line, the biggest, and the name hanging under it.
    chandelier(line[0].p[0], line[0].p[2], 1.3);
    hangSign('sign-high-roller', line[0].p[0], line[0].p[2], fwdAt(line, 0), 26);
  }

  // Dice tumble across the craps table; the roulette ball rolls across the road
  // out of the bottom of the spiral; the wheel turns and its ball circles the
  // other way.
  function movers(ctx) {
    const { track, groundY } = ctx;
    const line = track.line, n = line.length;
    const G = groundY != null ? groundY : -1.2;
    const S = sections(line);
    const out = [];

    // Casino dice: translucent red with white pips. Opposite faces sum to 7.
    const H = 2.2;
    const PIPS = { 1: [[0, 0]], 2: [[-1, -1], [1, 1]], 3: [[-1, -1], [0, 0], [1, 1]],
                   4: [[-1, -1], [1, -1], [-1, 1], [1, 1]], 5: [[-1, -1], [1, -1], [0, 0], [-1, 1], [1, 1]],
                   6: [[-1, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [1, 1]] };
    const dieParts = () => {
      const W = 0xf2eee6, o = H * 0.5, p = H * 0.14, t = 0.04;
      const parts = [[0, 0, 0, H, H, H, 0xa00c1c], [0, 0, 0, H * 0.96, H * 1.01, H * 0.96, 0xb41424]];
      const faces = [[[0, 1, 0], 1], [[0, -1, 0], 6], [[0, 0, 1], 2], [[0, 0, -1], 5], [[1, 0, 0], 3], [[-1, 0, 0], 4]];
      for (const [nrm, k] of faces) {
        for (const [a, b] of PIPS[k]) {
          let x = 0, y = 0, z = 0, hx = p, hy = p, hz = p;
          if (nrm[1]) { y = nrm[1] * (H + t); x = a * o; z = b * o; hy = t; }
          else if (nrm[2]) { z = nrm[2] * (H + t); x = a * o; y = b * o; hz = t; }
          else { x = nrm[0] * (H + t); z = a * o; y = b * o; hx = t; }
          parts.push([x, y, z, hx, hy, hz, W]);
        }
      }
      return parts;
    };
    // Across the straight felt, a whole number of quarter-turns each way so a
    // die always lands flat at the end of its throw.
    const flat = S.craps.filter((i) => !line[i].curv);
    for (const part of runs(flat)) {
      if (part.length < 8) continue;
      // Clear of the last third, which is the jump's run-up: a die tumbling
      // into you there throws the jump, not just the line.
      const picks = [0.12, 0.33, 0.55];
      for (let q = 0; q < picks.length; q++) {
        const e = line[part[Math.floor(part.length * picks[q])]];
        const reach = 3 * H;
        out.push({
          ax: e.p[0] - e.lat[0] * reach, az: e.p[2] - e.lat[2] * reach,
          bx: e.p[0] + e.lat[0] * reach, bz: e.p[2] + e.lat[2] * reach,
          y: e.p[1] + H, hx: H, hy: H, hz: H,
          period: [250, 310, 280][q], phase: q * 131, glow: true, tumble: H,
          parts: dieParts(),
        });
      }
    }

    if (S.spiral.length) {
      // **The ball, rolling down the spiral now and then.** It jumps the rim
      // of the wheel, lands on the spiral, runs down it - drifting from the
      // inside edge to the outside as it goes - out along the run under the
      // jump and into the slot machine, where it is gone; then the wheel is
      // quiet until the next one. Same direction as the car and slower than it,
      // so it is something you catch and get round, and it is a sphere in the
      // collider, not a box.
      //
      // **It appears inside the wheel, never on the road.** It used to appear
      // at the end of the betting layout, right after the checkpoint - so a car
      // arriving that step had a ball materialise on top of it, and the shove
      // came before the ball was ever drawn: a collision with nothing there.
      if (S.spiral.length > 8 && S.pad2.length) {
        const [wx0, wz0, wr0] = pivot(line, S.spiral);
        const WR0 = wr0 - line[S.spiral[0]].hw - 4, rimY = G + 8.5 + 1.25;
        // Join the road where it has come down to the rim's height.
        let j = S.spiral[0];
        for (const i of S.spiral) if (Math.abs(line[i].p[1] - rimY) < Math.abs(line[j].p[1] - rimY)) j = i;
        const to = Math.min(n - 1, S.pad2[0] + 10);
        const ej = line[j], dir = norm([ej.p[0] - wx0, 0, ej.p[2] - wz0]);
        const lj = norm([ej.lat[0], 0, ej.lat[2]]);
        const path = [], lat = [], cum = [];
        let run = 0;
        const push = (p, l) => {
          if (path.length) run += Math.hypot(p[0] - path[path.length - 3], p[1] - path[path.length - 2], p[2] - path[path.length - 1]);
          path.push(p[0], p[1], p[2]); lat.push(l[0], 0, l[2]); cum.push(run);
        };
        // On the ball track, then over the rim, then down onto the road.
        push([wx0 + dir[0] * WR0 * 0.86, rimY - 0.6, wz0 + dir[2] * WR0 * 0.86], [0, 0, 0]);
        push([wx0 + dir[0] * (WR0 + 1), rimY + 0.4, wz0 + dir[2] * (WR0 + 1)], [0, 0, 0]);
        for (let i = j; i <= to; i++) push(line[i].p, norm([line[i].lat[0], 0, line[i].lat[2]]));
        void lj;
        const R = 2.6;
        out.push({
          ax: path[0], az: path[2], bx: path[0], bz: path[2], y: path[1] + R,
          hx: R, hy: R, hz: R, sphere: R, r: R,
          path: path, lat: lat, cum: cum, len: run,
          hw: line[S.spiral[0]].hw, off0: -0.55, off1: 0.5, v0: 0.3,
          period: 1500, active: 900, phase: 0,
          quads: sphereQuads(0, 0, 0, R, 0xfffcf4, 18, 12),
        });
      }

      // The wheel head: pockets, number strip, frets, the cone and the
      // turret. A ghost: it turns inside the spiral and nothing touches it.
      const [wx, wz, wr] = pivot(line, S.spiral);
      const WR = wr - line[S.spiral[0]].hw - 4;
      const top = G + 8.5;
      const quads = [];
      const POCK = 37, r0 = WR * 0.5, r1 = WR * 0.74, y = 0.9;
      for (let k = 0; k < POCK; k++) {
        const u = k / POCK * Math.PI * 2, v = (k + 1) / POCK * Math.PI * 2;
        const colr = k === 0 ? 0x1a7038 : (k % 2 ? 0xa01424 : 0x16161a);
        quads.push([[Math.cos(u) * r0, y, Math.sin(u) * r0], [Math.cos(u) * r1, y, Math.sin(u) * r1],
                    [Math.cos(v) * r1, y, Math.sin(v) * r1], [Math.cos(v) * r0, y, Math.sin(v) * r0], colr]);
        quads.push([[Math.cos(u) * r1, y + 0.4, Math.sin(u) * r1], [Math.cos(u) * WR * 0.78, y + 0.4, Math.sin(u) * WR * 0.78],
                    [Math.cos(v) * WR * 0.78, y + 0.4, Math.sin(v) * WR * 0.78], [Math.cos(v) * r1, y + 0.4, Math.sin(v) * r1],
                    k === 0 ? 0x146030 : (k % 2 ? 0x7a0e1a : 0x0c0c0e)]);
        const fu = u - 0.008, fv = u + 0.008;
        quads.push([[Math.cos(fu) * r0, y + 0.6, Math.sin(fu) * r0], [Math.cos(fu) * r1, y + 0.6, Math.sin(fu) * r1],
                    [Math.cos(fv) * r1, y + 0.6, Math.sin(fv) * r1], [Math.cos(fv) * r0, y + 0.6, Math.sin(fv) * r0], 0xe0b850]);
      }
      const cone = [[r0, y + 0.3], [r0 * 0.75, y + 1.6], [r0 * 0.45, y + 2.6], [r0 * 0.18, y + 3.2]];
      for (let j = 0; j + 1 < cone.length; j++) {
        const [ra, ya] = cone[j], [rb, yb] = cone[j + 1];
        for (let k = 0; k < 24; k++) {
          const u = k / 24 * Math.PI * 2, v = (k + 1) / 24 * Math.PI * 2;
          quads.push([[Math.cos(u) * ra, ya, Math.sin(u) * ra], [Math.cos(v) * ra, ya, Math.sin(v) * ra],
                      [Math.cos(v) * rb, yb, Math.sin(v) * rb], [Math.cos(u) * rb, yb, Math.sin(u) * rb],
                      j % 2 ? 0x7a3a1a : 0x5a2810]);
        }
      }
      const T = WR * 0.3;
      out.push({
        ax: wx, az: wz, bx: wx, bz: wz, y: top, hx: 0.1, hy: 0.1, hz: 0.1,
        period: 2, ghost: true, spin: 0.012, glow: true, quads: quads,
        parts: [[0, y + 4.4, 0, 0.9, 1.6, 0.9, 0xd8b048],
                [0, y + 5.6, 0, T, 0.35, 0.35, 0xd8b048], [0, y + 5.6, 0, 0.35, 0.35, T, 0xd8b048],
                [T, y + 5.6, 0, 0.7, 0.7, 0.7, 0xf0d070], [-T, y + 5.6, 0, 0.7, 0.7, 0.7, 0xf0d070],
                [0, y + 5.6, T, 0.7, 0.7, 0.7, 0xf0d070], [0, y + 5.6, -T, 0.7, 0.7, 0.7, 0xf0d070]],
      });
      // The ball, riding the track the other way round.
      const BR = 1.1, BX = WR * 0.88;
      out.push({
        ax: wx, az: wz, bx: wx, bz: wz, y: top, hx: 0.1, hy: 0.1, hz: 0.1,
        period: 2, ghost: true, spin: -0.03,
        quads: sphereQuads(BX, 1.6, 0, BR, 0xfffcf4, 12, 8),
      });
    }
    // The `glow` movers are unlit, so their colours are authored as they
    // should read and converted once, here, to the linear values that render so.
    for (const m of out) {
      if (!m.glow) continue;
      for (const p of (m.parts || [])) p[6] = lin(p[6]);
      for (const q of (m.quads || [])) q[4] = lin(q[4]);
    }
    return out;
  }
})();
