(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.harbor = { props: props };

  const WATER_DECK = 6.0;
  const WOOD = 0x8a6244;
  const WOOD_DARK = 0x4a3a2c;
  const PLANK = 0xa07450;
  const BONE = 0x262722;
  const ROCK = 0x2a3333;
  const GHOST = 0x041a10;
  const GHOST_HOT = 0x3cff9a;

  const off = (e, side, d, up) => [
    e.p[0] + e.lat[0] * side * d + e.n[0] * (up || 0),
    e.p[1] + e.lat[1] * side * d + e.n[1] * (up || 0),
    e.p[2] + e.lat[2] * side * d + e.n[2] * (up || 0)];

  function runs(line, test) {
    const out = [];
    let a = -1;
    for (let i = 0; i < line.length; i++) {
      if (test(line[i], i)) { if (a < 0) a = i; }
      else if (a >= 0) { out.push([a, i - 1]); a = -1; }
    }
    if (a >= 0) out.push([a, line.length - 1]);
    return out;
  }

  function circumcenter(a, b, c) {
    const ax = a[0], az = a[2], bx = b[0], bz = b[2], cx = c[0], cz = c[2];
    const d = 2 * (ax * (bz - cz) + bx * (cz - az) + cx * (az - bz));
    const a2 = ax * ax + az * az, b2 = bx * bx + bz * bz, c2 = cx * cx + cz * cz;
    return [(a2 * (bz - cz) + b2 * (cz - az) + c2 * (az - bz)) / d, 0,
            (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d];
  }

  function props(ctx) {
    const { solid, bright, track, minY, shade } = ctx;
    const line = track.line, n = line.length;
    const water = minY - WATER_DECK;
    const rnd = ctx.mulberry(3301);
    const quad2 = (buf, a, b, c, d, k) => { buf.quad(a, b, c, d, k); buf.quad(a, d, c, b, k); };
    const at = (p, y) => [p[0], y, p[2]];
    const floor = (a, b, c, d) => {
      const ny = (b[2] - a[2]) * (d[0] - a[0]) - (b[0] - a[0]) * (d[2] - a[2]);
      if (ny > 0) ctx.col.addQuad(a, b, c, d, ctx.KIND.OFFROAD);
      else ctx.col.addQuad(a, d, c, b, ctx.KIND.OFFROAD);
    };
    const post = (x, y, z, hx, hy, hz, k) => {
      solid.box(x, y, z, hx, hy, hz, k);
      const P = (sx, sz, yy) => [x + sx * hx, yy, z + sz * hz];
      const y0 = y - hy, y1 = y + hy;
      for (const [a, b] of [[[-1, -1], [1, -1]], [[1, -1], [1, 1]], [[1, 1], [-1, 1]], [[-1, 1], [-1, -1]]]) {
        ctx.col.addQuad(P(a[0], a[1], y0), P(b[0], b[1], y0), P(b[0], b[1], y1), P(a[0], a[1], y1), ctx.KIND.WALL);
      }
    };

    const nearRoad = (x, z, half, margin, below) => {
      for (let j = 0; j < n; j += 2) {
        const r = line[j];
        if (below != null && r.p[1] > below) continue;
        if (Math.hypot(r.p[0] - x, r.p[2] - z) - half < r.hw + margin) return true;
      }
      return false;
    };

    const firstAir = line.findIndex((e) => e.air);
    const deckRun = runs(line, (e, i) => e.hw > 9.9 && !e.wrad && i < firstAir)[0];
    const onDeck = (i) => deckRun && i >= deckRun[0] && i <= deckRun[1];

    for (let i = 0; i < n; i += 3) {
      const e = line[i];
      if (e.wrad || e.air || onDeck(i) || e.n[1] < 0.85) continue;
      if (e.p[1] - water < 1.5) continue;
      for (const s of [-1, 1]) {
        const q = off(e, s, e.hw - 0.7, 0);
        if (nearRoad(q[0], q[2], 0.5, 0.5, e.p[1] - 2)) continue;
        const h = q[1] - 0.3 - water;
        solid.box(q[0], water + h / 2, q[2], 0.5, h / 2, 0.5, WOOD_DARK);
      }
    }

    if (deckRun) {
      const [a, b] = deckRun;
      const R = 14, L = 1.5;
      for (let i = a + 1; i <= b; i++) {
        const p = line[i - 1], q = line[i];
        const pr = off(p, 1, p.hw + R, -0.04), qr = off(q, 1, q.hw + R, -0.04);
        const pe = off(p, 1, p.hw, -0.04), qe = off(q, 1, q.hw, -0.04);
        quad2(solid, pe, qe, qr, pr, i % 2 ? PLANK : shade(PLANK, -0.08));
        floor(off(p, 1, p.hw - 0.2, 0), off(q, 1, q.hw - 0.2, 0), qr, pr);
        const pl = off(p, -1, p.hw + L, -0.2), ql = off(q, -1, q.hw + L, -0.2);
        quad2(solid, pl, ql, at(ql, water), at(pl, water), WOOD);
        quad2(solid, pr, qr, at(qr, water), at(pr, water), WOOD);
        const rb = off(p, 1, p.hw + R, 1.2), rq = off(q, 1, q.hw + R, 1.2);
        quad2(solid, pr, qr, rq, rb, WOOD_DARK);
        ctx.col.addQuad(pr, qr, rq, rb, ctx.KIND.WALL);
        quad2(bright, at(pl, water + 1.6), at(ql, water + 1.6), at(ql, water + 2.1), at(pl, water + 2.1), GHOST);
        quad2(bright, at(pr, water + 1.6), at(qr, water + 1.6), at(qr, water + 2.1), at(pr, water + 2.1), GHOST);
      }
      const e = line[b], f = [e.p[0] - line[b - 1].p[0], 0, e.p[2] - line[b - 1].p[2]];
      const fl = Math.hypot(f[0], f[2]); f[0] /= fl; f[2] /= fl;
      const tip = [e.p[0] + f[0] * 22 + e.lat[0] * R / 2, e.p[1] - 0.4, e.p[2] + f[2] * 22 + e.lat[2] * R / 2];
      const bl = off(e, -1, e.hw + L, -0.2), br = off(e, 1, e.hw + R, -0.2);
      quad2(solid, bl, tip, at(tip, water), at(bl, water), WOOD);
      quad2(solid, br, tip, at(tip, water), at(br, water), WOOD);
      quad2(solid, bl, br, tip, tip, WOOD_DARK);

      const s0 = line[a];
      const sx = off(s0, 1, s0.hw + 4, 0), sy = off(line[Math.min(b, a + 8)], 1, s0.hw + R, 0);
      post((sx[0] + sy[0]) / 2, s0.p[1] + 4, (sx[2] + sy[2]) / 2,
                Math.abs(sx[0] - sy[0]) / 2 + 1, 4, Math.abs(sx[2] - sy[2]) / 2 + 1, WOOD);

      for (const u of [0.3, 0.55, 0.8]) {
        const m = line[Math.round(a + (b - a) * u)];
        const base = off(m, 1, m.hw + 8, 0);
        const H = 30 + u * 10;
        post(base[0], base[1] + H / 2, base[2], 0.7, H / 2, 0.7, WOOD_DARK);
        for (const [y0, y1] of [[0.32, 0.6], [0.66, 0.92]]) {
          const yb = base[1] + H * y0, yt = base[1] + H * y1;
          const s = 7;
          for (let k = 0; k < 6; k++) {
            const d0 = -s + (2 * s) * k / 6, d1 = -s + (2 * s) * (k + 1) / 6;
            const sag = (0.2 + rnd() * 0.5) * (yt - yb);
            const c0 = [base[0] + m.lat[0] * d0, 0, base[2] + m.lat[2] * d0];
            const c1 = [base[0] + m.lat[0] * d1, 0, base[2] + m.lat[2] * d1];
            quad2(bright, at(c0, yt - (yt - yb) + sag * 0.5), at(c1, yt - (yt - yb) + sag * 0.5),
                  at(c1, yt), at(c0, yt), k % 2 ? GHOST : shade(GHOST, -0.2));
          }
          const y = yt + 0.4;
          const ya = [base[0] - m.lat[0] * (s + 1), base[2] - m.lat[2] * (s + 1)];
          const yb2 = [base[0] + m.lat[0] * (s + 1), base[2] + m.lat[2] * (s + 1)];
          solid.box((ya[0] + yb2[0]) / 2, y, (ya[1] + yb2[1]) / 2,
                    Math.abs(ya[0] - yb2[0]) / 2 + 0.3, 0.3, Math.abs(ya[1] - yb2[1]) / 2 + 0.3, WOOD_DARK);
        }
        bright.box(base[0], base[1] + H + 0.8, base[2], 0.6, 0.6, 0.6, GHOST_HOT);
      }
    }

    const wall = runs(line, (e) => e.wrad)[0];
    if (wall) {
      const [a, b] = wall;
      const c = circumcenter(line[a].p, line[(a + b) >> 1].p, line[b].p);
      const r = line[(a + b) >> 1].wrad;
      for (let k = 0; k < 7; k++) {
        const r0 = 8 + k * 9, r1 = r0 + 9;
        for (let j = 0; j < 48; j++) {
          const t0 = j / 48 * Math.PI * 2 + k * 0.5, t1 = (j + 1) / 48 * Math.PI * 2 + k * 0.5 + 0.35;
          const y = water + 0.05 + k * 0.01;
          bright.quad([c[0] + Math.cos(t0) * r0, y, c[2] + Math.sin(t0) * r0],
                      [c[0] + Math.cos(t1) * r1, y, c[2] + Math.sin(t1) * r1],
                      [c[0] + Math.cos(t0 + 0.13) * r1, y, c[2] + Math.sin(t0 + 0.13) * r1],
                      [c[0] + Math.cos(t0 - 0.05) * r0, y, c[2] + Math.sin(t0 - 0.05) * r0],
                      (j + k) % 2 ? 0x03100f : 0x061c1a);
        }
      }
      const top = Math.max(line[a].p[1], line[b].p[1]);
      const S = Math.min(12, r * 0.3);
      solid.box(c[0], water + (top - water) / 2, c[2], S * 0.8, (top - water) / 2, S * 0.8, ROCK);
      const hy = top + S * 0.9;
      bright.box(c[0], hy, c[2], S, S, S, BONE);
      bright.box(c[0], hy - S * 1.3, c[2], S * 0.7, S * 0.35, S * 0.7, shade(BONE, -0.2));
      for (const [ux, uz] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        for (const s of [-1, 1]) {
          const ex = c[0] + ux * (S + 0.05) + uz * s * S * 0.45;
          const ez = c[2] + uz * (S + 0.05) + ux * s * S * 0.45;
          bright.box(ex, hy + S * 0.15, ez, ux ? 0.3 : S * 0.25, S * 0.22, uz ? 0.3 : S * 0.25, GHOST_HOT);
        }
        bright.box(c[0] + ux * (S + 0.05), hy - S * 0.45, c[2] + uz * (S + 0.05),
                   ux ? 0.3 : S * 0.1, S * 0.15, uz ? 0.3 : S * 0.1, 0x02100a);
      }
    }

    const pipe = runs(line, (e) => e.pf && !e.wrad);
    let side = 1;
    for (const [a, b] of pipe) {
      for (let i = a; i <= b; i += 26) {
        const e = line[i];
        const q = off(e, side, e.hw + 34, 0);
        side = -side;
        if (nearRoad(q[0], q[2], 14, 6)) continue;
        const ax = rnd() < 0.5;
        const hx = ax ? 13 : 5, hz = ax ? 5 : 13;
        solid.box(q[0], water + 2.5, q[2], hx, 3, hz, WOOD_DARK);
        solid.box(q[0] + (ax ? 6 : 0), water + 5.5, q[2] + (ax ? 0 : 6), ax ? 6 : 4, 2, ax ? 4 : 6, WOOD);
        const mh = 10 + rnd() * 14;
        solid.box(q[0], water + 5 + mh / 2, q[2], 0.6, mh / 2, 0.6, WOOD_DARK);
        bright.box(q[0], water + 5 + mh + 0.7, q[2], 0.5, 0.5, 0.5, GHOST_HOT);
      }
    }
  }
})();
