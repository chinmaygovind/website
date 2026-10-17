(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.frost = { props: props };

  const ICE = 0xa9d6f0;
  const ICE_DEEP = 0x6fb2dc;
  const ICE_RIM = 0x4f8fc4;
  const WOOD = 0x6b4a34;
  const WOOD_DARK = 0x4a3324;
  const ROOF = 0x3b2c26;
  const SNOW = 0xf4f8fc;
  const GLOW = 0xffd08a;

  const LAKE = [0.80, 0.885];
  const LAKE_R = 85;
  const LODGE = 0.035;

  function props(ctx) {
    const { solid, bright, track, ground, face, shade } = ctx;
    const line = track.line, n = line.length;
    const at = (f) => Math.max(0, Math.min(n - 1, Math.round(f * (n - 1))));
    const add = (a, b, k) => [a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k];

    lake();
    cave();
    lodge();

    function lake() {
      let cx = 0, cz = 0, y = Infinity, c = 0;
      for (let i = at(LAKE[0]); i <= at(LAKE[1]); i++) {
        cx += line[i].p[0]; cz += line[i].p[2]; y = Math.min(y, line[i].p[1]); c++;
      }
      cx /= c; cz /= c;
      const h = y - 0.9, SEG = 64;
      for (let k = 0; k < SEG; k++) {
        const a0 = k / SEG * Math.PI * 2, a1 = (k + 1) / SEG * Math.PI * 2;
        const p0 = [cx + Math.cos(a0) * LAKE_R, h, cz + Math.sin(a0) * LAKE_R];
        const p1 = [cx + Math.cos(a1) * LAKE_R, h, cz + Math.sin(a1) * LAKE_R];
        const m0 = [cx + Math.cos(a0) * LAKE_R * 0.55, h, cz + Math.sin(a0) * LAKE_R * 0.55];
        const m1 = [cx + Math.cos(a1) * LAKE_R * 0.55, h, cz + Math.sin(a1) * LAKE_R * 0.55];
        solid.tri([cx, h, cz], m1, m0, ICE_DEEP);
        solid.quad(m0, m1, p1, p0, ICE);
      }
    }

    function cave() {
      let a = -1, b = -1;
      for (let i = 0; i < n; i++) if (line[i].pf) { if (a < 0) a = i; b = i; }
      if (a < 0) return;
      a += 3; b -= 3;
      const ARC = 14, LIP = 4.5;
      const ring = (e, r) => {
        const o = add(e.p, e.n, LIP), pts = [];
        for (let k = 0; k <= ARC; k++) {
          const t = Math.PI * k / ARC;
          pts.push(add(add(o, e.lat, Math.cos(t) * r), e.n, Math.sin(t) * r));
        }
        return pts;
      };
      const R = line[a].hw + 1.2;
      let prev = null;
      for (let i = a; i <= b; i++) {
        const e = line[i], cur = ring(e, R);
        cur.out = ring(e, R + 3);
        cur.sl = add(add(e.p, e.lat, -(R + 14)), e.n, -1.4);
        cur.sr = add(add(e.p, e.lat, R + 14), e.n, -1.4);
        const footL = add(cur[0], e.n, -LIP - 1.4), footR = add(cur[ARC], e.n, -LIP - 1.4);
        if (prev) {
          for (let k = 0; k < ARC; k++) {
            const lift = Math.sin(Math.PI * (k + 0.5) / ARC);
            const q = [prev.pts[k], cur[k], cur[k + 1], prev.pts[k + 1]];
            const c = shade(ICE, 0.08 * lift - (i % 4 < 2 ? 0.07 : 0) - ((k + (i >> 2)) % 3 === 0 ? 0.05 : 0));
            bright.quad(q[0], q[1], q[2], q[3], c);
            bright.quad(q[0], q[3], q[2], q[1], c);
            face(prev.out[k], cur.out[k], cur.out[k + 1], prev.out[k + 1], SNOW);
          }
          face(prev.sl, cur.sl, cur.out[ARC], prev.out[ARC], SNOW);
          face(prev.sr, cur.sr, cur.out[0], prev.out[0], SNOW);
          face(prev.fl, footL, cur[0], prev.pts[0], ICE_DEEP);
          face(prev.fr, footR, cur[ARC], prev.pts[ARC], ICE_DEEP);
        }
        prev = { pts: cur, out: cur.out, sl: cur.sl, sr: cur.sr, fl: footL, fr: footR };
      }
      for (const i of [a, b]) {
        const e = line[i], inner = ring(e, R), outer = ring(e, R + 3.5);
        for (let k = 0; k < ARC; k++) face(inner[k], inner[k + 1], outer[k + 1], outer[k], ICE_RIM);
        face(add(inner[0], e.n, -LIP - 1.4), inner[0], outer[0], add(outer[0], e.n, -LIP - 1.4), ICE_RIM);
        face(add(inner[ARC], e.n, -LIP - 1.4), inner[ARC], outer[ARC], add(outer[ARC], e.n, -LIP - 1.4), ICE_RIM);
      }
      for (let i = a + 6; i < b - 3; i += 9) {
        const e = line[i];
        for (const s of [-1, 1]) {
          const base = add(add(e.p, e.lat, s * (R - 0.4)), e.n, LIP + 0.3);
          const tip = add(base, e.lat, -s * 1.6);
          const top = add(base, e.n, 3.2);
          bright.quad(base, tip, top, top, 0xbfeaff);
          bright.quad(base, top, top, tip, 0xbfeaff);
        }
      }
    }

    function lodge() {
      const i = at(LODGE), e = line[i];
      const side = -1, off = 46;
      const x = e.p[0] + e.lat[0] * side * off, z = e.p[2] + e.lat[2] * side * off;
      const g = ground(i, side * off);
      const HX = 16, HZ = 8, H = 9;
      solid.box(x, g + H / 2, z, HX, H / 2, HZ, WOOD);
      solid.box(x, g + 0.6, z, HX + 0.6, 0.6, HZ + 0.6, WOOD_DARK);
      const r = g + H, peak = r + 7;
      const A = [x - HX - 1.5, r - 0.4, z - HZ - 2], B = [x + HX + 1.5, r - 0.4, z - HZ - 2];
      const C = [x + HX + 1.5, peak, z], D = [x - HX - 1.5, peak, z];
      const E = [x - HX - 1.5, r - 0.4, z + HZ + 2], F = [x + HX + 1.5, r - 0.4, z + HZ + 2];
      face(A, B, C, D, ROOF);
      face(E, F, C, D, ROOF);
      face(add(A, [0, 1, 0], 0.25), add(B, [0, 1, 0], 0.25), add(C, [0, 1, 0], 0.25), add(D, [0, 1, 0], 0.25), SNOW);
      face(add(E, [0, 1, 0], 0.25), add(F, [0, 1, 0], 0.25), add(C, [0, 1, 0], 0.25), add(D, [0, 1, 0], 0.25), SNOW);
      face([x - HX, r, z - HZ], [x - HX, r, z + HZ], [x - HX, peak - 0.5, z], [x - HX, peak - 0.5, z], WOOD);
      face([x + HX, r, z - HZ], [x + HX, r, z + HZ], [x + HX, peak - 0.5, z], [x + HX, peak - 0.5, z], WOOD);
      solid.box(x + HX * 0.55, peak, z + 3, 1.2, 3.5, 1.2, shade(WOOD_DARK, -0.2));
      const fz = e.lat[2] * side > 0 ? z - HZ - 0.05 : z + HZ + 0.05;
      for (let k = -3; k <= 3; k++) {
        const wx = x + k * 4.2;
        const q = [[wx - 1.2, g + 3, fz], [wx + 1.2, g + 3, fz], [wx + 1.2, g + 6, fz], [wx - 1.2, g + 6, fz]];
        bright.quad(q[0], q[1], q[2], q[3], GLOW);
        bright.quad(q[0], q[3], q[2], q[1], GLOW);
      }
    }
  }
})();
