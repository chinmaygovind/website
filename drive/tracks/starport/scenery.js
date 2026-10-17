(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.starport = { props: props };

  const HULL = 0x252b40;
  const HULL_DARK = 0x161a2a;
  const CYAN = 0x2ef2ff;
  const MAGENTA = 0xff2fc8;

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

  function circumcenter(a, b, c) {
    const ax = a[0], az = a[2], bx = b[0], bz = b[2], cx = c[0], cz = c[2];
    const d = 2 * (ax * (bz - cz) + bx * (cz - az) + cx * (az - bz));
    const a2 = ax * ax + az * az, b2 = bx * bx + bz * bz, c2 = cx * cx + cz * cz;
    return [(a2 * (bz - cz) + b2 * (cz - az) + c2 * (az - bz)) / d,
            (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d];
  }

  function props(ctx) {
    const { solid, bright, track, minY, maxY } = ctx;
    const line = track.line, n = line.length;
    const quad2 = (buf, a, b, c, d, k) => { buf.quad(a, b, c, d, k); buf.quad(a, d, c, b, k); };

    const s = [0];
    for (let i = 1; i < n; i++) {
      s.push(s[i - 1] + Math.hypot(line[i].p[0] - line[i - 1].p[0], line[i].p[2] - line[i - 1].p[2]));
    }
    const span = (i, d, dir) => {
      let j = i;
      while (j + dir >= 0 && j + dir < n && Math.abs(s[j + dir] - s[i]) < d && !line[j + dir].air) j += dir;
      return j;
    };

    const hull = (i0, i1, depth, endA, endB) => {
      const pts = [];
      for (let i = i0; i <= i1; i++) {
        const e = line[i], w = e.hw - 0.6, top = e.p[1] - 1.0;
        const L = [e.p[0] + e.lat[0] * w, top, e.p[2] + e.lat[2] * w];
        const R = [e.p[0] - e.lat[0] * w, top, e.p[2] - e.lat[2] * w];
        pts.push({ L, R, Lb: [L[0], top - depth, L[2]], Rb: [R[0], top - depth, R[2]],
                   Ls: [L[0], top - 1.4, L[2]], Rs: [R[0], top - 1.4, R[2]] });
      }
      for (let k = 1; k < pts.length; k++) {
        const a = pts[k - 1], b = pts[k];
        quad2(solid, a.L, b.L, b.R, a.R, HULL_DARK);
        quad2(bright, a.L, b.L, b.Ls, a.Ls, CYAN);
        quad2(bright, a.R, b.R, b.Rs, a.Rs, CYAN);
        quad2(solid, a.Ls, b.Ls, b.Lb, a.Lb, HULL);
        quad2(solid, a.Rs, b.Rs, b.Rb, a.Rb, HULL);
        quad2(solid, a.Lb, b.Lb, b.Rb, a.Rb, HULL_DARK);
        if (k % 6 === 0) {
          const m = (u, v, t) => [u[0] + (v[0] - u[0]) * t, u[1] + (v[1] - u[1]) * t, u[2] + (v[2] - u[2]) * t];
          quad2(bright, m(a.Ls, a.Lb, 0.35), m(b.Ls, b.Lb, 0.35), m(b.Ls, b.Lb, 0.5), m(a.Ls, a.Lb, 0.5), MAGENTA);
          quad2(bright, m(a.Rs, a.Rb, 0.35), m(b.Rs, b.Rb, 0.35), m(b.Rs, b.Rb, 0.5), m(a.Rs, a.Rb, 0.5), MAGENTA);
        }
      }
      const cap = (p, glow) => {
        quad2(solid, p.L, p.R, p.Rb, p.Lb, HULL);
        if (glow) quad2(bright, p.L, p.R, p.Rs, p.Ls, MAGENTA);
      };
      cap(pts[0], endA);
      cap(pts[pts.length - 1], endB);
    };

    for (const [a, b] of runs(line, (e) => e.air)) {
      hull(span(a - 1, 46, -1), a - 1, 16, false, true);
      hull(b + 1, span(b + 1, 60, 1), 16, true, false);
    }
    hull(0, span(0, 90, 1), 12, false, false);
    hull(span(n - 1, 230, -1), n - 1, 12, true, false);

    const wall = runs(line, (e) => e.wrad);
    if (wall.length) {
      const [a, b] = wall[0];
      const c = circumcenter(line[a].p, line[(a + b) >> 1].p, line[b].p);
      const r = 9, bot = minY - 70, top = maxY + 46, sides = 10;
      const ring = (y) => {
        const out = [];
        for (let k = 0; k < sides; k++) {
          const t = (k / sides) * Math.PI * 2;
          out.push([c[0] + Math.cos(t) * r, y, c[1] + Math.sin(t) * r]);
        }
        return out;
      };
      const lo = ring(bot), hi = ring(top);
      for (let k = 0; k < sides; k++) {
        const k2 = (k + 1) % sides;
        quad2(solid, lo[k], lo[k2], hi[k2], hi[k], HULL);
      }
      for (let y = bot + 6; y < top - 2; y += 9) {
        const A = ring(y), B = ring(y + 1.6);
        for (let k = 0; k < sides; k++) {
          const k2 = (k + 1) % sides, g = 1.04;
          const out = (p) => [c[0] + (p[0] - c[0]) * g, p[1], c[1] + (p[2] - c[1]) * g];
          quad2(bright, out(A[k]), out(A[k2]), out(B[k2]), out(B[k]), (Math.round((y - bot) / 9) % 2) ? CYAN : MAGENTA);
        }
      }
      const cap = (y, col) => {
        const R = ring(y);
        for (let k = 1; k < sides - 1; k++) quad2(bright, R[0], R[k], R[k + 1], R[k + 1], col);
      };
      cap(top, CYAN);
      cap(bot, MAGENTA);
    }
  }
})();
