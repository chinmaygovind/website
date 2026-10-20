(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.monument = { props: props };

  const WATER_DECK = 9.0;
  const STONE = 0x8a7f62;
  const STONE_DARK = 0x5e5844;
  const SAND = 0xb0a27a;
  const SAND_DARK = 0x8c7f5c;
  const MOSS = 0x3f6a38;
  const MOSS_DARK = 0x2c4c2a;
  const LEAF = 0x2f5e30;
  const GOLD = 0xd8aa3c;
  const FALLS = 0x6fae9e;
  const FALLS_HI = 0x9ccbbd;
  const FOAM = 0xa8d2c4;
  const CURRENT = 0x235f50;

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

  function bend(line, i) {
    const a = line[Math.max(0, i - 2)].p, b = line[i].p, c = line[Math.min(line.length - 1, i + 2)].p;
    const cr = (b[0] - a[0]) * (c[2] - b[2]) - (b[2] - a[2]) * (c[0] - b[0]);
    return Math.abs(cr) < 1e-3 ? 0 : Math.sign(cr);
  }

  const off = (e, side, d, up) => [
    e.p[0] + e.lat[0] * side * d + e.n[0] * (up || 0),
    e.p[1] + e.lat[1] * side * d + e.n[1] * (up || 0),
    e.p[2] + e.lat[2] * side * d + e.n[2] * (up || 0)];

  // The river. Drawn over the palette's flat `below` plane, which stays as the
  // respawn floor; everything here is picture and none of it is collided.
  const DEEP = 0x0a302a, SHALLOW = 0x245e4c;
  const RIPPLE = 0x8cc4ae, SURF = 0xcfe6d8;
  const mix = (a, b, t) => {
    const c = (s) => Math.round(((a >> s) & 255) * (1 - t) + ((b >> s) & 255) * t);
    return (c(16) << 16) | (c(8) << 8) | c(0);
  };

  function drawWater(ctx, water, wet, falls) {
    const { solid, bright, bbox, pal, shade } = ctx;
    const rnd = ctx.mulberry(4409);
    const reach = (pal.below && pal.below.reach) || 500;
    const C = 10;
    const x0 = bbox.x0 - reach, z0 = bbox.z0 - reach;
    const nx = Math.ceil((bbox.x1 - bbox.x0 + 2 * reach) / C);
    const nz = Math.ceil((bbox.z1 - bbox.z0 + 2 * reach) / C);
    // Distance from anything standing in the river, in cells: seeded at every
    // island, stack, ruin and pier, then a two-pass chamfer sweep.
    const D = new Float32Array(nx * nz).fill(1e9);
    for (const [wx, wz, r] of wet) {
      const k = Math.ceil(r / C);
      const cx = Math.round((wx - x0) / C), cz = Math.round((wz - z0) / C);
      for (let i = cx - k; i <= cx + k; i++) for (let j = cz - k; j <= cz + k; j++) {
        if (i >= 0 && j >= 0 && i < nx && j < nz) D[j * nx + i] = 0;
      }
    }
    for (let j = 0; j < nz; j++) for (let i = 0; i < nx; i++) {
      let v = D[j * nx + i];
      if (i) v = Math.min(v, D[j * nx + i - 1] + 1);
      if (j) v = Math.min(v, D[(j - 1) * nx + i] + 1);
      if (i && j) v = Math.min(v, D[(j - 1) * nx + i - 1] + 1.41);
      if (j && i < nx - 1) v = Math.min(v, D[(j - 1) * nx + i + 1] + 1.41);
      D[j * nx + i] = v;
    }
    for (let j = nz - 1; j >= 0; j--) for (let i = nx - 1; i >= 0; i--) {
      let v = D[j * nx + i];
      if (i < nx - 1) v = Math.min(v, D[j * nx + i + 1] + 1);
      if (j < nz - 1) v = Math.min(v, D[(j + 1) * nx + i] + 1);
      if (i < nx - 1 && j < nz - 1) v = Math.min(v, D[(j + 1) * nx + i + 1] + 1.41);
      if (j < nz - 1 && i) v = Math.min(v, D[(j + 1) * nx + i - 1] + 1.41);
      D[j * nx + i] = v;
    }
    const depth = (i, j) => Math.min(1, D[Math.min(nz - 1, j) * nx + Math.min(nx - 1, i)] / 5);
    // Vertex heights: a low swell, kept under the respawn line at water + 0.6.
    const hv = (i, j) => {
      const h = Math.sin(i * 1.7 + j * 0.9) * Math.sin(j * 1.3 - i * 0.6);
      const k = ((i * 73856093) ^ (j * 19349663)) >>> 0;
      return water + 0.25 + 0.12 * h + 0.1 * ((k % 1000) / 1000 - 0.5);
    };
    const V = (i, j) => [x0 + i * C, hv(i, j), z0 + j * C];
    for (let j = 0; j < nz; j++) for (let i = 0; i < nx; i++) {
      const A = V(i, j), B = V(i, j + 1), Cc = V(i + 1, j + 1), Dd = V(i + 1, j);
      const t = depth(i, j);
      const band = 0.05 * Math.sin(i * 0.21 + j * 0.08);
      solid.tri(A, B, Cc, shade(mix(SHALLOW, DEEP, t), band + (rnd() - 0.5) * 0.14));
      solid.tri(A, Cc, Dd, shade(mix(SHALLOW, DEEP, t), band + (rnd() - 0.5) * 0.14));
    }

    const top = water + 0.48;
    const flat = (cx, cz, ux, uz, len, w, y, colr) => {
      const vx = -uz, vz = ux;
      bright.quad([cx - ux * len - vx * w, y, cz - uz * len - vz * w],
                  [cx - ux * len + vx * w, y, cz - uz * len + vz * w],
                  [cx + ux * len + vx * w, y, cz + uz * len + vz * w],
                  [cx + ux * len - vx * w, y, cz + uz * len - vz * w], colr);
    };
    {
      // Ripple dashes, all running with the current, densest in the shallows.
      const fa = 0.35, ux = Math.cos(fa), uz = Math.sin(fa);
      for (let k = 0; k < 2600; k++) {
        const i = Math.floor(rnd() * nx), j = Math.floor(rnd() * nz);
        const t = depth(i, j);
        if (rnd() < t * 0.6) continue;
        flat(x0 + (i + rnd()) * C, z0 + (j + rnd()) * C, ux, uz, 2 + rnd() * 5, 0.18 + rnd() * 0.2, top,
             mix(RIPPLE, SHALLOW, t * 0.5 + rnd() * 0.3));
      }
      // A broken ring of surf round everything that stands in the river.
      for (const [wx, wz, r] of wet) {
        if (r > 30) continue;
        const m = 7 + Math.floor(r);
        for (let q = 0; q < m; q++) {
          if (rnd() < 0.3) continue;
          const a = (q + rnd() * 0.4) / m * Math.PI * 2, rr = r + 0.6 + rnd() * 1.2;
          const cx = wx + Math.cos(a) * rr, cz = wz + Math.sin(a) * rr;
          flat(cx, cz, -Math.sin(a), Math.cos(a), Math.PI * rr / m * 0.8, 0.3 + rnd() * 0.3, top + 0.02, SURF);
        }
      }
    }
    if (falls) {
      // Churned water where the falls land, thinning out downstream.
      for (let k = 0; k < 140; k++) {
        const u = rnd(), d = falls.faceD - 2 - u * u * 70;
        const t = (rnd() - 0.5) * 2 * (falls.w + u * 14);
        const cx = falls.mx + falls.fx * t + falls.lx * d, cz = falls.mz + falls.fz * t + falls.lz * d;
        const sz = (1.2 + rnd() * 2.6) * (1 - u * 0.6);
        flat(cx, cz, falls.fx, falls.fz, sz, sz * (0.5 + rnd() * 0.5), top + 0.04 + rnd() * 0.04,
             mix(SURF, RIPPLE, u * 0.8 + rnd() * 0.2));
      }
    }
  }

  function props(ctx) {
    const { solid, bright, track, minY, shade, face, col, KIND } = ctx;
    const line = track.line, n = line.length;
    const water = minY - WATER_DECK;
    const rnd = ctx.mulberry(7311);
    const wet = [];

    const obox = (cx, cz, fx, fz, hf, hl, y0, y1, k, hit) => {
      const lx = -fz, lz = fx;
      const P = (a, b, y) => [cx + fx * a * hf + lx * b * hl, y, cz + fz * a * hf + lz * b * hl];
      const c = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
      for (let i = 0; i < 4; i++) {
        const [a0, b0] = c[i], [a1, b1] = c[(i + 1) % 4];
        face(P(a0, b0, y0), P(a1, b1, y0), P(a1, b1, y1), P(a0, b0, y1), shade(k, (i % 2) * -0.08));
        if (hit && (hit === 2 || i % 2 === 0)) col.addQuad(P(a0, b0, y0), P(a1, b1, y0), P(a1, b1, y1), P(a0, b0, y1), KIND.WALL);
      }
      face(P(-1, -1, y1), P(-1, 1, y1), P(1, 1, y1), P(1, -1, y1), k);
      if (hit) col.addQuad(P(-1, -1, y1), P(-1, 1, y1), P(1, 1, y1), P(1, -1, y1), KIND.OFFROAD);
    };

    const nearRoad = (x, z, half, margin, skip) => {
      for (let j = 0; j < n; j += 2) {
        if (skip && skip(j)) continue;
        const r = line[j];
        if (Math.hypot(r.p[0] - x, r.p[2] - z) - half < r.hw + margin) return true;
      }
      return false;
    };
    const overRoad = (x, y, z, half) => {
      for (let j = 0; j < n; j++) {
        const r = line[j];
        if (r.p[1] > y - 1.5) continue;
        if (Math.hypot(r.p[0] - x, r.p[2] - z) < r.hw + half + 1) return true;
      }
      return false;
    };
    const flat = (e) => !e.air && (e.n[1] || 0) > 0.95;

    const level = line.map((e, i) => flat(e) && e.p[1] > minY + 8 && i > 0
      && Math.abs(e.p[1] - line[i - 1].p[1]) < 0.03);
    const summit = runs(level, (v) => v).filter((r) => r[1] - r[0] >= 8)
      .sort((p, q) => line[q[0]].p[1] - line[p[0]].p[1])[0];
    const inPyramid = [];
    if (summit) {
      const A = line[summit[0]], B = line[summit[1]];
      const cx = (A.p[0] + B.p[0]) / 2, cz = (A.p[2] + B.p[2]) / 2;
      let fx = B.p[0] - A.p[0], fz = B.p[2] - A.p[2];
      const fl = Math.hypot(fx, fz) || 1; fx /= fl; fz /= fl;
      const top = line[summit[0]].p[1];
      const along = (e) => (e.p[0] - cx) * fx + (e.p[2] - cz) * fz;
      const across = (e) => (e.p[0] - cx) * -fz + (e.p[2] - cz) * fx;
      const reach = (yk) => {
        let back = summit[0], fwd = summit[1];
        while (back > 0 && line[back].p[1] > yk + 0.8) back--;
        while (fwd < n - 1 && line[fwd].p[1] > yk + 0.8) fwd++;
        for (let j = back; j <= fwd; j++) inPyramid[j] = true;
        return Math.min(-along(line[back]), along(line[fwd])) - 0.6;
      };
      // Two things, the way the real temples are built: a body with straight,
      // steep sides of its own, and a stairway out of its front face that the
      // road climbs. The road cannot be steeper than a hill (or it is a kicker),
      // so a body whose steps followed the road came out as a low, curved mound.
      const N = 7;
      const hw = A.hw;
      const H = (top - minY) / N;
      const S = H * 0.7;                   // how far each step steps out
      const yAt = (k) => k === N - 1 ? top - 0.3 : minY + (top - minY) * (k + 1) / N;
      const reaches = [];
      for (let k = 0; k < N; k++) reaches.push(reach(yAt(k)));
      // Clear of every other road, never wider than the step below it.
      const clearHl = (a, hl, yTop) => {
        while (hl > hw + 2) {
          let hitRoad = false;
          for (let j = 0; j < n && !hitRoad; j += 2) {
            if (inPyramid[j]) continue;
            const e = line[j];
            if (e.p[1] > yTop + 0.2) continue;
            if (Math.abs(along(e)) < a + e.hw + 2 && Math.abs(across(e)) < hl + e.hw + 2) hitRoad = true;
          }
          if (!hitRoad) break;
          hl -= 2;
        }
        return Math.max(hl, hw + 2);
      };
      const topA = reaches[N - 1], topH = hw + 6;
      const steps = [];
      for (let k = N - 1; k >= 0; k--) {
        const up = steps.length ? steps[steps.length - 1] : null;
        const yk = yAt(k);
        const a = Math.min(reaches[k], topA + (N - 1 - k) * S);
        const hl = clearHl(a, topH + (N - 1 - k) * S, yk);
        steps.push(up ? [Math.max(a, up[0]), Math.max(hl, up[1])] : [a, hl]);
      }
      steps.reverse();
      let y0 = minY - 0.3;
      for (let k = 0; k < N; k++) {
        const yk = yAt(k), [a, hl] = steps[k];
        obox(cx, cz, fx, fz, a, hl, y0, yk, k % 2 ? SAND : SAND_DARK, true);
        // the stairway, out to where the road comes down to this step
        if (reaches[k] > a + 0.5) {
          obox(cx, cz, fx, fz, reaches[k], hw + 1.5, y0, yk - 0.3, k % 2 ? SAND_DARK : SAND, true);
        }
        if (k < N - 1) {
          for (const s of [-1, 1]) {
            obox(cx + -fz * s * (hl - 0.6), cz + fx * s * (hl - 0.6), fx, fz, a - 1, 0.7,
                 yk, yk + 0.25, MOSS, false);
          }
        }
        y0 = yk;
      }

      // The same slope carries on down into the river, so the pyramid stands in
      // the water rather than on a slab; the stairway's foot goes down with it.
      {
        let [ea, eh] = steps[0];
        const sa = reaches[0] + (reaches[0] - reaches[1]);
        obox(cx, cz, fx, fz, sa, hw + 1.5, water - 6, minY - 0.6, SAND_DARK, true);
        for (let m = 1; minY - 0.3 - (m - 1) * H > water - 6; m++) {
          const y1 = minY - 0.3 - (m - 1) * H;
          const yb = minY - 0.3 - m * H > water ? minY - 0.3 - m * H : water - 6;
          ea += S;
          eh = Math.max(eh, clearHl(ea, eh + S, y1));
          obox(cx, cz, fx, fz, ea, eh, yb, y1, m % 2 ? SAND_DARK : SAND, true);
        }
      }

      const roof = top + 11.5;
      const L = Math.hypot(B.p[0] - A.p[0], B.p[2] - A.p[2]) / 2;
      for (let t = -1; t <= 1; t += 0.5) {
        for (const s of [-1, 1]) {
          const px = cx + fx * t * (L - 3) + -fz * s * (hw + 2.4);
          const pz = cz + fz * t * (L - 3) + fx * s * (hw + 2.4);
          obox(px, pz, fx, fz, 1.1, 1.1, top - 0.3, roof, STONE, 2);
          obox(px, pz, fx, fz, 1.8, 1.8, roof - 1.4, roof - 0.6, GOLD, false);
        }
      }
      obox(cx, cz, fx, fz, L + 1, hw + 5, roof, roof + 1.6, STONE_DARK, false);
      obox(cx, cz, fx, fz, L - 4, hw + 2, roof + 1.6, roof + 3.4, STONE, false);
      obox(cx, cz, fx, fz, L - 10, hw - 2, roof + 3.4, roof + 4.8, MOSS, false);
      obox(cx, cz, fx, fz, L - 12, 1.0, roof + 4.8, roof + 6.2, GOLD, false);
      for (let t = -1; t <= 1; t += 0.125) {
        for (const s of [-1, 1]) {
          const len = 2 + rnd() * 5;
          const px = cx + fx * t * L + -fz * s * (hw + 4.6);
          const pz = cz + fz * t * L + fx * s * (hw + 4.6);
          solid.box(px, roof - len / 2, pz, 0.25, len / 2, 0.25, rnd() < 0.5 ? LEAF : MOSS);
        }
      }
    }

    let falls = null;
    const air = runs(line, (e) => e.air).sort((p, q) => (q[1] - q[0]) - (p[1] - p[0]))[0];
    const inCliff = [];
    if (air) {
      const A = line[Math.max(0, air[0] - 1)], B = line[Math.min(n - 1, air[1] + 1)];
      let fx = B.p[0] - A.p[0], fz = B.p[2] - A.p[2];
      const gl = Math.hypot(fx, fz) || 1; fx /= gl; fz /= gl;
      const mx = (A.p[0] + B.p[0]) / 2, mz = (A.p[2] + B.p[2]) / 2;
      const hw = A.hw;
      const cliffOff = hw + 72;
      let side = 1;
      for (const s of [1, -1]) {
        const px = mx + -fz * s * cliffOff, pz = mz + fx * s * cliffOff;
        if (!nearRoad(px, pz, 22, 6, (j) => j >= air[0] - 30 && j <= air[1] + 30)) { side = s; break; }
      }
      const lx = -fz * side, lz = fx * side;
      const lip = A.p[1];
      const ccx = mx + lx * cliffOff, ccz = mz + lz * cliffOff;
      wet.push([ccx, ccz, 16]);
      obox(ccx, ccz, fx, fz, gl / 2 + 18, 14, water, lip + 22, STONE_DARK, false);
      for (const t of [-1, 1]) {
        obox(ccx + fx * t * (gl / 2 + 26) + lx * 6, ccz + fz * t * (gl / 2 + 26) + lz * 6, fx, fz, 14, 16,
             water, lip + 10 + rnd() * 10, shade(STONE_DARK, -0.08), false);
      }
      obox(ccx + lx * 4, ccz + lz * 4, fx, fz, gl / 2 + 12, 11, lip + 22, lip + 24, MOSS_DARK, false);
      for (let i = 0; i < 10; i++) {
        tree(ccx + fx * (rnd() - 0.5) * (gl + 30) + lx * (2 + rnd() * 10),
             lip + 24, ccz + fz * (rnd() - 0.5) * (gl + 30) + lz * (2 + rnd() * 10), 8 + rnd() * 8);
      }
      const faceD = cliffOff - 14 - 0.4;
      const fw = gl * 0.38;
      const W = (t, d, y) => [mx + fx * t + lx * d, y, mz + fz * t + lz * d];
      bright.quad(W(-fw, faceD, lip + 22), W(fw, faceD, lip + 22), W(fw, faceD, water + 0.2), W(-fw, faceD, water + 0.2), FALLS);
      for (let i = 0; i < 7; i++) {
        const t = -fw + (i + 0.5) * (2 * fw / 7), w = 0.5 + rnd() * 0.8;
        bright.quad(W(t - w, faceD - 0.1, lip + 22), W(t + w, faceD - 0.1, lip + 22),
                    W(t + w, faceD - 0.1, water + 0.3), W(t - w, faceD - 0.1, water + 0.3), FALLS_HI);
      }
      falls = { w: fw + 6, fx, fz, lx, lz, faceD, mx, mz };
      // Flat foam and current at one height; a moving `water` sea rises through them.
      if (!ctx.pal.water) {
        bright.quad(W(-fw - 4, faceD - 8, water + 0.5), W(fw + 4, faceD - 8, water + 0.5),
                    W(fw + 4, faceD, water + 0.5), W(-fw - 4, faceD, water + 0.5), FOAM);
        bright.quad(W(-fw, -faceD - 20, water + 0.47), W(fw, -faceD - 20, water + 0.47),
                    W(fw, faceD - 8, water + 0.47), W(-fw, faceD - 8, water + 0.47), CURRENT);
      }

      const under = (i0, i1, k) => {
        if (i1 <= i0) return;
        const a = line[i0], b = line[i1];
        let ux = b.p[0] - a.p[0], uz = b.p[2] - a.p[2];
        const ul = Math.hypot(ux, uz) || 1; ux /= ul; uz /= ul;
        let lo = 1e9;
        for (let j = i0; j <= i1; j++) { lo = Math.min(lo, line[j].p[1]); inCliff[j] = true; }
        obox((a.p[0] + b.p[0]) / 2, (a.p[2] + b.p[2]) / 2, ux, uz, ul / 2, a.hw + 4, water, lo - 0.7, k, false);
      };
      let s0 = air[0] - 1, d = 0;
      while (s0 > 0 && d < 36) { d += Math.hypot(line[s0].p[0] - line[s0 - 1].p[0], line[s0].p[2] - line[s0 - 1].p[2]); s0--; }
      under(s0, air[0] - 1, STONE_DARK);
      let e0 = air[1] + 1; d = 0;
      while (e0 < n - 1 && d < 30) { d += Math.hypot(line[e0 + 1].p[0] - line[e0].p[0], line[e0 + 1].p[2] - line[e0].p[2]); e0++; }
      under(air[1] + 1, e0, STONE_DARK);
    }

    for (let i = 0; i < n; i += 4) {
      const e = line[i];
      if (e.air || inPyramid[i] || inCliff[i] || (e.n[1] || 0) < 0.9) continue;
      if (e.p[1] - water < 1) continue;
      for (const side of [-1, 1]) {
        const c = off(e, side, e.hw - 1.2, -0.6);
        if (overRoad(c[0], c[1], c[2], 1.2)) continue;
        solid.box(c[0], (c[1] + water) / 2, c[2], 1.2, (c[1] - water) / 2, 1.2,
                  shade(STONE_DARK, ((i * 3) % 5 - 2) * 0.03));
        solid.box(c[0], water + 1.5, c[2], 1.25, 1.5, 1.25, MOSS_DARK);
      }
    }

    let ci = 0, ruin = 0;
    while (ci < n) {
      const s = bend(line, ci);
      let cj = ci;
      while (cj + 1 < n && bend(line, cj + 1) === s) cj++;
      if (s !== 0 && cj - ci >= 6) {
        const e = line[(ci + cj) >> 1];
        if (flat(e) && !inPyramid[(ci + cj) >> 1]) {
          const p = off(e, -s, e.hw + 26);
          if (!nearRoad(p[0], p[2], 7, 6)) {
            ruin++;
            const top = e.p[1] + 3;
            solid.box(p[0], (top + water) / 2, p[2], 6, (top - water) / 2, 6, STONE_DARK);
            wet.push([p[0], p[2], 7]);
            solid.box(p[0], top + 0.4, p[2], 6.4, 0.4, 6.4, MOSS);
            if (ruin % 2) {
              solid.box(p[0], top + 5.5, p[2], 3.6, 4.8, 3.4, STONE);
              solid.box(p[0], top + 10.8, p[2], 4.0, 0.6, 3.8, MOSS);
              const ex = e.p[0] - p[0], ez = e.p[2] - p[2], el = Math.hypot(ex, ez) || 1;
              const fx = ex / el, fz = ez / el;
              for (const k of [-1, 1]) {
                const qx = p[0] + fx * 3.5 + -fz * k * 1.5, qz = p[2] + fz * 3.5 + fx * k * 1.5;
                solid.box(qx, top + 7, qz, 0.6, 0.5, 0.6, GOLD);
              }
              solid.box(p[0] + fx * 3.7, top + 3.2, p[2] + fz * 3.7, 0.5, 0.7, 0.5, STONE_DARK);
            } else {
              for (let k = 0; k < 2; k++) {
                const ox = (k ? 2.6 : -2.6), h = 6 + rnd() * 10;
                solid.box(p[0] + ox, top + 0.8 + h / 2, p[2], 1.3, h / 2, 1.3, STONE);
              }
              solid.box(p[0], top + 0.8 + 2, p[2] + 2.6, 4, 1.2, 1.2, STONE_DARK);
            }
          }
        }
      }
      ci = cj + 1;
    }

    const bb = ctx.bbox;
    function tree(x, y, z, h) {
      solid.box(x, y + h * 0.35, z, 0.5, h * 0.35, 0.5, STONE_DARK);
      const c = 2.4 + h * 0.22;
      solid.box(x, y + h * 0.75, z, c, h * 0.16, c * 0.9, shade(LEAF, (rnd() - 0.5) * 0.2));
      solid.box(x + 0.6, y + h * 0.98, z - 0.4, c * 0.6, h * 0.1, c * 0.55, shade(LEAF, 0.1));
    }
    for (let i = 0; i < 45; i++) {
      const px = bb.x0 - 260 + rnd() * (bb.x1 - bb.x0 + 520);
      const pz = bb.z0 - 260 + rnd() * (bb.z1 - bb.z0 + 520);
      const w0 = 14 + rnd() * 14;
      if (nearRoad(px, pz, w0, 46)) continue;
      const hgt = 30 + rnd() * 45, tiers = 3;
      wet.push([px, pz, w0 * 0.55]);
      let y = water;
      for (let t = 0; t < tiers; t++) {
        const u = t / tiers, th = hgt / tiers, w = w0 * (1 - u * 0.25);
        solid.box(px + (rnd() - 0.5) * 3, y + th / 2, pz + (rnd() - 0.5) * 3, w / 2, th / 2, w * 0.85 / 2,
                  shade(STONE_DARK, -0.12 + u * 0.1));
        y += th;
      }
      solid.box(px, y + 1.2, pz, w0 * 0.42, 1.4, w0 * 0.36, MOSS_DARK);
      for (let k = 0; k < 3; k++) {
        tree(px + (rnd() - 0.5) * w0 * 0.5, y + 2.4, pz + (rnd() - 0.5) * w0 * 0.4, 7 + rnd() * 7);
      }
      for (let v = 0; v < 5; v++) {
        const a = rnd() * Math.PI * 2, len = 8 + rnd() * 18;
        solid.box(px + Math.cos(a) * w0 * 0.4, y - len / 2, pz + Math.sin(a) * w0 * 0.34,
                  0.35, len / 2, 0.35, MOSS);
      }
    }
    for (let i = 0; i < 80; i++) {
      const px = bb.x0 - 120 + rnd() * (bb.x1 - bb.x0 + 240);
      const pz = bb.z0 - 120 + rnd() * (bb.z1 - bb.z0 + 240);
      const r = 6 + rnd() * 8;
      if (nearRoad(px, pz, r, 16)) continue;
      const top = water + 1.5 + rnd() * 2.5;
      solid.box(px, (top + water) / 2, pz, r, (top - water) / 2, r * 0.8, shade(MOSS_DARK, (rnd() - 0.5) * 0.2));
      wet.push([px, pz, r * 0.9]);
      const k = 1 + Math.floor(rnd() * 3);
      for (let t = 0; t < k; t++) {
        tree(px + (rnd() - 0.5) * r, top, pz + (rnd() - 0.5) * r * 0.8, 8 + rnd() * 9);
      }
    }

    for (let i = 0; i < 260; i++) {
      const px = bb.x0 - 160 + rnd() * (bb.x1 - bb.x0 + 320);
      const pz = bb.z0 - 160 + rnd() * (bb.z1 - bb.z0 + 320);
      const r = 2 + rnd() * 5;
      if (nearRoad(px, pz, r, 3)) continue;
      const h = 0.6 + rnd() * 1.8;
      solid.box(px, water + h / 2, pz, r, h / 2, r * (0.6 + rnd() * 0.5),
                rnd() < 0.6 ? shade(MOSS_DARK, (rnd() - 0.5) * 0.3) : shade(STONE_DARK, -0.1));
      wet.push([px, pz, r * 0.8]);
    }

    for (let i = 0; i < n; i += 3) wet.push([line[i].p[0], line[i].p[2], line[i].hw]);
    if (!ctx.pal.water) drawWater(ctx, water, wet, falls);
  }
})();
