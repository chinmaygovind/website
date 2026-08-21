// Monaco: the hillside, the harbour, the city, the mountains, and the tunnel.
//
// The largest `scenery.js` in the pool, and the reason is one geometric fact
// about the place: **the circuit crosses over itself.** Beau Rivage climbs
// directly above the harbour front with nine units of air between them, so the
// world here cannot be a single-valued height field sampled off the road -
// `pal.terrain` draws the upper road's run-off as a ceiling over the lower road,
// which is what the first render of this track showed. See `track.py`.
//
// So this is Mount Joy's pattern: the track floats (`ground = None`), and
// everything under and beside it is built here. What that buys, beyond being
// correct, is that a city can be *derived from the ribbon* rather than authored
// beside it - so nothing below has a literal coordinate in it and a leg that
// moves takes its buildings, its quay and its water with it.
//
// **Everything about how it looks came off two photographs**, and it is worth
// saying what they changed, because the first three passes of this file were
// built from a mental image of the words "Monte Carlo" and every one of them was
// wrong in the same direction - too grey, too sparse, too flat:
//
//  * **The water is deep cobalt navy, not cyan.** In an aerial it is nearly
//    black-blue in the open and only goes teal in the shallow marina. Three
//    passes of this file had a bright turquoise pool, because a mid blue picked
//    on a swatch renders *much* lighter in the unlit buffer than it looks.
//  * **Terracotta pitched roofs are the signature of the city.** From anywhere
//    above, Monaco is a field of orange-red roofs. Flat grey boxes read as any
//    business district on earth. The grand Belle Epoque buildings are the
//    exception and go the other way - oxidised copper green, with domes.
//  * **A limestone mountain fills the top third of the frame** from inside the
//    city, bare pale crags over dark wooded slopes. Without it the horizon here
//    is a flat pale plain, and that one absence was most of why the early renders
//    read as a quarry rather than the Riviera.
//  * **The marina is packed.** Dozens of small white boats bows-in along
//    pontoons in tight rows, not a handful of large ones scattered about, and the
//    tall thin masts on the sailing yachts are half of what makes it legible.
//  * Vegetation is everywhere and it is *dark* - umbrella pines and palms in
//    clumps threaded right through the city, not a line of palms on the quay.
//
// **This file is in the collider, not just the picture.** `verify.py` re-drives
// submitted laps through `buildTrack`, so the hillside a car slid down in the
// browser has to be there on the server too. Anything purely decorative -
// balconies, roofs, boats, mountains, trees - is drawn and never collided, which
// keeps the anti-cheat's triangle soup to the things a car can actually reach.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.monaco = { props: props };

  // How far under the road the pavement sits, and how steeply the hillside
  // climbs away from it.
  //
  // `DROP` is small because a street in a city is *in* the ground rather than on
  // a plinth over it - and because the engine's own trestles hang a flat 15.7
  // units under every station of a track with no ground, so anything deeper
  // leaves them poking out of the hill. Mount Joy buries them the same way.
  //
  // **`FLANK` was 0.62 and that buried the road.** A cone rising from the station
  // *centre* at 0.62 is back to road level 2.6 units out and 2.1 units *over* it
  // at the kerb, so the first render of this had the car in a trench with its
  // kerbs swallowed and pale scree closing over both sides of the road. Two
  // things fix it and both are needed: the rise does not start until `EDGE` past
  // the road edge, and 0.10 is a hillside where 0.62 is a scree slope.
  const DROP = 1.6;
  const FLANK = 0.10;        // rise per unit of distance, once past the pavement
  const EDGE = 4.0;          // pavement: flat this far beyond the kerb
  const CELLQ = 7.0;         // the field's own grid
  const SEA = -14.0;         // the harbour
  const THICK = 0.9;         // road slab, for standing the retaining walls under

  // **Which stretch is in a tunnel is a fact about Monaco, not something the
  // ribbon implies**, so it is declared - and by fraction of the lap rather than
  // by station index, the way Spa places its grandstands, so it survives the
  // ribbon being re-solved.
  //
  // The derived version was wrong in a way worth recording. The first rule was
  // "the longest run of stations with another part of the circuit above them",
  // which sounds like a definition of a tunnel and is actually a definition of a
  // *crossing*. On this track those are different places: the circuit passes over
  // itself at the harbour front, so the bore was built along the quay and its
  // roof came up through Beau Rivage nine units above it - tunnel geometry
  // cutting across the track just after Sainte Devote, a third of a lap from
  // where the tunnel belongs.
  const TUN_AT = [0.452, 0.614];

  // The palette this city is dealt from. Walls are the palette's cream plus four
  // more, because five is the difference between a city and a housing estate;
  // roofs are terracotta except on the grand stone buildings, which take
  // oxidised copper.
  // **These were five beiges and the city read as concrete.** A `MeshLambert`
  // face turned away from the key light is lit almost entirely by the
  // hemisphere, so a wall colour with no saturation in it has nothing to *be*
  // in shade - it goes straight to grey. The fix is on both sides: the bounce is
  // warm now (see `palette.py`), and these carry real colour rather than a tint
  // of one. Riviera pastels: apricot, peach, rose, ochre, pale yellow, cream.
  // **Value range, not just hue range.** Seven pastels all at the same lightness
  // is still one colour from the car: the street views came out as a single warm
  // beige however varied the hues were, because nothing in the frame was light or
  // dark. So this spans near-white to deep terracotta, and the contrast between
  // neighbours is what makes a row of buildings read as a row.
  const WALLS = [0xf7f2e6, 0xf2dfc0, 0xf0c89a, 0xe8a878, 0xdfa298,
                 0xf2e0a0, 0xc98f78, 0xb5705a, 0xfaf6ec];
  // **The blue ones.** Monte Carlo is not all stucco - there are glass towers
  // through it, and the reference has a turquoise curtain-wall block that is the
  // one cool thing in a frame of warm stone. A cool colour among warm ones reads
  // as far more colourful than another warm one does, so these are worth more
  // than their share of the buildings: one in six.
  const GLASS = [0x7fb6bd, 0x6aa3c4, 0x8fc6c2, 0x5f93b8];
  const ROOFS = [0xc4543a, 0xb04630, 0xd06a44, 0xa53f2b];
  const COPPER = 0x5f8f74;
  // Awnings, which are most of what puts colour at eye level in a town like
  // this. Saturated on purpose - they are small, and they are the only pure
  // colour in the frame besides the kerbs.
  const AWNING = [0xc0392b, 0x21618c, 0x1e8449, 0xd68910, 0x7d3c98];

  function props(ctx) {
    const { solid, bright, col, signs, track, pal, bbox, KIND, shade, mulberry } = ctx;
    const line = track.line;
    // **A stream per section, not one shared stream.** The ground draw pulls one
    // number per cell, so the *number of cells it draws* decides where the city
    // lands - and moving the harbour's edge by four units once reshuffled every
    // building and put a tower squarely in front of the cover shot. Nothing about
    // that edit was supposed to touch the city.
    const rndGround = mulberry(0x30f1ac);
    const rndCity = mulberry(0x5b2d17);
    const rndTree = mulberry(0x1f7a3c);
    const rndSea = mulberry(0x2c6ea1);
    const rndHill = mulberry(0x77c1e3);

    const TUN = tunnelRun(line);
    const inTunnel = new Set(TUN);

    const PAD = CELLQ * 12;
    const x0 = bbox.x0 - PAD, x1 = bbox.x1 + PAD;
    const z0 = bbox.z0 - PAD, z1 = bbox.z1 + PAD;
    const nx = Math.ceil((x1 - x0) / CELLQ) + 1;
    const nz = Math.ceil((z1 - z0) / CELLQ) + 1;
    const H = new Float64Array(nx * nz).fill(1e9);

    // ---- the height field ------------------------------------------------
    // A **lower envelope of upward cones**, one per station - Mount Joy's rule,
    // and for Mount Joy's reason: it is at most `y - DROP` at every station and
    // rises away from one, so it is *arithmetically* incapable of coming up
    // through any road whatever the layout does. That matters more here than it
    // does there, because this circuit passes nine units over itself.
    //
    // Built as a **chamfer sweep** rather than by asking every cell about every
    // station: two passes taking `min(here, neighbour + FLANK * step)` is the
    // same cone field in O(cells), and - the reason it is worth writing down -
    // it has **no reach cutoff**. The first version stopped looking at 190 units
    // and fell to sea level past that, which drew a ring of sawtooth cliffs round
    // the whole track.
    //
    // The tunnel's stations are **excluded from the stamp**. A tunnel is road
    // with hill over it: include it and the envelope is pulled down to the tunnel
    // floor and the hill above it vanishes, leaving an open cutting. Same rule as
    // Shroom Street excluding its free-standing caps, for the opposite purpose.
    for (let i = 0; i < line.length; i++) {
      const e = line[i];
      if (e.air || inTunnel.has(i)) continue;
      const y = e.p[1] - DROP;
      const r = e.hw + EDGE;
      const ci = Math.round((e.p[0] - x0) / CELLQ), cj = Math.round((e.p[2] - z0) / CELLQ);
      const k = Math.ceil(r / CELLQ);
      for (let a = -k; a <= k; a++) {
        for (let b = -k; b <= k; b++) {
          const ii = ci + a, jj = cj + b;
          if (ii < 0 || jj < 0 || ii >= nx || jj >= nz) continue;
          const dx = x0 + ii * CELLQ - e.p[0], dz = z0 + jj * CELLQ - e.p[2];
          if (dx * dx + dz * dz > r * r) continue;
          const q = ii * nz + jj;
          if (y < H[q]) H[q] = y;
        }
      }
    }
    sweep(H, nx, nz, FLANK * CELLQ, FLANK * CELLQ * 1.41421);

    // ---- how far every cell is from the road -----------------------------
    // **A second chamfer sweep, and it replaces a bucketed nearest-station
    // search that was quietly wrong.** That search stopped as soon as it had a
    // hit closer than one bucket, which is not a guarantee: the query point can
    // sit hard against its own bucket's edge with the real nearest station a
    // metre away on the other side, so it returned 30 where the truth was 5.
    // Every caller uses this as a *clearance* check, so an over-estimate is how a
    // 38-unit apartment block ended up standing on the harbour-front road.
    //
    // A distance transform has no such case: it is seeded from the road cells and
    // relaxed, so it is monotone by construction and cannot report a cell as
    // further from the road than it is. Discrete placements still use the exact
    // linear scan below - a few hundred calls is nothing, and there the answer
    // has to be exact rather than within a chamfer's few percent.
    const DR = new Float64Array(nx * nz).fill(1e9);
    for (let i = 0; i < line.length; i++) {
      const e = line[i];
      if (e.air) continue;
      const ci = Math.round((e.p[0] - x0) / CELLQ), cj = Math.round((e.p[2] - z0) / CELLQ);
      for (let a = -2; a <= 2; a++) {
        for (let b = -2; b <= 2; b++) {
          const ii = ci + a, jj = cj + b;
          if (ii < 0 || jj < 0 || ii >= nx || jj >= nz) continue;
          const d = Math.hypot(x0 + ii * CELLQ - e.p[0], z0 + jj * CELLQ - e.p[2]);
          const q = ii * nz + jj;
          if (d < DR[q]) DR[q] = d;
        }
      }
    }
    sweep(DR, nx, nz, CELLQ, CELLQ * 1.41421);

    // ---- the harbour -----------------------------------------------------
    // Port Hercule, and **it is found by flooding rather than by a
    // point-in-polygon test.** The obvious rule - inside the ribbon's plan
    // polygon and far enough from the road - does not work here for a reason
    // specific to this track: the circuit crosses over itself, so the ribbon is
    // not a simple polygon and the even-odd rule flips parity at the crossing.
    // Whole regions of the port came out "outside" and the basin was never cut.
    //
    // So the water is what a harbour physically is: **the low ground inside the
    // circuit, bounded by the road corridor and by the land rising out of it**,
    // seeded at the centroid of the lowest quarter of the lap - which for Monaco
    // is the quay road running round three sides of the port, so its centroid is
    // in the water.
    const wet = new Uint8Array(nx * nz);
    const solidLine = line.filter((e) => !e.air);
    const ys = solidLine.map((e) => e.p[1]).sort((p, q) => p - q);
    const lowY = ys[Math.floor(ys.length * 0.25)];
    const OFF = 20.0;
    let sx = 0, sz = 0, sn = 0;
    for (const e of solidLine) if (e.p[1] <= lowY) { sx += e.p[0]; sz += e.p[2]; sn++; }
    if (sn) {
      sx /= sn; sz /= sn;
      const si = Math.max(0, Math.min(nx - 1, Math.round((sx - x0) / CELLQ)));
      const sj = Math.max(0, Math.min(nz - 1, Math.round((sz - z0) / CELLQ)));
      const seedH = H[si * nz + sj];
      const seen = new Uint8Array(nx * nz);
      const q = [si * nz + sj];
      seen[si * nz + sj] = 1;
      while (q.length) {
        const k = q.pop();
        wet[k] = 1;
        const i = Math.floor(k / nz), j = k - i * nz;
        const nb = [];
        if (i > 0) nb.push((i - 1) * nz + j);
        if (i < nx - 1) nb.push((i + 1) * nz + j);
        if (j > 0) nb.push(k - 1);
        if (j < nz - 1) nb.push(k + 1);
        for (const m of nb) {
          if (seen[m] || DR[m] <= OFF || H[m] >= seedH + 9) continue;
          seen[m] = 1; q.push(m);
        }
      }
      // **Ramping this carve at all was the mistake.** At 30 units it was five
      // visible terraces into the water and at 9 it was still three, because the
      // grid is 7 units wide and every cell in a ramp lands at its own depth - so
      // a short ramp *is* a staircase, and what it read as was a concrete
      // reservoir cut into the hill. A port has a **quay wall**: one step, every
      // wet cell at the same depth, so the boundary is a single near-vertical
      // quad of uniform height all the way round the basin.
      for (let k = 0; k < H.length; k++) if (wet[k]) H[k] = SEA - 7;
    }

    // ---- the bore corridor -----------------------------------------------
    // **The hill has to be cut out of, or the tunnel is solid rock.** Excluding
    // the tunnel's stations from the height field is what puts a hill over the
    // road - and the hill is *ground*, which is drawn and collided, so it filled
    // the bore: measured, 13 of 15 stations along the run had ground up to 14
    // units above the road. From the car the road ran into a hillside and the
    // game threw you out of bounds, which is the worst kind of defect this file
    // can have, and no picture of the outside of the hill would ever show it.
    //
    // So the corridor is punched out of the ground the way the Costco punches its
    // travelator holes in its roof: derived from where the road actually is,
    // never a list of cells to keep in step by hand.
    const bore = new Uint8Array(nx * nz);
    for (const i of TUN) {
      const e = line[i];
      if (e.air) continue;
      const r = e.hw + 4.5;
      const ci = Math.round((e.p[0] - x0) / CELLQ), cj = Math.round((e.p[2] - z0) / CELLQ);
      const k = Math.ceil(r / CELLQ) + 1;
      for (let a = -k; a <= k; a++) for (let b = -k; b <= k; b++) {
        const ii = ci + a, jj = cj + b;
        if (ii < 0 || jj < 0 || ii >= nx || jj >= nz) continue;
        const dx = x0 + ii * CELLQ - e.p[0], dz = z0 + jj * CELLQ - e.p[2];
        if (dx * dx + dz * dz <= r * r) bore[ii * nz + jj] = 1;
      }
    }

    // ---- the ground, the quay and the promenade --------------------------
    // Stone, and lighter the higher it climbs, because a hill lit from one side
    // needs something standing in for the light it is not getting. The band
    // nearest the road is paved a shade paler: a promenade is the one thing
    // between the water and the buildings in every photograph of this place, and
    // per `docs/track-defects.md` anything laid *on* the floor buys more than the
    // same effort spent on things standing up.
    for (let i = 0; i < nx - 1; i++) {
      for (let j = 0; j < nz - 1; j++) {
        const ax = x0 + i * CELLQ, bx = ax + CELLQ;
        const az = z0 + j * CELLQ, bz = az + CELLQ;
        const h00 = at(H, nx, nz, i, j), h01 = at(H, nx, nz, i, j + 1);
        const h11 = at(H, nx, nz, i + 1, j + 1), h10 = at(H, nx, nz, i + 1, j);
        const mean = (h00 + h01 + h11 + h10) / 4;
        if (bore[i * nz + j]) continue;          // the tunnel runs through here
        const dr = DR[i * nz + j];
        // **A bare tan plate is not a hillside.** In every photograph of this
        // place the ground away from the streets is dark green - terraced
        // planting, umbrella pine, garden - and the pale stone is only the
        // promenade and the squares. So the floor is graded: limestone paving by
        // the road, vegetation as it climbs and moves away from it. That is two
        // lerps and it does more for the frame than anything standing up on it,
        // which is the note in `docs/track-defects.md` about a dead floor.
        const paved = dr < 26 && !wet[i * nz + j];
        const veg = Math.min(1, Math.max(0, (mean - 4) / 34))
                  * Math.min(1, Math.max(0, (dr - 24) / 46));
        const base = paved ? shade(pal.ground, 0.20)
                           : mix(pal.ground, 0x46663a, veg * 0.78);
        const c = shade(base, (mean * 0.0028) + (rndGround() - 0.5) * 0.06);
        // Winding copied from the engine's own ground quad, because a quad wound
        // the wrong way is invisible and nothing says so.
        const a = [ax, h00, az], b = [ax, h01, bz], cc = [bx, h11, bz], d = [bx, h10, az];
        solid.quad(a, b, cc, d, c);
        col.addQuad(a, b, cc, d, KIND.OFFROAD);
      }
    }

    // ---- the water -------------------------------------------------------
    // Drawn and never collided, like Sandy Cove's sea: leaving the quay is a
    // fall, not a slow patch.
    //
    // **Deep navy, and picked far darker than it looks right.** `bright` is
    // `MeshBasicMaterial`, so nothing multiplies it down, while the same hex in
    // `solid` is scaled by a key light well under 1 - so three passes of this
    // rendered as cyan plastic from values that were, on a swatch, darker than
    // the track's own road. The shallow band by the quay goes green, which is
    // what a marina actually does.
    for (let i = 0; i < nx - 1; i++) {
      for (let j = 0; j < nz - 1; j++) {
        if (!(wet[i * nz + j] || wet[(i + 1) * nz + j] || wet[i * nz + j + 1])) continue;
        const ax = x0 + i * CELLQ, bx = ax + CELLQ, az = z0 + j * CELLQ, bz = az + CELLQ;
        const shallow = Math.max(0, 1 - (DR[i * nz + j] - OFF) / 46);
        const t = Math.sin(i * 0.7 + j * 0.5) + Math.sin(i * 0.23 - j * 0.31)
                + Math.sin(i * 0.11 + j * 0.09) * 1.5;
        // A band of glitter on the sun's own diagonal, which is the one thing a
        // flat sheet of water has that a flat sheet of anything else does not.
        // Narrow and high frequency: broad and it is a colour change, narrow and
        // it is light on ripples.
        const gl = Math.pow(Math.max(0, Math.sin(i * 0.9 - j * 0.55)), 6)
                 * Math.max(0, Math.sin(i * 0.31 + j * 0.19)) * 0.42;
        const c = shade(mix(0x0b3a40, 0x1a8a8c, shallow * 0.92), t * 0.045 + gl);
        bright.quad([ax, SEA, az], [ax, SEA, bz], [bx, SEA, bz], [bx, SEA, az], c);
      }
    }

    // ---- retaining walls under the road edges ---------------------------
    // **Two roads nine units apart in height cannot both have ground snug under
    // them**, because the field is single-valued: the `min` hands the gap to the
    // lower road, so Beau Rivage comes out with a nine-unit drop off its edge
    // down to the harbour-front terrace. That is not a defect to design away - it
    // is what a hillside city is - but it has to be *built*, or the road reads as
    // floating and the engine's own trestles hang in the open air under it.
    //
    // Drawn and not collided: the ribbon carries a `rail` on both kerbs for the
    // whole lap, so a car physically cannot reach these.
    //
    // **A wall may not stand on another road, and this is where that bites
    // hardest.** Beau Rivage's outer edge is nine units above the harbour front
    // and directly over it in plan, so its retaining wall came down through the
    // lower road - a fifteen-unit dark slab across the track at the exit of the
    // tunnel, which is what the harbour-front road view kept showing. It is the
    // same signal Spa's armco, run-off and grandstands all read: if some *other*
    // leg is under this point, something else is there and the run is cut.
    for (let i = 0; i < line.length - 1; i++) {
      const e = line[i], f = line[i + 1];
      if (e.air || f.air || inTunnel.has(i)) continue;
      for (const sd of [-1, 1]) {
        const ax = e.p[0] + e.lat[0] * sd * e.hw, az = e.p[2] + e.lat[2] * sd * e.hw;
        const bx = f.p[0] + f.lat[0] * sd * f.hw, bz = f.p[2] + f.lat[2] * sd * f.hw;
        if (overRoad(line, i, ax, az, e.p[1]) || overRoad(line, i, bx, bz, f.p[1])) continue;
        const ay = e.p[1] - THICK, by = f.p[1] - THICK;
        const ag = fieldAt(H, nx, nz, x0, z0, ax, az);
        const bg = fieldAt(H, nx, nz, x0, z0, bx, bz);
        if (ay - ag < 0.4 && by - bg < 0.4) continue;
        const c = shade(pal.ground, -0.16);
        // Both faces: the world mesh is `MeshLambertMaterial` and therefore
        // FrontSide, and these are placed by a signed `side`, so half of them
        // would otherwise be inside-out - the trap that made Spa's pit building
        // an invisible shed.
        solid.quad([ax, ay, az], [ax, ag, az], [bx, bg, bz], [bx, by, bz], c);
        solid.quad([bx, by, bz], [bx, bg, bz], [ax, ag, az], [ax, ay, az], c);
      }
    }

    // ---- the city --------------------------------------------------------
    // Monte Carlo, derived off the ribbon: nothing here has a literal
    // coordinate, so the city moves when the road does.
    //
    // **Four ranks, and the back ones are what make it a city.** With one row of
    // blocks along the road it rendered as a street with desert behind it: from
    // anywhere with a sightline - the climb, the hairpin, across the water - you
    // saw one building deep and then bare hillside.
    const RANKS = [[3.0, 0.70, 0], [17.0, 0.46, 8], [36.0, 0.30, 16], [58.0, 0.20, 26]];
    const towers = [];
    for (let i = 5; i < line.length - 5; i += 3) {
      const e = line[i];
      if (e.air || inTunnel.has(i)) continue;
      for (const side of [-1, 1]) for (let r = 0; r < RANKS.length; r++) {
        const rank = RANKS[r];
        if (rndCity() > rank[1]) continue;
        // Footprint first, then how far out to stand it. **It is the corner that
        // hangs off**, so the offset carries half the footprint and the clearance
        // test does too - a block sized after being placed puts its corner in the
        // road on one side and over the harbour on the other.
        const w = 7 + rndCity() * 8, d = 7 + rndCity() * 7;
        const half = Math.max(w, d) / 2;
        const off = e.hw + rank[0] + half + rndCity() * 5;
        const px = e.p[0] + e.lat[0] * side * off;
        const pz = e.p[2] + e.lat[2] * side * off;
        if (px < x0 + half + 8 || px > x1 - half - 8) continue;
        if (pz < z0 + half + 8 || pz > z1 - half - 8) continue;
        const gy = fieldAt(H, nx, nz, x0, z0, px, pz);
        if (gy < SEA + 1) continue;                       // never in the harbour
        // Exact, not the chamfer field: this is a clearance test and it is the
        // one that failed before.
        if (toRoad(line, px, pz) < e.hw + 2.5 + half) continue;
        let clash = false;
        for (const t of towers) if (Math.hypot(t[0] - px, t[1] - pz) < t[2] + 8) { clash = true; break; }
        if (clash) continue;
        const h = 13 + rndCity() * 30 + rank[2] + Math.max(0, e.p[1]) * 0.55;
        towers.push([px, pz, half]);
        building(solid, bright, col, KIND, shade, rndCity, px, pz, gy, w, d, h,
                 r === 0, e.lat, side);
      }
    }

    // ---- vegetation ------------------------------------------------------
    // Palms on the promenade, umbrella pines up the hill. Dark, and in clumps -
    // in every photograph of this city the planting is the darkest thing in the
    // frame, and it is threaded right through the blocks rather than lining the
    // road.
    for (let i = 0; i < line.length; i += 2) {
      const e = line[i];
      if (e.air || inTunnel.has(i)) continue;
      for (const side of [-1, 1]) {
        if (rndTree() > 0.52) continue;
        const off = e.hw + 3.0 + rndTree() * 52;
        const px = e.p[0] + e.lat[0] * side * off;
        const pz = e.p[2] + e.lat[2] * side * off;
        if (px < x0 + 12 || px > x1 - 12 || pz < z0 + 12 || pz > z1 - 12) continue;
        const gy = fieldAt(H, nx, nz, x0, z0, px, pz);
        if (gy < SEA + 1) continue;
        if (toRoad(line, px, pz) < e.hw + 2.6) continue;
        if (off < 12 || gy < 8) palm(solid, px, gy, pz, 5.5 + rndTree() * 4, shade, rndTree);
        else pine(solid, px, gy, pz, 6 + rndTree() * 6, shade, rndTree);
      }
    }

    // ---- street lamps ----------------------------------------------------
    // Small, and the one piece of furniture that reads at every distance: a
    // regular rhythm of verticals down both sides is most of what separates a
    // street from a strip of tarmac.
    for (let i = 6; i < line.length - 6; i += 9) {
      const e = line[i];
      if (e.air || inTunnel.has(i)) continue;
      for (const side of [-1, 1]) {
        const off = e.hw + 2.1;
        const px = e.p[0] + e.lat[0] * side * off;
        const pz = e.p[2] + e.lat[2] * side * off;
        const gy = fieldAt(H, nx, nz, x0, z0, px, pz);
        if (gy < SEA + 1) continue;
        const base = Math.max(gy, e.p[1] - THICK);
        solid.box(px, base + 3.1, pz, 0.16, 3.1, 0.16, 0x3b3f44);
        solid.box(px, base + 6.3, pz, 0.5, 0.16, 0.5, 0x3b3f44);
        // Dim, and unlit. It is midday, so a lamp head is a pale shape rather
        // than a light source - at full `bright` value a row of them would be the
        // brightest thing on the track.
        bright.box(px, base + 6.1, pz, 0.34, 0.12, 0.34, 0x6e6a5c);
      }
    }

    // ---- catch fencing --------------------------------------------------
    // **The dark branded barrier with a fence on top is the most recognisable
    // thing about this circuit** and it is in every single frame, because it is
    // at the road edge for the whole lap. The barrier itself is the ribbon's own
    // `rail`, so it costs nothing but a colour (see `palette.py` - it is charcoal
    // now, not white). This is the mesh above it: a post every few stations and a
    // top rail, which is what reads as fencing without drawing wire.
    for (let i = 4; i < line.length - 4; i += 3) {
      const e = line[i], f = line[i + 3] || line[i];
      if (e.air || inTunnel.has(i)) continue;
      for (const side of [-1, 1]) {
        const o = e.hw + 0.55, o2 = f.hw + 0.55;
        const bx = e.p[0] + e.lat[0] * side * o, bz = e.p[2] + e.lat[2] * side * o;
        solid.box(bx, e.p[1] + 2.6, bz, 0.10, 1.3, 0.10, 0x2f333c);
        const tx = f.p[0] + f.lat[0] * side * o2, tz = f.p[2] + f.lat[2] * side * o2;
        // A top rail between this post and the next, drawn as a thin quad so it
        // follows the road rather than stepping round it.
        const y = e.p[1] + 3.85, y2 = f.p[1] + 3.85;
        solid.quad([bx, y, bz], [bx, y - 0.16, bz], [tx, y2 - 0.16, tz], [tx, y2, tz], 0x3b4049);
        solid.quad([tx, y2, tz], [tx, y2 - 0.16, tz], [bx, y - 0.16, bz], [bx, y, bz], 0x3b4049);
      }
    }

    // ---- sponsor boards ---------------------------------------------------
    // **Spa and Silverstone get these from `pal.furniture`, which this track
    // cannot reach** - it is only wired up inside `buildTrack`'s ground branch,
    // and there is no ground here. But the `signs` list is on the context, so the
    // boards themselves are available: the same nine painters, the same
    // `CanvasTexture`, pushed on from here the way the Costco pushes its food
    // court board. This is the one bit of Spa's trackside kit worth rebuilding by
    // hand, because hoardings on the barrier are what says Grand Prix.
    //
    // Hung on the barrier, facing the car: `n` points back across the road, `r`
    // runs along it, and `u` is world up. A board is a flat quad and the barrier
    // it hangs on is not flat, so it takes its right vector from the chord
    // between two stations rather than from one station's lateral.
    const BOARDS = ['DRIVE', 'MARLBORO', 'CGOVIND.COM', 'TICKET TO RIDE',
                    'GO BIRDS', 'TACO BELL', 'KING OF TOKYO', 'RAT SCREW',
                    'COSTCO WHOLESALE', 'PENN ENGINEERING'];
    let nb = 0;
    for (let i = 8; i < line.length - 12; i += 14) {
      const e = line[i], f = line[i + 4];
      if (!f || e.air || f.air || inTunnel.has(i)) continue;
      // One side only, alternating, so the boards do not wall the car in.
      const side = (nb % 2) ? 1 : -1;
      const o = e.hw + 0.62, o2 = f.hw + 0.62;
      const ax = e.p[0] + e.lat[0] * side * o, az = e.p[2] + e.lat[2] * side * o;
      const bx = f.p[0] + f.lat[0] * side * o2, bz = f.p[2] + f.lat[2] * side * o2;
      const rx = bx - ax, rz = bz - az;
      const L = Math.hypot(rx, rz);
      if (L < 6) continue;
      // **Size a hoarding, do not derive it** - the note Spa's own boards carry,
      // and this ignored it twice over: at `L * 0.46` a board came out as wide as
      // whatever four stations happened to span and nearly four units tall, which
      // put a fifteen-unit billboard on the barrier filling a third of the frame.
      // Spa's `boardH` is 2.6 and Silverstone's 2.2; this is 1.7, because the
      // barrier here is a metre and a half from a twelve-unit road.
      const hw = Math.min(3.4, L * 0.30), hh = hw / 4;
      signs.push({
        text: BOARDS[nb % BOARDS.length],
        c: [(ax + bx) / 2, (e.p[1] + f.p[1]) / 2 + 0.55 + hh, (az + bz) / 2],
        r: [rx / L, 0, rz / L], u: [0, 1, 0], hw: hw, hh: hh,
        n: [-e.lat[0] * side, 0, -e.lat[2] * side],
      });
      nb++;
    }

    // ---- Monegasque flags on the pit straight -----------------------------
    // Red over white, which is Monaco's flag, and the one thing that says which
    // country you are in from inside a corner - the reason Silverstone has its
    // union flags. On the run to the line, where a circuit actually lines them up.
    for (let i = 6; i < Math.floor(line.length * 0.055); i += 5) {
      const e = line[i];
      if (e.air) continue;
      const side = -1;
      const o = e.hw + 3.4;
      const px = e.p[0] + e.lat[0] * side * o, pz = e.p[2] + e.lat[2] * side * o;
      const gy = fieldAt(H, nx, nz, x0, z0, px, pz);
      const base = Math.max(gy, e.p[1] - THICK);
      solid.box(px, base + 5.0, pz, 0.13, 5.0, 0.13, 0xe8e6e0);
      // The flag itself, hanging off the pole along the road.
      const fx = -e.lat[2] * side, fz = e.lat[0] * side;
      obox(solid, px + fx * 1.7, base + 8.6, pz + fz * 1.7,
           [fx, 0, fz], e.lat, 1.7, 0.07, 0.62, 0xc8102e);
      obox(solid, px + fx * 1.7, base + 7.36, pz + fz * 1.7,
           [fx, 0, fz], e.lat, 1.7, 0.07, 0.62, 0xf4f2ec);
    }

    // ---- the marina ------------------------------------------------------
    marina(solid, bright, line, H, nx, nz, x0, z0, wet, DR, OFF, lowY, inTunnel,
           shade, rndSea);

    // ---- the mountains ---------------------------------------------------
    // **The one thing that changed the whole frame.** Monaco sits in a bowl with
    // bare limestone crags 500 m above it, and from inside the city they fill the
    // top third of the view. Without them the horizon here was a flat pale plain,
    // which is most of why the early renders read as a quarry.
    mountains(solid, bbox, line, shade, rndHill);

    casino(solid, bright, line, H, nx, nz, x0, z0, pal, shade);
    tunnel(solid, bright, col, KIND, shade, line, TUN, H, nx, nz, x0, z0);
    pool(solid, bright, line, H, nx, nz, x0, z0, shade);
  }

  // -- fields -------------------------------------------------------------

  /** Two chamfer passes, in place: `min(here, neighbour + step)`. */
  function sweep(F, nx, nz, STEP, DIAG) {
    for (let i = 0; i < nx; i++) for (let j = 0; j < nz; j++) {
      const q = i * nz + j; let v = F[q];
      if (i > 0) v = Math.min(v, F[(i - 1) * nz + j] + STEP);
      if (j > 0) v = Math.min(v, F[q - 1] + STEP);
      if (i > 0 && j > 0) v = Math.min(v, F[(i - 1) * nz + j - 1] + DIAG);
      if (i > 0 && j < nz - 1) v = Math.min(v, F[(i - 1) * nz + j + 1] + DIAG);
      F[q] = v;
    }
    for (let i = nx - 1; i >= 0; i--) for (let j = nz - 1; j >= 0; j--) {
      const q = i * nz + j; let v = F[q];
      if (i < nx - 1) v = Math.min(v, F[(i + 1) * nz + j] + STEP);
      if (j < nz - 1) v = Math.min(v, F[q + 1] + STEP);
      if (i < nx - 1 && j < nz - 1) v = Math.min(v, F[(i + 1) * nz + j + 1] + DIAG);
      if (i < nx - 1 && j > 0) v = Math.min(v, F[(i + 1) * nz + j - 1] + DIAG);
      F[q] = v;
    }
  }

  function at(F, nx, nz, i, j) {
    return F[Math.max(0, Math.min(nx - 1, i)) * nz + Math.max(0, Math.min(nz - 1, j))];
  }

  function fieldAt(H, nx, nz, x0, z0, x, z) {
    const fi = (x - x0) / CELLQ, fj = (z - z0) / CELLQ;
    const i = Math.max(0, Math.min(nx - 2, Math.floor(fi)));
    const j = Math.max(0, Math.min(nz - 2, Math.floor(fj)));
    const u = Math.max(0, Math.min(1, fi - i)), v = Math.max(0, Math.min(1, fj - j));
    const a = H[i * nz + j], b = H[i * nz + j + 1];
    const c = H[(i + 1) * nz + j], d = H[(i + 1) * nz + j + 1];
    return (a * (1 - v) + b * v) * (1 - u) + (c * (1 - v) + d * v) * u;
  }

  /**
   * Is some *other*, lower part of the circuit under this point?
   *
   * The question Spa's armco asks, and the Costco's trestles - with the height
   * window the Costco's note says is needed, because on a track with road over
   * road a plan-only answer reports the upper road as being "at" every point
   * beneath it. Neighbours along the ribbon are skipped or every station is over
   * the one before it.
   */
  function overRoad(line, i, x, z, y) {
    const n = line.length;
    for (let j = 0; j < n; j++) {
      if (Math.min(Math.abs(i - j), n - Math.abs(i - j)) <= 12) continue;
      const o = line[j];
      if (o.air || o.p[1] > y - 3) continue;
      if (Math.hypot(o.p[0] - x, o.p[2] - z) < o.hw + 3.5) return true;
    }
    return false;
  }

  /**
   * Nearest road centre in plan, exactly.
   *
   * Used only for discrete placements - a few hundred calls, where 695 stations
   * apiece is nothing. The per-cell answer comes off a distance transform
   * instead; see the note there for why the bucketed search this replaced was
   * both faster and wrong.
   */
  function toRoad(line, x, z) {
    let best = Infinity;
    for (let i = 0; i < line.length; i++) {
      const e = line[i]; if (e.air) continue;
      const d = Math.hypot(e.p[0] - x, e.p[2] - z);
      if (d < best) best = d;
    }
    return best;
  }

  function tunnelRun(line) {
    const n = line.length, out = [];
    for (let i = Math.floor(n * TUN_AT[0]); i < Math.ceil(n * TUN_AT[1]); i++) {
      if (i >= 0 && i < n && !line[i].air) out.push(i);
    }
    return out;
  }

  /**
   * How high the bore may be roofed without hitting anything.
   *
   * A guard rather than a constant, because the failure it prevents is one this
   * file already shipped: a roof at a fixed clearance over one road, punched up
   * through another road crossing above it. Nothing on the real tunnel run passes
   * overhead, so in practice this returns the full clearance - but a re-solved
   * ribbon or a moved `TUN_AT` cannot bring the bug back.
   */
  function roofClear(line, TUN, want) {
    const n = line.length;
    let lim = want;
    for (const i of TUN) {
      const a = line[i];
      for (let j = 0; j < n; j++) {
        if (Math.min(Math.abs(i - j), n - Math.abs(i - j)) <= 12) continue;
        const b = line[j];
        if (b.air || b.p[1] <= a.p[1]) continue;
        if (Math.hypot(b.p[0] - a.p[0], b.p[2] - a.p[2]) > a.hw + b.hw + 6) continue;
        lim = Math.min(lim, b.p[1] - a.p[1] - 2.5);
      }
    }
    return Math.max(6.5, lim);
  }

  function mix(a, b, t) {
    const ar = (a >> 16) & 255, ag = (a >> 8) & 255, ab = a & 255;
    const br = (b >> 16) & 255, bg = (b >> 8) & 255, bb = b & 255;
    return (Math.round(ar + (br - ar) * t) << 16)
         | (Math.round(ag + (bg - ag) * t) << 8)
         | Math.round(ab + (bb - ab) * t);
  }

  /**
   * An oriented box: eight corners off a forward and a lateral vector.
   *
   * `solid.box` is axis-aligned, which is fine for a building and **wrong for
   * anything lying at an angle**. The first fleet of yachts was a hull of side
   * quads with an axis-aligned box dropped on top, sized by
   * `max(abs(fx) * l, beam)` to fudge the rotation - and a harbour full of those
   * reads as a raft of crates and torn white sheets, which is how it rendered.
   *
   * **Each face is drawn once, wound outward - and drawing them twice is what
   * made the whole marina flicker.** Two coplanar triangles at identical
   * coordinates give the depth test nothing to choose between, so which one wins
   * changes as the camera moves: from the road that reads as the boats strobing.
   * The double draw was there to dodge the mirrored-winding trap (a box placed by
   * a signed `side` has its faces reversed on one side of the circuit), and the
   * real fix for that is to *measure* the winding rather than hedge it - compare
   * each face's own normal against the direction it should point and reverse the
   * ones that come out backwards. Half the triangles and no z-fighting.
   */
  function obox(buf, cx, cy, cz, f, lat, hu, hv, hh, c) {
    const P = (su, sv, sh) => [cx + f[0] * su * hu + lat[0] * sv * hv,
                               cy + sh * hh,
                               cz + f[2] * su * hu + lat[2] * sv * hv];
    const a = P(-1, -1, -1), b = P(1, -1, -1), d = P(1, 1, -1), e = P(-1, 1, -1);
    const g = P(-1, -1, 1), h = P(1, -1, 1), i = P(1, 1, 1), j = P(-1, 1, 1);
    const up = [0, 1, 0];
    const neg = (v) => [-v[0], -v[1], -v[2]];
    const F = [[[g, h, i, j], up], [[a, e, d, b], neg(up)],
               [[a, b, h, g], neg(lat)], [[e, j, i, d], lat],
               [[a, g, j, e], neg(f)], [[b, d, i, h], f]];
    for (const ff of F) face(buf, ff[0][0], ff[0][1], ff[0][2], ff[0][3], ff[1], c);
  }

  /** One quad, wound so its own normal points along `out`. */
  function face(buf, a, b, c, d, out, col) {
    const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    const v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    const n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
               u[0] * v[1] - u[1] * v[0]];
    if (n[0] * out[0] + n[1] * out[1] + n[2] * out[2] >= 0) buf.quad(a, b, c, d, col);
    else buf.quad(d, c, b, a, col);
  }

  /**
   * A low-poly cone, drawn both ways round.
   *
   * `jit` jitters each base vertex's radius and the tip's position, which is the
   * difference between a massif and a party hat: a true cone of revolution has a
   * silhouette no real hill has, and a ring of them behind the city read as
   * traffic bollards. The domes on the Casino want `jit` of zero, because a dome
   * *is* a solid of revolution.
   */
  function cone(solid, x, y, z, r, h, c, rnd, jit) {
    const N = 12;
    const rad = [];
    for (let k = 0; k < N; k++) rad.push(r * (1 + (jit ? (rnd() - 0.5) * jit : 0)));
    const tip = [x + (jit ? (rnd() - 0.5) * r * jit * 0.7 : 0), y + h,
                 z + (jit ? (rnd() - 0.5) * r * jit * 0.7 : 0)];
    for (let k = 0; k < N; k++) {
      const a0 = (k / N) * Math.PI * 2, a1 = ((k + 1) / N) * Math.PI * 2;
      const p0 = [x + Math.cos(a0) * rad[k], y, z + Math.sin(a0) * rad[k]];
      const p1 = [x + Math.cos(a1) * rad[(k + 1) % N], y, z + Math.sin(a1) * rad[(k + 1) % N]];
      // Outward is the flank's own horizontal direction; same reason as `obox`,
      // and it halves a backdrop that is a lot of triangles.
      const mid = (a0 + a1) / 2;
      face(solid, p0, p1, tip, tip, [Math.cos(mid), 0.35, Math.sin(mid)], c);
    }
  }

  // -- the city -----------------------------------------------------------

  /**
   * One Monte Carlo apartment block.
   *
   * Three things carry it and all three came off the references rather than out
   * of my head:
   *
   *  * **a terracotta pitched roof**, which is the signature of this city from
   *    anywhere above it and the single biggest difference from the flat grey
   *    boxes this started as. The tall modern slabs keep a flat roof with a
   *    parapet, because those are the ones that really do have one;
   *  * **balconies as protruding slabs**, not painted bands. Monaco's blocks are
   *    horizontal lines of balcony with shadow under each one. Painted bands were
   *    tried twice - dark, which averaged the whole city to concrete, then pale,
   *    which turned every building into a multi-storey car park;
   *  * **a darker ground floor**, because a shopfront plinth is what stops a
   *    block reading as a solid extruded rectangle.
   */
  function building(solid, bright, col, KIND, shade, rnd, px, pz, gy, w, d, h,
                    front, lat, side) {
    const glass = rnd() > 0.84;
    const wall = glass
      ? shade(GLASS[Math.floor(rnd() * GLASS.length)], (rnd() - 0.5) * 0.08)
      : shade(WALLS[Math.floor(rnd() * WALLS.length)], (rnd() - 0.5) * 0.10);
    const top = gy + h;
    solid.box(px, gy + h / 2, pz, w / 2, h / 2, d / 2, wall);
    solid.box(px, gy + 1.5, pz, w / 2 + 0.10, 1.5, d / 2 + 0.10, shade(wall, -0.30));
    solid.box(px, gy + 3.15, pz, w / 2 + 0.18, 0.13, d / 2 + 0.18, shade(wall, 0.10));

    // **Fewer, thinner storeys.** At one band every 3.6 units projecting 0.46,
    // a ten-wide block wears a shelf a tenth of its own width every three
    // metres, and what that reads as from the car is a stack of trays - which
    // was the single ugliest thing about this city and had nothing to do with its
    // colour. A balcony is a lip, not a canopy.
    const floors = Math.max(2, Math.floor((h - 3.5) / 5.2));
    for (let f = 1; f <= floors; f++) {
      const y = gy + 3.2 + ((h - 3.6) * f) / (floors + 1);
      if (y > top - 1.2) break;
      if (front) {
        // Three pieces, and each is doing a job: a **dark reveal** for the window
        // behind, the balcony **slab**, and a **white rail** on it. The rail is
        // the one that was missing - a crisp near-white horizontal against a dark
        // opening is the single most recognisable thing about a Riviera apartment
        // block, and without it the facade was slab, shadow, slab, shadow in one
        // flat value.
        bright.box(px, y + 0.52, pz, w / 2 + 0.02, 0.52, d / 2 + 0.02, 0x232a31);
        solid.box(px, y, pz, w / 2 + 0.17, 0.09, d / 2 + 0.17, shade(wall, 0.14));
        solid.box(px, y + 0.34, pz, w / 2 + 0.17, 0.26, d / 2 + 0.17, 0xf6f4ee);
      } else {
        // Further back one dark reveal per floor is enough and is a twelfth of
        // the triangles. Dark, not pale: unlit geometry renders at full value.
        bright.box(px, y, pz, w / 2 + 0.05, 0.34, d / 2 + 0.05, 0x2a313a);
      }
    }

    if (!glass && h < 30 && rnd() > 0.22) {
      const roof = shade(ROOFS[Math.floor(rnd() * ROOFS.length)], (rnd() - 0.5) * 0.10);
      const rh = 1.6 + Math.min(w, d) * 0.16;
      const ex = w / 2 + 0.45, ez = d / 2 + 0.45;
      const along = w >= d;
      const r0 = along ? [px - ex, top + rh, pz] : [px, top + rh, pz - ez];
      const r1 = along ? [px + ex, top + rh, pz] : [px, top + rh, pz + ez];
      const eaves = along
        ? [[[px - ex, top, pz - ez], [px + ex, top, pz - ez]],
           [[px - ex, top, pz + ez], [px + ex, top, pz + ez]]]
        : [[[px - ex, top, pz - ez], [px - ex, top, pz + ez]],
           [[px + ex, top, pz - ez], [px + ex, top, pz + ez]]];
      for (const e of eaves) {
        solid.quad(e[0], e[1], r1, r0, roof);
        solid.quad(r0, r1, e[1], e[0], roof);
      }
      // The gables, so the roof is not two sheets with daylight between them.
      const g0 = along ? [[px - ex, top, pz - ez], [px - ex, top, pz + ez], r0]
                       : [[px - ex, top, pz - ez], [px + ex, top, pz - ez], r0];
      const g1 = along ? [[px + ex, top, pz - ez], [px + ex, top, pz + ez], r1]
                       : [[px - ex, top, pz + ez], [px + ex, top, pz + ez], r1];
      for (const g of [g0, g1]) {
        solid.tri(g[0], g[1], g[2], shade(roof, -0.12));
        solid.tri(g[2], g[1], g[0], shade(roof, -0.12));
      }
    } else {
      // A parapet and a plant room, which is what a flat roof actually has.
      solid.box(px, top + 0.5, pz, w / 2 + 0.3, 0.5, d / 2 + 0.3, shade(wall, -0.14));
      if (rnd() > 0.45) {
        solid.box(px + (rnd() - 0.5) * w * 0.4, top + 2.1, pz + (rnd() - 0.5) * d * 0.4,
                  1.6, 1.6, 1.6, shade(wall, -0.22));
      }
    }
    // Awnings over the shopfronts on the rank you drive past, on the face that
    // actually looks at the road - anything placed at a fixed offset faces the
    // road on one side of the circuit and a blank wall on the other, which is the
    // trap that left both of Silverstone's hangars as grey slabs.
    if (front && lat && rnd() > 0.30) {
      // **Which axis the road is on decides the whole shape of these.** The first
      // pass used `w` for the stand-off and one square half-extent for both axes,
      // which put a square slab floating a metre off the corner of the building
      // instead of a strip flush along its shopfront - three coloured panels
      // hanging in mid air, and from the car that is worse than no awning at all.
      const ex = -lat[0] * side, ez = -lat[2] * side;    // back toward the road
      const alongX = Math.abs(ez) > Math.abs(ex);        // the face runs along x
      const outHalf = (alongX ? d : w) / 2;              // to the facing wall
      const faceHalf = (alongX ? w : d) / 2;             // along that wall
      const sx = alongX ? 0 : Math.sign(ex) || 1;
      const sz = alongX ? Math.sign(ez) || 1 : 0;
      const c = AWNING[Math.floor(rnd() * AWNING.length)];
      const n = Math.max(1, Math.floor(faceHalf / 2.2));
      for (let k = 0; k < n; k++) {
        const t = n === 1 ? 0 : -1 + (2 * k) / (n - 1);
        const cxx = px + sx * (outHalf + 0.55) + (alongX ? t * faceHalf * 0.68 : 0);
        const czz = pz + sz * (outHalf + 0.55) + (alongX ? 0 : t * faceHalf * 0.68);
        // Flush to the wall, projecting just over half a unit, and thin. Striped
        // by alternating the shade, which at this size reads as canvas.
        solid.box(cxx, gy + 2.85, czz,
                  alongX ? faceHalf * 0.30 : 0.58, 0.09,
                  alongX ? 0.58 : faceHalf * 0.30,
                  k % 2 ? c : shade(c, 0.40));
      }
    }
    // The one collision quad: the face a car could reach. Buildings stand well
    // back from the kerb behind a rail, so this is belt and braces rather than
    // load bearing, and one quad keeps the anti-cheat's soup small.
    col.addQuad([px - w / 2, gy, pz - d / 2], [px - w / 2, top, pz - d / 2],
                [px + w / 2, top, pz - d / 2], [px + w / 2, gy, pz - d / 2], KIND.WALL);
  }

  function palm(solid, x, y, z, h, shade, rnd) {
    solid.box(x, y + h / 2, z, 0.26, h / 2, 0.26, 0x6b5a44);
    for (let k = 0; k < 6; k++) {
      const a = (k / 6) * Math.PI * 2 + rnd();
      solid.box(x + Math.cos(a) * 1.9, y + h - 0.35, z + Math.sin(a) * 1.9,
                2.0, 0.16, 0.62, shade(0x2c5f34, (k % 2) * 0.08));
    }
  }

  /** An umbrella pine: a bare trunk and two dark canopy slabs. */
  function pine(solid, x, y, z, h, shade, rnd) {
    solid.box(x, y + h * 0.45, z, 0.24, h * 0.45, 0.24, 0x554636);
    const r = 2.4 + rnd() * 1.8;
    solid.box(x, y + h * 0.92, z, r, 0.5, r, shade(0x24512c, (rnd() - 0.5) * 0.10));
    solid.box(x, y + h * 1.12, z, r * 0.62, 0.42, r * 0.62,
              shade(0x1e4526, (rnd() - 0.5) * 0.10));
  }

  // -- the harbour --------------------------------------------------------

  /**
   * Port Hercule: pontoons off the quay with boats packed either side.
   *
   * The fleet is placed off the *water* rather than off the road - walk out from
   * a low station until the flood says there is water, put a pontoon there, and
   * berth along it. The first version reached a fixed 20-46 units and moored
   * nothing at all, because the carve starts 20 out and those cells are still
   * dry: how far the quay is from the road is not a number to author, it is
   * whatever the flood decided.
   */
  function marina(solid, bright, line, H, nx, nz, x0, z0, wet, DR, OFF, lowY,
                  inTunnel, shade, rnd) {
    const berths = [];
    let piers = 0;
    for (let i = 0; i < line.length && piers <= 14; i += 4) {
      const e = line[i];
      if (e.air || inTunnel.has(i) || e.p[1] > lowY + 6) continue;
      for (const side of [-1, 1]) {
        let edge = 0;
        for (let r = OFF; r < 130; r += 4) {
          const tx = e.p[0] + e.lat[0] * side * r, tz = e.p[2] + e.lat[2] * side * r;
          const ti = Math.round((tx - x0) / CELLQ), tj = Math.round((tz - z0) / CELLQ);
          if (ti < 1 || tj < 1 || ti >= nx - 1 || tj >= nz - 1) break;
          if (wet[ti * nz + tj]) { edge = r; break; }
        }
        if (!edge || rnd() > 0.5) continue;
        const lat = e.lat, f = [-lat[2], 0, lat[0]];
        const len = 26 + rnd() * 22;
        const cx = e.p[0] + lat[0] * side * (edge + len / 2 + 2);
        const cz = e.p[2] + lat[2] * side * (edge + len / 2 + 2);
        // Only build it if the far end is still in water.
        const ei = Math.round((e.p[0] + lat[0] * side * (edge + len) - x0) / CELLQ);
        const ej = Math.round((e.p[2] + lat[2] * side * (edge + len) - z0) / CELLQ);
        if (ei < 1 || ej < 1 || ei >= nx - 1 || ej >= nz - 1) continue;
        if (!wet[ei * nz + ej]) continue;
        let tight = false;
        for (const b of berths) if (Math.hypot(b[0] - cx, b[1] - cz) < 26) { tight = true; break; }
        if (tight) continue;
        berths.push([cx, cz]);
        piers++;
        obox(solid, cx, SEA + 0.55, cz, lat, f, len / 2, 1.5, 0.35, 0xd6d2c6);
        // Boats bows-in, both sides, packed. Small ones mostly - it is the
        // *count* that reads as a marina, and a row of twenty tenders says more
        // than three superyachts do.
        const n = Math.max(3, Math.floor(len / 9));
        for (let k = 0; k < n; k++) {
          const along = -len / 2 + 3 + (k * (len - 6)) / Math.max(1, n - 1);
          for (const s2 of [-1, 1]) {
            if (rnd() > 0.92) continue;
            const bl = 11 + rnd() * 11;
            const bx = cx + lat[0] * side * along + f[0] * s2 * (bl / 2 + 1.6);
            const bz = cz + lat[2] * side * along + f[2] * s2 * (bl / 2 + 1.6);
            boat(solid, bright, bx, SEA, bz, f, lat, bl, shade, rnd, rnd() > 0.62);
          }
        }
        // And one big one on the end of the pier, because this is Monaco.
        if (rnd() > 0.45) {
          const bl = 30 + rnd() * 20;
          boat(solid, bright,
               cx + lat[0] * side * (len / 2 + 5), SEA, cz + lat[2] * side * (len / 2 + 5),
               lat, f, bl, shade, rnd, false);
        }
        if (piers > 14) break;
      }
    }
  }

  /** One boat: dark hull, white topside, superstructure aft, sometimes a mast. */
  function boat(solid, bright, x, y, z, f, lat, len, shade, rnd, mast) {
    const beam = Math.max(1.7, len * 0.26);
    const hull = 1.2 + len * 0.035;
    const white = shade(0xf9f7f2, (rnd() - 0.5) * 0.04);
    // Dark boot-topping at the waterline, which is what puts a boat *in* the
    // water rather than on it.
    obox(solid, x, y - 0.3, z, f, lat, len / 2, beam / 2, 0.8, 0x161f27);
    obox(solid, x, y + hull / 2, z, f, lat, len / 2, beam / 2, hull / 2, white);
    // A dark window band down the hull, and a sheer line above it.
    // **0.03 is not a stand-off, it is a coin toss.** The run-off's own note puts
    // the floor near 0.15; anything applied to a face here uses that.
    obox(bright, x, y + hull * 0.72, z, f, lat, len * 0.40, beam / 2 + 0.16,
         hull * 0.17, 0x27333d);
    // **Three tiers, stepped and set back**, which is the silhouette of every
    // boat in Port Hercule: a wide main deck, a narrower bridge deck, a small
    // sun deck. One box was a shed on a hull.
    const decks = len > 18 ? 3 : 2;
    let dy = y + hull, dl = len * 0.52, dw = beam * 0.40;
    for (let t = 0; t < decks; t++) {
      const dh = 0.9 + len * 0.030;
      const dx = x + f[0] * (-len * 0.06 * t), dz = z + f[2] * (-len * 0.06 * t);
      obox(solid, dx, dy + dh / 2, dz, f, lat, dl / 2, dw, dh / 2, white);
      obox(bright, dx, dy + dh * 0.62, dz, f, lat, dl / 2 + 0.16, dw + 0.16,
           dh * 0.20, 0x1f2a34);
      dy += dh; dl *= 0.66; dw *= 0.74;
    }
    // A radar arch and, on the big ones, a tender on the aft deck.
    if (len > 16) {
      solid.box(x + f[0] * (-len * 0.16), dy + 0.9, z + f[2] * (-len * 0.16),
                0.5, 0.9, 0.5, shade(white, -0.10));
      obox(solid, x + f[0] * (len * 0.33), y + hull + 0.45, z + f[2] * (len * 0.33),
           f, lat, len * 0.075, beam * 0.16, 0.30,
           rnd() > 0.5 ? 0xd06a2a : 0x2b3a46);
    }
    // A mast is a thin vertical and it is half of what makes a marina legible at
    // a distance - a field of them reads as boats where a field of white boxes
    // reads as crates.
    if (mast) {
      const mh = len * 1.15;
      solid.box(x + f[0] * len * 0.06, y + hull + mh / 2, z + f[2] * len * 0.06,
                0.11, mh / 2, 0.11, 0xe6e4dc);
    }
  }

  // -- the backdrop -------------------------------------------------------

  /**
   * The limestone bowl Monaco sits in.
   *
   * Cones, not a height field: they stand well outside the plate, are never
   * collided and never near a road, and they are the cheapest thing in this file
   * per unit of effect. Two tones stacked - dark wooded slope below, bare pale
   * crag above - because that is what the hillside behind the city actually looks
   * like, and a single grey cone reads as a slag heap.
   *
   * Only on the inland side. Out to sea there is sea, and a mountain there would
   * be the one thing in the frame saying this is not the Mediterranean. Which way
   * is the sea is derived: the harbour is the low ground, so the low quarter of
   * the lap points at it and the ridge goes opposite.
   */
  function mountains(solid, bbox, line, shade, rnd) {
    const cx = (bbox.x0 + bbox.x1) / 2, cz = (bbox.z0 + bbox.z1) / 2;
    let my = Infinity;
    for (const e of line) if (!e.air && e.p[1] < my) my = e.p[1];
    let lx = 0, lz = 0, n = 0;
    for (const e of line) {
      if (e.air || e.p[1] > my + 8) continue;
      lx += e.p[0]; lz += e.p[2]; n++;
    }
    const seaAz = n ? Math.atan2(lz / n - cz, lx / n - cx) : 0;

    // **A ridge walked along an arc, not cones scattered at random.** The version
    // before this placed independent massifs whose height was about nine tenths
    // of their radius, and that ratio is the whole problem: a hill that tall for
    // its width is a spike, so a row of them read as traffic bollards on the
    // horizon however they were coloured. Distant hills sit nearer 0.35, and they
    // *overlap* - what you actually see behind Monte Carlo is one continuous
    // skyline with peaks in it, not a line of separate pyramids.
    //
    // Two layers: a pale far range that is nearly sky, and a nearer darker one in
    // front of it. That is the whole trick for depth in a low-poly backdrop -
    // one range is a cutout, two is a landscape.
    const LAYERS = [
      { dist: 1080, rad: 300, hgt: 0.30, wood: 0xa9b3ad, rock: 0xc3c7bd, step: 0.44 },
      { dist: 760, rad: 235, hgt: 0.36, wood: 0x81977f, rock: 0xacb3a4, step: 0.36 },
    ];
    for (const L of LAYERS) {
      for (let t = -1.65; t < 1.65; t += L.step) {
        const a = seaAz + Math.PI + t + (rnd() - 0.5) * 0.14;
        const r = L.rad * (0.78 + rnd() * 0.5);
        const dist = L.dist * (0.92 + rnd() * 0.16);
        const px = cx + Math.cos(a) * dist, pz = cz + Math.sin(a) * dist;
        if (toRoad(line, px, pz) < r + 220) continue;
        // Low and wide. `h` is a fraction of the *radius*, which is what keeps
        // the silhouette a hill rather than a cone.
        const h = r * L.hgt * (0.8 + rnd() * 0.5);
        // A wooded skirt, a rock band, and a crown - each its own jittered cone
        // so the outline breaks at every level rather than only at the top.
        cone(solid, px, -90, pz, r, h * 0.72, shade(L.wood, (rnd() - 0.5) * 0.07), rnd, 0.34);
        cone(solid, px + (rnd() - 0.5) * r * 0.18, -90 + h * 0.40,
             pz + (rnd() - 0.5) * r * 0.18, r * 0.62, h * 0.58,
             shade(L.rock, (rnd() - 0.5) * 0.06), rnd, 0.40);
        // Shoulders, close in, so neighbours merge into a run instead of standing
        // apart as separate hills.
        for (let q = 0; q < 2; q++) {
          const ba = a + (q ? 0.16 : -0.16) + (rnd() - 0.5) * 0.10;
          const br = r * (0.52 + rnd() * 0.24);
          cone(solid, cx + Math.cos(ba) * dist * (0.94 + rnd() * 0.12), -90,
               cz + Math.sin(ba) * dist * (0.94 + rnd() * 0.12),
               br, br * L.hgt * (0.7 + rnd() * 0.6),
               shade(L.wood, (rnd() - 0.5) * 0.09), rnd, 0.38);
        }
      }
    }
  }

  // -- landmarks ----------------------------------------------------------

  /**
   * The Casino de Monte-Carlo, at the top of the hill.
   *
   * The one authored building on the track, and it earns it: Casino Square is
   * what the corner is named after and it is the only place here where a block
   * dealt off the ribbon at random would be standing where something famous is.
   * Still placed by *fraction of the lap* rather than by coordinate, so it
   * survives a re-solve.
   *
   * Copper rather than terracotta, and it is the one building here that gets it -
   * the Belle Epoque stone buildings in Monaco all wear oxidised green, and it is
   * what tells this one apart from three hundred apartment blocks.
   */
  function casino(solid, bright, line, H, nx, nz, x0, z0, pal, shade) {
    const i = Math.floor(line.length * 0.265);
    const e = line[i]; if (!e || e.air) return;
    const off = e.hw + 27;
    const cx = e.p[0] + e.lat[0] * off, cz = e.p[2] + e.lat[2] * off;
    const gy = fieldAt(H, nx, nz, x0, z0, cx, cz);
    if (gy < SEA + 1) return;
    const stone = shade(0xf0e6d2, 0.04);
    solid.box(cx, gy + 8, cz, 18, 8, 12, stone);
    solid.box(cx, gy + 16.4, cz, 18.6, 0.5, 12.6, shade(stone, -0.10));
    for (const s of [-1, 1]) {
      const tx = cx + e.lat[2] * s * 13.5, tz = cz - e.lat[0] * s * 13.5;
      solid.box(tx, gy + 11, tz, 5, 11, 5, stone);
      cone(solid, tx, gy + 22, tz, 5.4, 5.5, COPPER, null, 0);
    }
    solid.box(cx, gy + 19, cz, 7, 3.5, 7, stone);
    cone(solid, cx, gy + 22.5, cz, 7.6, 7, COPPER, null, 0);
    // Arched windows as a dark colonnade - the whole point of a colonnade is the
    // shadow in it, so this is unlit and dark rather than glazed and pale.
    for (let f = 0; f < 2; f++) {
      bright.box(cx, gy + 4.2 + f * 6.4, cz, 18.1, 1.5, 12.1, 0x2b2f36);
    }
    // Gold, because the one thing everybody knows about this building is that it
    // glitters. Kept to a cornice line rather than a slab.
    bright.box(cx, gy + 16.9, cz, 18.7, 0.22, 12.7, pal.deco);
    // Formal gardens in front: dark parterres and a fountain.
    for (let g = -1; g <= 1; g++) {
      const px = cx - e.lat[0] * 17 + e.lat[2] * g * 8;
      const pz = cz - e.lat[2] * 17 - e.lat[0] * g * 8;
      solid.box(px, fieldAt(H, nx, nz, x0, z0, px, pz) + 0.30, pz,
                3.2, 0.30, 3.2, shade(0x24512c, 0.04));
    }
    const fx = cx - e.lat[0] * 17, fz = cz - e.lat[2] * 17;
    const fy = fieldAt(H, nx, nz, x0, z0, fx, fz);
    solid.box(fx, fy + 0.5, fz, 3.0, 0.5, 3.0, shade(0xf0e6d2, -0.06));
    bright.box(fx, fy + 0.85, fz, 2.4, 0.14, 2.4, 0x14414f);
  }

  /** The bore: walls, an unlit ceiling, and a lit strip down the crown. */
  function tunnel(solid, bright, col, KIND, shade, line, TUN, H, nx, nz, x0, z0) {
    if (!TUN.length) return;
    const CLEAR = roofClear(line, TUN, 10.5);
    const OUT = 2.4;
    const conc = 0xc7c1b2;
    for (let k = 0; k < TUN.length - 1; k++) {
      const e = line[TUN[k]], f = line[TUN[k + 1]];
      if (e.air || f.air) continue;
      const roofE = e.p[1] + CLEAR, roofF = f.p[1] + CLEAR;
      for (const s of [-1, 1]) {
        const w = e.hw + OUT, w2 = f.hw + OUT;
        const ex = e.p[0] + e.lat[0] * s * w, ez = e.p[2] + e.lat[2] * s * w;
        const fx = f.p[0] + f.lat[0] * s * w2, fz = f.p[2] + f.lat[2] * s * w2;
        // **The wall has to reach the cut, not just the roof.** The corridor is
        // punched out of the ground, so a wall that stops at the ceiling leaves
        // the hillside sliced open above it and you see straight through the hole
        // into the tunnel from outside. It runs up to whichever is higher, the
        // roof or the ground it was cut from - which above the ceiling is inside
        // the hill and costs nothing to look at.
        const topE = Math.max(roofE, fieldAt(H, nx, nz, x0, z0, ex, ez) + 0.6);
        const topF = Math.max(roofF, fieldAt(H, nx, nz, x0, z0, fx, fz) + 0.6);
        const a = [ex, e.p[1] - 1.4, ez];
        const b = [ex, topE, ez];
        const c = [fx, topF, fz];
        const d = [fx, f.p[1] - 1.4, fz];
        solid.quad(a, b, c, d, shade(conc, -0.30));
        solid.quad(d, c, b, a, shade(conc, -0.30));
        col.addQuad(a, b, c, d, KIND.WALL);
      }
      // **A footway either side, because the bore has no floor otherwise.** The
      // corridor is punched out of the height field, so inside the tunnel there
      // is no ground at all - and the road is only `hw` wide, so from the car you
      // looked over the kerb straight into the void. Reported from inside the
      // tunnel, and invisible from every outside view of it. Collided as OFFROAD:
      // it is a raised footway, not a second lane.
      for (const s2 of [-1, 1]) {
        const a1 = [e.p[0] + e.lat[0] * s2 * e.hw, e.p[1] - 0.55, e.p[2] + e.lat[2] * s2 * e.hw];
        const b1 = [e.p[0] + e.lat[0] * s2 * (e.hw + OUT), e.p[1] - 0.55,
                    e.p[2] + e.lat[2] * s2 * (e.hw + OUT)];
        const c1 = [f.p[0] + f.lat[0] * s2 * (f.hw + OUT), f.p[1] - 0.55,
                    f.p[2] + f.lat[2] * s2 * (f.hw + OUT)];
        const d1 = [f.p[0] + f.lat[0] * s2 * f.hw, f.p[1] - 0.55, f.p[2] + f.lat[2] * s2 * f.hw];
        solid.quad(a1, b1, c1, d1, shade(conc, -0.16));
        solid.quad(d1, c1, b1, a1, shade(conc, -0.16));
        col.addQuad(a1, b1, c1, d1, KIND.OFFROAD);
      }
      // The ceiling, in `bright`. A downward-facing quad gets nothing from a key
      // light above it and there are no shadow maps, so a "correctly" lit tunnel
      // roof is black - the most obvious thing in the tunnel.
      const wl = e.hw + OUT, wr = f.hw + OUT;
      bright.quad(
        [e.p[0] + e.lat[0] * -wl, roofE, e.p[2] + e.lat[2] * -wl],
        [e.p[0] + e.lat[0] * wl, roofE, e.p[2] + e.lat[2] * wl],
        [f.p[0] + f.lat[0] * wr, roofF, f.p[2] + f.lat[2] * wr],
        [f.p[0] + f.lat[0] * -wr, roofF, f.p[2] + f.lat[2] * -wr],
        shade(conc, -0.62));
      // A strip of lighting down the crown, which is what a real road tunnel has
      // and what stops the ceiling reading as a void.
      if (k % 6 === 0) {
        bright.quad(
          [e.p[0] + e.lat[0] * -1.4, roofE - 0.12, e.p[2] + e.lat[2] * -1.4],
          [e.p[0] + e.lat[0] * 1.4, roofE - 0.12, e.p[2] + e.lat[2] * 1.4],
          [f.p[0] + f.lat[0] * 1.4, roofF - 0.12, f.p[2] + f.lat[2] * 1.4],
          [f.p[0] + f.lat[0] * -1.4, roofF - 0.12, f.p[2] + f.lat[2] * -1.4],
          0xb9b08f);
      }
    }
  }

  /** The pool the Piscine is named after, on the harbour side of that section. */
  function pool(solid, bright, line, H, nx, nz, x0, z0, shade) {
    const i = Math.floor(line.length * 0.80);
    const e = line[i]; if (!e || e.air) return;
    const off = e.hw + 17;
    const cx = e.p[0] + e.lat[0] * -off, cz = e.p[2] + e.lat[2] * -off;
    const gy = fieldAt(H, nx, nz, x0, z0, cx, cz);
    if (gy < SEA + 1) return;
    const W = 13, D = 8;
    solid.box(cx, gy + 0.5, cz, W / 2 + 1.6, 0.5, D / 2 + 1.6, 0xe8e4d8);
    bright.quad([cx - W / 2, gy + 0.92, cz - D / 2], [cx - W / 2, gy + 0.92, cz + D / 2],
                [cx + W / 2, gy + 0.92, cz + D / 2], [cx + W / 2, gy + 0.92, cz - D / 2],
                0x14657a);
    // Loungers along one side, which is the detail that says pool rather than tank.
    for (let k = -2; k <= 2; k++) {
      solid.box(cx + k * 2.6, gy + 1.15, cz + D / 2 + 0.9, 0.5, 0.16, 1.0, 0xf4f2ea);
    }
  }
})();
