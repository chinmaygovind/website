// Baku: the city, the Old City wall, the sea, and the walls that are the track.
//
// Monaco's architecture (`ground = None`, the world built here on a lower
// envelope of cones) for a different reason: the circuit never crosses itself,
// but a street circuit is walls on both kerbs for the whole lap, and only a
// floating track may wear a ribbon `rail`. See `track.py`.
//
// **Everything here came off reference footage, section by section** - the
// 2026 pole lap sampled once a second, aerials from the build documentary, a
// track walk and a street walk. The notes on each block say what it was taken
// from. The things that most decide whether this reads as Baku:
//
//  * **the walls change colour every few corners.** Maroon down the start
//    straight, yellow down the Turn 2-3 avenue, navy into the castle, red all
//    the way down the hill, light blue at Turn 16. The brief was blank boards
//    in the real colours, with the odd Drive hoarding among them.
//  * **a grey catch fence stands on every wall, for the whole lap**, three
//    metres of it, leaning in at the top. It is in every frame of the onboard.
//  * **honey sandstone, textured.** One family of Beaux-Arts blocks, tiled with
//    storey textures painted by `tools/make_baku_facades.py`. Textured quads
//    are unlit, so the light is baked in: a face turned to the sun gets the
//    `lit` picture and every other face the `shade` one.
//  * **the landmarks are where they are**: Government House behind the pits,
//    the Old City wall and a round bastion on the inside of Turn 8, the Maiden
//    Tower in the Old City, the Four Seasons at Turn 16, the Flame Towers and
//    the TV tower on the hill, and the Caspian past the boulevard park.
//
// Only the ground near the road is in the collider. Nothing else can be
// reached: the rail is on both kerbs for the whole lap.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.baku = { props: props };

  const DROP = 1.2;          // pavement under the road
  const FLANK = 0.05;        // a city on a gentle amphitheatre, not a hillside
  const EDGE = 16.0;         // pavement held flat this far past the kerb
  const CELLQ = 9.0;
  const PAD = 380;
  const PARK = 64;           // the boulevard park: road centre to the sea wall
  const SH = 3.6;            // one storey
  const ART = '/static/img/art/baku/';

  // Where things are, as fractions of the lap, so they survive a re-solve.
  const F = { t1: 0.038, t2: 0.098, t3: 0.237, t4: 0.270, t5: 0.322, t6: 0.333,
              t7: 0.405, t8: 0.441, t12: 0.471, t13: 0.533, t14: 0.568,
              t15: 0.610, t16: 0.675, t17: 0.712, t18: 0.748, t19: 0.771,
              t20: 0.800 };

  // The wall wraps, per section, off the onboard (the real sponsor behind each
  // one in the comment, because that is what the colour was matched against).
  // [from, to, left, right]
  const MAROON = 0x6a1c36, YELLOW = 0xe3b30e, NAVY = 0x1d2b56, WHITE = 0xe2e0da,
        RED = 0xc4221b, BLACK = 0x1d1f25, MSC = 0x1a2748, SF = 0x173c7a,
        AGREEN = 0x0c7a43, ABLUE = 0x1c56a4, HBLUE = 0x17408a, HGREEN = 0x1f7a3a,
        AMEX = 0x2074c6, MARSH = 0x86b6da, CREAM = 0xd8d0bd;
  const ZONES = [
    [0.000, 0.098, MAROON, MAROON],   // Qatar, both sides, to Turn 2
    [0.098, 0.237, YELLOW, YELLOW],   // Pirelli, the avenue into the sun
    [0.237, 0.270, NAVY, NAVY],       // crypto.com, Turn 3 to 4
    [0.270, 0.322, WHITE, WHITE],     // Liqui Moly, white with red
    [0.322, 0.340, NAVY, RED],        // aws, and the red 'Baku' block at 5-6
    [0.340, 0.405, BLACK, BLACK],     // Louis Vuitton, to Turn 7
    [0.405, 0.455, MSC, MSC],         // MSC, into the castle
    [0.455, 0.475, SF, SF],           // Salesforce, the top of the castle
    [0.475, 0.533, AGREEN, ABLUE],    // Aramco, green and blue, up the hill
    [0.533, 0.568, HBLUE, HGREEN],    // Heineken
    [0.568, 0.675, RED, RED],         // Lenovo, all the way down
    [0.675, 0.712, AMEX, AMEX],       // American Express at Turn 16
    [0.712, 0.748, BLACK, BLACK],     // PwC
    [0.748, 0.800, MSC, MSC],         // Louis Vuitton again, navy and gold
    [0.800, 0.880, WHITE, MARSH],     // #AZERBAIJANGP / Marsh
    [0.880, 1.001, MAROON, MAROON],   // Qatar to the line
  ];
  // Accents on the wraps: a band along the top in a second colour, which is
  // what made each sponsor's run read as a *board* rather than painted concrete.
  const ACCENT = new Map([[WHITE, 0xc8211d], [BLACK, 0xd88a1e], [MSC, 0xc9a24a],
                          [YELLOW, 0x1b1b1b], [RED, 0xf2f0ea], [MAROON, 0xe9e4dc]]);

  const WALLC = [0xd6c39c, 0xdcc9a4, 0xcfb991, 0xe0d0ae, 0xd3bd94];
  const STYLES = ['sand', 'sand', 'cream', 'ochre'];
  const SEATS = [0xd8467e, 0x2f9b58, 0x2f74c0, 0xe6c02c, 0xeeeeea, 0xe07a2c, 0x6ab0d8];

  function props(ctx) {
    const { solid, bright, signs, col, track, pal, bbox, KIND, shade, mulberry } = ctx;
    const line = track.line;
    const n = line.length;
    const idx = (fr) => Math.max(0, Math.min(n - 1, Math.round(fr * (n - 1))));
    const frac = (i) => i / (n - 1);
    const rCity = mulberry(0x3b1a57), rTree = mulberry(0x11c0de), rSeat = mulberry(0x5eed01),
          rGround = mulberry(0x60a7d3), rWall = mulberry(0x0dc17e), rMisc = mulberry(0x7aa7aa);

    // The light, for choosing which facade picture a face gets.
    const Ld = (pal.sky && pal.sky.light && pal.sky.light.dir) || [-0.74, 0.58, 0.34];
    const Lm = Math.hypot(Ld[0], Ld[2]) || 1;
    const LX = Ld[0] / Lm, LZ = Ld[2] / Lm;

    // Horizontal forward and right at a station.
    const fwd = (i) => {
      const a = line[Math.max(0, i - 1)].p, b = line[Math.min(n - 1, i + 1)].p;
      const x = b[0] - a[0], z = b[2] - a[2], m = Math.hypot(x, z) || 1;
      return [x / m, 0, z / m];
    };
    const latH = (i) => { const f = fwd(i); return [-f[2], 0, f[0]]; };
    // `lat` from the builder is road-right; confirm the sign once so everything
    // below can say "side +1 is the car's right".
    const L0 = line[Math.floor(n / 2)].lat, l0 = latH(Math.floor(n / 2));
    const LSIGN = (L0[0] * l0[0] + L0[2] * l0[2]) >= 0 ? 1 : -1;
    const right = (i) => { const l = latH(i); return [l[0] * LSIGN, 0, l[2] * LSIGN]; };
    const off = (i, side, o) => {
      const e = line[i], r = right(i);
      return [e.p[0] + r[0] * side * o, e.p[2] + r[2] * side * o];
    };
    const inRange = (i, a, b) => { const f = frac(i); return f >= a && f < b; };
    // The seafront: the sea is on the right from Turn 16 to Turn 1.
    const seafront = (i) => inRange(i, F.t16 - 0.004, 1.01) || inRange(i, 0, F.t1 - 0.004);

    // ---- the height field, the distance field, and who is nearest ---------
    const x0 = bbox.x0 - PAD, x1 = bbox.x1 + PAD, z0 = bbox.z0 - PAD, z1 = bbox.z1 + PAD;
    const nx = Math.ceil((x1 - x0) / CELLQ) + 1, nz = Math.ceil((z1 - z0) / CELLQ) + 1;
    const H = new Float64Array(nx * nz).fill(1e9);
    const cellOf = (x, z) => {
      const i = Math.round((x - x0) / CELLQ), j = Math.round((z - z0) / CELLQ);
      if (i < 0 || j < 0 || i >= nx || j >= nz) return -1;
      return i * nz + j;
    };
    const DR = new Float64Array(nx * nz).fill(1e9);
    const NI = new Int32Array(nx * nz).fill(-1);
    for (let i = 0; i < n; i++) {
      const e = line[i];
      const y = e.p[1] - DROP, r = e.hw + EDGE;
      const ci = Math.round((e.p[0] - x0) / CELLQ), cj = Math.round((e.p[2] - z0) / CELLQ);
      const k = Math.ceil(r / CELLQ) + 1;
      for (let a = -k; a <= k; a++) for (let b = -k; b <= k; b++) {
        const ii = ci + a, jj = cj + b;
        if (ii < 0 || jj < 0 || ii >= nx || jj >= nz) continue;
        const d = Math.hypot(x0 + ii * CELLQ - e.p[0], z0 + jj * CELLQ - e.p[2]);
        const q = ii * nz + jj;
        if (d <= r && y < H[q]) H[q] = y;
        if (d < DR[q]) { DR[q] = d; NI[q] = i; }
      }
    }
    sweep(H, null, nx, nz, FLANK * CELLQ, FLANK * CELLQ * 1.41421);
    sweep(DR, NI, nx, nz, CELLQ, CELLQ * 1.41421);
    // The same again seeded only from the seafront, so every cell knows which
    // stretch of shore it faces - and past either end of the boulevard the
    // last station's own heading carries the shoreline on, so the bay runs on
    // past Turn 1 instead of stopping at the edge of the circuit.
    const DS = new Float64Array(nx * nz).fill(1e9);
    const NS = new Int32Array(nx * nz).fill(-1);
    for (let i = 0; i < n; i++) {
      if (!seafront(i)) continue;
      const e = line[i];
      const q = cellOf(e.p[0], e.p[2]);
      if (q >= 0 && 0 < DS[q]) { DS[q] = 0; NS[q] = i; }
    }
    sweep(DS, NS, nx, nz, CELLQ, CELLQ * 1.41421);
    let minRoad = Infinity;
    for (const e of line) minRoad = Math.min(minRoad, e.p[1]);
    const SEA = minRoad - 5.5;

    // The sea: nearest road is the seafront, the cell is on its right, and it
    // is past the park. Plus everything that far out on that side of the start
    // straight, so the bay does not stop at the edge of what the road can see.
    const wet = new Uint8Array(nx * nz);
    for (let q = 0; q < H.length; q++) {
      const i = NS[q];
      if (i < 0) continue;
      const ii = Math.floor(q / nz), jj = q - ii * nz;
      const x = x0 + ii * CELLQ, z = z0 + jj * CELLQ;
      const e = line[i], r = right(i);
      const side = (x - e.p[0]) * r[0] + (z - e.p[2]) * r[2];
      if (side > PARK && DR[q] > PARK * 0.9) {
        wet[q] = 1; H[q] = SEA - 3;
      }
    }
    const fieldAt = (x, z) => {
      const fi = (x - x0) / CELLQ, fj = (z - z0) / CELLQ;
      const i = Math.max(0, Math.min(nx - 2, Math.floor(fi)));
      const j = Math.max(0, Math.min(nz - 2, Math.floor(fj)));
      const u = Math.max(0, Math.min(1, fi - i)), v = Math.max(0, Math.min(1, fj - j));
      const a = H[i * nz + j], b = H[i * nz + j + 1], c = H[(i + 1) * nz + j], d = H[(i + 1) * nz + j + 1];
      return (a * (1 - v) + b * v) * (1 - u) + (c * (1 - v) + d * v) * u;
    };
    const isWet = (x, z) => { const q = cellOf(x, z); return q < 0 || wet[q] === 1; };
    const roadDist = (x, z) => { const q = cellOf(x, z); return q < 0 ? 1e9 : DR[q]; };
    // Distance to the nearest road *edge*, exactly, off a bucket grid: a linear
    // scan here is paid thousands of times, and on every lap the anti-cheat
    // re-drives in QuickJS (Monaco's note on `toRoad`).
    const BK = 32, bucket = new Map();
    for (let i = 0; i < n; i++) {
      const e = line[i], key = Math.floor(e.p[0] / BK) + ',' + Math.floor(e.p[2] / BK);
      if (!bucket.has(key)) bucket.set(key, []);
      bucket.get(key).push(i);
    }
    const toRoad = (x, z) => {
      const bi = Math.floor(x / BK), bj = Math.floor(z / BK);
      let best = Infinity;
      for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
        const l = bucket.get((bi + a) + ',' + (bj + b));
        if (!l) continue;
        for (const i of l) {
          const e = line[i], d = Math.hypot(e.p[0] - x, e.p[2] - z) - e.hw;
          if (d < best) best = d;
        }
      }
      return Math.min(best, BK);
    };
    // **A building is clear of the road only if its whole footprint is.**
    // Checking the centre let the Four Seasons - 48 units long, placed just
    // past Turn 16 - put a corner straight across the track after CP5. So every
    // landmark samples its footprint edge and middle, rotated as it is built.
    const clearBox = (cx, cz, f, lat, hu, hv, margin) => {
      for (let a = -1; a <= 1; a += 0.25) for (let b = -1; b <= 1; b += 0.25) {
        if (Math.abs(a) < 1 && Math.abs(b) < 1 && (a !== 0 || b !== 0)) continue;
        const x = cx + f[0] * a * hu + lat[0] * b * hv, z = cz + f[2] * a * hu + lat[2] * b * hv;
        if (toRoad(x, z) < margin) return false;
      }
      return true;
    };

    // ---- the ground ------------------------------------------------------
    // Paving by the road, the city's sandy grey further out, lawn in the
    // boulevard park, and stone in the Old City. Laid flat on the floor, which
    // `docs/track-defects.md` says buys more than anything standing up.
    const lobeOld = (i) => inRange(i, F.t7 + 0.02, F.t12 + 0.01) || inRange(i, F.t15 + 0.03, F.t16 + 0.02);
    for (let i = 0; i < nx - 1; i++) {
      for (let j = 0; j < nz - 1; j++) {
        const q = i * nz + j;
        if (wet[q] && wet[q + nz] && wet[q + 1] && wet[q + nz + 1]) continue;
        const ax = x0 + i * CELLQ, bx = ax + CELLQ, az = z0 + j * CELLQ, bz = az + CELLQ;
        const h00 = H[q], h01 = H[q + 1], h11 = H[q + nz + 1], h10 = H[q + nz];
        const dr = DR[q], ni = NI[q];
        let c;
        if (wet[q]) c = 0x9c8f78;                                   // the sea wall's foot
        else if (dr < 16) c = 0x9d978c;                             // pavement
        else if (ni >= 0 && seafront(ni) && sideOf(ni, ax, az) > 0) c = dr < 30 ? 0xa39c8e : 0x5f7a3c;  // park
        else if (ni >= 0 && lobeOld(ni) && sideOf(ni, ax, az) < 0) c = 0xa8966f;  // the Old City
        else c = 0xa99f8b;
        c = shade(c, (rGround() - 0.5) * 0.07);
        const a = [ax, h00, az], b = [ax, h01, bz], cc = [bx, h11, bz], d = [bx, h10, az];
        solid.quad(a, b, cc, d, c);
        if (dr < 90) col.addQuad(a, b, cc, d, KIND.OFFROAD);
      }
    }
    // A skirt off every dry edge cell, out to the haze, at the edge's own height:
    // otherwise the city stops at a cliff over the sea sheet.
    const SK = 4000;
    const skirt = (i, j, di, dj, i2, j2) => {
      const qa = i * nz + j, qb = i2 * nz + j2;
      if (wet[qa] || wet[qb]) return;
      const a = [x0 + i * CELLQ, H[qa], z0 + j * CELLQ], b = [x0 + i2 * CELLQ, H[qb], z0 + j2 * CELLQ];
      const c = [b[0] + di * SK, b[1], b[2] + dj * SK], d = [a[0] + di * SK, a[1], a[2] + dj * SK];
      face2(solid, a, b, c, d, 0xa29a86);
    };
    for (let i = 0; i < nx - 1; i++) { skirt(i, 0, 0, -1, i + 1, 0); skirt(i, nz - 1, 0, 1, i + 1, nz - 1); }
    for (let j = 0; j < nz - 1; j++) { skirt(0, j, -1, 0, 0, j + 1); skirt(nx - 1, j, 1, 0, nx - 1, j + 1); }

    function sideOf(i, x, z) {
      const e = line[i], r = right(i);
      return (x - e.p[0]) * r[0] + (z - e.p[2]) * r[2];
    }

    // **Everything past this point is drawn and never collided, so the
    // anti-cheat stops here.** `buildTrack` already throws the picture away in
    // QuickJS (`NullBuf`), so this is not about memory - it saves the ~1s of
    // placement arithmetic, on every lap the verifier re-drives. The cost is the
    // one `docs/track-defects.md` warns about: a throw below this line cannot
    // fail pytest, so `tools/validate_track.py` is the check after an edit here.
    if (typeof document === 'undefined') return;

    // ---- the Caspian -------------------------------------------------------
    // Grey-blue in the late sun, never Monaco's cobalt, with the glitter laid
    // on the sun's own bearing. Unlit, so authored far darker than it looks.
    // One wide sheet under everything too, so the bay runs out to the haze.
    const cx0 = (bbox.x0 + bbox.x1) / 2, cz0 = (bbox.z0 + bbox.z1) / 2;
    {
      const R = 5200, y = SEA - 0.4;
      bright.quad([cx0 - R, y, cz0 - R], [cx0 - R, y, cz0 + R], [cx0 + R, y, cz0 + R],
                  [cx0 + R, y, cz0 - R], 0x16293a);
    }
    for (let i = 0; i < nx - 1; i++) {
      for (let j = 0; j < nz - 1; j++) {
        const q = i * nz + j;
        if (!(wet[q] || wet[q + nz] || wet[q + 1])) continue;
        const ax = x0 + i * CELLQ, bx = ax + CELLQ, az = z0 + j * CELLQ, bz = az + CELLQ;
        const t = Math.sin(i * 0.61 + j * 0.37) * 0.5 + Math.sin(i * 0.173 - j * 0.291) * 0.5
                + (rGround() - 0.5) * 0.6;
        const gl = Math.pow(Math.max(0, Math.sin(i * 1.31 + j * 0.47) * Math.sin(i * 0.37 - j * 0.83)), 3) * 0.16;
        bright.quad([ax, SEA, az], [ax, SEA, bz], [bx, SEA, bz], [bx, SEA, az],
                    shade(0x17303f, t * 0.04 + gl));
      }
    }

    // ---- walls, kerbs, the fence -------------------------------------------
    // The rail is a zero-thickness wall on each kerb. Its road face is wrapped
    // here, three centimetres inboard so it wins the depth test, in each
    // section's colour; the back stays the rail's bare concrete.
    const zoneOf = (i) => {
      const f = frac(i);
      for (const z of ZONES) if (f >= z[0] && f < z[1]) return z;
      return ZONES[0];
    };
    const edge = (i, side, o, y) => {
      const e = line[i];
      return [e.p[0] + e.lat[0] * side * (e.hw + o), e.p[1] + y + e.lat[1] * side * (e.hw + o),
              e.p[2] + e.lat[2] * side * (e.hw + o)];
    };
    const RAIL = 1.15;
    // **How far anything laid on the road or the rail stands off it.** The
    // engine's kerb stripe is 0.05 over the road and the rail is a quad on the
    // road edge, so paint at 0.05 and a wrap 3 cm inboard fought them for the
    // depth buffer and shimmered as you drove. At a camera near plane of 0.4
    // that needs about a tenth of a unit to hold at 800 units out.
    const PAINT = 0.12, WRAP = 0.14;
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      const z = zoneOf(i);
      for (const side of [-1, 1]) {
        let c = side < 0 ? z[2] : z[3];
        // Plain concrete stretches on the avenue, where the onboard has them.
        if (c === YELLOW && side > 0 && inRange(i, 0.19, 0.225)) c = CREAM;
        // Aramco alternates green and blue down its run.
        if (c === AGREEN || c === ABLUE) c = (Math.floor(i / 9) % 2) ? AGREEN : ABLUE;
        const a0 = edge(i, side, -WRAP, 0.0), b0 = edge(j, side, -WRAP, 0.0);
        const a1 = edge(i, side, -WRAP, RAIL * 0.80), b1 = edge(j, side, -WRAP, RAIL * 0.80);
        const a2 = edge(i, side, -WRAP, RAIL + 0.02), b2 = edge(j, side, -WRAP, RAIL + 0.02);
        face2(solid, a0, b0, b1, a1, c);
        face2(solid, a1, b1, b2, a2, ACCENT.get(c) != null && (i % 18) < 9 ? ACCENT.get(c) : shade(c, -0.18));
        // the top of the block
        const t0 = edge(i, side, 0.45, RAIL + 0.02), t1 = edge(j, side, 0.45, RAIL + 0.02);
        face2(solid, a2, b2, t1, t0, 0xbfb8a8);
      }
    }

    // Red and white kerbs at the corners only. The engine's own stripe is the
    // white edge line; these sit a hair above it, wider, at every station with
    // real curvature, and one station either side.
    const curvAt = (i) => {
      const a = fwd(Math.max(0, i - 2)), b = fwd(Math.min(n - 1, i + 2));
      const cr = a[0] * b[2] - a[2] * b[0];
      return cr / 14.0;
    };
    const K = [];
    for (let i = 0; i < n; i++) K.push(Math.abs(curvAt(i)) > 1 / 80 ? 1 : 0);
    for (let i = 0; i < n; i++) {
      if (!(K[i] || K[(i + 1) % n] || K[(i + n - 1) % n])) continue;
      const j = (i + 1) % n;
      const c = (i % 2) ? 0x9e0a0c : 0xcfcdc6;       // authored linear: renders red and white
      for (const side of [-1, 1]) {
        const a0 = edge(i, side, -1.0, PAINT), b0 = edge(j, side, -1.0, PAINT);
        const a1 = edge(i, side, -0.12, PAINT), b1 = edge(j, side, -0.12, PAINT);
        face2(bright, a0, b0, b1, a1, c);
      }
    }

    // The white edge line: thin, a little in from the kerb, everywhere there is
    // no kerb. The engine's own stripe is painted the colour of worn tarmac.
    for (let i = 0; i < n; i++) {
      if (K[i] || K[(i + 1) % n]) continue;
      const j = (i + 1) % n;
      for (const side of [-1, 1]) {
        face2(bright, edge(i, side, -0.66, PAINT), edge(j, side, -0.66, PAINT),
              edge(j, side, -0.48, PAINT), edge(i, side, -0.48, PAINT), 0xc4c4be);
      }
    }

    // Dashed lane lines on the wide streets: these are city roads, and the
    // markings are in every frame of the onboard.
    for (let i = 0; i < n - 2; i++) {
      const e = line[i];
      if (e.hw < 6.4 || K[i] || (i % 4) > 1) continue;
      const j = i + 1;
      for (const u of [-0.34, 0.34]) {
        const w = 0.09;
        const P = (k, du) => { const s = line[k]; return [s.p[0] + s.lat[0] * s.hw * u + s.lat[0] * du, s.p[1] + PAINT,
                                                          s.p[2] + s.lat[2] * s.hw * u + s.lat[2] * du]; };
        face2(bright, P(i, -w), P(j, -w), P(j, w), P(i, w), 0xb4b4ae);
      }
    }

    // The catch fence: posts leaning in at the top, a top rail, and wires.
    // Galvanised grey. Posts every other station, which is about four metres.
    const FEN = 3.2, POSTC = 0x6a7076, WIREC = 0x8e949a;
    for (let i = 0; i < n; i += 2) {
      const j = (i + 2) % n;
      for (const side of [-1, 1]) {
        const base = edge(i, side, 0.25, RAIL), top = edge(i, side, 0.25, RAIL + FEN);
        const lean = edge(i, side, -0.35, RAIL + FEN + 0.55);
        rod(solid, base, top, 0.07, POSTC);
        rod(solid, top, lean, 0.06, POSTC);
        const nb = edge(j, side, 0.25, RAIL), ntop = edge(j, side, 0.25, RAIL + FEN);
        // Four rails and no mesh. Hairline wires a pixel wide alias into a
        // crawling shimmer at speed; four that are a few pixels wide read as a
        // fence and hold still.
        for (let w = 1; w <= 4; w++) {
          const t = w / 4;
          const a = lerp3(base, top, t), b = lerp3(nb, ntop, t);
          strip(solid, a, b, w === 4 ? 0.06 : 0.035, w === 4 ? POSTC : WIREC);
        }
      }
    }

    // ---- the Drive hoardings, now and then ---------------------------------
    // Mostly the walls are blank; every so often one of the game's own boards
    // is hung on the fence above them, which is where Baku hangs its banners.
    const BOARDS = ['DRIVE', 'CGOVIND.COM', 'CONDUCTOR', 'KING OF TOKYO', 'RAT SCREW',
                    'GO BIRDS', 'TACO BELL', 'MARLBORO', 'COSTCO WHOLESALE', 'PENN ENGINEERING'];
    let nb = 0;
    for (let i = 20; i < n - 8; i += 47) {
      if (K[i] || K[i + 4]) continue;
      const side = (nb % 2) ? 1 : -1;
      const a = edge(i, side, 0.3, RAIL + 2.6), b = edge(i + 4, side, 0.3, RAIL + 2.6);
      const rx = b[0] - a[0], rz = b[2] - a[2], L = Math.hypot(rx, rz);
      if (L < 8) continue;
      const hw = Math.min(3.4, L * 0.28), hh = hw / 4;
      const r = right(i);
      signs.push({ text: BOARDS[nb % BOARDS.length],
                   c: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + hh, (a[2] + b[2]) / 2],
                   r: [rx / L, 0, rz / L], u: [0, 1, 0], hw, hh,
                   n: [-r[0] * side, 0, -r[2] * side] });
      nb++;
    }

    // ---- keep-out for the landmarks ----------------------------------------
    const keep = [];
    const kept = (x, z, half) => keep.some((k) => Math.abs(x - k[0]) < k[2] + half && Math.abs(z - k[1]) < k[3] + half);

    // ---- Government House and the pits -------------------------------------
    // Behind the pit building on the left of the start straight, which is how
    // it stands in every photograph of the grid: a sandstone palace with a
    // tall arcaded centre tower and pinnacled corner towers.
    {
      const i = idx(0.962), f = fwd(i), r = right(i);
      const o = line[i].hw + 62;
      const cx = line[i].p[0] - r[0] * o, cz = line[i].p[2] - r[2] * o;
      const gy = fieldAt(cx, cz);
      const b0 = [-r[0], 0, -r[2]];
      if (clearBox(cx + b0[0] * 4, cz + b0[2] * 4, f, b0, 57, 34, 8)) {
        govHouse(cx, gy, cz, f, b0);
        keep.push([cx, cz, 70, 70]);
      }
    }
    {
      // The pit building: two long storeys, white with a dark glazed top, from
      // before the line to past it.
      const a = idx(0.915), b = n - 1;
      for (let i = a; i < b; i += 3) {
        const f = fwd(i), r = right(i), e = line[i];
        const o = e.hw + 12;
        const cx = e.p[0] - r[0] * o, cz = e.p[2] - r[2] * o;
        if (toRoad(cx, cz) < 5.5) continue;
        const gy = fieldAt(cx, cz);
        obox(solid, cx, gy + 3.2, cz, f, r, 5.4, 6, 3.2, 0xe4e4e0);
        obox(bright, cx, gy + 7.4, cz, f, r, 5.4, 6.05, 1.1, 0x1a2b3a);
        for (const u of [-3.6, -1.8, 0, 1.8, 3.6]) {
          obox(solid, cx + f[0] * u, gy + 7.4, cz + f[2] * u, f, r, 0.08, 6.1, 1.1, 0xf0f0ec);
        }
        obox(solid, cx, gy + 8.9, cz, f, r, 5.5, 6.8, 0.4, 0xf2f2ee);
        obox(solid, cx, gy + 6.15, cz, f, r, 5.45, 6.1, 0.15, 0x6a1c36);
        // garage doors on the road face
        const dx = cx + r[0] * 6.08, dz = cz + r[2] * 6.08;
        obox(bright, dx, gy + 1.8, dz, f, r, 2.0, 0.04, 1.8, 0x0e1216);
        keep.push([cx, cz, 9, 9]);
      }
    }

    // ---- grandstands ----------------------------------------------------------
    // Off the aerials and the 2018 walk: open steel stands, seats in a mosaic
    // of bright colours rather than one, and packed on race day.
    stand(0.930, 0.995, 1, 12);   // opposite the pits
    stand(0.024, 0.052, 1, 9);    // Turn 1
    stand(0.426, 0.438, 1, 7);    // Turn 8, outside the castle
    stand(0.648, 0.700, 1, 11);   // Turn 16, facing the Four Seasons
    stand(0.300, 0.318, 1, 7);    // Turn 5

    // ---- the Old City wall and the bastion at Turn 8 ------------------------
    // On the inside of the castle section, right behind the fence: rough grey
    // limestone ten metres high with square merlons and a round tower every
    // thirty metres or so. In the onboard the bastion at Turn 8 fills the left
    // of the frame.
    {
      const a = idx(0.436), b = idx(0.478);
      let last = -99;
      for (let i = a; i < b; i++) {
        const e = line[i], s = line[i + 1];
        const o = e.hw + 1.9, o2 = s.hw + 1.9;
        const r = right(i), r2 = right(i + 1);
        const p = [e.p[0] - r[0] * o, e.p[2] - r[2] * o], q = [s.p[0] - r2[0] * o2, s.p[2] - r2[2] * o2];
        const g0 = Math.min(fieldAt(p[0], p[1]), e.p[1] - 1.2), g1 = Math.min(fieldAt(q[0], q[1]), s.p[1] - 1.2);
        const WH = 10.5 + (e.p[1] - line[a].p[1]) * 0.0;
        const c = shade(0xb9a07a, (rWall() - 0.5) * 0.10);
        // the wall as a slab two units thick
        const t = 2.2;
        const p2 = [p[0] - r[0] * t, p[1] - r[2] * t], q2 = [q[0] - r2[0] * t, q[1] - r2[2] * t];
        // the face as courses of blocks, each its own shade: rough limestone
        for (let k = 0; k < 7; k++) for (let h2 = 0; h2 < 2; h2++) {
          const ta = (h2 + (k % 2) * 0.5) / 2, tb = Math.min(1, ta + 0.5);
          const ya = k * WH / 7, yb = (k + 1) * WH / 7;
          const A = [p[0] + (q[0] - p[0]) * ta, g0 + (g1 - g0) * ta, p[1] + (q[1] - p[1]) * ta];
          const B = [p[0] + (q[0] - p[0]) * tb, g0 + (g1 - g0) * tb, p[1] + (q[1] - p[1]) * tb];
          face2(solid, [A[0], A[1] + ya, A[2]], [B[0], B[1] + ya, B[2]], [B[0], B[1] + yb, B[2]], [A[0], A[1] + yb, A[2]],
                shade(c, (rWall() - 0.5) * 0.16 - (k === 0 ? 0.08 : 0)));
          if (ta > 0 && k % 2 === 1 && h2 === 0) {
            const A0 = [p[0] + (q[0] - p[0]) * 0, g0, p[1] + (q[1] - p[1]) * 0];
            face2(solid, [A0[0], A0[1] + ya, A0[2]], [A[0], A[1] + ya, A[2]], [A[0], A[1] + yb, A[2]], [A0[0], A0[1] + yb, A0[2]],
                  shade(c, (rWall() - 0.5) * 0.16));
          }
        }
        face2(solid, [p[0], g0 + WH, p[1]], [q[0], g1 + WH, q[1]], [q2[0], g1 + WH, q2[1]], [p2[0], g0 + WH, p2[1]], shade(c, 0.05));
        // stone courses: faint darker bands, which are what make it masonry
        for (let k = 1; k < 7; k++) {
          const y0 = g0 + k * 1.5, y1 = g1 + k * 1.5;
          face2(solid, [p[0] + r[0] * 0.03, y0, p[1] + r[2] * 0.03], [q[0] + r2[0] * 0.03, y1, q[1] + r2[2] * 0.03],
                [q[0] + r2[0] * 0.03, y1 + 0.12, q[1] + r2[2] * 0.03], [p[0] + r[0] * 0.03, y0 + 0.12, p[1] + r[2] * 0.03],
                shade(c, -0.16));
        }
        // merlons, one per station on the road face
        if (i % 1 === 0) {
          const mx = (p[0] + q[0]) / 2 - r[0] * 0.6, mz = (p[1] + q[1]) / 2 - r[2] * 0.6;
          obox(solid, mx, (g0 + g1) / 2 + WH + 0.75, mz, fwd(i), r, 0.85, 0.6, 0.75, shade(c, 0.03));
        }
        // a round tower every nine stations, and the big one at the apex
        if (i - last >= 9) {
          last = i;
          const big = Math.abs(i - idx(F.t8)) < 5;
          const R = big ? 5.2 : 3.4, TH = big ? 15.5 : 13;
          const tx = p[0] - r[0] * (R - 0.8), tz = p[1] - r[2] * (R - 0.8);
          tower(tx, g0, tz, R, TH, c);
        }
        keep.push([p[0], p[1], 6, 6]);
      }
    }

    // ---- the Maiden Tower ------------------------------------------------------
    // In the Old City, near its seaward corner: a squat cylinder of grey-buff
    // stone with the buttress down one side, horizontal courses all the way up.
    {
      const i = idx(0.664), e = line[i], r = right(i);
      const o = e.hw + 48;
      const cx = e.p[0] - r[0] * o, cz = e.p[2] - r[2] * o;
      const gy = fieldAt(cx, cz);
      if (clearBox(cx, cz, fwd(i), r, 12, 9, 5)) {
        maiden(cx, gy, cz, fwd(i), r);
        keep.push([cx, cz, 16, 16]);
      }
    }

    // ---- the Four Seasons, at Turn 16 -----------------------------------------
    {
      const i = idx(0.690), e = line[i], f = fwd(i), r = right(i);
      const o = e.hw + 26;
      let cx = e.p[0] - r[0] * o, cz = e.p[2] - r[2] * o;
      // walk it back from the road until the whole footprint clears
      for (let k = 0; k < 12 && !clearBox(cx, cz, f, r, 25, 15, 6); k++) { cx -= r[0] * 6; cz -= r[2] * 6; }
      const gy = fieldAt(cx, cz);
      if (clearBox(cx, cz, f, r, 25, 15, 6) && clearBox(cx, cz, f, r, 5, 5, 6)) {
        fourSeasons(cx, gy, cz, f, [-r[0], 0, -r[2]]);
        keep.push([cx, cz, 30, 30]);
      }
    }

    // ---- the Hilton and the Port Baku towers, by Turn 1 --------------------
    {
      const i = idx(0.018), e = line[i], f = fwd(i), r = right(i);
      const cx = e.p[0] - r[0] * (e.hw + 70), cz = e.p[2] - r[2] * (e.hw + 70);
      if (clearBox(cx, cz, f, r, 16, 10, 6)) {
        glassTower(cx, fieldAt(cx, cz), cz, f, r, 15, 9, 64, 0x2f5f9e, true);
        keep.push([cx, cz, 18, 18]);
      }
      const specs = [[0.060, 1, 90, 12, 12, 88], [0.075, 1, 130, 10, 14, 104], [0.050, -1, 160, 14, 10, 74]];
      for (const sp of specs) {
        const k = idx(sp[0]), ee = line[k], rr = right(k);
        const px = ee.p[0] + rr[0] * sp[1] * sp[2], pz = ee.p[2] + rr[2] * sp[1] * sp[2];
        if (!clearBox(px, pz, fwd(k), rr, sp[3] + 1, sp[4] + 1, 6) || isWet(px, pz)) continue;
        glassTower(px, fieldAt(px, pz), pz, fwd(k), rr, sp[3], sp[4], sp[5], 0x5d7f99, false);
        keep.push([px, pz, 18, 18]);
      }
    }

    // ---- the Flame Towers and the TV tower, on the hill ----------------------
    // West of the Old City, up on the ridge above the bay: three curved glass
    // flames, the tallest thing in any view of Baku, and the red-and-white TV
    // mast further along the same ridge.
    {
      // **Each hill is walked away from the circuit until its whole footprint
      // clears the road.** They were placed off the bounding box, and the lobe's
      // west edge ran straight through two of them: after CP5 the road dived
      // under a hillside, a brown ceiling and then a wall.
      const W = [-1, 0, 0.35];                 // west, a little north: the ridge
      const wm = Math.hypot(W[0], W[2]);
      const clearHill = (x, z, R) => {
        for (const e of line) if (Math.hypot(e.p[0] - x, e.p[2] - z) < R + 30) return false;
        return true;
      };
      const siteHill = (x, z, R) => {
        for (let k = 0; k < 60 && !clearHill(x, z, R); k++) { x += W[0] / wm * 15; z += W[2] / wm * 15; }
        return [x, z];
      };
      const eL = line[idx(0.60)];
      const [hx, hz] = siteHill(bbox.x0 - 110, eL.p[2] + 150, 260);
      hill(hx, hz, 260, 58);
      const top = SEA + 58 + 4;
      flame(hx - 26, top, hz - 18, 12, 112, 0.0);
      flame(hx + 22, top, hz - 8, 11, 98, 2.1);
      flame(hx - 2, top, hz + 26, 11.5, 104, 4.2);
      const [mx, mz] = siteHill(hx - 180, hz + 260, 220);
      hill(mx, mz, 220, 50);
      mast(mx, SEA + 50 + 2, mz, 150);
      for (const [dx, dz, R, h] of [[60, -360, 300, 44], [-140, -120, 240, 40]]) {
        const [px, pz] = siteHill(hx + dx, hz + dz, R);
        hill(px, pz, R, h);
      }
    }

    // ---- the city -------------------------------------------------------------
    // Filled on a lattice over the whole ground, not dealt along the road: the
    // first pass placed four ranks off the ribbon and the plan view showed what
    // that is - a street of buildings with sand behind it, and the inside of the
    // lobe, which is the Old City, almost empty. Baku's centre is solid blocks.
    //
    // Each block is squared to the nearest road and textured on any face that
    // looks at a road within reach; the rest are plain stone with a dark band
    // per storey, which is all anybody sees of them past the first row.
    //
    // The Old City is the inside of the lobe nearest the castle and Turn 16:
    // small ochre houses packed on a tight lattice, two and three storeys.
    const lobe = [];
    for (let i = idx(F.t7); i <= idx(F.t16 + 0.02); i += 4) lobe.push([line[i].p[0], line[i].p[2]]);
    const inLobe = (x, z) => {
      let c = false;
      for (let a = 0, b = lobe.length - 1; a < lobe.length; b = a++) {
        const [xa, za] = lobe[a], [xb, zb] = lobe[b];
        if ((za > z) !== (zb > z) && x < (xb - xa) * (z - za) / (zb - za) + xa) c = !c;
      }
      return c;
    };
    const blocks = [];
    const place = (px, pz, w, d, floors, style, old) => {
      const half = Math.max(w, d) / 2;
      if (px < x0 + half + 6 || px > x1 - half - 6 || pz < z0 + half + 6 || pz > z1 - half - 6) return;
      if (isWet(px, pz) || kept(px, pz, half)) return;
      const q = cellOf(px, pz);
      const ni = q >= 0 ? NI[q] : -1;
      if (ni < 0) return;
      if (seafront(ni) && sideOf(ni, px, pz) > 0) return;          // the park
      // squared to the nearest road
      const f = fwd(ni), r = right(ni), side = sideOf(ni, px, pz) >= 0 ? 1 : -1;
      if (toRoad(px, pz) < 5.5 + half || !clearBox(px, pz, f, r, w / 2 + 1, d / 2 + 1, 5)) return;
      const gy = fieldAt(px, pz);
      const near = DR[q] - line[ni].hw - half < 40;
      blocks.push([px, pz, half]);
      building(px, gy, pz, f, r, side, w, d, floors, style, near, old);
    };
    const LAT = 27;
    for (let gx = x0 + 20; gx < x1 - 20; gx += LAT) {
      for (let gz = z0 + 20; gz < z1 - 20; gz += LAT) {
        const px = gx + (rCity() - 0.5) * 6, pz = gz + (rCity() - 0.5) * 6;
        const q = cellOf(px, pz);
        if (q < 0) continue;
        const far = DR[q];
        if (far > 330 && rCity() < 0.5) continue;
        if (rCity() < 0.10) continue;                                   // squares, courtyards
        const ni = NI[q];
        const old = ni >= 0 && inLobe(px, pz) && (lobeOld(ni) || far < 70) && sideOf(ni, px, pz) < 0 &&
                    (inRange(ni, F.t7, F.t12 + 0.02) || inRange(ni, F.t15, F.t16 + 0.03));
        if (old) {
          // four little houses to one lattice cell
          for (const [du, dv] of [[-6.5, -6.5], [6.5, -6.5], [-6.5, 6.5], [6.5, 6.5]]) {
            if (rCity() < 0.15) continue;
            place(px + du, pz + dv, 7 + rCity() * 4, 7 + rCity() * 4, 2 + Math.floor(rCity() * 2), 'ochre', true);
          }
          continue;
        }
        const tall = far > 120 && rCity() < 0.12;
        const floors = tall ? 10 + Math.floor(rCity() * 10) : 4 + Math.floor(rCity() * 4) + (far > 80 ? 1 : 0);
        place(px, pz, 14 + rCity() * 9, 12 + rCity() * 9, floors,
              tall ? 'cream' : STYLES[Math.floor(rCity() * STYLES.length)], false);
      }
    }

    // ---- trees ----------------------------------------------------------------
    // Plane trees down the avenues, pine and cypress in the boulevard park.
    for (let i = 1; i < n; i += 3) {
      const e = line[i];
      for (const side of [-1, 1]) {
        const park = side > 0 && seafront(i);
        const avenue = inRange(i, F.t2, F.t3) || inRange(i, F.t13, F.t15) || inRange(i, F.t4, F.t7);
        if (!park && !avenue && rTree() > 0.25) continue;
        const reps = park ? 3 : 1;
        for (let k = 0; k < reps; k++) {
          const o = park ? e.hw + 6 + rTree() * (PARK - 12) : e.hw + 3.2 + rTree() * 2.5;
          const [px, pz] = off(i, side, o);
          if (isWet(px, pz) || kept(px, pz, 3)) continue;
          if (toRoad(px, pz) < 2.8) continue;
          if (blocks.some((b) => Math.hypot(b[0] - px, b[1] - pz) < b[2] + 2)) continue;
          const gy = fieldAt(px, pz);
          if (park) {
            const t = rTree();
            if (t < 0.45) pine(px, gy, pz, 8 + rTree() * 5);
            else if (t < 0.75) cypress(px, gy, pz, 9 + rTree() * 6);
            else plane(px, gy, pz, 8 + rTree() * 4);
          } else plane(px, gy, pz, 8 + rTree() * 5);
        }
      }
    }

    // ---- the boulevard: promenade, sea wall, lamps, flags, the Baku Eye --------
    for (let i = 0; i < n; i += 2) {
      if (!seafront(i)) continue;
      const e = line[i], r = right(i), f = fwd(i);
      // the sea wall and its railing, at the edge of the park
      const [wx, wz] = off(i, 1, PARK - 2);
      if (!isWet(wx + r[0] * 10, wz + r[2] * 10)) continue;
      const gy = fieldAt(wx - r[0] * 6, wz - r[2] * 6);
      obox(solid, wx, (gy + SEA) / 2, wz, f, r, 3.6, 1.0, (gy - SEA) / 2 + 0.3, 0xb3a78f);
      obox(solid, wx, gy + 0.9, wz, f, r, 3.6, 0.08, 0.05, 0x2a2a2c);
      if (i % 6 === 0) {
        solid.box(wx, gy + 0.5, wz, 0.14, 0.5, 0.14, 0xc9bda2);
        lamp(wx - r[0] * 4, gy, wz - r[2] * 4);
      }
    }
    // the row of flags along the boulevard, where they stand in the onboard
    for (let i = idx(0.835); i < idx(0.862); i += 3) {
      const e = line[i], r = right(i), f = fwd(i);
      const [px, pz] = off(i, 1, e.hw + 3.6);
      const gy = fieldAt(px, pz);
      solid.box(px, gy + 5.5, pz, 0.12, 5.5, 0.12, 0xe6e6e2);
      azFlag(px + f[0] * 1.6, gy + 9.4, pz + f[2] * 1.6, f, r, 1.6, 1.05);
    }
    {
      const i = idx(0.845), [px, pz] = off(i, 1, PARK - 20);
      if (!isWet(px, pz)) ferris(px, fieldAt(px, pz), pz, fwd(i), right(i));
    }

    // ---- street lamps -----------------------------------------------------------
    // Baku's black-and-gold three-globe lamps, on the pavement behind the fence.
    for (let i = 5; i < n; i += 10) {
      for (const side of [-1, 1]) {
        if (side > 0 && seafront(i)) continue;
        const [px, pz] = off(i, side, line[i].hw + 2.3);
        if (kept(px, pz, 1)) continue;
        lamp(px, Math.min(fieldAt(px, pz), line[i].p[1] - DROP), pz);
      }
    }

    // ---- big screens --------------------------------------------------------
    for (const [fr, side, o] of [[0.012, 1, 22], [0.684, 1, 32], [0.465, 1, 16], [0.905, 1, 20]]) {
      const i = idx(fr), [px, pz] = off(i, side, line[i].hw + o);
      screen(px, fieldAt(px, pz), pz, fwd(i), right(i), side);
    }

    // =====================================================================
    // builders

    function building(px, gy, pz, f, r, side, w, d, floors, style, textured, old) {
      // `w` along the road, `d` back from it.
      const h = floors * SH;
      const wall = shade(WALLC[Math.floor(rCity() * WALLC.length)], (rCity() - 0.5) * 0.06);
      obox(solid, px, gy + h / 2, pz, f, r, w / 2, d / 2, h / 2, old ? shade(0xc7ad7d, (rCity() - 0.5) * 0.08) : wall);
      // cornice and parapet
      obox(solid, px, gy + h + 0.25, pz, f, r, w / 2 + 0.35, d / 2 + 0.35, 0.25, shade(wall, 0.12));
      obox(solid, px, gy + h + 0.95, pz, f, r, w / 2, d / 2, 0.45, shade(wall, -0.06));
      // a domed corner turret on the grand ones, on the road corner
      if (!old && floors >= 5 && rCity() > 0.55) {
        const cx = px - r[0] * side * (d / 2 - 2.6) + f[0] * (w / 2 - 2.6) * (rCity() > 0.5 ? 1 : -1);
        const cz = pz - r[2] * side * (d / 2 - 2.6) + f[2] * (w / 2 - 2.6) * (rCity() > 0.5 ? 1 : -1);
        solid.box(cx, gy + h + 2.2, cz, 2.2, 2.2, 2.2, shade(wall, 0.05));
        dome(cx, gy + h + 4.4, cz, 2.5, 3.2, rCity() > 0.5 ? 0x53806e : 0x6f6a64);
      }
      if (old && rCity() > 0.6) solid.box(px, gy + h + 0.1, pz, w / 2 - 0.4, 0.12, d / 2 - 0.4, 0x6b5a48);
      if (!textured) {
        // back ranks: one dark reveal per storey is enough at that distance
        for (let k = 1; k < floors; k++) {
          obox(bright, px, gy + k * SH + 1.6, pz, f, r, w / 2 + 0.03, d / 2 + 0.03, 0.55, 0x121416);
        }
        return;
      }
      // The four faces: toward the road, away, and the two ends. Only the faces
      // that look at the road are textured; that is what anyone sees.
      const faces = [
        [[-r[0] * side, 0, -r[2] * side], d / 2, w, f],
        [[f[0], 0, f[2]], w / 2, d, r],
        [[-f[0], 0, -f[2]], w / 2, d, r],
      ];
      for (const [nrm, reach, width, along] of faces) {
        const cx = px + nrm[0] * (reach + 0.05), cz = pz + nrm[2] * (reach + 0.05);
        // does this face look at a road near it?
        if (toRoad(cx + nrm[0] * 18, cz + nrm[2] * 18) > toRoad(cx, cz) + 4) continue;
        const lit = nrm[0] * LX + nrm[2] * LZ > 0.08 ? 'lit' : 'shade';
        const m = Math.max(1, Math.round(width / 12.5));
        const mw = width / m;
        for (let k = 0; k < floors; k++) {
          const kind = k === 0 ? 'g' : k === floors - 1 ? 't' : 'm';
          for (let s = 0; s < m; s++) {
            const t = -width / 2 + mw * (s + 0.5);
            signs.push({ art: ART + style + '-' + kind + '-' + lit + '.png', aspect: 4,
                         c: [cx + along[0] * t, gy + k * SH + SH / 2, cz + along[2] * t],
                         r: [along[0], 0, along[2]], u: [0, 1, 0], hw: mw / 2, hh: SH / 2, n: nrm });
          }
        }
      }
    }

    function govHouse(cx, gy, cz, f, back) {
      // `back` points away from the road. A U: the front range along the road,
      // two wings running back, a tall centre tower, four corner towers.
      const S = 0xd8c194;
      const lat = [back[0], 0, back[2]];
      const at = (u, v) => [cx + f[0] * u + lat[0] * v, cz + f[2] * u + lat[2] * v];
      const blk = (u, v, hu, hv, h, c) => { const p = at(u, v); obox(solid, p[0], gy + h / 2, p[1], f, lat, hu, hv, h / 2, c); };
      blk(0, -18, 56, 11, 26, S);
      blk(-47, 12, 9, 26, 24, shade(S, -0.03));
      blk(47, 12, 9, 26, 24, shade(S, -0.03));
      blk(0, -20, 11, 12, 40, shade(S, 0.04));      // centre tower
      blk(0, -20, 8, 9, 48, shade(S, 0.06));
      for (const u of [-52, 52]) {
        blk(u, -22, 6, 6, 34, shade(S, 0.03));
        for (const du of [-4.5, 4.5]) for (const dv of [-4.5, 4.5]) {
          const p = at(u + du, -22 + dv); solid.box(p[0], gy + 36.5, p[1], 0.5, 2.5, 0.5, shade(S, 0.08));
        }
      }
      // pinnacles along the parapet, which is what gives it that crenellated look
      for (let u = -54; u <= 54; u += 6) {
        const p = at(u, -29.2); solid.box(p[0], gy + 27.2, p[1], 0.45, 1.2, 0.45, shade(S, 0.07));
      }
      // the arcade: tall dark arches across the front, ground and centre tower
      for (let u = -50; u <= 50; u += 5) {
        const p = at(u, -29.1);
        obox(bright, p[0], gy + 4.2, p[1], f, lat, 1.5, 0.05, 3.4, 0x0f1216);
        for (let k = 1; k < 5; k++) obox(bright, p[0], gy + 8 + k * 4.2, p[1], f, lat, 0.9, 0.05, 1.3, 0x151a20);
      }
      for (let k = 0; k < 4; k++) {
        const p = at(0, -32.1);
        obox(bright, p[0], gy + 29 + k * 4.5, p[1], f, lat, 3.2, 0.05, 1.6, 0x10141a);
      }
      // the flag on the tower
      const p = at(0, -20);
      solid.box(p[0], gy + 52, p[1], 0.14, 4, 0.14, 0xe0e0dc);
      azFlag(p[0] + f[0] * 1.8, gy + 54.5, p[1] + f[2] * 1.8, f, lat, 1.8, 1.2);
    }

    function stand(fa, fb, side, tiers) {
      const a = idx(fa), b = idx(fb), mine = [];
      for (let i = a; i < b; i += 2) {
        const e = line[i], f = fwd(i), r = right(i);
        const base = e.hw + 3.0;
        for (let t = 0; t < tiers; t++) {
          const o = base + t * 1.25;
          const [px, pz] = off(i, side, o + 0.6);
          if (toRoad(px, pz) < 2.4 || kept(px, pz, 1)) break;
          const gy = Math.min(fieldAt(px, pz), e.p[1] - DROP);
          const y = gy + 0.9 + t * 0.8;
          obox(solid, px, y - 0.4, pz, f, r, 3.6, 0.62, 0.4, 0x8a8e94);
          // seats: a mosaic of colours, three blocks per station
          for (let s = -1; s <= 1; s++) {
            const sx = px + f[0] * s * 2.4, sz = pz + f[2] * s * 2.4;
            const c = SEATS[Math.floor(rSeat() * SEATS.length)];
            obox(solid, sx, y + 0.25, sz, f, r, 1.15, 0.3, 0.25, c);
            // people, most of them
            if (rSeat() < 0.78) {
              const pc = [0xe8e2d6, 0x2a2c33, 0xc0392b, 0x2e6fb0, 0xf2c14e, 0x3a8a4a, 0x7a4a2a][Math.floor(rSeat() * 7)];
              obox(solid, sx + f[0] * (rSeat() - 0.5), y + 0.95, sz + f[2] * (rSeat() - 0.5), f, r, 0.9, 0.22, 0.45, pc);
            }
          }
          if (t === tiers - 1) {
            const [bx, bz] = off(i, side, o + 1.4);
            obox(solid, bx, (gy + y + 2.4) / 2, bz, f, r, 3.6, 0.12, (y + 2.4 - gy) / 2, 0x6c7178);
          }
        }
        // the scaffold under it, seen from the side
        const [ux, uz] = off(i, side, base + tiers * 0.62);
        const gy = fieldAt(ux, uz);
        solid.box(ux, gy + tiers * 0.4, uz, 0.12, tiers * 0.4, 0.12, 0x5b6068);
        mine.push([ux, uz, tiers * 0.7 + 3, tiers * 0.7 + 3]);
      }
      // Registered only once the whole stand is up: pushed per bay, each bay's
      // box swallowed the next one and every stand stopped after its first.
      keep.push(...mine);
    }

    function tower(x, gy, z, R, TH, c) {
      const N = 14;
      for (let k = 0; k < N; k++) {
        const a0 = (k / N) * Math.PI * 2, a1 = ((k + 1) / N) * Math.PI * 2;
        const p0 = [x + Math.cos(a0) * R, z + Math.sin(a0) * R], p1 = [x + Math.cos(a1) * R, z + Math.sin(a1) * R];
        const cc = shade(c, (rWall() - 0.5) * 0.08 + Math.cos((a0 + a1) / 2 - Math.atan2(LZ, LX)) * 0.04);
        face2(solid, [p0[0], gy, p0[1]], [p1[0], gy, p1[1]], [p1[0], gy + TH, p1[1]], [p0[0], gy + TH, p0[1]], cc);
        if (k % 2 === 0) obox(solid, (p0[0] + p1[0]) / 2, gy + TH + 0.7, (p0[1] + p1[1]) / 2,
                              [Math.cos((a0 + a1) / 2 + Math.PI / 2), 0, Math.sin((a0 + a1) / 2 + Math.PI / 2)],
                              [Math.cos((a0 + a1) / 2), 0, Math.sin((a0 + a1) / 2)], 0.8, 0.5, 0.7, shade(c, 0.04));
        for (let s = 1; s < TH / 1.6; s++) {
          face2(solid, [p0[0] + Math.cos(a0) * 0.03, gy + s * 1.6, p0[1] + Math.sin(a0) * 0.03],
                [p1[0] + Math.cos(a1) * 0.03, gy + s * 1.6, p1[1] + Math.sin(a1) * 0.03],
                [p1[0] + Math.cos(a1) * 0.03, gy + s * 1.6 + 0.12, p1[1] + Math.sin(a1) * 0.03],
                [p0[0] + Math.cos(a0) * 0.03, gy + s * 1.6 + 0.12, p0[1] + Math.sin(a0) * 0.03], shade(c, -0.15));
        }
      }
      disc(solid, x, gy + TH, z, R, shade(c, 0.06));
    }

    function maiden(x, gy, z, f, r) {
      const c = 0xa89a82, R = 7.2, TH = 24;
      tower(x, gy, z, R, TH, c);
      // the buttress: a tall wedge on one side, as tall as the tower
      obox(solid, x + f[0] * (R + 1.2), gy + TH / 2 - 0.5, z + f[2] * (R + 1.2), f, r, 3.2, 3.6, TH / 2 - 0.5, shade(c, -0.04));
      solid.box(x, gy + TH + 1.4, z, 0.12, 1.4, 0.12, 0x444444);
    }

    function fourSeasons(cx, gy, cz, f, back) {
      const S = 0xe0cfa8, ROOF = 0x4f8a7a;
      const lat = back;
      const at = (u, v) => [cx + f[0] * u + lat[0] * v, cz + f[2] * u + lat[2] * v];
      let p = at(0, 0);
      obox(solid, p[0], gy + 15, p[1], f, lat, 24, 14, 15, S);
      // the arcade at the foot and the storeys over it
      for (let u = -21; u <= 21; u += 4.2) {
        const q = at(u, -14.06);
        obox(bright, q[0], gy + 3.2, q[1], f, lat, 1.4, 0.05, 2.4, 0x14181c);
        for (let k = 0; k < 5; k++) obox(bright, q[0], gy + 8.2 + k * 3.8, q[1], f, lat, 0.8, 0.05, 1.2, 0x1a2026);
      }
      // mansard in oxidised copper, and the corner domes
      obox(solid, p[0], gy + 31.5, p[1], f, lat, 23, 13, 1.5, ROOF);
      obox(solid, p[0], gy + 33.6, p[1], f, lat, 20, 10, 0.8, shade(ROOF, -0.08));
      for (const u of [-21, 21]) for (const v of [-11, 11]) {
        const q = at(u, v);
        solid.box(q[0], gy + 33, q[1], 3, 3, 3, S);
        dome(q[0], gy + 36, q[1], 3.2, 3.6, ROOF);
        solid.box(q[0], gy + 40.2, q[1], 0.12, 1, 0.12, 0x333333);
      }
      p = at(0, -6);
      dome(p[0], gy + 34.4, p[1], 5, 5.6, ROOF);
    }

    function glassTower(x, gy, z, f, r, hu, hv, h, c, slab) {
      obox(solid, x, gy + h / 2, z, f, r, hu, hv, h / 2, c);
      for (let y = 3.5; y < h; y += 3.5) obox(bright, x, gy + y, z, f, r, hu + 0.04, hv + 0.04, 0.09, 0x3a4e62);
      if (slab) {
        // the Hilton's curved crown
        obox(solid, x, gy + h + 2, z, f, r, hu * 0.7, hv * 0.8, 2, shade(c, 0.1));
      }
    }

    function hill(x, z, R, h) {
      const N = 18, rings = 5;
      for (let k = 0; k < rings; k++) {
        const r0 = R * (1 - k / rings), r1 = R * (1 - (k + 1) / rings);
        const y0 = SEA + h * (k / rings) ** 0.7, y1 = SEA + h * ((k + 1) / rings) ** 0.7;
        for (let s = 0; s < N; s++) {
          const a0 = (s / N) * Math.PI * 2, a1 = ((s + 1) / N) * Math.PI * 2;
          const c = shade(k < 3 ? 0x8f8468 : 0x6f7a52, (rMisc() - 0.5) * 0.08);
          face2(solid, [x + Math.cos(a0) * r0, y0, z + Math.sin(a0) * r0], [x + Math.cos(a1) * r0, y0, z + Math.sin(a1) * r0],
                [x + Math.cos(a1) * r1, y1, z + Math.sin(a1) * r1], [x + Math.cos(a0) * r1, y1, z + Math.sin(a0) * r1], c);
        }
        // houses climbing it: Baku's amphitheatre
        for (let s = 0; s < 14 - k * 2; s++) {
          const a = rMisc() * Math.PI * 2, rr = r1 + (r0 - r1) * rMisc();
          const hx = x + Math.cos(a) * rr, hz = z + Math.sin(a) * rr, hy = SEA + h * ((k + 0.5) / rings) ** 0.7;
          const bw = 5 + rMisc() * 7, bh = 6 + rMisc() * 12;
          solid.box(hx, hy + bh / 2 - 1, hz, bw / 2, bh / 2, bw / 2, shade(WALLC[s % WALLC.length], (rMisc() - 0.5) * 0.12));
        }
      }
    }

    function flame(x, y, z, R, h, rot) {
      // A flame in plan is a rounded triangle; up the tower the section shrinks
      // and slides toward its point, which is what curves the silhouette.
      const N = 12, L = 26;
      const ring = (t) => {
        const s = Math.pow(1 - t, 0.85) * R + 0.4, shift = t * t * R * 0.9;
        const pts = [];
        for (let k = 0; k < N; k++) {
          const a = (k / N) * Math.PI * 2;
          const rr = s * (1 + 0.22 * Math.cos(3 * a));
          const px = Math.cos(a) * rr + shift, pz = Math.sin(a) * rr * 0.86;
          pts.push([x + px * Math.cos(rot) - pz * Math.sin(rot), y + t * h, z + px * Math.sin(rot) + pz * Math.cos(rot)]);
        }
        return pts;
      };
      let prev = ring(0);
      for (let l = 1; l <= L; l++) {
        const t = l / L, cur = ring(Math.min(t, 0.985));
        for (let k = 0; k < N; k++) {
          const a0 = prev[k], a1 = prev[(k + 1) % N], b1 = cur[(k + 1) % N], b0 = cur[k];
          const nx0 = (a0[0] + a1[0]) / 2 - x, nz0 = (a0[2] + a1[2]) / 2 - z;
          const m = Math.hypot(nx0, nz0) || 1;
          const lit = (nx0 * LX + nz0 * LZ) / m;
          const c = shade(0x7394b4, lit * 0.22 + t * 0.12 + ((l % 3) === 0 ? -0.10 : 0));
          face2(solid, a0, a1, b1, b0, c);
        }
        prev = cur;
      }
    }

    function mast(x, y, z, h) {
      for (let k = 0; k < 10; k++) {
        const y0 = y + (k / 10) * h, hh = h / 20, w = 2.2 - k * 0.15;
        solid.box(x, y0 + hh, z, w, hh, w, k % 2 ? 0xd9d6cf : 0xb5362d);
      }
      solid.box(x, y + h * 0.62, z, 4.5, 2.2, 4.5, 0xd9d6cf);
    }

    function lamp(x, gy, z) {
      solid.box(x, gy + 2.7, z, 0.1, 2.7, 0.1, 0x1c1c1f);
      solid.box(x, gy + 0.5, z, 0.2, 0.5, 0.2, 0x1c1c1f);
      solid.box(x, gy + 3.1, z, 0.14, 0.12, 0.14, 0xb08a2a);
      solid.box(x, gy + 5.35, z, 0.75, 0.05, 0.75, 0x1c1c1f);
      for (const [dx, dz] of [[0.7, 0], [-0.7, 0], [0, 0.7], [0, -0.7], [0, 0]]) {
        bright.box(x + dx, gy + 5.75 + (dx === 0 && dz === 0 ? 0.35 : 0), z + dz, 0.26, 0.3, 0.26, 0xb9b1a0);
      }
    }

    function crown(x, y, z, r, hgt, g, k) {
      // A crown as a cluster of faceted lumps round a core, at staggered heights
      // and in two tones. One box per tree read as a green crate, and a stack of
      // boxes as a table; a faceted blob is the cheapest thing that reads as
      // foliage.
      blob(x, y, z, r * 0.85, hgt * 0.75, r * 0.85, g);
      for (let s = 0; s < k; s++) {
        const a = (s / k) * Math.PI * 2 + rTree() * 0.8, rr = r * (0.5 + rTree() * 0.25);
        const sz = r * (0.42 + rTree() * 0.2);
        blob(x + Math.cos(a) * rr, y + (rTree() - 0.35) * hgt * 0.8, z + Math.sin(a) * rr,
             sz, sz * 0.8, sz, shade(g, (rTree() - 0.35) * 0.18));
      }
    }

    function blob(x, y, z, rx, ry, rz, c) {
      const N = 6, lat = [-Math.PI / 2, -0.45, 0.5, Math.PI / 2];
      const P = (a, l) => [x + Math.cos(a) * Math.cos(l) * rx, y + Math.sin(l) * ry, z + Math.sin(a) * Math.cos(l) * rz];
      const ro = rTree() * Math.PI;
      for (let k = 0; k < N; k++) {
        const a0 = ro + (k / N) * Math.PI * 2, a1 = ro + ((k + 1) / N) * Math.PI * 2;
        for (let m = 0; m < 3; m++) {
          const A = P(a0, lat[m]), B = P(a1, lat[m]), C = P(a1, lat[m + 1]), D = P(a0, lat[m + 1]);
          const mx = (A[0] + B[0] + C[0] + D[0]) / 4 - x, my = (A[1] + B[1] + C[1] + D[1]) / 4 - y,
                mz = (A[2] + B[2] + C[2] + D[2]) / 4 - z;
          wound(solid, A, B, C, D, [mx, my, mz], shade(c, m === 2 ? 0.07 : 0));
        }
      }
    }

    function plane(x, gy, z, h) {
      // Plane trees: pale mottled trunk, a fork, and a broad rounded crown.
      solid.box(x, gy + h * 0.3, z, 0.22, h * 0.3, 0.22, 0x9a917c);
      solid.box(x + 0.4, gy + h * 0.55, z, 0.14, h * 0.12, 0.14, 0x8a8170);
      solid.box(x - 0.35, gy + h * 0.55, z + 0.2, 0.14, h * 0.12, 0.14, 0x8a8170);
      const g = shade(0x5b7534, (rTree() - 0.5) * 0.16);
      crown(x, gy + h * 0.76, z, 2.4 + rTree() * 1.1, h * 0.24, g, 4);
    }

    function pine(x, gy, z, h) {
      // The boulevard's stone pines: a bare leaning trunk and a flat dark
      // parasol of a crown made of overlapping lumps.
      const lx = (rTree() - 0.5) * 1.2, lz = (rTree() - 0.5) * 1.2;
      solid.box(x + lx * 0.5, gy + h * 0.4, z + lz * 0.5, 0.24, h * 0.4, 0.24, 0x6a5540);
      const g = shade(0x2d5430, (rTree() - 0.5) * 0.12);
      const r0 = 3.2 + rTree() * 1.6;
      for (let s = 0; s < 5; s++) {
        const a = (s / 5) * Math.PI * 2 + rTree(), rr = s === 0 ? 0 : r0 * 0.55;
        const sz = s === 0 ? r0 * 0.75 : r0 * (0.4 + rTree() * 0.2);
        blob(x + lx + Math.cos(a) * rr, gy + h * 0.88 + rTree() * 0.6, z + lz + Math.sin(a) * rr,
             sz, 0.8 + rTree() * 0.4, sz, shade(g, (rTree() - 0.4) * 0.14));
      }
    }

    function cypress(x, gy, z, h) {
      solid.box(x, gy + 0.6, z, 0.2, 0.6, 0.2, 0x5a4a38);
      const g = shade(0x243f29, (rTree() - 0.5) * 0.1);
      for (let k = 0; k < 5; k++) {
        const t = k / 5, w = 1.05 * (1 - t * 0.75);
        solid.box(x, gy + 1.2 + h * (t + 0.1) * 0.9, z, w, h * 0.11, w, shade(g, (k % 2) * 0.05));
      }
    }

    function azFlag(x, y, z, f, r, hw, hh) {
      // blue over red over green, a white crescent and star in the red
      const b = hh / 3;
      obox(solid, x, y + b, z, f, r, hw, 0.05, b / 2, 0x1b9ed8);
      obox(solid, x, y, z, f, r, hw, 0.05, b / 2, 0xd9263a);
      obox(solid, x, y - b, z, f, r, hw, 0.05, b / 2, 0x3a9e3f);
      obox(bright, x, y, z, f, r, b * 0.22, 0.07, b * 0.3, 0xd6d6d2);
    }

    function ferris(x, gy, z, f, r) {
      // the Baku Eye: a white wheel on the boulevard, square to the sea
      const R = 26, cy = gy + R + 4;
      for (let k = 0; k < 32; k++) {
        const a0 = (k / 32) * Math.PI * 2, a1 = ((k + 1) / 32) * Math.PI * 2;
        const p0 = [x + f[0] * Math.cos(a0) * R, cy + Math.sin(a0) * R, z + f[2] * Math.cos(a0) * R];
        const p1 = [x + f[0] * Math.cos(a1) * R, cy + Math.sin(a1) * R, z + f[2] * Math.cos(a1) * R];
        rod(solid, p0, p1, 0.3, 0xe8e8e4);
        if (k % 4 === 0) {
          rod(solid, [x, cy, z], p0, 0.1, 0xd0d0cc);
          obox(solid, p0[0], p0[1] - 1.4, p0[2], f, r, 1.0, 1.0, 1.0, 0xd8d4c8);
        }
      }
      for (const s of [-1, 1]) {
        rod(solid, [x + f[0] * s * 12, gy, z + f[2] * s * 12], [x, cy, z], 0.5, 0xd0d0cc);
      }
    }

    function screen(x, gy, z, f, r, side) {
      solid.box(x, gy + 5, z, 0.3, 5, 0.3, 0x4a4e55);
      const n = [-r[0] * side, 0, -r[2] * side];
      obox(solid, x, gy + 12, z, f, r, 6.4, 0.3, 3.8, 0x202329);
      obox(bright, x + n[0] * 0.32, gy + 12, z + n[2] * 0.32, f, r, 6.0, 0.02, 3.4, 0x2c3f55);
    }

    function dome(x, y, z, R, h, c) {
      const N = 10;
      for (let k = 0; k < N; k++) {
        const a0 = (k / N) * Math.PI * 2, a1 = ((k + 1) / N) * Math.PI * 2;
        for (let l = 0; l < 3; l++) {
          const t0 = l / 3, t1 = (l + 1) / 3;
          const r0 = R * Math.cos(t0 * Math.PI / 2), r1 = R * Math.cos(t1 * Math.PI / 2);
          const y0 = y + h * Math.sin(t0 * Math.PI / 2), y1 = y + h * Math.sin(t1 * Math.PI / 2);
          face2(solid, [x + Math.cos(a0) * r0, y0, z + Math.sin(a0) * r0], [x + Math.cos(a1) * r0, y0, z + Math.sin(a1) * r0],
                [x + Math.cos(a1) * r1, y1, z + Math.sin(a1) * r1], [x + Math.cos(a0) * r1, y1, z + Math.sin(a0) * r1],
                shade(c, l * 0.06));
        }
      }
    }
  }

  // -- helpers ---------------------------------------------------------------

  /** Chamfer sweep, in place. With `I`, carries the index of whoever won. */
  function sweep(D, I, nx, nz, STEP, DIAG) {
    const upd = (q, p, s) => { if (D[p] + s < D[q]) { D[q] = D[p] + s; if (I) I[q] = I[p]; } };
    for (let i = 0; i < nx; i++) for (let j = 0; j < nz; j++) {
      const q = i * nz + j;
      if (i > 0) upd(q, q - nz, STEP);
      if (j > 0) upd(q, q - 1, STEP);
      if (i > 0 && j > 0) upd(q, q - nz - 1, DIAG);
      if (i > 0 && j < nz - 1) upd(q, q - nz + 1, DIAG);
    }
    for (let i = nx - 1; i >= 0; i--) for (let j = nz - 1; j >= 0; j--) {
      const q = i * nz + j;
      if (i < nx - 1) upd(q, q + nz, STEP);
      if (j < nz - 1) upd(q, q + 1, STEP);
      if (i < nx - 1 && j < nz - 1) upd(q, q + nz + 1, DIAG);
      if (i < nx - 1 && j > 0) upd(q, q + nz - 1, DIAG);
    }
  }

  function lerp3(a, b, t) {
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  }

  /** Both windings, always: see `docs/track-defects.md` on invisible quads. */
  function face2(buf, a, b, c, d, col) {
    buf.quad(a, b, c, d, col);
    buf.quad(d, c, b, a, col);
  }

  /** A flat ribbon from a to b, `w` wide, standing up. For wires and rails. */
  function strip(buf, a, b, w, col) {
    face2(buf, [a[0], a[1] - w, a[2]], [b[0], b[1] - w, b[2]], [b[0], b[1] + w, b[2]], [a[0], a[1] + w, a[2]], col);
  }

  /** A square rod from a to b: two crossed strips, which reads as round. */
  function rod(buf, a, b, w, col) {
    const dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
    const m = Math.hypot(dx, dy, dz) || 1;
    // any vector not parallel to the rod
    const up = Math.abs(dy / m) > 0.9 ? [1, 0, 0] : [0, 1, 0];
    let s = [dy * up[2] - dz * up[1], dz * up[0] - dx * up[2], dx * up[1] - dy * up[0]];
    let sm = Math.hypot(s[0], s[1], s[2]) || 1; s = [s[0] / sm * w, s[1] / sm * w, s[2] / sm * w];
    let t = [(dy * s[2] - dz * s[1]) / m, (dz * s[0] - dx * s[2]) / m, (dx * s[1] - dy * s[0]) / m];
    const P = (p, v, k) => [p[0] + v[0] * k, p[1] + v[1] * k, p[2] + v[2] * k];
    face2(buf, P(a, s, -1), P(b, s, -1), P(b, s, 1), P(a, s, 1), col);
    face2(buf, P(a, t, -1), P(b, t, -1), P(b, t, 1), P(a, t, 1), col);
  }

  function disc(buf, x, y, z, R, col) {
    const N = 14;
    for (let k = 0; k < N; k++) {
      const a0 = (k / N) * Math.PI * 2, a1 = ((k + 1) / N) * Math.PI * 2;
      buf.tri([x, y, z], [x + Math.cos(a1) * R, y, z + Math.sin(a1) * R], [x + Math.cos(a0) * R, y, z + Math.sin(a0) * R], col);
      buf.tri([x, y, z], [x + Math.cos(a0) * R, y, z + Math.sin(a0) * R], [x + Math.cos(a1) * R, y, z + Math.sin(a1) * R], col);
    }
  }

  /** An oriented box, each face wound outward (see Monaco's note on `obox`). */
  function obox(buf, cx, cy, cz, f, lat, hu, hv, hh, c) {
    const P = (su, sv, sh) => [cx + f[0] * su * hu + lat[0] * sv * hv, cy + sh * hh,
                               cz + f[2] * su * hu + lat[2] * sv * hv];
    const a = P(-1, -1, -1), b = P(1, -1, -1), d = P(1, 1, -1), e = P(-1, 1, -1);
    const g = P(-1, -1, 1), h = P(1, -1, 1), i = P(1, 1, 1), j = P(-1, 1, 1);
    const up = [0, 1, 0], neg = (v) => [-v[0], -v[1], -v[2]];
    const L = [lat[0], 0, lat[2]], Fv = [f[0], 0, f[2]];
    const FS = [[[g, h, i, j], up], [[a, e, d, b], neg(up)], [[a, b, h, g], neg(L)], [[e, j, i, d], L],
                [[a, g, j, e], neg(Fv)], [[b, d, i, h], Fv]];
    for (const ff of FS) wound(buf, ff[0][0], ff[0][1], ff[0][2], ff[0][3], ff[1], c);
  }

  function wound(buf, a, b, c, d, out, col) {
    const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]], v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    const n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
    if (n[0] * out[0] + n[1] * out[1] + n[2] * out[2] >= 0) buf.quad(a, b, c, d, col);
    else buf.quad(d, c, b, a, col);
  }
})();
