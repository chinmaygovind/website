/**
 * Mount Joy: the mountain.
 *
 * Every other track in the pool either sits on one flat collidable quad
 * (`track.ground`) or floats in the void over scenery nothing can touch. Neither
 * works here. A flat plate at the valley floor would be a ceiling through the
 * middle of a track that climbs a hundred and eighty-five units; scenery you fall through
 * would mean sinking into a visibly solid snowfield every time you ran wide,
 * which reads as a bug rather than as a mistake. So the mountain is a **height
 * field, and it is in the collider**: go off, and you are on the mountainside.
 *
 * Spa has the pool's only other height field and this is deliberately not it.
 * `buildTerrain` answers "how high is the nearest bit of road", which is the
 * right question for a circuit lying in one sheet and the wrong one here, where
 * switchbacks stack legs a hundred units above each other and `toRoad` cannot
 * tell you which of them you are under (`docs/tracks-and-geometry.md` says so,
 * in the note about Costco's rooftop deck). It also has no answer for a *gap*:
 * the air stations carry a ballistic bow, so a field built from them fills the
 * jump in and the car lands on the snow a tenth of a second after leaving the
 * lip.
 *
 * The rule here has no notion of "nearest" at all:
 *
 *     h(x,z) = min( min over solid stations of  y - drop + rise(d)
 *                 , max( max over solid stations of  y - drop - FALL * d
 *                      , the peak cone ) )
 *
 * The first term is a **lower envelope of upward cones**, one per station. It is
 * at most `y - DROP` at every station, so **the snow can never come up through
 * the road** - not by construction of the layout, but arithmetically, for any
 * layout, which is what makes this safe to author against. Between two legs at
 * different heights it rises out of the lower one at `FLANK` until it runs into
 * the upper one, which is a mountainside with a road cut into it. The `APRON`
 * keeps a flat shoulder either side of the tarmac, without which every road on
 * the hill sits in its own trench.
 *
 * The second term is an **upper envelope of downward cones**, and it is what
 * makes the thing a mountain rather than a bowl. Without it the first term
 * climbs forever in every direction away from the road, so the outfield rises
 * into a wall around the track. `FALL` is much gentler than `FLANK`, so it only
 * ever bites away from the road: near the summit it is a broad cone falling off
 * the top, out past the valley it takes the ground down to the floor.
 *
 * The peak is a third term, `max`ed in under the same `min`, and it has to be
 * *in the field* rather than a mesh sitting on top of it. The spiral leaves a
 * hole in the middle with no road anywhere near it, and the falling cones dig
 * that hole out: derived from the track alone, the highest ground on this
 * mountain is the summit road itself, so the middle of the spiral comes out as
 * a bowl with the track round its rim. Adding an authored cone there fills it
 * and costs nothing in safety, because it goes under the same `min` as
 * everything else and the up-fill still decides wherever the road is. Its
 * profile is concave - steep near the top, shallowing toward the base - which
 * is the difference between a mountain and a tent.
 *
 * **The gap is the thing to be careful of, and it is why `rise(d)` is in two
 * pieces.** The jump lands forty units *above* its lip, so the snow under the
 * flight is the fill between the lip's cone and the shelf's, and the car's arc
 * has to stay over it. The gap is forty units long and the soft zone reaches
 * forty-three, so that arc is measured against `FLANK` alone - which is what
 * lets `STEEP` be as steep as the launch face needs without ever reaching the
 * flight. Get that wrong and the face surfaces through the parabola somewhere
 * near the far end, and what it looks like from the car is the jump simply not
 * working, once, with no error anywhere.
 */
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.mountjoy = { props: props };

  // The shape of the hill.
  //
  // The up-cone is in **two gradients and it has to be**, which is the one thing
  // here that was not obvious. A single gradient is doing two unrelated jobs: it
  // is the run-off beside the road, where gentle is the whole point, and it is
  // how fast the snow can climb away from a *distant* low station, where gentle
  // is fatal. This track puts the valley floor a hundred and twenty units from a
  // shelf a hundred and eighty-five units above it, because that is what a ski
  // jump is - at one soft gradient the valley's own cone reaches up under the
  // summit and holds the whole top of the mountain ninety units in the air.
  //
  // So: `FLANK` for `SOFT` units past the shoulder, which is the verge you can
  // run wide onto and drive back off; and `STEEP` past that, which is the face.
  // The gap is 40 units long and the soft zone reaches 43, so the arc across it
  // is measured against `FLANK` alone and `STEEP` cannot reach it however big it
  // gets. That is what buys the freedom to make the launch face a cliff.
  const FLANK = 0.55;      // gradient of the verge, for SOFT units
  const SOFT = 26.0;
  const STEEP = 3.2;       // gradient of the face past it
  const FALL = 0.50;       // gradient of the snow falling away from everything
  const APRON = 17.0;      // flat shoulder either side of the road
  // How far under the tarmac the snow sits. It has two jobs and they pull
  // opposite ways: deep enough that the road reads as a ribbon laid on the hill
  // rather than z-fighting with it, and shallow enough to bury `buildTrack`'s
  // own trestle legs, which on a track with no ground plane are a fixed sixteen
  // units long and are drawn under *every* raised station. Whatever sticks out
  // of the snow is `DROP - THICK` of steel post every seven stations, all the
  // way round - at 4.5 that is a picket fence you can see the road through from
  // the far side of the valley.
  const DROP = 3.0;

  // ...except over the last `FLUSH` units of road, where it comes up to
  // `DROP_FLUSH` and the run to the flag reads as cut into the valley floor
  // rather than laid on top of it.
  //
  // How far it may come up is set by two things and neither is taste. The
  // tarmac slab is `THICK` (0.9) deep, so anything under that and the snow is
  // through the road from the side; and a *banked* station drops its outer kerb
  // by `sin(bank) * hw` below the centre - twelve degrees on a seven-unit half
  // width is 1.45 - so a flush section has to be unbanked or the snow closes
  // over the low kerb. The last corner is authored flat for exactly that reason.
  // 1.5 clears the slab with room and still reads as flush from the car.
  const DROP_FLUSH = 1.5, FLUSH = 150.0, FLUSH_BLEND = 90.0;
  const FLOOR = -9.0;      // the valley floor; nothing goes below it
  // Resolution, and how far past the track the field is built. Both are as
  // coarse as they can be, because this is the most expensive thing in the
  // game's build: every cell asks every second station two questions, and even
  // at these numbers that is three million of them and about a second inside
  // QuickJS, which is where the anti-cheat re-drives laps. Spa's height field
  // is the only comparable thing in the pool and costs 1.25s, so this is in
  // range rather than novel - but an 8-unit grid would be four times it.
  const CELLM = 18.0;
  const STRIDE = 2;        // every nth station feeds the field; they are 3.5 apart
  const PAD = 320.0;
  const FAR = 2600.0;      // the drawn-only plate past that, so there is a horizon
  const SOFT_TOP = FLANK * SOFT;

  // The peak. `PEAK_RISE` is how far it stands over the highest road, and
  // `PEAK_POW` under 1 is what makes it concave: at 0.78 the cone is near
  // vertical for the top few units and has flattened right out by the time it
  // reaches the summit road.
  //
  // **Past `PEAK_REACH` it has to become a straight line falling at
  // `PEAK_FALL`**, and that is not tidiness. A concave profile flattens forever:
  // left to run, a peak this tall was still twenty-two units up five hundred
  // units away, which is out at the start line - and since the up-fill only
  // clips it where there is road, what that looks like from the grid is the
  // whole valley closed in by a grey wall a couple of car lengths off the kerb.
  // A mountain has to *end*.
  const PEAK_RISE = 54.0, PEAK_REACH = 100.0, PEAK_POW = 0.78, PEAK_FALL = 0.82;

  // Roughness. Only ever *subtracted*, so no amount of it can lift the snow
  // into the road, and faded out near the tarmac so the shoulder stays flat.
  const ROUGH = 9.0, ROUGH_SCALE = 96.0, ROUGH2 = 2.2, ROUGH2_SCALE = 26.0;

  // Steeper than this and the snow has slid off, leaving rock - but only below
  // the cap, because the top of a mountain is white however steep it is. The
  // threshold has to sit well clear of FLANK itself: the whole flank is at
  // exactly that gradient by construction, so anything near it paints half the
  // hill in grey blotches, which reads as dirt rather than as stone.
  const SNOW_STEEP = 1.35, CAP_BELOW = 26.0;

  // The conifers. Hardcoded rather than taken from the palette because the
  // palette contract (`tracks/look.py`) has exactly two structural colour slots
  // and this track needs three - steel, rock and trees - and steel is the one
  // `buildTrack` reads for itself.
  const CONIFER = 0x24503a;

  function props(ctx) {
    const { solid, col, track, pal, bbox, KIND, shade, mulberry } = ctx;
    const rnd = mulberry(20260811);

    // ---- the stations the field is built from ------------------------------
    // Solid road only. An `air` station is a point on a ballistic hint, not a
    // place there is ground - see the header.
    const line = track.line;
    const n = line.length;
    const sx = new Float64Array(n), sy = new Float64Array(n), sz = new Float64Array(n);
    const sd = new Float64Array(n);        // this station's own drop
    // Distance back from the flag, along the road, so the flush run is a length
    // rather than a station count and does not move when the ribbon is retimed.
    const back = new Float64Array(n);
    for (let i = n - 2; i >= 0; i--) {
      const a = line[i].p, c = line[i + 1].p;
      back[i] = back[i + 1] + Math.hypot(c[0] - a[0], c[1] - a[1], c[2] - a[2]);
    }
    const dropAt = (i) => {
      const t = (back[i] - FLUSH) / FLUSH_BLEND;     // 0 at the flush edge, 1 clear of it
      return DROP_FLUSH + (DROP - DROP_FLUSH) * Math.min(1, Math.max(0, t));
    };
    let ns = 0;
    for (let i = 0; i < n; i += STRIDE) {
      const e = line[i];
      if (e.air) continue;
      sx[ns] = e.p[0]; sy[ns] = e.p[1]; sz[ns] = e.p[2]; sd[ns] = dropAt(i); ns++;
    }
    // The last station always counts, whatever the stride lands on, or the road
    // under the flag has no ground derived from it.
    const last = line[n - 1];
    sx[ns] = last.p[0]; sy[ns] = last.p[1]; sz[ns] = last.p[2];
    sd[ns] = DROP_FLUSH; ns++;

    // ---- where the peak goes -----------------------------------------------
    // **Beside the summit road**, which is the only place worth putting it: the
    // whole point of the launch is that you end up on top of a mountain, and a
    // peak you cannot see from the shelf you land on does not say so. Left to
    // find the widest open snow on the track it wanders off into the valley,
    // which is a different mountain.
    //
    // So it is searched for on a line out from the highest road, perpendicular
    // to it, both ways, and the offset that keeps the most air around it wins.
    // Clearance is measured against *every* station, the air ones included, so
    // the flight across the gap cannot pass through the peak either.
    let peakX = (bbox.x0 + bbox.x1) / 2, peakZ = (bbox.z0 + bbox.z1) / 2, room = -1;
    {
      let hi = 0;
      for (let k = 0; k < n; k++) if (!line[k].air && line[k].p[1] > line[hi].p[1]) hi = k;
      const e = line[hi];
      for (const s of [-1, 1]) {
        for (let off = 60; off <= PEAK_REACH * 1.7; off += 10) {
          const x = e.p[0] + e.lat[0] * s * off, z = e.p[2] + e.lat[2] * s * off;
          let near = Infinity;
          for (let k = 0; k < n; k++) {
            const p = line[k].p;
            const d2 = (p[0] - x) * (p[0] - x) + (p[2] - z) * (p[2] - z);
            if (d2 < near) near = d2;
          }
          if (near > room) { room = near; peakX = x; peakZ = z; }
        }
      }
    }
    const apex = ctx.maxY + PEAK_RISE;
    const peakK = PEAK_RISE / Math.pow(PEAK_REACH, PEAK_POW);
    const peakEdge = apex - PEAK_RISE;                 // its height at PEAK_REACH
    const peakAt = (d) => d <= PEAK_REACH
      ? apex - peakK * Math.pow(d, PEAK_POW)
      : peakEdge - PEAK_FALL * (d - PEAK_REACH);

    // ---- the field ---------------------------------------------------------
    const x0 = bbox.x0 - PAD, x1 = bbox.x1 + PAD;
    const z0 = bbox.z0 - PAD, z1 = bbox.z1 + PAD;
    const nx = Math.ceil((x1 - x0) / CELLM) + 1;
    const nz = Math.ceil((z1 - z0) / CELLM) + 1;
    const H = new Float64Array(nx * nz);      // height
    const D = new Float64Array(nx * nz);      // distance to the nearest road centre

    for (let ix = 0; ix < nx; ix++) {
      const px = x0 + ix * CELLM;
      for (let iz = 0; iz < nz; iz++) {
        const pz = z0 + iz * CELLM;
        let up = Infinity, down = -Infinity, near = Infinity;
        for (let k = 0; k < ns; k++) {
          const dx = sx[k] - px, dz = sz[k] - pz;
          const d = Math.sqrt(dx * dx + dz * dz);
          if (d < near) near = d;
          const base = sy[k] - sd[k];
          const o = d - APRON;
          const u = o <= 0 ? base
                  : o <= SOFT ? base + FLANK * o
                  : base + SOFT_TOP + STEEP * (o - SOFT);
          if (u < up) up = u;
          const w = base - FALL * d;
          if (w > down) down = w;
        }
        down = Math.max(down, peakAt(Math.hypot(px - peakX, pz - peakZ)));
        let h = Math.min(up, down);
        // Roughness, faded in past the shoulder so the road keeps its verge.
        const t = Math.min(1, Math.max(0, (near - APRON - 8) / 26));
        if (t > 0) {
          h -= t * (ROUGH * noise(px, pz, ROUGH_SCALE, 7)
                    + ROUGH2 * noise(px, pz, ROUGH2_SCALE, 19));
        }
        const idx = ix * nz + iz;
        H[idx] = Math.max(FLOOR, h);
        D[idx] = near;
      }
    }

    const at = (ix, iz) => [x0 + ix * CELLM, H[ix * nz + iz], z0 + iz * CELLM];
    // Bilinear sample, for anything that has to stand on the snow.
    const heightAt = (x, z) => {
      const fx = Math.min(nx - 1.001, Math.max(0, (x - x0) / CELLM));
      const fz = Math.min(nz - 1.001, Math.max(0, (z - z0) / CELLM));
      const ix = Math.floor(fx), iz = Math.floor(fz);
      const tx = fx - ix, tz = fz - iz;
      const a = H[ix * nz + iz], b = H[ix * nz + iz + 1];
      const c = H[(ix + 1) * nz + iz], d = H[(ix + 1) * nz + iz + 1];
      return (a * (1 - tz) + b * tz) * (1 - tx) + (c * (1 - tz) + d * tz) * tx;
    };
    const roadAt = (x, z) => {
      const fx = Math.min(nx - 1.001, Math.max(0, (x - x0) / CELLM));
      const fz = Math.min(nz - 1.001, Math.max(0, (z - z0) / CELLM));
      return D[Math.round(fx) * nz + Math.round(fz)];
    };

    // ---- draw it, and collide it ------------------------------------------
    // Snow where it lies and rock where it cannot: a face steeper than
    // SNOW_STEEP is bare, which is most of what gives the hill any shape at
    // all. Everything here is one flat-shaded quad, so the colour *is* the
    // shading.
    const snow = pal.ground, bright_ = pal.snow != null ? pal.snow : 0xffffff;
    const rock = pal.prop2, rock2 = shade(pal.prop2, -0.26);
    const capY = apex - CAP_BELOW;
    for (let ix = 0; ix + 1 < nx; ix++) {
      for (let iz = 0; iz + 1 < nz; iz++) {
        const a = at(ix, iz), b = at(ix, iz + 1);
        const c = at(ix + 1, iz + 1), d = at(ix + 1, iz);
        const lo = Math.min(a[1], b[1], c[1], d[1]);
        const hi = Math.max(a[1], b[1], c[1], d[1]);
        const grade = (hi - lo) / CELLM;
        let colr;
        if (grade > SNOW_STEEP && hi < capY) {
          colr = shade(grade > SNOW_STEEP + 0.5 ? rock2 : rock,
                       (noise(a[0], a[2], 31, 3) - 0.5) * 0.26);
        } else {
          // A touch of variation, and the flatter faces a shade brighter, so a
          // field of identical white quads has some relief in it.
          const lift = Math.min(0.1, Math.max(-0.07, (lo - FLOOR) * 0.0014 - 0.035));
          colr = shade(grade < 0.2 ? bright_ : snow,
                       lift + (noise(a[0], a[2], 46, 11) - 0.5) * 0.07);
        }
        solid.quad(a, b, c, d, colr);
        col.addQuad(a, b, c, d, KIND.OFFROAD);
      }
    }

    // A drawn-only plate a long way out, so the mountain has a valley to stand
    // in rather than an edge to fall off in the middle distance. Never
    // collided: past the field, leaving the mountain is meant to be a fall.
    const fy = FLOOR - 0.4;
    solid.quad([x0 - FAR, fy, z0 - FAR], [x0 - FAR, fy, z1 + FAR],
               [x1 + FAR, fy, z1 + FAR], [x1 + FAR, fy, z0 - FAR],
               shade(snow, -0.06));

    // ---- the range behind it ----------------------------------------------
    // Drawn only, a long way out, and capped below the track's own lowest
    // point plus a little - they are a horizon, not a place.
    // They are sized against `maxY` rather than against a constant, because
    // the one job they have is to say how big the mountain you are standing on
    // is - a range that tops out well below the summit road reads as a set of
    // hills the track is flying over, which is the opposite of the point.
    const cx0 = (bbox.x0 + bbox.x1) / 2, cz0 = (bbox.z0 + bbox.z1) / 2;
    const span = Math.max(bbox.x1 - bbox.x0, bbox.z1 - bbox.z0);
    const hSpan = Math.max(90, ctx.maxY - FLOOR);
    for (let i = 0; i < 40; i++) {
      const a = (i / 40) * Math.PI * 2 + rnd() * 0.14;
      // Clear of the track's own bounding box, always. They are drawn and never
      // collided, so one that lands inside it is a mountain you drive through.
      const r = span * (0.78 + rnd() * 1.2) + 220;
      const mx = cx0 + Math.cos(a) * r, mz = cz0 + Math.sin(a) * r;
      const h = hSpan * (0.45 + rnd() * 0.85);
      farPeak(mx, mz, h * (0.62 + rnd() * 0.5), h);
    }

    function farPeak(cx, cz, R, h) {
      const SEG = 9, base = FLOOR - 0.4;
      const top = [cx + (rnd() - 0.5) * R * 0.2, base + h, cz + (rnd() - 0.5) * R * 0.2];
      const ring = [], mid = [];
      for (let s = 0; s < SEG; s++) {
        const a = (s / SEG) * Math.PI * 2;
        const w = 0.7 + rnd() * 0.6;
        ring.push([cx + Math.cos(a) * R * w, base, cz + Math.sin(a) * R * w]);
        mid.push([cx + Math.cos(a) * R * w * 0.42, base + h * 0.62,
                  cz + Math.sin(a) * R * w * 0.42]);
      }
      for (let s = 0; s < SEG; s++) {
        const s2 = (s + 1) % SEG;
        // Rock below the snow line, white above it - which is what tells you
        // how big the thing is meant to be.
        solid.quad(ring[s], ring[s2], mid[s2], mid[s],
                   shade(rock, (rnd() - 0.5) * 0.22 - 0.1));
        solid.tri(mid[s], mid[s2], top, shade(bright_, (rnd() - 0.5) * 0.1));
      }
    }

    // ---- the trestles ------------------------------------------------------
    // The ramp is a ski jump and a ski jump stands on a tower. That is not a
    // decision, it is what the height field says: the fill is flat for `APRON`
    // units around a station, and seventeen plan units along a sixty-four degree
    // ramp is thirty-five units of climb, so the snow under the ramp can never
    // be nearer than that however the field is tuned. Everything else on the
    // track is within five units of the snow; here it is up to seventy-seven,
    // and the honest thing to draw under it is a trestle.
    //
    // `buildTrack` already puts a pair of slim legs under raised road, but on a
    // track with no ground plane they are a fixed sixteen units long, so on the
    // ramp they stop in mid-air. These stand on the snow, and they are in the
    // same `pal.prop` steel as the built-in pair, which then reads as part of
    // the same tower rather than as a different thing hanging in it.
    const every = 4;
    for (let i = 0; i < n; i += every) {
      const e = line[i];
      if (e.air || e.pf) continue;
      const deck = e.p[1] - 1.2;
      const base = heightAt(e.p[0], e.p[2]);
      const rise = deck - base;
      // Well clear of `DROP`. The snow sits 4.5 under the tarmac *everywhere*,
      // which is what stops the two z-fighting, so a threshold under that puts a
      // three-unit trestle beneath every station on the track - two thousand
      // little structures, which from the road is a picket fence you cannot see
      // the mountain through. Only road that is genuinely up in the air gets one.
      if (rise < 7.0) continue;
      const steel = shade(rock, -0.04 + (noise(e.p[0], e.p[2], 17, 23) - 0.5) * 0.1);
      // Two legs, splayed - a tower this tall on parallel legs reads as a pair
      // of pipes, and the splay is most of what makes it look like it is
      // carrying something.
      const splay = Math.min(0.55, 0.16 + rise * 0.006);
      for (const s of [-1, 1]) {
        const tx = e.p[0] + e.lat[0] * s * e.hw * 0.66;
        const tz = e.p[2] + e.lat[2] * s * e.hw * 0.66;
        const bx = e.p[0] + e.lat[0] * s * e.hw * (0.66 + splay);
        const bz = e.p[2] + e.lat[2] * s * e.hw * (0.66 + splay);
        // A splayed leg as a stack of short boxes, because a `box` is
        // axis-aligned and a single one cannot lean.
        const seg = Math.max(2, Math.round(rise / 9));
        for (let k = 0; k < seg; k++) {
          const u0 = k / seg, u1 = (k + 1) / seg;
          const y0 = base + rise * u0, y1 = base + rise * u1;
          const m = (u0 + u1) / 2;
          solid.box(bx + (tx - bx) * m, (y0 + y1) / 2, bz + (tz - bz) * m,
                    0.62, (y1 - y0) / 2 + 0.05, 0.62, steel);
        }
      }
      // Cross-bracing every few units of height, and a beam under the deck.
      const bays = Math.max(1, Math.round(rise / 11));
      for (let k = 1; k <= bays; k++) {
        const u = k / bays;
        const y = base + rise * u;
        const half = e.hw * (0.66 + splay * (1 - u)) + 0.6;
        const lx = e.p[0] - e.lat[0] * half, lz = e.p[2] - e.lat[2] * half;
        const rx = e.p[0] + e.lat[0] * half, rz = e.p[2] + e.lat[2] * half;
        solid.box((lx + rx) / 2, y, (lz + rz) / 2,
                  Math.abs(rx - lx) / 2 + 0.4, 0.34, Math.abs(rz - lz) / 2 + 0.4,
                  shade(steel, k === bays ? 0.08 : -0.12));
      }
    }

    // ---- trees -------------------------------------------------------------
    // The lower flanks only. A treeline is the cheapest possible altitude cue
    // and this track is entirely about altitude: bare white above it, dark
    // green below, and you can see which one you are in from the car.
    const density = pal.density != null ? pal.density : 0.3;
    const TREELINE = FLOOR + 40, STEP = CELLM * 1.35;
    for (let x = x0 + STEP; x < x1; x += STEP) {
      for (let z = z0 + STEP; z < z1; z += STEP) {
        if (rnd() > density) continue;
        const px2 = x + (rnd() - 0.5) * STEP * 0.8, pz2 = z + (rnd() - 0.5) * STEP * 0.8;
        if (roadAt(px2, pz2) < APRON + 13) continue;      // off the road and its verge
        const y = heightAt(px2, pz2);
        if (y > TREELINE) continue;
        // Nothing grows on a face the snow has slid off.
        const gx = heightAt(px2 + 4, pz2) - heightAt(px2 - 4, pz2);
        const gz = heightAt(px2, pz2 + 4) - heightAt(px2, pz2 - 4);
        if (Math.hypot(gx, gz) / 8 > 0.75) continue;
        // Thinner and scrubbier the higher it is, which is what a treeline
        // actually looks like from a distance.
        const alt = Math.max(0, Math.min(1, (TREELINE - y) / 34));
        if (rnd() > 0.25 + alt * 0.75) continue;
        conifer(px2, y - 0.4, pz2, (2.6 + rnd() * 4.2) * (0.62 + alt * 0.5));
      }
    }

    function conifer(x, y, z, hgt) {
      solid.box(x, y + hgt * 0.2, z, 0.28, hgt * 0.2, 0.28, 0x4a3722);
      const tiers = 3;
      for (let t = 0; t < tiers; t++) {
        const u = t / tiers;
        const w = (1.45 - u * 0.62) * (hgt / 5.2);
        const cy = y + hgt * (0.42 + u * 0.29);
        solid.box(x, cy, z, w, hgt * 0.19, w, shade(CONIFER, (rnd() - 0.5) * 0.18));
        // Snow sits on the whorls, but not on all of them - a slab on every
        // one turns the tree into a wedding cake.
        if (rnd() > 0.34) {
          solid.box(x, cy + hgt * 0.19 - 0.05, z, w * 0.84, 0.14, w * 0.84, bright_);
        }
      }
    }
  }

  /** Value noise on a lattice, in 0..1. Deterministic, and no allocation. */
  function noise(x, z, scale, seed) {
    const xf = x / scale, zf = z / scale;
    const xi = Math.floor(xf), zi = Math.floor(zf);
    const tx = xf - xi, tz = zf - zi;
    const sx = tx * tx * (3 - 2 * tx), sz = tz * tz * (3 - 2 * tz);
    const h = (a, b) => {
      let v = (Math.imul(a, 374761393) + Math.imul(b, 668265263)
               + Math.imul(seed, 1442695041)) | 0;
      v = Math.imul(v ^ (v >>> 13), 1274126177) | 0;
      return ((v ^ (v >>> 16)) >>> 0) / 4294967295;
    };
    const a0 = h(xi, zi), b0 = h(xi + 1, zi), c0 = h(xi, zi + 1), d0 = h(xi + 1, zi + 1);
    return (a0 + (b0 - a0) * sx) * (1 - sz) + (c0 + (d0 - c0) * sx) * sz;
  }
})();
