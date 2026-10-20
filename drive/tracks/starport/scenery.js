(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.starport = { props: props };

  // Display colour -> the linear value `bright` needs to land on it.
  const lin = (c) => {
    const f = (v) => Math.round(255 * Math.pow(v / 255, 2.2));
    return (f((c >> 16) & 255) << 16) | (f((c >> 8) & 255) << 8) | f(c & 255);
  };
  const mix = (a, b, t) => {
    const ch = (s) => Math.round(((a >> s) & 255) * (1 - t) + ((b >> s) & 255) * t);
    return (ch(16) << 16) | (ch(8) << 8) | ch(0);
  };
  const scale = (a, k) => mix(0, a, Math.max(0, Math.min(1, k)));
  const smooth = (e0, e1, x) => { const t = Math.max(0, Math.min(1, (x - e0) / (e1 - e0))); return t * t * (3 - 2 * t); };
  const add = (a, b, k) => [a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const norm = (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };

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

  function props(ctx) {
    const { solid, bright, col, track, pal, KIND, shade, minY, maxY, mulberry } = ctx;
    const line = track.line, n = line.length;
    const rnd = mulberry(310);
    const face = (a, b, c, d, k) => { solid.quad(a, b, c, d, k); solid.quad(a, d, c, b, k); };
    const glow = (a, b, c, d, k) => bright.quad(a, b, c, d, k);

    const HULL = pal.prop, TRIM = pal.prop2, LIGHT = lin(pal.deco);
    const HAZARD = pal.kerb, HAZARD2 = pal.kerb2;
    const WINDOW = lin(0xffe2a8), CYAN = lin(0x7fe6ff), RED = lin(0xff4a3a);

    // An oriented box: centre, three unit axes, three half extents.
    const obox = (c, X, Y, Z, hx, hy, hz, k, buf) => {
      const v = [];
      for (const sx of [-1, 1]) for (const sy of [-1, 1]) for (const sz of [-1, 1]) {
        v.push(add(add(add(c, X, sx * hx), Y, sy * hy), Z, sz * hz));
      }
      // v index = (sx>0)*4 + (sy>0)*2 + (sz>0)
      const q = buf === bright ? glow : face;
      q(v[0], v[1], v[3], v[2], k); q(v[4], v[6], v[7], v[5], k);
      q(v[0], v[4], v[5], v[1], k); q(v[2], v[3], v[7], v[6], k);
      q(v[0], v[2], v[6], v[4], k); q(v[1], v[5], v[7], v[3], k);
      return v;
    };
    // The four upright sides of an oriented box, in the collider.
    const collide = (v) => {
      col.addQuad(v[0], v[1], v[3], v[2], KIND.WALL);
      col.addQuad(v[4], v[6], v[7], v[5], KIND.WALL);
      col.addQuad(v[0], v[4], v[5], v[1], KIND.WALL);
      col.addQuad(v[2], v[3], v[7], v[6], KIND.WALL);
    };
    const UP = [0, 1, 0];
    // A cylinder along an arbitrary axis.
    const tube = (a, b, r, sides, k, buf) => {
      const ax = norm([b[0] - a[0], b[1] - a[1], b[2] - a[2]]);
      const u = norm(cross(ax, Math.abs(ax[1]) > 0.9 ? [1, 0, 0] : UP)), w = cross(ax, u);
      const q = buf === bright ? glow : face;
      for (let s = 0; s < sides; s++) {
        const t0 = s / sides * Math.PI * 2, t1 = (s + 1) / sides * Math.PI * 2;
        const o0 = add([0, 0, 0], u, Math.cos(t0) * r), o1 = add([0, 0, 0], u, Math.cos(t1) * r);
        const p0 = add(o0, w, Math.sin(t0) * r), p1 = add(o1, w, Math.sin(t1) * r);
        q(add(a, p0, 1), add(b, p0, 1), add(b, p1, 1), add(a, p1, 1), k);
      }
    };

    // Distance along the lap, and the station at a fraction of it.
    const s = new Float64Array(n);
    for (let i = 1; i < n; i++) s[i] = s[i - 1] + Math.hypot(line[i].p[0] - line[i - 1].p[0], line[i].p[2] - line[i - 1].p[2]);
    const atDist = (f) => {
      const want = f * s[n - 1];
      let lo = 0, hi = n - 1;
      while (lo < hi) { const m = (lo + hi) >> 1; if (s[m] < want) lo = m + 1; else hi = m; }
      return lo;
    };
    const fwd = (i) => {
      const a = line[Math.max(0, i - 1)].p, b = line[Math.min(n - 1, i + 1)].p;
      return norm([b[0] - a[0], 0, b[2] - a[2]]);
    };
    const level = (e) => (e.n[1] || 0) > 0.9 && !e.air && !e.pf;
    // Nearest road centre in plan, for keeping things off the track.
    const toRoad = (x, z) => {
      let best = 1e9;
      for (let i = 0; i < n; i += 2) best = Math.min(best, Math.hypot(line[i].p[0] - x, line[i].p[2] - z));
      return best;
    };

    let x0 = 1e9, x1 = -1e9, z0 = 1e9, z1 = -1e9;
    for (const e of line) {
      x0 = Math.min(x0, e.p[0]); x1 = Math.max(x1, e.p[0]);
      z0 = Math.min(z0, e.p[2]); z1 = Math.max(z1, e.p[2]);
    }
    const cx = (x0 + x1) / 2, cz = (z0 + z1) / 2, midY = (minY + maxY) / 2;
    // Which side of a station is the outside of the lap.
    const outside = (i) => {
      const e = line[i];
      const dx = e.p[0] - cx, dz = e.p[2] - cz;
      return (e.lat[0] * dx + e.lat[2] * dz) > 0 ? 1 : -1;
    };

    // ---- the planet --------------------------------------------------------
    const sky = pal.sky || {};
    const az = sky.sun ? sky.sun.az : 2.5;
    const sun = [Math.sin(az), Math.cos(az)];
    {
      const R = 2600, top = minY - 95, C = [cx, top - R, cz];
      const NR = 60, NS = 180, TH = 0.62;
      const waves = [];
      for (let k = 0; k < 7; k++) {
        waves.push([norm([rnd() - 0.5, rnd() - 0.5, rnd() - 0.5]), 3 + rnd() * 9, rnd() * 6.28, 1 / (1 + k * 0.5)]);
      }
      const OCEAN = 0x123f7a, SHALLOW = 0x2a78b4, LAND = 0x5d7c45, DRY = 0xa89466, CLOUD = 0xeef3f8;
      const NIGHT = 0x040812;
      const colour = (d, th) => {
        let h = 0;
        for (const [k, f, ph, a] of waves) h += Math.sin((d[0] * k[0] + d[1] * k[1] + d[2] * k[2]) * f * 6 + ph) * a;
        let c = h > 0.55 ? mix(LAND, DRY, smooth(0.9, 1.6, h)) : mix(OCEAN, SHALLOW, smooth(0.0, 0.55, h));
        // Cloud bands: streaks swept round the planet, broken up by the noise.
        const band = Math.sin(d[2] * 38 + Math.sin(d[0] * 21) * 2.2 + h * 1.4);
        const cl = smooth(0.45, 0.95, band) * smooth(-0.6, 0.4, Math.sin(d[0] * 13 + h * 2));
        c = mix(c, CLOUD, cl * 0.9);
        // Day and night across the cap, toward the sun's bearing.
        const r = Math.hypot(d[0], d[2]) || 1e-6;
        const t = (d[0] * sun[0] + d[2] * sun[1]) / r * Math.min(1, th / TH * 1.4);
        const day = 0.08 + 0.92 * smooth(-0.75, -0.15, t);
        // A thin bright rim toward the limb, where you look through the most air.
        const rim = smooth(0.2, 0.62, th) * 0.35;
        return lin(mix(mix(NIGHT, c, day), 0x9fd2f2, rim * day));
      };
      const ring = [];
      for (let i = 0; i <= NR; i++) {
        const th = TH * Math.pow(i / NR, 1.15);
        const row = [];
        for (let j = 0; j < NS; j++) {
          const ph = j / NS * Math.PI * 2;
          const d = [Math.sin(th) * Math.cos(ph), Math.cos(th), Math.sin(th) * Math.sin(ph)];
          row.push({ p: add(C, d, R), c: colour(d, th) });
        }
        ring.push(row);
      }
      for (let i = 1; i <= NR; i++) {
        for (let j = 0; j < NS; j++) {
          const j2 = (j + 1) % NS;
          const a = ring[i - 1][j], b = ring[i][j], c = ring[i][j2], d = ring[i - 1][j2];
          bright.quadV(a.p, d.p, c.p, b.p, a.c, d.c, c.c, b.c);
        }
      }
    }

    // ---- under the road: a keel ---------------------------
    for (let i = 1; i < n; i++) {
      const a = line[i - 1], b = line[i];
      if (!level(a) || !level(b)) continue;
      const kh = 0.35 * a.hw;
      const P = (e, o, dy) => [e.p[0] + e.lat[0] * o, e.p[1] - dy, e.p[2] + e.lat[2] * o];
      face(P(a, -kh, 1.2), P(b, -kh, 1.2), P(b, -kh, 3.4), P(a, -kh, 3.4), TRIM);
      face(P(a, kh, 1.2), P(b, kh, 1.2), P(b, kh, 3.4), P(a, kh, 3.4), TRIM);
      face(P(a, -kh, 3.4), P(b, -kh, 3.4), P(b, kh, 3.4), P(a, kh, 3.4), shade(TRIM, -0.2));
    }

    // ---- modules under the jumps ----------------------------------------------
    const span = (i, d, dir) => {
      let j = i;
      while (j + dir >= 0 && j + dir < n && Math.abs(s[j + dir] - s[i]) < d && !line[j + dir].air) j += dir;
      return j;
    };
    const hull = (i0, i1, depth) => {
      if (i1 - i0 < 2) return;
      const pts = [];
      for (let i = i0; i <= i1; i++) {
        const e = line[i], w = e.hw + 1.5, top = e.p[1] - 0.6;
        pts.push({ L: [e.p[0] + e.lat[0] * w, top, e.p[2] + e.lat[2] * w],
                   R: [e.p[0] - e.lat[0] * w, top, e.p[2] - e.lat[2] * w], top, e });
      }
      const dn = (p, d) => [p[0], p[1] - d, p[2]];
      for (let k = 1; k < pts.length; k++) {
        const a = pts[k - 1], b = pts[k];
        face(dn(a.L, 1.2), dn(b.L, 1.2), dn(b.L, depth), dn(a.L, depth), HULL);
        face(dn(a.R, 1.2), dn(b.R, 1.2), dn(b.R, depth), dn(a.R, depth), HULL);
        face(a.L, b.L, dn(b.L, 1.2), dn(a.L, 1.2), HAZARD);
        face(a.R, b.R, dn(b.R, 1.2), dn(a.R, 1.2), HAZARD);
        face(a.L, b.L, b.R, a.R, TRIM);
        face(dn(a.L, depth), dn(b.L, depth), dn(b.R, depth), dn(a.R, depth), TRIM);
        // Window rows down both flanks.
        if (k % 2 === 0) {
          for (const side of ['L', 'R']) {
            const m = (t) => [a[side][0] + (b[side][0] - a[side][0]) * t, 0, a[side][2] + (b[side][2] - a[side][2]) * t];
            const o = side === 'L' ? 1 : -1, e = b.e;
            for (const dy of [4, 8]) {
              const p0 = m(0.25), p1 = m(0.75), y = b.top - dy;
              const off = [e.lat[0] * o * 0.08, 0, e.lat[2] * o * 0.08];
              glow(add([p0[0], y, p0[2]], off, 1), add([p1[0], y, p1[2]], off, 1),
                   add([p1[0], y - 1.2, p1[2]], off, 1), add([p0[0], y - 1.2, p0[2]], off, 1), WINDOW);
            }
          }
        }
      }
      const cap = (p) => face(p.L, p.R, dn(p.R, depth), dn(p.L, depth), HULL);
      cap(pts[0]); cap(pts[pts.length - 1]);
    };
    for (const [a, b] of runs(line, (e) => e.air)) {
      hull(span(a - 1, 50, -1), a - 1, 18);
      hull(b + 1, span(b + 1, 60, 1), 18);
    }

    // ---- docking rings and gantries over the road -----------------------------
    // Full height, no lintel under the camera: the ring's crown is hw + 14 over
    // the road and its sides stand well past the kerb.
    const ringAt = (i) => {
      const e = line[i];
      if (!level(e)) return;
      const f = fwd(i), up = e.n, lat = e.lat, rad = e.hw + 15, SEG = 36;
      for (let k = 0; k < SEG; k++) {
        const t = (k + 0.5) / SEG * Math.PI * 2;
        const c = add(add(e.p, lat, Math.cos(t) * rad), up, Math.sin(t) * rad);
        const rdir = norm(add(add([0, 0, 0], lat, Math.cos(t)), up, Math.sin(t)));
        const tdir = cross(f, rdir);
        obox(c, rdir, tdir, f, 1.6, rad * Math.PI / SEG + 0.15, 3.2, k % 2 ? HULL : TRIM, solid);
        if (k % 3 === 0) obox(add(c, rdir, -1.7), rdir, tdir, f, 0.15, 0.6, 3.4, k % 6 ? LIGHT : CYAN, bright);
      }
    };
    const gantryAt = (i) => {
      const e = line[i];
      if (!level(e) || Math.abs(e.curv || 0) > 1 / 70) return;
      const f = fwd(i), H = 14;
      for (const sd of [-1, 1]) {
        const base = add(e.p, e.lat, sd * (e.hw + 3.2));
        const v = obox(add(base, UP, H / 2 - 4), e.lat, UP, f, 1.1, H / 2 + 4, 1.1, TRIM, solid);
        collide(v);
        obox(add(base, UP, -6), e.lat, UP, f, 0.9, 0.9, 0.9, HAZARD, solid);
      }
      const beam = add(e.p, UP, H + 1.2);
      obox(beam, e.lat, UP, f, e.hw + 4.3, 1.2, 1.2, HULL, solid);
      for (let k = -3; k <= 3; k++) {
        obox(add(add(beam, e.lat, k * (e.hw + 2) / 3.5), UP, -1.25), e.lat, UP, f, 0.6, 0.08, 0.6, k % 2 ? LIGHT : HAZARD2, bright);
      }
    };
    for (const f of [0.012, 0.035, 0.955]) ringAt(atDist(f));
    for (const f of [0.08, 0.44, 0.58, 0.80, 0.90]) gantryAt(atDist(f));

    // ---- solar array wings off the outside of the lap ----------------------------
    const clearOf = (pts, d) => pts.every((p) => toRoad(p[0], p[2]) > d);
    const array = (i, out, len, wid, dy) => {
      const e = line[i], sd = outside(i), f = fwd(i);
      const root = add(e.p, e.lat, sd * out);
      root[1] = e.p[1] + dy;
      const lat = [e.lat[0] * sd, 0, e.lat[2] * sd];
      const corners = [add(root, f, len), add(root, f, -len), add(add(root, lat, wid * 2 + 8), f, len), add(add(root, lat, wid * 2 + 8), f, -len)];
      if (!clearOf(corners, e.hw + 18)) return;
      // The boom, then two rows of panels tilted toward the sun.
      tube(root, add(root, lat, wid * 2 + 10), 1.1, 6, TRIM, solid);
      const tilt = norm([sun[0] * 0.5, 1, sun[1] * 0.5]);
      for (const row of [0, 1]) {
        const c = add(root, lat, 4 + wid * (row + 0.5));
        const X = f, Z = norm(cross(X, tilt)), Y = cross(Z, X);
        obox(c, X, Y, Z, len, 0.25, wid / 2 - 0.6, 0x1a2c5c, solid);
        for (let g = -len + 6; g < len; g += 6) {
          obox(add(add(c, Y, 0.3), X, g), X, Y, Z, 0.18, 0.05, wid / 2 - 0.6, 0x5f7fb8, solid);
        }
        obox(add(c, Y, 0.3), X, Y, Z, len, 0.05, 0.16, 0x9fb4d8, solid);
      }
      obox(add(root, lat, wid * 2 + 10), lat, UP, f, 0.5, 0.5, 0.5, RED, bright);
    };
    for (const f of [0.10, 0.22, 0.50, 0.66, 0.74, 0.86]) array(atDist(f), 38, 34, 16, -8);

    // ---- docked freighters ----------------------------------------------------
    const ship = (i, out, dy) => {
      const e = line[i], sd = outside(i), f = fwd(i);
      const c = add(e.p, e.lat, sd * out);
      c[1] = e.p[1] + dy;
      const L = 30, W = 8, H = 7;
      const lat = norm([e.lat[0] * sd, 0, e.lat[2] * sd]);
      const span4 = [add(c, f, L + 10), add(c, f, -L - 6), add(add(c, f, L), lat, -W), add(add(c, f, -L), lat, -W)];
      if (!clearOf(span4, e.hw + 14)) return;
      obox(c, f, UP, lat, L, H, W, HULL, solid);
      obox(add(c, UP, H + 2), f, UP, lat, L * 0.55, 2, W * 0.6, TRIM, solid);
      obox(add(add(c, f, L + 4), UP, 1), f, UP, lat, 4, H * 0.7, W * 0.7, TRIM, solid);
      obox(add(add(c, f, L + 8.1), UP, 2), f, UP, lat, 0.1, 1.2, W * 0.5, CYAN, bright);
      for (const zz of [-1, 1]) obox(add(add(c, f, -L - 1.5), lat, zz * W * 0.5), f, UP, lat, 1.5, H * 0.5, W * 0.3, lin(0xff9a3c), bright);
      for (let k = -L + 4; k < L - 2; k += 3.2) {
        for (const zz of [-1, 1]) {
          obox(add(add(add(c, f, k), lat, zz * (W + 0.05)), UP, 2.5), f, UP, lat, 0.9, 0.5, 0.05, WINDOW, bright);
        }
      }
      // A docking arm back to the station.
      const arm0 = add(add(c, lat, -W), UP, 0), arm1 = add(e.p, e.lat, sd * (e.hw + 10));
      arm1[1] = e.p[1] - 6;
      tube(arm0, arm1, 1.6, 6, TRIM, solid);
    };
    for (const f of [0.30, 0.62, 0.70, 0.94]) ship(atDist(f), 48, -3);

    // ---- the station core in the infield --------------------------------------
    let rIn = 1e9;
    for (const e of line) rIn = Math.min(rIn, Math.hypot(e.p[0] - cx, e.p[2] - cz));
    {
      const core = [cx, midY, cz];
      // The spine, the reactor and the hub.
      prismAt(core, 12, 10, midY - 90, midY + 70, HULL);
      for (let y = midY - 80; y < midY + 66; y += 12) prismAt(core, 12, 10.4, y, y + 1.2, LIGHT, true);
      for (let k = 0; k < 4; k++) prismAt(core, 14, 18 - k * 3, midY - 110 + k * 5, midY - 104 + k * 5, CYAN, true);
      prismAt(core, 14, 22, midY + 10, midY + 26, TRIM);
      // The wheel: habitat modules round a rim, on four spokes.
      const Rw = Math.max(60, rIn * 0.55), SEG = 40;
      const wy = midY + 8;
      for (let k = 0; k < SEG; k++) {
        const t = (k + 0.5) / SEG * Math.PI * 2;
        const c = [cx + Math.cos(t) * Rw, wy, cz + Math.sin(t) * Rw];
        const r = [Math.cos(t), 0, Math.sin(t)], tg = [-Math.sin(t), 0, Math.cos(t)];
        obox(c, tg, UP, r, Rw * Math.PI / SEG + 0.2, 5, 6, k % 5 === 0 ? TRIM : HULL, solid);
        for (const zz of [-1, 1]) {
          obox(add(add(c, r, zz * 6.05), UP, 1), tg, UP, r, Rw * Math.PI / SEG * 0.7, 0.8, 0.05, WINDOW, bright);
        }
      }
      for (let k = 0; k < 4; k++) {
        const t = k / 4 * Math.PI * 2 + 0.4;
        tube([cx, wy, cz], [cx + Math.cos(t) * Rw, wy, cz + Math.sin(t) * Rw], 2.2, 6, TRIM, solid);
      }
      // Two great solar wings off the spine, along the long axis of the infield.
      const ax = (x1 - x0) > (z1 - z0) ? [1, 0, 0] : [0, 0, 1];
      for (const sd of [-1, 1]) {
        let reach = Rw + 20;
        while (reach < 900 && toRoad(cx + ax[0] * sd * (reach + 20), cz + ax[2] * sd * (reach + 20)) > 70) reach += 10;
        if (reach < Rw + 40) continue;
        const a0 = [cx + ax[0] * sd * (Rw + 14), midY - 24, cz + ax[2] * sd * (Rw + 14)];
        const a1 = [cx + ax[0] * sd * reach, midY - 24, cz + ax[2] * sd * reach];
        tube([cx, midY - 24, cz], a1, 1.8, 6, TRIM, solid);
        const side = cross(ax, UP);
        const tilt = norm([sun[0] * 0.4, 1, sun[1] * 0.4]);
        for (let d = 0; d < reach - Rw - 20; d += 34) {
          const c = add(a0, ax, sd * (d + 16));
          for (const zz of [-1, 1]) {
            const pc = add(c, side, zz * 24);
            const Z = norm(cross(ax, tilt));
            obox(pc, ax, cross(Z, ax), Z, 15, 0.3, 20, 0x1a2c5c, solid);
            obox(add(pc, UP, 0.35), ax, cross(Z, ax), Z, 15, 0.05, 0.2, 0x9fb4d8, solid);
          }
        }
        obox(a1, ax, UP, side, 1, 1, 1, RED, bright);
      }
    }
    function prismAt(c, sides, r, y0, y1, k, lit) {
      const q = lit ? glow : face;
      for (let i = 0; i < sides; i++) {
        const t0 = i / sides * Math.PI * 2, t1 = (i + 1) / sides * Math.PI * 2;
        const A = [c[0] + Math.cos(t0) * r, y0, c[2] + Math.sin(t0) * r], B = [c[0] + Math.cos(t1) * r, y0, c[2] + Math.sin(t1) * r];
        q(A, B, [B[0], y1, B[2]], [A[0], y1, A[2]], k);
        q([c[0], y1, c[2]], [B[0], y1, B[2]], [A[0], y1, A[2]], [c[0], y1, c[2]], k);
        q([c[0], y0, c[2]], [A[0], y0, A[2]], [B[0], y0, B[2]], [c[0], y0, c[2]], k);
      }
    }
  }
})();
