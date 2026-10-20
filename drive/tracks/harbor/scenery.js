(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.harbor = { props: props };

  // Kept equal to WATER_DECK and the LAMP_* numbers in track.py; the palette
  // imports those, this file cannot.
  const WATER_DECK = 5.0;
  const LAMP_EVERY = 18, LAMP_OFF = 11, LAMP_UP = 4.2;
  // The galleon's centreline, off the road's right edge, and its half beam.
  const SHIP_OFF = 13.5, SHIP_HALF = 24.0;

  const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const mul = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const norm = (a) => { const m = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / m, a[1] / m, a[2] / m]; };
  const lerp3 = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  const off = (e, s, d, up) => [
    e.p[0] + e.lat[0] * s * d + e.n[0] * (up || 0),
    e.p[1] + e.lat[1] * s * d + e.n[1] * (up || 0),
    e.p[2] + e.lat[2] * s * d + e.n[2] * (up || 0)];

  /** An sRGB colour for the unlit buffer, which is handed through as linear. */
  function lin(c, k) {
    const f = (v) => { v /= 255; v = v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); return Math.round(Math.min(1, v * (k || 1)) * 255); };
    return (f((c >> 16) & 255) << 16) | (f((c >> 8) & 255) << 8) | f(c & 255);
  }
  function mix(a, b, t) {
    t = Math.max(0, Math.min(1, t));
    const ch = (s) => Math.round(((a >> s) & 255) * (1 - t) + ((b >> s) & 255) * t);
    return (ch(16) << 16) | (ch(8) << 8) | ch(0);
  }
  function face2(buf, a, b, c, d, k) { buf.quad(a, b, c, d, k); buf.quad(a, d, c, b, k); }

  /** A box in any right-handed frame (R, U, B), wound the way `box` is. */
  function fbox(buf, c, R, U, B, hr, hu, hb, k) {
    const P = (sx, sy, sz) => [c[0] + R[0] * sx * hr + U[0] * sy * hu + B[0] * sz * hb,
                               c[1] + R[1] * sx * hr + U[1] * sy * hu + B[1] * sz * hb,
                               c[2] + R[2] * sx * hr + U[2] * sy * hu + B[2] * sz * hb];
    const v = [P(-1, -1, -1), P(1, -1, -1), P(1, -1, 1), P(-1, -1, 1),
               P(-1, 1, -1), P(1, 1, -1), P(1, 1, 1), P(-1, 1, 1)];
    buf.quad(v[4], v[7], v[6], v[5], k); buf.quad(v[0], v[1], v[2], v[3], k);
    buf.quad(v[0], v[4], v[5], v[1], k); buf.quad(v[1], v[5], v[6], v[2], k);
    buf.quad(v[2], v[6], v[7], v[3], k); buf.quad(v[3], v[7], v[4], v[0], k);
  }
  /** A square timber from A to B, any angle - never a stretched axis box. */
  function beam(buf, A, B, w, k) {
    const d = norm(sub(B, A));
    let r = cross(d, [0, 1, 0]);
    if (Math.hypot(r[0], r[1], r[2]) < 1e-3) r = [1, 0, 0];
    r = norm(r);
    const u = cross(d, r);
    fbox(buf, lerp3(A, B, 0.5), r, u, d, w, w, Math.hypot(B[0] - A[0], B[1] - A[1], B[2] - A[2]) / 2, k);
  }
  /** Horizontal box turned to face `f` (unit x/z). */
  function ybox(buf, c, f, hf, hr, hy, k) {
    const R = [-f[1], 0, f[0]];          // right of f
    fbox(buf, c, R, [0, 1, 0], cross(R, [0, 1, 0]), hr, hy, hf, k);
  }
  /** Quads between consecutive cross-sections, both faces. */
  function loft(buf, secs, k, kf) {
    for (let i = 0; i + 1 < secs.length; i++) {
      const a = secs[i], b = secs[i + 1];
      for (let j = 0; j + 1 < a.length; j++) {
        face2(buf, a[j], a[j + 1], b[j + 1], b[j], kf ? kf(i, j) : k);
      }
    }
  }

  function props(ctx) {
    const { solid, bright, soft, col, KIND, track, pal, minY, bbox, shade, mulberry } = ctx;
    const line = track.line, n = line.length;
    const W = minY - WATER_DECK;
    const rnd = mulberry(3307);

    // Stations bucketed, so "how far is the nearest road" is cheap anywhere.
    const BK = 32, bk = new Map();
    const key = (i, j) => i * 100003 + j;
    for (let i = 0; i < n; i++) {
      const p = line[i].p, k = key(Math.floor(p[0] / BK), Math.floor(p[2] / BK));
      if (!bk.has(k)) bk.set(k, []);
      bk.get(k).push(i);
    }
    /** Distance from (x, z) to the nearest road edge, capped at `cap`. */
    const dRoad = (x, z, cap) => {
      cap = cap || 96;
      const r = Math.ceil(cap / BK), ci = Math.floor(x / BK), cj = Math.floor(z / BK);
      let best = cap;
      for (let a = -r; a <= r; a++) for (let b = -r; b <= r; b++) {
        const l = bk.get(key(ci + a, cj + b));
        if (!l) continue;
        for (const i of l) {
          const e = line[i];
          const d = Math.hypot(e.p[0] - x, e.p[2] - z) - e.hw;
          if (d < best) best = d;
        }
      }
      return best;
    };

    // ---- the galleon's deck: the one part of this file a car can touch ----
    const firstAir = line.findIndex((e) => e.air);
    let da = -1, db = -1;
    for (let i = 0; i < firstAir; i++) {
      if (line[i].hw > 9.9) { if (da < 0) da = i; db = i; }
    }
    const ship = da >= 0;
    const wallQuad = (a, b, h) => {
      const A2 = [a[0], a[1] + h, a[2]], B2 = [b[0], b[1] + h, b[2]];
      col.addQuad(a, b, B2, A2, KIND.WALL);
    };
    const NULLBUF = { quad() {}, tri() {} };
    const post = (c, f, hf, hr, hy, k, buf) => {
      ybox(buf || solid, c, f, hf, hr, hy, k);
      const R = [-f[1], 0, f[0]];
      const P = (sf, sr, y) => [c[0] + f[0] * sf * hf + R[0] * sr * hr, y, c[2] + f[1] * sf * hf + R[2] * sr * hr];
      const y0 = c[1] - hy, y1 = c[1] + hy;
      for (const [a, b] of [[[-1, -1], [1, -1]], [[1, -1], [1, 1]], [[1, 1], [-1, 1]], [[-1, 1], [-1, -1]]]) {
        col.addQuad(P(a[0], a[1], y0), P(b[0], b[1], y0), P(b[0], b[1], y1), P(a[0], a[1], y1), KIND.WALL);
      }
    };
    const fwd = (i) => {
      const a = line[Math.max(0, i - 1)].p, b = line[Math.min(n - 1, i + 1)].p;
      const m = Math.hypot(b[0] - a[0], b[2] - a[2]) || 1;
      return [(b[0] - a[0]) / m, (b[2] - a[2]) / m];
    };
    const DECK = pal.road;
    const HULL = pal.rail;
    // The far gunwale, measured from the road centre, at each deck station:
    // full beam amidships, a touch in at the stern, drawn in hard to the bow.
    const tOf = (i) => (db > da ? (i - da) / (db - da) : 0);
    const taper = (t) => t < 0.12 ? 0.9 + 0.1 * t / 0.12
      : t < 0.5 ? 1 : 1 - 0.5 * Math.pow((t - 0.5) / 0.5, 1.6);
    const edgeAt = (i) => SHIP_OFF + SHIP_HALF * taper(tOf(i));
    const masts = [];
    let castle = null;
    if (ship) {
      for (let i = da + 1; i <= db; i++) {
        const p = line[i - 1], q = line[i];
        const pe = off(p, 1, p.hw - 0.1, -0.03), qe = off(q, 1, q.hw - 0.1, -0.03);
        const pr = off(p, 1, edgeAt(i - 1), -0.03), qr = off(q, 1, edgeAt(i), -0.03);
        // `lat` is to the right, so this is the winding that faces up.
        col.addQuad(pe, pr, qr, qe, KIND.OFFROAD);
        solid.quad(pe, pr, qr, qe, i % 2 ? DECK : shade(DECK, -0.06));
        wallQuad(off(p, 1, edgeAt(i - 1), 0), off(q, 1, edgeAt(i), 0), 1.4);
        if (!q.kick && !q.bp) wallQuad(off(p, -1, p.hw + 0.25, 0), off(q, -1, q.hw + 0.25, 0), 1.1);
      }
      // the sterncastle, standing on the deck beside the road; its collider
      // is this box, and the visual half below draws it
      // Its after face sits just inside the hull's own transom, so the raked
      // stern above it hangs out over the water the way a galleon's does.
      const s0 = line[da], f0 = fwd(da + 2);
      const hr0 = (edgeAt(da) - s0.hw - 3) / 2;
      const c0 = off(s0, 1, s0.hw + 3 + hr0, 0);
      const cc = [c0[0] + f0[0] * 9.3, c0[1], c0[2] + f0[1] * 9.3];
      castle = { c: [cc[0], s0.p[1] + 3.6, cc[2]], f: f0, hf: 9, hr: hr0, hy: 3.6 };
      post(castle.c, f0, castle.hf, castle.hr, castle.hy, 0, NULLBUF);
      for (const u of [0.22, 0.52, 0.8]) {
        const i = Math.round(da + (db - da) * u), e = line[i];
        const base = off(e, 1, SHIP_OFF, 0);
        const H = u === 0.52 ? 60 : u < 0.5 ? 44 : 52;
        masts.push({ i, base, H, f: fwd(i), e, main: u === 0.52 });
        post([base[0], base[1] + 1.5, base[2]], fwd(i), 0.8, 0.8, 1.5, shade(HULL, 0.15));
      }
    }

    const onDeck = (i) => ship && i >= da && i <= db;
    // the lantern posts' colliders, here so the anti-cheat builds them too;
    // the posts themselves are drawn with the lanterns below
    for (let i = 0; i < n; i += LAMP_EVERY) {
      const e = line[i];
      if (e.air || e.n[1] < 0.85) continue;
      const y = e.p[1] + LAMP_UP;
      for (const s of [-1, 1]) {
        if (onDeck(i)) {
          if (s > 0) continue;
          const g = off(e, -1, e.hw + 0.6, 0);
          post([g[0], e.p[1] + 2.6, g[2]], fwd(i), 0.18, 0.18, 2.6, 0, NULLBUF);
        } else {
          const q = off(e, s, LAMP_OFF, 0), y0 = W - 1;
          post([q[0], (y0 + y + 0.7) / 2, q[2]], fwd(i), 0.42, 0.42, (y + 0.7 - y0) / 2, 0, NULLBUF);
        }
      }
    }

    // **Everything past this point is drawn and never collided**, so the
    // anti-cheat stops here: a throw below this line cannot fail pytest, and
    // `tools/validate_track.py` is the check after an edit.
    if (typeof document === 'undefined') return;

    const WOOD = pal.prop, WOOD_DARK = shade(pal.prop, -0.35), WET = shade(pal.prop, -0.55);
    const ROCK = (pal.below && pal.below.crust) || 0x2a3036;
    const LAMP = lin(pal.deco), LAMP_DIM = lin(shade(pal.deco, -0.35));
    const GHOST = lin(pal.pad || 0x7dffc0, 0.9);
    const SAIL = pal.prop2 || 0x9aa8a0;
    const moon = (pal.sky && pal.sky.sun) || { az: 1.9, color: 0xdfe8f0 };
    const MX = Math.sin(moon.az), MZ = Math.cos(moon.az);
    const cx = (bbox.x0 + bbox.x1) / 2, cz = (bbox.z0 + bbox.z1) / 2;
    const span = Math.max(bbox.x1 - bbox.x0, bbox.z1 - bbox.z0);

    // ---- road planking ------------------------------------------------------
    // The engine's road is one flat colour. Seams across it every plank, and
    // lengthwise on the ship's deck, are what make it read as timber.
    const SEAM = shade(pal.road, -0.42);
    for (let i = 1; i < n; i++) {
      const p = line[i - 1], q = line[i];
      if (p.air || q.air || p.bp || q.bp || p.pf || q.pf) continue;
      if (onDeck(i)) {
        for (let u = -p.hw + 1.4; u < Math.min(edgeAt(i - 1), edgeAt(i)) - 0.5; u += 1.4) {
          if (Math.abs(u - p.hw) < 0.3) continue;
          const a = off(p, 1, u, 0.12), b = off(q, 1, u, 0.12);
          const a2 = off(p, 1, u + 0.12, 0.12), b2 = off(q, 1, u + 0.12, 0.12);
          solid.quad(a, a2, b2, b, SEAM);
        }
        continue;
      }
      for (const t of [0, 0.34, 0.67]) {
        const L = lerp3(off(p, -1, p.hw - 0.2, 0.12), off(q, -1, q.hw - 0.2, 0.12), t);
        const R = lerp3(off(p, 1, p.hw - 0.2, 0.12), off(q, 1, q.hw - 0.2, 0.12), t);
        const L2 = lerp3(off(p, -1, p.hw - 0.2, 0.12), off(q, -1, q.hw - 0.2, 0.12), t + 0.05);
        const R2 = lerp3(off(p, 1, p.hw - 0.2, 0.12), off(q, 1, q.hw - 0.2, 0.12), t + 0.05);
        solid.quad(L, R, R2, L2, SEAM);
      }
    }

    // ---- pilings, stringers and bracing under the docks ---------------------
    const foamAt = [];
    // **Every post stands outside the road, measured at the edge it is beside.**
    // They used to stand under the planking at `hw - 0.8` with their tops
    // at the centreline's height, which on a banked corner is above the low
    // edge - so they came up through the road on the inside of every bank.
    // `posts` records each one and `checkPosts` below refuses any that reach
    // the road surface anywhere it is.
    const posts = [];
    const PILE = 0.55, PILE_AT = (e) => e.hw + PILE + 0.15;
    for (let i = 0; i < n; i += 3) {
      const e = line[i];
      if (e.air || onDeck(i) || e.n[1] < 0.85) continue;
      const pts = [];
      for (const s of [-1, 1]) {
        const q = off(e, s, PILE_AT(e), 0), edgeY = off(e, s, e.hw, 0)[1];
        const top = edgeY - 0.3;
        if (top - W < 1.2) { pts.push(null); continue; }
        const h = top - (W - 1.5);
        solid.box(q[0], W - 1.5 + h / 2, q[2], PILE, h / 2, PILE, i % 2 ? WOOD_DARK : WET);
        posts.push([q[0], q[2], PILE, top]);
        pts.push([q[0], top, q[2]]);
        foamAt.push([q[0], q[2], 1.3]);
      }
      if (!pts[0] || !pts[1]) continue;
      // a cross-brace every other bent, an X under the planking
      const yt = Math.min(pts[0][1], pts[1][1]) - 0.6;
      if (i % 6 === 0 && yt - W > 3.4) {
        const yb = W + 0.8;
        beam(solid, [pts[0][0], yb, pts[0][2]], [pts[1][0], yt, pts[1][2]], 0.22, WOOD_DARK);
        beam(solid, [pts[0][0], yt, pts[0][2]], [pts[1][0], yb, pts[1][2]], 0.22, WOOD_DARK);
      }
      // the stringer along each edge, to the next bent, just under the kerb
      const nx = line[Math.min(n - 1, i + 3)];
      if (!nx.air && !onDeck(i + 3) && nx.n[1] >= 0.85) {
        for (const s of [-1, 1]) {
          const a = off(e, s, PILE_AT(e), 0), b = off(nx, s, PILE_AT(nx), 0);
          a[1] = off(e, s, e.hw, 0)[1] - 0.55; b[1] = off(nx, s, nx.hw, 0)[1] - 0.55;
          beam(solid, a, b, 0.3, WOOD_DARK);
        }
      }
    }

    // ---- lanterns on mooring posts, where `pal.lamps` puts the light --------
    for (let i = 0; i < n; i += LAMP_EVERY) {
      const e = line[i];
      if (e.air || e.n[1] < 0.85) continue;
      for (const s of [-1, 1]) {
        const q = off(e, s, LAMP_OFF, 0);
        const y = e.p[1] + LAMP_UP;
        let y0 = W - 1;
        if (onDeck(i)) {
          if (s > 0) continue;
          else {
            const g = off(e, -1, e.hw + 0.6, 0);
            solid.box(g[0], e.p[1] + 2.6, g[2], 0.18, 2.6, 0.18, WOOD_DARK);
            beam(solid, [g[0], y + 0.9, g[2]], [q[0], y + 0.9, q[2]], 0.1, WOOD_DARK);
            y0 = null;
          }
        } else {
          foamAt.push([q[0], q[2], 1.6]);
        }
        if (y0 != null) {
          solid.box(q[0], (y0 + y - 0.6) / 2, q[2], 0.3, (y - 0.6 - y0) / 2, 0.3, WOOD);
          posts.push([q[0], q[2], 0.5, y + 0.7]);
          solid.box(q[0], y - 0.6, q[2], 0.42, 0.08, 0.42, 0x3a3634);
        }
        bright.box(q[0], y, q[2], 0.32, 0.45, 0.32, LAMP);
        solid.box(q[0], y + 0.58, q[2], 0.42, 0.12, 0.42, 0x1a1a1c);
      }
    }

    // ---- the ghost galleon --------------------------------------------------
    // What makes a galleon and not a ferry, in order: a sheer line that sweeps
    // up at both ends, warm planking in bands with a pale wale, one stepped
    // castle with a raked transom and a few small lit windows, one row of gun
    // ports - and masts and torn sails taller than everything else put together.
    if (ship) {
      // **The hull is drawn unlit.** Every face of it you see is vertical, and
      // the one you drive at - the stern - faces away from a moon low in the
      // other direction, so lit timber came out a black slab whatever colour it
      // was given. These are the on-screen colours, authored in linear.
      const HB = bright;
      const PLANK_A = lin(0x6e5038), PLANK_B = lin(0x5a3f2c), WALE = lin(0xa08462);
      const BELOW = lin(0x2c2622), RAIL = lin(0x8c6e50);
      const GLOW_LO = lin(pal.pad || 0x7dffc0, 0.22), GLOW_HI = lin(pal.pad || 0x7dffc0, 0.55);
      // how far the bulwark stands over the deck: low amidships, up at both ends
      const sheer = (t) => 1.1 + 4.2 * Math.pow(1 - t, 3) * (t < 0.5 ? 1 : 0) + 3.6 * Math.pow(Math.max(0, t - 0.55) / 0.45, 2);
      const secs = [], stn = [];
      const section = (i) => {
        const e = line[i], t = tOf(i), d = e.p[1] - W, edge = edgeAt(i), w = taper(t);
        const at = (lat, y) => { const q = off(e, 1, lat, 0); return [q[0], y, q[2]]; };
        const top = e.p[1] + sheer(t), kL = -e.hw, kR = edge;
        const keel = SHIP_HALF * 0.45 * w;
        return [
          at(kL - 0.3, top), at(kL - 0.6, e.p[1] - 0.2), at(kL - 1.3, e.p[1] - d * 0.25),
          at(kL - 1.8, e.p[1] - d * 0.55), at(kL - 1.0, W - 0.3),
          at(SHIP_OFF - keel, W - 2.6), at(SHIP_OFF + keel, W - 2.6),
          at(kR + 1.0, W - 0.3), at(kR + 1.8, e.p[1] - d * 0.55), at(kR + 1.3, e.p[1] - d * 0.25),
          at(kR + 0.6, e.p[1] - 0.2), at(kR + 0.3, top + 0.4),
        ];
      };
      for (let i = da; i < db; i += 2) { secs.push(section(i)); stn.push(i); }
      secs.push(section(db)); stn.push(db);
      // bands: bulwark, wale, gun deck, lower strake, bottom, ... mirrored
      const bandCol = [PLANK_A, WALE, PLANK_B, PLANK_A, BELOW, BELOW, BELOW, PLANK_A, PLANK_B, WALE, PLANK_A];
      loft(HB, secs, HULL, (k, j) => bandCol[j]);
      // a cap rail along both bulwarks, so the sheer line reads as a line
      for (let k = 0; k + 1 < secs.length; k++) {
        for (const j of [0, 11]) beam(HB, secs[k][j], secs[k + 1][j], 0.28, RAIL);
      }
      // one row of small gun ports in the gun-deck band, unevenly lit
      for (let k = 1; k + 1 < secs.length; k += 2) {
        for (const [a, b, sgn] of [[2, 3, -1], [9, 8, 1]]) {
          const e = line[stn[k]], f = fwd(stn[k]);
          const P = lerp3(secs[k][a], secs[k][b], 0.4);
          const c = [P[0] + e.lat[0] * sgn * 0.08, P[1], P[2] + e.lat[2] * sgn * 0.08];
          const r = rnd();
          ybox(bright, c, f, 0.55, 0.06, 0.55, r < 0.3 ? 0x050605 : r < 0.75 ? GLOW_LO : GLOW_HI);
          if (r > 0.4) beam(solid, c, [c[0] + e.lat[0] * sgn * 1.4, c[1] - 0.15, c[2] + e.lat[2] * sgn * 1.4], 0.22, 0x18181a);
        }
      }
      // the stern below the castle: the hull's own transom, closed
      {
        const s = secs[0];
        // Below the deck it closes right across; above it, the bulwark is
        // only the part beside the road - the road boards through an entry
        // port the full height of the sky, with nothing over it.
        for (let j = 1; j < 5; j++) face2(HB, s[j], s[j + 1], s[10 - j], s[11 - j], bandCol[j]);
        {
          const e0 = line[da], L0 = -e0.hw - 0.3, R0 = edgeAt(da) + 0.3;
          const tt = (e0.hw + 1.2 - L0) / (R0 - L0);
          const A = lerp3(s[0], s[11], tt), B = lerp3(s[1], s[10], tt);
          face2(HB, A, s[11], s[10], B, bandCol[0]);
          beam(HB, [A[0], B[1], A[2]], A, 0.3, RAIL);       // the port's after post
        }
        // the rudder, hung off the sternpost
        const e = line[da], f = fwd(da), rp = off(e, 1, SHIP_OFF, 0);
        HB.box(rp[0] - f[0] * 0.8, (W - 2 + e.p[1]) / 2, rp[2] - f[1] * 0.8, 0.5, (e.p[1] - W + 2) / 2, 0.5, PLANK_B);
      }
      // the bow: each section line drawn in to a stem that rises to a beakhead
      {
        const f = fwd(db), e = line[db];
        const stemTop = off(e, 1, SHIP_OFF, 0);
        const stem = [stemTop[0] + f[0] * 22, e.p[1] - 1.2, stemTop[2] + f[1] * 22];
        const stemLow = [stemTop[0] + f[0] * 12, W - 1.5, stemTop[2] + f[1] * 12];
        const s = secs[secs.length - 1];
        // Band 0 on the road's side would run from the left bulwark to the stem
        // straight across the flight off the bow, so it is not drawn; the
        // left bulwark ends in a post at the lip instead.
        for (let j = 1; j + 1 < s.length; j++) {
          const t0 = j / (s.length - 1), t1 = (j + 1) / (s.length - 1);
          const tip = (t) => lerp3(stem, stemLow, Math.sin(Math.PI * t));
          face2(HB, s[j], s[j + 1], tip(t1), tip(t0), bandCol[j]);
        }
        beam(HB, s[1], s[0], 0.3, RAIL);
        beam(HB, s[11], stem, 0.28, RAIL);
        // the bowsprit, up and out over where the car flies
        const sprit = [stem[0] + f[0] * 24, stem[1] + 11, stem[2] + f[1] * 24];
        beam(solid, stem, sprit, 0.5, WOOD_DARK);
        bright.box(stem[0], stem[1] + 1.2, stem[2], 0.4, 0.55, 0.4, LAMP);
        m0: for (const m of masts) { if (m.i > db - 12) { beam(solid, sprit, [m.base[0], m.base[1] + m.H * 0.86, m.base[2]], 0.07, 0x2a2622); break m0; } }
      }
      // the sterncastle: one stepped deck, a raked transom hanging out over the
      // water, a few small arched windows glowing
      if (castle) {
        const { c, f, hf, hr, hy } = castle;
        const R = [-f[1], 0, f[0]];
        const y0 = c[1] - hy, y1 = c[1] + hy;
        const at = (df, dr, y) => [c[0] + f[0] * df + R[0] * dr, y, c[2] + f[1] * df + R[2] * dr];
        // the castle's sides in planking bands (its collider is the same box)
        for (let b = 0; b < 3; b++) {
          const ya = y0 + (y1 - y0) * b / 3, yb = y0 + (y1 - y0) * (b + 1) / 3, col2 = b === 1 ? PLANK_B : PLANK_A;
          face2(HB, at(-hf, -hr, ya), at(hf, -hr, ya), at(hf, -hr, yb), at(-hf, -hr, yb), col2);
          face2(HB, at(-hf, hr, ya), at(hf, hr, ya), at(hf, hr, yb), at(-hf, hr, yb), col2);
          face2(HB, at(hf, -hr, ya), at(hf, hr, ya), at(hf, hr, yb), at(hf, -hr, yb), col2);
        }
        face2(solid, at(-hf, -hr, y1), at(hf, -hr, y1), at(hf, hr, y1), at(-hf, hr, y1), DECK);
        // the raked transom: leaning back out past the stern as it rises
        const RK = 3.2;
        const T = (dr, y) => at(-hf - RK * (y - y0) / (y1 + 3 - y0), dr, y);
        face2(HB, T(-hr - 0.4, y0 - 2), T(hr + 0.4, y0 - 2), T(hr + 0.8, y1 + 3), T(-hr - 0.8, y1 + 3), PLANK_B);
        face2(HB, at(-hf, -hr - 0.4, y0 - 2), T(-hr - 0.4, y0 - 2), T(-hr - 0.8, y1 + 3), at(-hf, -hr, y1 + 3), PLANK_A);
        face2(HB, at(-hf, hr + 0.4, y0 - 2), T(hr + 0.4, y0 - 2), T(hr + 0.8, y1 + 3), at(-hf, hr, y1 + 3), PLANK_A);
        beam(HB, T(-hr - 0.8, y1 + 3), T(hr + 0.8, y1 + 3), 0.35, RAIL);
        // three small arched windows, not in a grid
        const win = [[-0.55, 0.42, GLOW_HI], [0.05, 0.55, LAMP_DIM], [0.6, 0.38, GLOW_LO]];
        for (const [u, v, k] of win) {
          const y = y0 + (y1 + 3 - y0) * v, q = T(u * hr, y), nb = [-f[0] * 0.12, 0, -f[1] * 0.12];
          const Q = (dr, dy) => add(add(q, nb), [R[0] * dr, dy, R[2] * dr]);
          bright.quad(Q(-1.0, -1.4), Q(1.0, -1.4), Q(1.0, 0.7), Q(-1.0, 0.7), k);
          bright.tri(Q(-1.0, 0.7), Q(1.0, 0.7), Q(0, 1.7), k);
          beam(solid, Q(0, -1.4), Q(0, 1.6), 0.07, 0x101012);
          beam(solid, Q(-1.0, -0.3), Q(1.0, -0.3), 0.07, 0x101012);        // the leading
        }
        // the poop deck: one step up, aft, with a balustrade and a big lantern
        const pf = hf * 0.5, pr = hr * 0.8, pc = -hf + pf, py = y1 + 2.6;
        for (const [a2, b2] of [[[-1, -1], [1, -1]], [[1, -1], [1, 1]], [[1, 1], [-1, 1]]]) {
          face2(HB, at(pc + a2[0] * pf, a2[1] * pr, y1), at(pc + b2[0] * pf, b2[1] * pr, y1),
                at(pc + b2[0] * pf, b2[1] * pr, py), at(pc + a2[0] * pf, a2[1] * pr, py), PLANK_A);
        }
        face2(solid, at(pc - pf, -pr, py), at(pc + pf, -pr, py), at(pc + pf, pr, py), at(pc - pf, pr, py), DECK);
        for (let t = -1; t <= 1.001; t += 0.25) {
          for (const sr of [-1, 1]) {
            const q = at(pc + t * pf, sr * pr, py + 0.7);
            HB.box(q[0], q[1], q[2], 0.14, 0.7, 0.14, RAIL);
          }
          const q = at(pc + pf, t * pr, py + 0.7);
          HB.box(q[0], q[1], q[2], 0.14, 0.7, 0.14, RAIL);
        }
        for (const sr of [-1, 1]) beam(HB, at(pc - pf, sr * pr, py + 1.45), at(pc + pf, sr * pr, py + 1.45), 0.12, RAIL);
        // a short step forward of the castle's front, so the step reads
        for (const sr of [-1, 1]) {
          const q = at(-hf - RK * 0.9, sr * (hr + 0.6), py + 2.4);
          solid.box(q[0], q[1] - 1.4, q[2], 0.15, 1.4, 0.15, WOOD_DARK);
          bright.box(q[0], q[1] + 0.3, q[2], 0.5, 0.7, 0.5, LAMP);
        }
      }
      // masts, tops, yards, rigging, the sails in tatters, and the colours
      // The sails are unlit too: a sheet lit from behind by a low moon is grey
      // whatever it is made of, and these are meant to glow faintly.
      const SAILC = (k) => lin(mix(shade(SAIL, k), 0x9adcc0, 0.12), 0.6);
      for (const m of masts) {
        const { base, H, f, e } = m;
        const R = [e.lat[0], 0, e.lat[2]];
        HB.box(base[0], base[1] + H * 0.33, base[2], 0.8, H * 0.33, 0.8, lin(0x5c4632));
        HB.box(base[0], base[1] + H * 0.8, base[2], 0.5, H * 0.2, 0.5, lin(0x4e3c2c));
        const yards = [[0.3, 0.27], [0.53, 0.21], [0.75, 0.16], [0.93, 0.1]];
        // the top, a platform with a rim, where the lower mast meets the upper
        const ty = base[1] + H * 0.66;
        solid.box(base[0], ty, base[2], 2.6, 0.25, 2.6, WOOD_DARK);
        if (m.main) {
          // the crow's nest: an open tub of staves, higher up
          const cy = base[1] + H * 0.86;
          solid.box(base[0], cy, base[2], 1.8, 0.2, 1.8, WOOD_DARK);
          for (let k = 0; k < 10; k++) {
            const a = k / 10 * Math.PI * 2;
            HB.box(base[0] + Math.cos(a) * 1.8, cy + 1.0, base[2] + Math.sin(a) * 1.8, 0.35, 1.0, 0.35, PLANK_A);
          }
          bright.box(base[0], cy + 1.0, base[2], 0.4, 0.5, 0.4, GHOST);
        }
        for (let k = 0; k < yards.length; k++) {
          const [hy, hk] = yards[k];
          const half = H * hk, y = base[1] + H * hy;
          const A = [base[0] - R[0] * half, y, base[2] - R[2] * half], B = [base[0] + R[0] * half, y, base[2] + R[2] * half];
          beam(solid, A, B, 0.25, WOOD_DARK);
          // the sail hanging off it: torn hem, rents right through, bellied
          const bottom = k === 0 ? base[1] + 3.5 : base[1] + H * yards[k - 1][0] + 0.6;
          const COLS = 7, ROWS = 5, drop = y - 0.4 - bottom;
          const hem = [];
          for (let c = 0; c <= COLS; c++) hem.push(drop * (c % 2 ? 0.45 + 0.4 * rnd() : 0.7 + 0.3 * rnd()));
          const holes = new Set();
          for (let h = 0; h < 3; h++) holes.add(Math.floor(rnd() * COLS) * ROWS + 1 + Math.floor(rnd() * 3));
          const P = (c, r) => {
            const u = -half * 0.95 + 1.9 * half * c / COLS, t = r / ROWS;
            const bl = Math.sin(Math.PI * t * 0.9) * (0.06 * half + 0.8) * (1 - Math.pow(u / half, 2) * 0.6);
            return [base[0] + R[0] * u + f[0] * (bl + 0.6), y - 0.4 - hem[c] * t, base[2] + R[2] * u + f[1] * (bl + 0.6)];
          };
          for (let c = 0; c < COLS; c++) for (let r = 0; r < ROWS; r++) {
            if (holes.has(c * ROWS + r)) continue;
            // the last row of every strip is a torn tooth, not a square
            if (r === ROWS - 1) {
              const tip = lerp3(P(c, r + 1), P(c + 1, r + 1), rnd());
              bright.tri(P(c, r), P(c + 1, r), tip, SAILC(-0.25));
              continue;
            }
            bright.quad(P(c, r), P(c + 1, r), P(c + 1, r + 1), P(c, r + 1), SAILC(-0.06 * r + (c % 2) * 0.04 - Math.abs(c - COLS / 2) * 0.03));
          }
          // ratlines aside, the shrouds: from under each top out to the rails
          if (k === 1) {
            for (const sgn of [-1, 1]) for (const dfd of [-2.5, 0, 2.5]) {
              const g = sgn < 0 ? off(e, -1, e.hw + 0.4, sheer(tOf(m.i)) + 0.3) : off(e, 1, edgeAt(m.i) + 0.2, 1.6);
              const gg = [g[0] + f[0] * dfd, g[1], g[2] + f[1] * dfd];
              beam(solid, [base[0] + R[0] * sgn * 2.4, ty, base[2] + R[2] * sgn * 2.4], gg, 0.05, 0x2a2622);
            }
          }
        }
        // a stay from this masthead down to the foot of the next mast forward
        const nxt = masts.find((o) => o.i > m.i);
        if (nxt) beam(solid, [base[0], base[1] + H * 0.95, base[2]], [nxt.base[0], nxt.base[1] + nxt.H * 0.3, nxt.base[2]], 0.06, 0x2a2622);
        // the colours: a black flag with a skull on the main, a pennant on the rest
        const fy = base[1] + H + 0.4;
        const back = [-f[0], 0, -f[1]];
        if (m.main) {
          const FL = 7, FH = 4.6;
          const FP = (u, v) => [base[0] + back[0] * u + R[0] * Math.sin(u * 0.7) * 0.6, fy - v, base[2] + back[2] * u + R[2] * Math.sin(u * 0.7) * 0.6];
          for (let s2 = 0; s2 < 4; s2++) {
            const u0 = s2 * FL / 4, u1 = (s2 + 1) * FL / 4;
            face2(solid, FP(u0, 0), FP(u1, 0), FP(u1, FH), FP(u0, FH), 0x101012);
          }
          // the skull and crossbones, a hair off both faces
          const mark = (u, v, w, h) => {
            for (const sr of [-1, 1]) {
              const o = [R[0] * sr * 0.08, 0, R[2] * sr * 0.08];
              const A = add(FP(u - w, v - h), o), B = add(FP(u + w, v - h), o), C = add(FP(u + w, v + h), o), D = add(FP(u - w, v + h), o);
              bright.quad(A, B, C, D, 0xb8b4a8);
            }
          };
          mark(3.5, 1.6, 0.9, 0.8);                       // the skull
          mark(3.5, 2.5, 0.5, 0.25);                      // its jaw
          mark(2.4, 3.4, 0.9, 0.18); mark(4.6, 3.4, 0.9, 0.18); // the bones
        } else {
          face2(solid, [base[0], fy, base[2]], [base[0], fy - 1.2, base[2]],
                [base[0] + back[0] * 6, fy - 0.8, base[2] + back[2] * 6], [base[0] + back[0] * 6, fy - 0.8, base[2] + back[2] * 6], 0x3a1414);
        }
        bright.box(base[0], base[1] + H * 0.66 + 1.2, base[2], 0.35, 0.5, 0.35, GHOST);
      }
      // the water round her: foam at the hull, and a faint ghost light lying on it
      for (let k = 0; k < secs.length; k++) for (const j of [4, 7]) {
        const p = secs[k][j];
        if (rnd() < 0.6) foamAt.push([p[0], p[2], 2.2]);
      }
      if (!pal.water) for (let k = 0; k + 1 < secs.length; k++) {
        for (const [j, sgn] of [[4, -1], [7, 1]]) {
          const e0 = line[stn[k]], e1 = line[stn[k + 1]];
          const A = secs[k][j], B = secs[k + 1][j];
          const y = W + 0.75;
          const o0 = [e0.lat[0] * sgn, 0, e0.lat[2] * sgn], o1 = [e1.lat[0] * sgn, 0, e1.lat[2] * sgn];
          const P = (p, o, d) => [p[0] + o[0] * d, y, p[2] + o[2] * d];
          bright.quad(P(A, o0, 0.2), P(B, o1, 0.2), P(B, o1, 5), P(A, o0, 5), GLOW_LO);
        }
      }
    }

    // ---- the whirlpool and the skull rock ------------------------------------
    let pool = null;
    {
      const idx = [];
      for (let i = 0; i < n; i++) {
        const e = line[i];
        if (e.curv && Math.abs(Math.abs(1 / e.curv) - 46) < 0.6) idx.push(i);
      }
      if (idx.length > 3) {
        const a = line[idx[0]].p, b = line[idx[idx.length >> 1]].p, c = line[idx[idx.length - 1]].p;
        const ax = a[0], az = a[2], bx = b[0], bz = b[2], cx2 = c[0], cz2 = c[2];
        const d = 2 * (ax * (bz - cz2) + bx * (cz2 - az) + cx2 * (az - bz));
        const a2 = ax * ax + az * az, b2 = bx * bx + bz * bz, c2 = cx2 * cx2 + cz2 * cz2;
        const C = [(a2 * (bz - cz2) + b2 * (cz2 - az) + c2 * (az - bz)) / d, 0,
                   (a2 * (cx2 - bx) + b2 * (ax - cx2) + c2 * (bx - ax)) / d];
        const roadY = Math.min(a[1], b[1], c[1]);
        // how far in the water can go before the road's inner edge
        let rin = 1e9;
        for (const i of idx) rin = Math.min(rin, Math.hypot(line[i].p[0] - C[0], line[i].p[2] - C[2]) - line[i].hw);
        pool = { C, R: Math.max(16, rin - 6), roadY, face: idx[0] };
      }
    }
    const TROUGH = lin(pal.ground), CREST = lin(shade(pal.ground, 0.3)), FOAM = lin(0xa9c4c8, 0.75);
    const DEEP = (pal.below && pal.below.lava) || lin(shade(pal.ground, -0.4));
    const GLINT = lin(moon.color || 0xdfe8f0, 0.8);
    if (pool) {
      const { C, R } = pool;
      const RINGS = 12, SEG = 56, DEPTH = 13;
      // The funnel and its foam are flat and still; a moving `water` sea cuts
      // through both, so with one the skull just stands in open water.
      if (!pal.water) {
      const yAt = (r) => W - DEPTH * Math.pow(1 - r / R, 1.7);
      for (let k = 0; k < RINGS; k++) {
        const r0 = R * (1 - k / RINGS), r1 = R * (1 - (k + 1) / RINGS);
        for (let j = 0; j < SEG; j++) {
          const sw0 = k * 0.42, sw1 = (k + 1) * 0.42;
          const t0 = j / SEG * Math.PI * 2, t1 = (j + 1) / SEG * Math.PI * 2;
          const P = (r, t) => [C[0] + Math.cos(t) * r, yAt(r), C[2] + Math.sin(t) * r];
          const stripe = Math.sin(t0 * 3 + k * 1.1);
          const c = stripe > 0.72 ? FOAM : mix(mix(CREST, TROUGH, k / RINGS + (stripe < 0 ? 0.3 : 0)), DEEP, k / RINGS * 0.8);
          bright.quad(P(r0, t0 + sw0), P(r1, t0 + sw1), P(r1, t1 + sw1), P(r0, t1 + sw0), c);
        }
      }
      // foam arms on the surface, winding in to the lip: the part you can
      // actually see from a road five units above the water
      for (let arm = 0; arm < 4; arm++) {
        for (let s = 0; s < 40; s++) {
          const t0 = arm * Math.PI / 2 + s * 0.09, t1 = t0 + 0.08;
          const r0 = R + 12 - s * 0.36, r1 = r0 - 0.36, w = 0.7 + 1.6 * Math.sin(Math.PI * s / 40);
          const y = W + 0.7;
          const Q = (t, r) => [C[0] + Math.cos(t) * r, y, C[2] + Math.sin(t) * r];
          if (rnd() < 0.15) continue;
          bright.quad(Q(t0, r0), Q(t1, r1), Q(t1, r1 + w), Q(t0, r0 + w), FOAM);
        }
      }
      }
      // the column the skull sits on, out of the throat of the whirlpool
      const top = pool.roadY + 4;
      for (let k = 0; k < 9; k++) {
        const t = k / 9 * Math.PI * 2, t2 = (k + 1) / 9 * Math.PI * 2;
        const rb = 9 + (k % 3) * 1.4, rt = 6.5 + ((k * 7) % 3);
        const A = [C[0] + Math.cos(t) * rb, W - DEPTH + 2, C[2] + Math.sin(t) * rb];
        const B = [C[0] + Math.cos(t2) * rb, W - DEPTH + 2, C[2] + Math.sin(t2) * rb];
        const A2 = [C[0] + Math.cos(t) * rt, top, C[2] + Math.sin(t) * rt];
        const B2 = [C[0] + Math.cos(t2) * rt, top, C[2] + Math.sin(t2) * rt];
        face2(solid, A, B, B2, A2, shade(ROCK, (k % 2) * 0.08));
      }
      // the skull, facing the way the road arrives
      const fe = line[Math.max(0, pool.face - 14)].p;
      let f = [fe[0] - C[0], fe[2] - C[2]];
      const fm = Math.hypot(f[0], f[1]) || 1; f = [f[0] / fm, f[1] / fm];
      const Rv = [-f[1], 0, f[0]];
      const BONE = 0xc9c2ae, SOCKET = 0x0c0d0e;
      const S = 1.0;
      const at = (df, dr, y) => [C[0] + f[0] * df + Rv[0] * dr, top + y, C[2] + f[1] * df + Rv[2] * dr];
      ybox(solid, at(0, 0, 9 * S), f, 8.5, 8.5, 6.5, BONE);              // cranium
      ybox(solid, at(-0.5, 0, 16.5 * S), f, 7, 7, 1.6, shade(BONE, 0.05)); // crown
      ybox(solid, at(0, 0, 18.6 * S), f, 5, 5, 0.9, shade(BONE, 0.08));
      ybox(solid, at(2.5, 0, 1.6), f, 5.5, 6.5, 1.8, shade(BONE, -0.08)); // jaw
      ybox(solid, at(-3, 9.0, 8), f, 4, 0.6, 4.5, shade(BONE, -0.05));   // temples
      ybox(solid, at(-3, -9.0, 8), f, 4, 0.6, 4.5, shade(BONE, -0.05));
      for (const s of [-1, 1]) {
        ybox(solid, at(8.55, s * 3.6, 10), f, 0.25, 2.6, 2.4, SOCKET);    // the sockets
        ybox(bright, at(8.75, s * 3.6, 9.6), f, 0.1, 0.9, 0.9, GHOST);    // and what is in them
      }
      ybox(solid, at(8.55, 0, 6), f, 0.25, 1.1, 1.6, SOCKET);              // nose
      for (let k = -3; k <= 3; k++) ybox(solid, at(8.3, k * 1.45, 3.6), f, 0.5, 0.55, 0.9, 0xe8e2cc); // teeth
      foamAt.push([C[0], C[2], 0]);
    }

    // ---- the sea ----------------------------------------------------------------
    // Off a game, not off a photograph (Marina Bay's lesson): deep teal, never
    // black; a visible pattern of lit crests and dark troughs; a path of moonlight
    // laid across it towards the moon; foam where anything stands in it.
    const waveY = (x, z) => W + 0.32 * Math.sin(x * 0.29 + z * 0.13) + 0.22 * Math.sin(-x * 0.17 + z * 0.37 + 1.3)
                          + 0.1 * Math.sin(x * 0.71 - z * 0.53 + 0.4);
    const band = (x, z) => {
      const a = (x - cx) * MX + (z - cz) * MZ;
      if (a < -span * 0.6) return 0;
      const s = Math.abs((x - cx) * MZ - (z - cz) * MX);
      const hw = 26 + Math.max(0, a + span * 0.6) * 0.1;
      return Math.max(0, 1 - s / hw);
    };
    const facet = (A, B, Cc, far) => {
      const u = sub(B, A), v = sub(Cc, A);
      let nn = cross(u, v);
      if (nn[1] < 0) nn = mul(nn, -1);
      nn = norm(nn);
      const tilt = -(nn[0] * MX + nn[2] * MZ);
      const mx = (A[0] + B[0] + Cc[0]) / 3, mz = (A[2] + B[2] + Cc[2]) / 3;
      const g = band(mx, mz);
      let c = mix(TROUGH, CREST, 0.35 + tilt * 7 + (rnd() - 0.5) * 0.25);
      if (g > 0 && tilt > -0.01) c = mix(c, GLINT, Math.min(0.55, g * (0.25 + tilt * 18)));
      bright.tri(A, B, Cc, mix(c, DEEP, far));
    };
    const sheet = (x0, z0, size, k, far) => {
      const st = size / k;
      for (let u = 0; u < k; u++) for (let v = 0; v < k; v++) {
        const xa = x0 + u * st, za = z0 + v * st, xb = xa + st, zb = za + st;
        if (pool && Math.hypot((xa + xb) / 2 - pool.C[0], (za + zb) / 2 - pool.C[2]) < pool.R - st * 0.4) continue;
        const P = (x, z) => [x, waveY(x, z), z];
        facet(P(xa, za), P(xa, zb), P(xb, zb), far);
        facet(P(xa, za), P(xb, zb), P(xb, za), far);
      }
    };
    const sparkle = (x, z, big) => {
      const s = big ? 0.5 + rnd() * 0.5 : 0.18, y = waveY(x, z) + 0.08;
      bright.quad([x - s, y, z - s * 0.35], [x - s, y, z + s * 0.35], [x + s, y, z + s * 0.35], [x + s, y, z - s * 0.35], GLINT);
    };
    // An animated `water` block in the palette is the sea instead.
    if (!pal.water) {
      const CELL = 16, M = 380;
      const x0 = Math.floor((bbox.x0 - M) / CELL) * CELL, x1 = bbox.x1 + M;
      const z0 = Math.floor((bbox.z0 - M) / CELL) * CELL, z1 = bbox.z1 + M;
      for (let x = x0; x < x1; x += CELL) for (let z = z0; z < z1; z += CELL) {
        const d = dRoad(x + CELL / 2, z + CELL / 2, 200);
        const g = band(x + CELL / 2, z + CELL / 2);
        if (d < 70) sheet(x, z, CELL, 4, 0);
        else if (d < 199) sheet(x, z, CELL, 1, Math.min(0.55, (d - 70) / 240));
        else sheet(x, z, CELL, 1, 0.6);
        const ns = g > 0 ? 3 + Math.floor(g * 6) : (d < 120 ? 1 : 0);
        for (let k = 0; k < ns; k++) if (rnd() < 0.7) sparkle(x + rnd() * CELL, z + rnd() * CELL, g > 0.2);
      }
      // the path of moonlight on out to the horizon, past the drawn sea
      for (let a = 0; a < 1500; a += 14) {
        const ox = cx + MX * (span * 0.5 + M + a), oz = cz + MZ * (span * 0.5 + M + a);
        const wdt = 30 + (span * 0.5 + M + a) * 0.1;
        for (let k = 0; k < 6; k++) {
          const s = (rnd() - 0.5) * 2 * wdt * Math.pow(rnd(), 0.6);
          const x = ox + MZ * s, z = oz - MX * s, L = 2 + rnd() * 5;
          const y = W + 0.05;
          bright.quad([x - MZ * L, y, z + MX * L], [x - MZ * L + MX * 0.8, y, z + MX * L + MZ * 0.8],
                      [x + MZ * L + MX * 0.8, y, z - MX * L + MZ * 0.8], [x + MZ * L, y, z - MX * L],
                      mix(GLINT, DEEP, Math.abs(s) / wdt * 0.7));
        }
      }
    }

    // ---- rocks, wrecks and the cove around it ------------------------------------
    const rock = (x, z, r, h, k) => {
      const N = 6 + Math.floor(rnd() * 3);
      const peak = [x + (rnd() - 0.5) * r * 0.6, W + h, z + (rnd() - 0.5) * r * 0.6];
      const ring = [], mid = [];
      for (let j = 0; j < N; j++) {
        const t = j / N * Math.PI * 2 + rnd() * 0.3, rr = r * (0.7 + rnd() * 0.5);
        ring.push([x + Math.cos(t) * rr, W - 2, z + Math.sin(t) * rr]);
        mid.push([x + Math.cos(t) * rr * 0.62, W + h * (0.45 + rnd() * 0.2), z + Math.sin(t) * rr * 0.62]);
      }
      for (let j = 0; j < N; j++) {
        const j2 = (j + 1) % N, c = shade(k || ROCK, (rnd() - 0.5) * 0.25);
        face2(solid, ring[j], ring[j2], mid[j2], mid[j], c);
        solid.tri(mid[j], mid[j2], peak, shade(c, 0.08));
        solid.tri(mid[j], peak, mid[j2], shade(c, 0.08));
      }
      foamAt.push([x, z, r * 1.1]);
    };
    const wreck = (x, z, f, len, kind) => {
      const R = [-f[1], 0, f[0]];
      const P = (df, dr, y) => [x + f[0] * df + R[0] * dr, W + y, z + f[1] * df + R[2] * dr];
      const roll = (rnd() < 0.5 ? -1 : 1) * (0.25 + rnd() * 0.3);
      const beamW = len * 0.17;
      if (kind === 0) {
        // a hull on its side, half under
        const secs = [];
        for (let k = 0; k <= 6; k++) {
          const u = k / 6, df = (u - 0.5) * len;
          const w = beamW * Math.sin(Math.PI * Math.min(1, 0.2 + u * 0.95)) + 0.4;
          const lift = 1.5 + 2.5 * Math.pow(Math.abs(u - 0.6), 2) * 4 - 3.5;
          const pts = [[-w, 3.2], [-w * 1.05, 0.2], [-w * 0.5, -2.5], [0, -3.4], [w * 0.5, -2.5], [w * 1.05, 0.2], [w, 3.2]];
          secs.push(pts.map(([dr, y]) => {
            const yy = y * Math.cos(roll) + dr * Math.sin(roll) + lift, rr = dr * Math.cos(roll) - y * Math.sin(roll);
            return P(df, rr, yy);
          }));
        }
        loft(solid, secs, shade(WOOD_DARK, -0.1), (i, j) => j === 0 || j === 5 ? shade(WOOD, -0.2) : shade(WOOD_DARK, -0.15));
        // a deck, a broken mast and a rag of sail
        const mb = P(len * 0.05, Math.sin(roll) * 3, 2.8);
        const mt = add(mb, [R[0] * Math.sin(roll) * 16 + f[0] * 3, 16 * Math.cos(roll), R[2] * Math.sin(roll) * 16 + f[1] * 3]);
        beam(solid, mb, mt, 0.45, WOOD_DARK);
        const ya = lerp3(mb, mt, 0.8);
        beam(solid, add(ya, mul(R, -5)), add(ya, mul(R, 5)), 0.22, WOOD_DARK);
        face2(soft, add(ya, mul(R, -4)), add(ya, mul(R, 1)), add(add(ya, mul(R, 0.5)), [0, -6, 0]), add(add(ya, mul(R, -4)), [0, -3.5, 0]), shade(SAIL, -0.2));
      } else {
        // the bones of one: a keel and its ribs out of the water
        beam(solid, P(-len / 2, 0, -0.3), P(len / 2, 0, 1.0), 0.6, WOOD_DARK);
        for (let k = 0; k < 9; k++) {
          const df = (k / 8 - 0.5) * len * 0.85, h = 5 + 4 * Math.sin(Math.PI * k / 8) - rnd() * 2;
          for (const s of [-1, 1]) {
            if (rnd() < 0.12) continue;
            const w = beamW * (0.6 + 0.4 * Math.sin(Math.PI * k / 8));
            const a = P(df, 0, 0.2), b = P(df, s * w, h * 0.45), c = P(df, s * w * 0.75, h);
            beam(solid, a, b, 0.32, shade(WOOD, -0.25));
            beam(solid, b, c, 0.28, shade(WOOD, -0.25));
          }
        }
      }
      foamAt.push([x, z, len * 0.45]);
    };
    // wrecks down the two long legs, rocks everywhere, both clear of the road
    {
      let placed = 0;
      for (let i = 30; i < n && placed < 14; i += 21) {
        const e = line[i];
        if (e.air) continue;
        const s = (i / 21) % 2 ? 1 : -1;
        const dist = e.hw + 30 + rnd() * 34;
        const q = off(e, s, dist, 0);
        const L = 26 + rnd() * 14;
        if (dRoad(q[0], q[2], 60) < L * 0.6 + 10) continue;
        if (pool && Math.hypot(q[0] - pool.C[0], q[2] - pool.C[2]) < pool.R + L) continue;
        if (ship && dRoad(q[0], q[2], 60) < 40 && (i > da - 40 && i < db + 20)) continue;
        const a = rnd() * Math.PI * 2;
        wreck(q[0], q[2], [Math.cos(a), Math.sin(a)], L, placed % 3 === 2 ? 1 : 0);
        placed++;
        i += 30;
      }
      for (let k = 0; k < 90; k++) {
        const x = bbox.x0 - 200 + rnd() * (bbox.x1 - bbox.x0 + 400);
        const z = bbox.z0 - 200 + rnd() * (bbox.z1 - bbox.z0 + 400);
        const r = 3 + rnd() * rnd() * 14;
        const d = dRoad(x, z, 80);
        if (d < r + 14) continue;
        if (pool && Math.hypot(x - pool.C[0], z - pool.C[2]) < pool.R + r) continue;
        rock(x, z, r, r * (0.6 + rnd() * 1.6));
      }
      if (pool) {
        for (let k = 0; k < 5; k++) {
          const t = k / 5 * Math.PI * 2 + 0.6, rr = pool.R + 3;
          const x = pool.C[0] + Math.cos(t) * rr, z = pool.C[2] + Math.sin(t) * rr;
          if (dRoad(x, z, 40) > 9) rock(x, z, 3 + rnd() * 2, 4 + rnd() * 6);
        }
      }
    }
    // boathouses along the first stretch of dock, back from the edge
    {
      let made = 0;
      for (let i = 8; i < Math.min(n, 140) && made < 4; i += 9) {
        const e = line[i], s = made % 2 ? 1 : -1;
        const q = off(e, s, e.hw + 19, 0);
        if (dRoad(q[0], q[2], 40) < 13) continue;
        const f = fwd(i), y0 = e.p[1] - 0.4;
        const hf = 7, hr = 6, hy = 4;
        const R = [-f[1], 0, f[0]];
        for (const sf of [-1, 1]) for (const sr of [-1, 1]) {
          const p = [q[0] + f[0] * sf * (hf - 0.5) + R[0] * sr * (hr - 0.5), 0, q[2] + f[1] * sf * (hf - 0.5) + R[2] * sr * (hr - 0.5)];
          solid.box(p[0], (W - 1 + y0) / 2, p[2], 0.5, (y0 - W + 1) / 2, 0.5, WET);
          posts.push([p[0], p[2], 0.5, y0 + 9]);
          foamAt.push([p[0], p[2], 1.2]);
        }
        ybox(solid, [q[0], y0 + hy, q[2]], f, hf, hr, hy, shade(WOOD, -0.12));
        // gable roof, ridge along f
        const top = y0 + hy * 2, ridge = top + 4;
        const C4 = (sf, sr, y) => [q[0] + f[0] * sf * (hf + 0.8) + R[0] * sr * (hr + 0.8), y, q[2] + f[1] * sf * (hf + 0.8) + R[2] * sr * (hr + 0.8)];
        const Rg = (sf) => [q[0] + f[0] * sf * (hf + 0.8), ridge, q[2] + f[1] * sf * (hf + 0.8)];
        face2(solid, C4(-1, -1, top - 0.6), C4(1, -1, top - 0.6), Rg(1), Rg(-1), 0x2a2a30);
        face2(solid, C4(-1, 1, top - 0.6), C4(1, 1, top - 0.6), Rg(1), Rg(-1), 0x26262c);
        for (const sf of [-1, 1]) {
          const a = [q[0] + f[0] * sf * hf + R[0] * -hr, top, q[2] + f[1] * sf * hf + R[2] * -hr];
          const b = [q[0] + f[0] * sf * hf + R[0] * hr, top, q[2] + f[1] * sf * hf + R[2] * hr];
          face2(solid, a, b, [q[0] + f[0] * sf * hf, ridge - 0.5, q[2] + f[1] * sf * hf], [q[0] + f[0] * sf * hf, ridge - 0.5, q[2] + f[1] * sf * hf], shade(WOOD, -0.2));
        }
        // a lit window on the side facing the road
        const w = [q[0] - R[0] * s * (hr + 0.06), y0 + hy + 0.6, q[2] - R[2] * s * (hr + 0.06)];
        ybox(bright, w, f, 1.6, 0.06, 1.1, LAMP);
        made++;
        i += 12;
      }
    }
    // the lighthouse out at the mouth of the cove, under the moon
    {
      const d = span * 0.5 + 170;
      let x = cx + MX * d, z = cz + MZ * d;
      for (let k = 0; k < 8 && dRoad(x, z, 80) < 40; k++) { x += MX * 30; z += MZ * 30; }
      rock(x, z, 22, 10, shade(ROCK, -0.1));
      const H = 52, N = 8;
      for (let k = 0; k < N; k++) {
        const t = k / N * Math.PI * 2, t2 = (k + 1) / N * Math.PI * 2;
        for (let b = 0; b < 4; b++) {
          const y0 = W + 8 + H * b / 4, y1 = W + 8 + H * (b + 1) / 4;
          const r0 = 7.5 - b * 0.8, r1 = 7.5 - (b + 1) * 0.8;
          face2(solid, [x + Math.cos(t) * r0, y0, z + Math.sin(t) * r0], [x + Math.cos(t2) * r0, y0, z + Math.sin(t2) * r0],
                [x + Math.cos(t2) * r1, y1, z + Math.sin(t2) * r1], [x + Math.cos(t) * r1, y1, z + Math.sin(t) * r1],
                b % 2 ? 0x8a8478 : 0x5a2a26);
        }
      }
      const yt = W + 8 + H;
      solid.box(x, yt + 0.5, z, 5.4, 0.5, 5.4, 0x1c1c20);
      bright.box(x, yt + 3, z, 3.2, 2.5, 3.2, LAMP);
      solid.box(x, yt + 6.3, z, 4, 0.8, 4, 0x1c1c20);
      solid.box(x, yt + 8, z, 2, 0.9, 2, 0x1c1c20);
    }
    // the cove: dark cliffs round the back, open to the sea under the moon
    {
      const Rc = span * 0.5 + 520, N = 72;
      const hgt = [];
      for (let k = 0; k < N; k++) {
        const t = k / N * Math.PI * 2;
        const toMoon = Math.cos(t - Math.atan2(MZ, MX));
        const open = Math.max(0, (toMoon - 0.55) / 0.45);
        hgt.push(Math.max(0, (70 + 34 * Math.sin(t * 5) + 20 * Math.sin(t * 11 + 1) + rnd() * 18) * (1 - open)));
      }
      for (let k = 0; k < N; k++) {
        const h0 = hgt[k], h1 = hgt[(k + 1) % N];
        if (h0 < 2 && h1 < 2) continue;
        const t = k / N * Math.PI * 2, t2 = (k + 1) / N * Math.PI * 2;
        const P = (tt, r, y) => [cx + Math.cos(tt) * r, y, cz + Math.sin(tt) * r];
        const c = shade(ROCK, -0.2 + (k % 3) * 0.06);
        face2(solid, P(t, Rc, W - 2), P(t2, Rc, W - 2), P(t2, Rc + 30, W + h1), P(t, Rc + 30, W + h0), c);
        face2(solid, P(t, Rc + 30, W + h0), P(t2, Rc + 30, W + h1), P(t2, Rc + 160, W + h1 * 1.2), P(t, Rc + 160, W + h0 * 1.2), shade(c, -0.25));
      }
    }

    // ---- nothing stands up through the road ----------------------------------
    // Every post recorded above, against every station near it: inside the
    // road's footprint its top must be under the surface at that point, with
    // the station's own half-width and roll. A failure throws, which
    // `tools/validate_track.py` reports as `uncaught:`.
    {
      const bad = [];
      for (const [x, z, r, top] of posts) {
        const ci = Math.floor(x / BK), cj = Math.floor(z / BK);
        for (let a2 = -1; a2 <= 1; a2++) for (let b2 = -1; b2 <= 1; b2++) {
          const l = bk.get(key(ci + a2, cj + b2));
          if (!l) continue;
          for (const i of l) {
            const e = line[i];
            if (e.air) continue;
            const f = fwd(i), lh = Math.hypot(e.lat[0], e.lat[2]) || 1;
            const dx = x - e.p[0], dz = z - e.p[2];
            const along = dx * f[0] + dz * f[1], side = (dx * e.lat[0] + dz * e.lat[2]) / lh;
            if (Math.abs(along) > 2.2 || Math.abs(side) - r > e.hw) continue;
            const u = Math.max(-e.hw, Math.min(e.hw, side)) / lh;
            const surf = e.p[1] + e.lat[1] * u;
            if (top > surf - 0.05) bad.push(i);
          }
        }
      }
      if (bad.length) throw new Error('harbor: ' + bad.length + ' post(s) stand up through the road, first at station ' + bad[0]);
    }

    // ---- foam --------------------------------------
    // Flat rings at one height; a moving `water` sea rises through them.
    if (!pal.water) for (const [x, z, r] of foamAt) {
      const rr = Math.max(0.9, r), N = rr > 4 ? 12 : 6;
      for (let j = 0; j < N; j++) {
        if (rnd() < 0.3) continue;
        const t = j / N * Math.PI * 2, t2 = (j + 0.7) / N * Math.PI * 2;
        const r0 = rr * (0.9 + rnd() * 0.2), r1 = r0 + 0.5 + rr * 0.08;
        const y = W + 0.36;
        bright.quad([x + Math.cos(t) * r0, y, z + Math.sin(t) * r0], [x + Math.cos(t2) * r0, y, z + Math.sin(t2) * r0],
                    [x + Math.cos(t2) * r1, y, z + Math.sin(t2) * r1], [x + Math.cos(t) * r1, y, z + Math.sin(t) * r1], FOAM);
      }
    }
  }
})();
