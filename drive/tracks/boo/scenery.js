// BOO!: the chapel, the churchyard it stands in, and the crypt under both.
//
// **Why this is a plan and not a corridor.** The first version of this track
// grew its building outward from the road - a hall the same distance from the
// tarmac everywhere - and it was rejected on sight from the car, because a
// corridor that follows you has no parts. The nave, the aisle and the gallery
// all looked identical, so nothing about the lap read as a place.
//
// A building has a *footprint*. The plan lives in `tracks/boo/track.py`, which
// the layout is written against, and it arrives here through `pal.building` -
// so there is one copy of it rather than the two-in-two-languages this repo has
// been bitten by before. Everything below is that plan drawn as axis-aligned
// masonry: an aisled basilica with a square east end, over an undercroft.
//
//        z=-49  ####################################  outer wall, buttressed
//        z=-44  |    north aisle       road y=0   |   vault at y=20
//        z=-24  +--||-----||-----||-----||-----||-+   arcade
//               |                                 |
//        z=  0  |    n a v e           road y=0   |   soffit at y=42
//               |                                 |
//        z= 24  +--||-----||-----||-----||-----||-+   arcade + triforium
//        z= 44  |    south aisle - TRIFORIUM over |   deck y=24, road on it
//        z= 49  ####################################
//               420   464                 790   847
//               door  arcade begins    sanctuary  east gable
//
// **The floor of the world is drawn here too, and that is new.** `ground` is
// None so the crypt can have a void under it, which means `addScenery` plants
// nothing (`if (!onGround) continue` - there is nothing to stand a tree on in
// a void) and `buildTrack` lays no ground quad. So the churchyard is an apron
// stamped round the outdoor road, and every tree and headstone on it is placed
// by this file at the apron's own height. That is also the fix for the props
// that used to hover: the engine stands them at `track.ground`, and there is
// no longer any such number to be wrong about.
//
// **This file is in the collider, not just the picture.** `verify.py` re-drives
// submitted laps through the same `buildTrack`, so a pew clipped in the browser
// has to be clipped on the server too. Everything a car can touch goes through
// `span` with `hit` set, so there is no way to draw masonry and forget to make
// it solid.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.boo = { props: props, movers: movers };

  function props(ctx) {
    // **Every name on this line is used below and none is optional.** A name
    // missing from this destructure is the defect that took out Tokyo Drift's
    // whole city with 58 tests still passing: the name is undefined, the throw
    // is swallowed, and the track builds with no error and no building.
    const { solid, bright, signs, col, track, pal, bbox, KIND, shade,
            mulberry } = ctx;
    const B = ctx.cfg || {};
    const line = track.line, n = line.length;
    const rnd = mulberry(0xb00);

    // ---- the plan ----------------------------------------------------------
    const WX = B.westX, NX = B.narthexX, EX = B.eastX, BX = B.backX;
    const NHW = B.naveHW, CHW = B.colHW, AHW = B.aisleHW;
    const FY = B.floorY, NC = B.naveCeil, AC = B.aisleCeil, TY = B.trifY;
    const EV = B.eaves, RG = B.ridge, T = B.wallT, BAY = B.bay;
    const TT = B.towerTop, ST = B.spireTop;
    const STEPS = 20, GSTEP = 14;  // treads in the nave roof and in the gables
    const TWHW = 24.5;            // the tower's half-width: the narthex,
                                  // square in plan, with the aisle roofs
                                  // landing either side of it
    const DHW = B.doorHW, DH = B.doorH, CY = B.cryptY;
    const wallC = B.wall, innerC = B.inner, stoneC = B.stone;
    const leadC = B.lead, floorC = B.floor, grassC = pal.ground;
    const glassC = B.glass, candleC = B.candle, eastC = B.east, pewC = B.pew;
    const JEWEL = B.jewel || [glassC];
    const bannerC = B.banner, trimC = B.bannerTrim;
    const PARAPET = 3.4;          // how high the gallery's balustrade stands

    // ---- drawing ------------------------------------------------------------
    // One primitive for the whole world: a box given as the two corners it
    // spans. Masonry is written as extents, not as centres and half-extents,
    // because every number in the plan is an extent - converting them by hand
    // at each of two hundred call sites is how a wall ends up half a thickness
    // out. `hit` is 'wall' for masonry, 'deck' for something drivable, 'lit'
    // for an unlit pane, and absent for decoration nothing can touch.
    const span = (x0, x1, y0, y1, z0, z1, colour, hit) => {
      const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, cz = (z0 + z1) / 2;
      const hx = Math.abs(x1 - x0) / 2, hy = Math.abs(y1 - y0) / 2;
      const hz = Math.abs(z1 - z0) / 2;
      if (hx < 1e-4 || hy < 1e-4 || hz < 1e-4) return;
      (hit === 'lit' ? bright : solid).box(cx, cy, cz, hx, hy, hz, colour);
      if (!hit || hit === 'lit') return;
      const P = (sx, sy, sz) => [cx + sx * hx, cy + sy * hy, cz + sz * hz];
      const v = [P(-1,-1,-1), P(1,-1,-1), P(1,-1,1), P(-1,-1,1),
                 P(-1,1,-1), P(1,1,-1), P(1,1,1), P(-1,1,1)];
      // The lid gets the kind asked for. The underside is left off: nothing
      // here can be beneath a floor and above the world.
      //
      // **A deck gets no sides, and that is what made the track drivable.** The
      // apron and the crypt's floor and lid are stamped as one box per row of an
      // 8-unit grid, so a walled deck buries a vertical WALL quad every 8 units
      // of z, topping out at FY - 0.12 - twelve hundredths under the road. The
      // car's collision sphere is 1.25 and its centre rides at 0.45, so every one
      // of those buried faces is inside it and pushes *up*: measured 0.68 units
      // straight up at z = +-4 across the whole churchyard, and the same again
      // the length of the crypt. It reads as the road being bumpy, which is the
      // one thing it is not - the ribbon is dead flat. Masonry still gets sides.
      col.addQuad(v[4], v[7], v[6], v[5], hit === 'deck' ? KIND.OFFROAD : KIND.WALL);
      if (hit !== 'wall') return;
      col.addQuad(v[0], v[4], v[5], v[1], KIND.WALL);
      col.addQuad(v[1], v[5], v[6], v[2], KIND.WALL);
      col.addQuad(v[2], v[6], v[7], v[3], KIND.WALL);
      col.addQuad(v[3], v[7], v[4], v[0], KIND.WALL);
    };

    // Where the piers stand. One list, read by the arcade, the buttresses, the
    // windows, the candles and the crypt, so all five are on the same rhythm -
    // which is what makes a bay read as a bay from the car instead of as five
    // unrelated things that happen to repeat.
    const bays = [];
    for (let x = NX; x <= BX + 0.5; x += BAY) bays.push(x);
    const mids = [];
    for (let k = 0; k + 1 < bays.length; k++) mids.push((bays[k] + bays[k + 1]) / 2);

    // ---- the churchyard apron ----------------------------------------------
    // **The floor of the world, and it is stamped rather than authored.** A
    // rectangle over the bounding box would be a lid over the crypt and a
    // floor under the void; what is wanted is ground where the lap is outdoors
    // and nothing anywhere else. So: stamp every station that is at or near
    // surface level, then punch out everything near a station that is not,
    // which opens the hole the jump falls through and the cutting the crypt
    // climbs out of without either being a number anybody has to keep in step.
    const G = 8.0;
    const gx0 = Math.floor((bbox.x0 - 110) / G), gx1 = Math.ceil((bbox.x1 + 110) / G);
    const gz0 = Math.floor((bbox.z0 - 110) / G), gz1 = Math.ceil((bbox.z1 + 110) / G);
    const GW = gx1 - gx0 + 1, GH = gz1 - gz0 + 1;
    const apron = new Uint8Array(GW * GH);
    const hole = new Uint8Array(GW * GH);
    const near = new Uint8Array(GW * GH);      // too close to the road to plant
    const stamp = (m, px, pz, r, v) => {
      const a0 = Math.max(0, Math.floor((px - r) / G) - gx0);
      const a1 = Math.min(GW - 1, Math.ceil((px + r) / G) - gx0);
      const b0 = Math.max(0, Math.floor((pz - r) / G) - gz0);
      const b1 = Math.min(GH - 1, Math.ceil((pz + r) / G) - gz0);
      const rr = r * r;
      for (let a = a0; a <= a1; a++) {
        const dx = (a + gx0) * G - px;
        for (let b = b0; b <= b1; b++) {
          const dz = (b + gz0) * G - pz;
          if (dx * dx + dz * dz <= rr) m[a * GH + b] = v;
        }
      }
    };
    const SURFACE = -6.0;
    for (let i = 0; i < n; i++) {
      const e = line[i], p = e.p;
      if (p[1] > SURFACE && !e.air) {
        stamp(apron, p[0], p[2], e.hw + 52, 1);
        stamp(near, p[0], p[2], e.hw + 9, 1);
      }
    }
    for (let i = 0; i < n; i++) {
      const e = line[i], p = e.p;
      if (p[1] <= SURFACE || e.air) stamp(hole, p[0], p[2], (e.hw || 7) + 34, 1);
    }
    // **And a tighter punch for the band between the two, which is where the
    // apron used to stand on top of the road.** The sheet is flat at FY - 0.12
    // and `SURFACE` is -6, so every station on a ramp between -6 and the
    // surface got grass laid *over* it - measured 1.85 units proud across seven
    // stations of the climb out of the cutting, which is a kerb grown across
    // the road at the one place the car is flat out. It was always slightly
    // wrong and the shallower climb made it wide enough to see: 8 units of rise
    // over 120 spends ninety of them under a sheet, where 24 over 110 spent
    // thirty. So the rule is the geometry rather than a threshold - anything
    // more than a unit below the apron takes the apron off itself, with just
    // enough radius to clear its own kerb, and what is left beside the ramp is
    // the cutting the road is supposed to be climbing out of.
    for (let i = 0; i < n; i++) {
      const e = line[i], p = e.p;
      if (!e.air && p[1] < FY - 1.0) stamp(hole, p[0], p[2], (e.hw || 7) + 10, 1);
    }
    // The chapel stands on its own slab, so the apron stops at its walls -
    // two coplanar sheets at the same height fight for the same depth.
    const inChapel = (x, z) => x > WX - T - G && x < BX + T + G
                            && z > -AHW - T - G && z < AHW + T + G;
    const isGrass = (a, b) => {
      if (!apron[a * GH + b] || hole[a * GH + b]) return 0;
      return inChapel((a + gx0) * G, (b + gz0) * G) ? 0 : 1;
    };
    // Merged into runs per row. A flat sheet drawn one box per cell is the
    // defect that made `tools/track_views.py` time out and shoot a different
    // track: ~13,000 boxes for what is geometrically a few sheets.
    for (let b = 0; b < GH; b++) {
      let a0 = -1;
      for (let a = 0; a <= GW; a++) {
        const on = a < GW && isGrass(a, b);
        if (on && a0 < 0) a0 = a;
        else if (!on && a0 >= 0) {
          span((a0 + gx0) * G - G / 2, (a - 1 + gx0) * G + G / 2, FY - 3.2, FY - 0.12,
               (b + gz0) * G - G / 2, (b + gz0) * G + G / 2,
               shade(grassC, -0.05 + rnd() * 0.12), 'deck');
          a0 = -1;
        }
      }
    }

    // ---- the chapel floor ---------------------------------------------------
    span(WX - T, BX + T, FY - 3.2, FY - 0.12, -AHW - T, AHW + T, floorC, 'deck');

    // ---- the outer walls ---------------------------------------------------
    for (const s of [-1, 1]) {
      const zi = s * AHW, zo = s * (AHW + T);
      const za = Math.min(zi, zo), zb = Math.max(zi, zo);
      span(WX - T, BX + T, FY - 3.2, EV, za, zb, wallC, 'wall');
      span(WX - T, BX + T, EV, EV + 2.2, za, zb, shade(wallC, -0.10), 'wall');
      for (const x of bays) {
        if (x < WX || x > BX) continue;
        const zf = s * (AHW + T);
        // Two stages, the upper stepped back. Not collided: a face on a wall
        // that is already solid, and the car is on the other side of it.
        span(x - 3.2, x + 3.2, FY - 3.2, FY + 20, zf, zf + s * 7.0, shade(wallC, 0.05));
        span(x - 2.4, x + 2.4, FY + 20, EV + 1.0, zf, zf + s * 4.2, shade(wallC, 0.02));
        span(x - 2.9, x + 2.9, EV + 1.0, EV + 4.6, zf, zf + s * 3.0, shade(wallC, -0.06));
      }
      // **The lancets, and they need masonry round them.** One `bright` box
      // through the wall's whole thickness is lit from the aisle and lit from
      // the churchyard in a single draw, which is right - but on its own, on a
      // wall this dark, the nearest one reads as a large white sheet hanging in
      // mid-air, because there is no visible edge anywhere near it.
      //
      // Two rows. The second exists because the triforium deck is at 24 and the
      // aisle windows top out at 17, so the one storey of this building the lap
      // spends fifteen seconds in had no daylight in it at all.
      const lancet = (x, y0, y1, seed) => {
        // **Glazed in four courses rather than filled with one pane.** The
        // gaps between them are not stone, they are nothing - the dark wall
        // behind shows through a tenth of a unit of daylight and reads as the
        // lead holding the courses apart, which is a line of came for no
        // triangles at all.
        //
        // Which colour goes where is the bay's own index, so the aisle is
        // varied and the *same* varied every lap: a window you drove past is
        // the window you drove past, which is what makes a building a place
        // rather than a texture.
        // **One window is one colour**, in three tones of it, with a single
        // course of something else a third of the way down. Four different hues
        // stacked was the first try and it read as a colour chart nailed to the
        // wall - real glazing is a field of one colour with an accent in it,
        // and which colour is the bay's own business.
        const base = JEWEL[seed % JEWEL.length];
        const accent = JEWEL[(seed + 2) % JEWEL.length];
        const course = [shade(base, 0.10), accent, base, shade(base, -0.12)];
        for (let k = 0; k < 4; k++) {
          const a = y0 + (y1 - y0) * (k / 4), b = y0 + (y1 - y0) * ((k + 1) / 4);
          span(x - 1.9, x + 1.9, a + 0.14, b - 0.14, za, zb, course[k], 'lit');
        }
        span(x - 0.35, x + 0.35, y0, y1, za - 0.3, zb + 0.3, shade(stoneC, -0.06));
        span(x - 1.9, x + 1.9, y1 - 6.0, y1 - 5.3, za - 0.3, zb + 0.3, shade(stoneC, -0.06));
        for (const d of [-1, 1])
          span(x + d * 2.5, x + d * 3.1, y0 - 1.0, y1 + 1.4, za - 0.4, zb + 0.4,
               shade(stoneC, 0.04));
        span(x - 3.1, x + 3.1, y1 + 1.4, y1 + 2.6, za - 0.4, zb + 0.4, shade(stoneC, 0.08));
      };
      mids.forEach((x, i) => {
        if (x < NX || x > BX) return;
        lancet(x, FY + 5.0, FY + 17.0, i);
        if (s > 0) lancet(x, TY + 2.5, EV - 3.5, i + 2);  // the gallery's own row
      });
    }

    // ---- the west front ----------------------------------------------------
    // The great door, built as the three pieces left round it. Cut generously
    // wide: the chase camera trails the car by up to 11.6 units and swings out
    // as it comes through, so it arrives a beat late and off to one side.
    span(WX - T, WX, FY - 3.2, EV, -AHW - T, -DHW, wallC, 'wall');
    span(WX - T, WX, FY - 3.2, EV, DHW, AHW + T, wallC, 'wall');
    span(WX - T, WX, FY + DH, RG, -DHW, DHW, wallC, 'wall');
    // A moulded order round it, so the door is an event rather than a gap.
    for (let k = 0; k < 3; k++) {
      const o = 1.6 + k * 2.0, d = 0.9 + k * 0.7;
      span(WX - T - d, WX - T + 0.4, FY - 3.2, FY + DH + o, -DHW - o, -DHW + o * 0.3,
           shade(stoneC, 0.10 - k * 0.04));
      span(WX - T - d, WX - T + 0.4, FY - 3.2, FY + DH + o, DHW - o * 0.3, DHW + o,
           shade(stoneC, 0.10 - k * 0.04));
      span(WX - T - d, WX - T + 0.4, FY + DH + o - 1.5, FY + DH + o, -DHW - o, DHW + o,
           shade(stoneC, 0.10 - k * 0.04));
    }
    // The west front, which is now the foot of the tower rather than a gable.
    // Above the aisle roofs it steps in once, from the full width of the
    // building to the tower's own - so the aisles read as having roofs that
    // land against something, which is what they are for.
    span(WX - T, WX, EV, EV + 3.0, -(AHW + T), AHW + T,
         shade(wallC, -0.03), 'wall');
    span(WX - T, WX, EV + 3.0, TT, -TWHW - T, TWHW + T, shade(wallC, 0.20));
    // A rose window over the loft: the one thing you see from the gallery
    // looking back west, and the one lit thing on the front as you arrive.
    //
    // **Nine lights and a gold boss**, rather than the one pane it was. A rose
    // is the piece of a west front anybody remembers and it was a grey
    // rectangle; cut into a three by three with the corners darker, the middle
    // row bright and the centre gilded, it reads as tracery from the far end of
    // the nave and as a window from under it. The stone cross over it stays -
    // it is what stops the nine reading as a chequerboard.
    for (const d of [[WX - 0.9, WX + 0.5], [WX - T - 0.5, WX - T + 0.9]]) {
      const y0 = TY + 4.0, y1 = TY + 15.0, zh = 9.0;
      for (let r = 0; r < 3; r++) {
        for (let c = 0; c < 3; c++) {
          const a = y0 + (y1 - y0) * (r / 3), b = y0 + (y1 - y0) * ((r + 1) / 3);
          const za2 = -zh + (zh * 2) * (c / 3), zb2 = -zh + (zh * 2) * ((c + 1) / 3);
          const mid = r === 1 && c === 1;
          // Indigo and ruby only, alternating, with the gold boss in the
          // middle. The full jewel set read as a colour chart from the far end
          // of the churchyard - five hues in nine small panels is a chequer,
          // and a rose wants to be one colour with a heart in it.
          span(d[0], d[1], a + 0.18, b - 0.18, za2 + 0.18, zb2 - 0.18,
               mid ? (B.deco || 0xb8912f) : JEWEL[(r + c) % 2 ? 1 : 0], 'lit');
        }
      }
      span(d[0] - 0.2, d[1] + 0.2, TY + 9.0, TY + 10.0, -9.4, 9.4, shade(stoneC, 0.04));
      span(d[0] - 0.2, d[1] + 0.2, TY + 4.0, TY + 15.0, -0.5, 0.5, shade(stoneC, 0.04));
    }

    // ---- the east gable ----------------------------------------------------
    // Full height, because the sanctuary is open to the roof and this wall is
    // what the whole nave is pointed at. The hole in it is where the gallery
    // stops: the roof has gone at this end, and the lap leaves through it.
    // **It tops out at the eaves and carries a gable over the nave, rather
    // than running to the ridge across the whole width.** It used to be a
    // rectangle 49 units either side of the axis and as tall as the roof's
    // highest point, so the nave roof terraced up *behind* it and the east end
    // of the building was a flat wall with nothing above it. The lintel over
    // the gallery's opening is the south aisle roof, which lands at `EV` and
    // runs to `BX - 2`, so nothing here has to hold the hole's top up.
    const holeA = CHW + 2.0, holeB = AHW - 1.5;
    span(BX, BX + T, FY - 3.2, EV, -AHW - T, holeA, wallC, 'wall');
    span(BX, BX + T, FY - 3.2, TY - 1.5, holeA, AHW + T, wallC, 'wall');
    span(BX, BX + T, FY - 3.2, EV, holeB, AHW + T, wallC, 'wall');
    // The gable itself, on the roof's own taper so the two meet along a line
    // rather than crossing. Decoration: it begins ten units over the highest
    // road on the track.
    for (let k = 0; k < GSTEP; k++) {
      const f = k / GSTEP, g = (k + 1) / GSTEP;
      span(BX, BX + T, EV + (RG - EV) * f, EV + (RG - EV) * g,
           -(CHW + T) * (1 - f), (CHW + T) * (1 - f),
           shade(wallC, -0.03 - f * 0.05));
    }
    // The great east window, which now has a gable over it instead of stopping
    // three units under a flat wall head.
    span(BX - 0.9, BX + 0.5, FY + 30.0, EV + 11.0, -14.0, 14.0, eastC, 'lit');
    span(BX - 1.1, BX + 0.7, FY + 30.0, EV + 11.0, -0.5, 0.5, shade(stoneC, 0.04));

    // ---- the arcades -------------------------------------------------------
    // Piers from the floor to the soffit, with the arches open between them.
    // The bands above are what make the elevation three storeys instead of a
    // row of holes: arcade, then the spandrel the aisle roof lands on, then the
    // triforium, then the wall head.
    for (const s of [-1, 1]) {
      const z = s * CHW, zi = z - s * 2.4, zo = z + s * 2.4;
      const za = Math.min(zi, zo), zb = Math.max(zi, zo);
      const end = s < 0 ? EX : BX;        // the south arcade carries the gallery
      for (const x of bays) {
        if (x > end + 0.5) continue;
        span(x - 3.0, x + 3.0, FY - 3.2, NC, za, zb, stoneC, 'wall');
        span(x - 4.1, x + 4.1, FY + 17.0, FY + 19.2, za - 0.8, zb + 0.8,
             shade(stoneC, 0.10), 'wall');                      // the capital
        span(x - 3.8, x + 3.8, FY - 0.2, FY + 1.4, za - 0.6, zb + 0.6,
             shade(stoneC, 0.06), 'wall');                      // and the base
      }
      // **A parclose screen across every arch, and it is what stops the cut.**
      // The arcade's openings run from the floor to nineteen, which is a
      // thirty-five-unit doorway between the nave and the aisle on every bay -
      // so the whole sanctuary turn, which is the end of the long straight and
      // the one place on the lap you have to brake, could be skipped by
      // driving through an arch. `tools/cut_check.py` called those chords
      // blocked because its ray happened to strike a pier; a car aimed at the
      // gap between two does not. Stone to six, tracery over it, open above -
      // it reads as a screened chapel and a car cannot get through it.
      for (const x of mids) {
        if (x > end - BAY * 0.5) continue;
        const half = BAY * 0.5 - 3.0;
        span(x - half, x + half, FY - 0.2, FY + 6.0, za + 0.5, zb - 0.5,
             shade(stoneC, -0.08), 'wall');
        span(x - half, x + half, FY + 6.0, FY + 6.9, za, zb,
             shade(stoneC, 0.08), 'wall');                      // the cresting
        for (let k = 0; k * 4.6 < half * 2 - 1.0; k++)          // the mullions
          span(x - half + 0.6 + k * 4.6, x - half + 1.5 + k * 4.6,
               FY + 6.9, FY + 17.0, za + 0.9, zb - 0.9,
               shade(stoneC, -0.02), 'wall');
      }

      // The arch heads themselves, stepped, so the openings are pointed rather
      // than rectangular. Four courses is enough at the speed you pass them.
      for (const x of mids) {
        if (x > end - BAY * 0.5) continue;
        for (let k = 0; k < 4; k++) {
          const w = BAY * 0.5 - 3.0 - k * (BAY * 0.5 - 4.0) / 4;
          span(x - w, x + w, FY + 19.2 + k * 0.7, FY + 19.2 + (k + 1) * 0.7,
               za, zb, shade(stoneC, -0.03 - k * 0.02), 'wall');
        }
      }
      span(NX - 3.0, end, AC, TY, za, zb, shade(stoneC, -0.06), 'wall');
      // The balustrade. On the south it is the only thing between the gallery
      // road and a twenty-four-unit drop into the nave, and it has to be
      // scenery rather than a ribbon `rail`, because `test_barriers_are_opt_in`
      // counts walled *stations* and a quarter of this track's are spent in the
      // crypt already.
      span(NX - 3.0, end, TY, TY + PARAPET, za, zb, shade(stoneC, 0.04), 'wall');
      span(NX - 3.0, end, NC - 2.4, NC, za, zb, shade(stoneC, -0.10), 'wall');
      // North side only: blind above the arcade, because there is no gallery
      // behind it to see into and an opening would look into dead roof space.
      if (s < 0) span(NX - 3.0, end, TY + PARAPET, NC - 2.4, za, zb,
                      shade(stoneC, -0.14), 'wall');
    }

    // ---- the decks ---------------------------------------------------------
    // The triforium over the south aisle, and the loft across the west end over
    // the door you came in through. Both are the road's floor, so both are
    // OFFROAD: running off the gallery road lands you on lead, not in the nave.
    // **Stopped short of the east wall, because the jump starts inside it.**
    // The gap's drop begins at x~841, six units before the gable, so the last
    // two stations of road were *under* this slab and the car flew into its end
    // face at 20..24 on the way out. The deck ends where the road leaves level.
    span(NX - 4.0, BX - 8, AC, TY - 0.15, CHW, AHW, leadC, 'deck');
    // **Stopped twelve short of the arcade, because the ramp is still climbing
    // there.** The road comes up out of the north aisle and reaches TY at
    // x=457; this slab used to begin at NX=464, where the road is at 23.7 and
    // the slab's top is 23.85 - so its end face stood a fifth of a unit proud
    // across the whole width of the ramp and simply stopped the car. A floor
    // the road drives onto has to begin where the road has finished climbing.
    span(WX, NX - 12, AC, TY - 0.15, -AHW, AHW, leadC, 'deck');
    span(WX, NX, TY, TY + PARAPET, -AHW, -AHW + 1.6, shade(stoneC, 0.04), 'wall');
    span(WX, NX, TY, TY + PARAPET, AHW - 1.6, AHW, shade(stoneC, 0.04), 'wall');

    // ---- the thing at the gable --------------------------------------------
    // **There is nothing here now, and that is the fix.**
    //
    // The jump used to have a face hanging in it: a hollow ring of masonry on
    // the flight path, no collider, drawn so you flew through it. Two goes at
    // it, and both failed the same way. Drawn `bright` it was self-lit, which
    // on a midnight track makes it the brightest object in the world - you came
    // down the gallery with it in the gap ahead of you for four seconds,
    // decided what it was, and arrived. Drawn `solid` and revealed by the storm
    // flash it was better and still not a fright, because the thing is *static*
    // and you are the one moving: it grows on you at the speed of your own car,
    // which is the speed everything else grows at.
    //
    // A jumpscare is something that moves at you, and nothing in the world can.
    // A `Movers` entry is posed off the physics step index, so where it is when
    // you leave the roof depends on how you drove the four hundred units before
    // it - at the far end of its sweep about as often as the near one, which is
    // a coincidence rather than a scare. So the scare is not in the world at
    // all: it is a screen overlay, lunged at the camera by `jumpscare()` in
    // `game.js` off the same `onThunder('scare')` the shriek comes from. The
    // storm spot at the lip of the gable (`palette.py`) is what fires both.
    //
    // The gap is left empty on purpose. It is the one place on this track where
    // a lap can be lost outright, and something in it is a thing to look at
    // exactly when you need to be looking at the landing.

    // ---- the aisle vault ---------------------------------------------------
    // **The one thing derived rather than authored.** The lap climbs out of the
    // north aisle to reach the gallery, so the vault cannot be there - and
    // rather than authoring the x where it stops (a third copy of a fact
    // `track.py` and the ribbon already hold between them), it is laid where
    // the road is not above it. The bays whose roof has fallen in are then
    // exactly the bays the road climbs through, for any layout.
    const CELL = 8.0;
    const bucket = (x) => Math.round((x - WX) / CELL);
    const climbs = new Set();
    for (let i = 0; i < n; i++) {
      const p = line[i].p;
      if (p[0] < WX - CELL || p[0] > BX + CELL) continue;
      if (p[1] < AC - 6.0) continue;
      const side = p[2] < 0 ? 'n' : 's';
      for (let d = -3; d <= 3; d++) climbs.add(side + (bucket(p[0]) + d));
    }
    const vaultC = shade(innerC, -0.34);
    {
      let a = null;
      for (let x = NX; x <= EX + CELL; x += CELL) {
        const ok = x <= EX && !climbs.has('n' + bucket(x));
        if (ok && a === null) a = x;
        else if (!ok && a !== null) {
          span(a, x, AC, AC + 1.6, -AHW, -CHW, vaultC);
          col.addQuad([a, AC, -AHW], [x, AC, -AHW], [x, AC, -CHW], [a, AC, -CHW],
                      KIND.WALL);
          a = null;
        }
      }
    }

    // ---- the roofs ---------------------------------------------------------
    // Flat lead behind the parapets over the aisles, which is what an English
    // church actually has, and two boxes instead of a stepped lean-to.
    span(NX - T, EX, EV - 1.4, EV, -AHW - T, -CHW, leadC);
    // **The south one runs to the gable now, and stopping it short was a hole
    // in the ceiling you drive under.** It ended at `BX - 30` while the gallery
    // deck it covers runs to `BX - 8`, so the last twenty-two units of the
    // upstairs road - the run at the exit, where you are looking ahead at the
    // gap rather than up - had open black over it.
    //
    // Safe to extend because this slab is decoration: no `hit` argument, so it
    // is not in the collider, and the lap leaves through the opening in the
    // east gable at y 22-24 while the lead sits at 34.6. It is stopped two
    // units short of the wall so the join still reads as a roof meeting
    // masonry rather than as one box.
    span(NX - T, BX - 2.0, EV - 1.4, EV, CHW, AHW + T, leadC);
    span(NX - 4.0, BX, NC, NC + 1.6, -CHW, CHW, vaultC);
    col.addQuad([NX - 4, NC, -CHW], [BX, NC, -CHW], [BX, NC, CHW], [NX - 4, NC, CHW],
                KIND.WALL);
    span(WX, NX, NC, NC + 1.6, -AHW, AHW, vaultC);
    col.addQuad([WX, NC, -AHW], [NX, NC, -AHW], [NX, NC, AHW], [WX, NC, AHW],
                KIND.WALL);
    // The ridge roof. **The two slopes overlap past the centreline rather than
    // stopping short of it**: tapering to a positive width left a five-unit
    // slot the length of the nave, invisible from inside and, from above, the
    // whole interior drawn in `plan.png` with no roof over it.
    // **Twenty steps, not seven.** Seven treads across 26.5 units is a 3.8-unit
    // terrace every two units of climb, which from any establishing height is a
    // ziggurat - and `shoot_tracks.py` looks at this building from above. At
    // twenty the tread is 1.3 and it reads as a slope from the churchyard and
    // as a roof from the cover. The cost is 26 boxes instead of 12, in a file
    // that draws two thousand.
    for (let k = 0; k < STEPS; k++) {
      const f = k / STEPS, g = (k + 1) / STEPS;
      const w0 = (CHW + T) * (1 - f), w1 = (CHW + T) * (1 - g);
      const y0 = EV + (RG - EV) * f, y1 = EV + (RG - EV) * g;
      span(NX - T, BX - 24.0, y0, y1, -w0, -w1 + 1.2, shade(leadC, 0.06 - f * 0.04));
      span(NX - T, BX - 24.0, y0, y1, w1 - 1.2, w0, shade(leadC, 0.02 - f * 0.04));
    }
    // And the ribs on the underside of it, which is most of what you see of a
    // vault from a car with headlights pointed forward.
    for (const x of bays) {
      if (x < NX || x > BX) continue;
      span(x - 1.5, x + 1.5, NC - 1.3, NC, -CHW, CHW, shade(vaultC, 0.16));
    }

    // ---- the west tower and its spire --------------------------------------
    // **The thing that makes it a church from outside.** The building was a box
    // with a terraced lid: eaves at 36, the highest point of it 50, and no part
    // of the silhouette that arrived at a point. This stands over the narthex -
    // the one bay you drive *through* on the way in, square in plan and already
    // walled on all four sides at ground level, so the tower is those walls
    // continued rather than new footings in the churchyard.
    //
    // **It is lit like the landmark it is, which is not how the rest of the
    // building is lit.** The key light points down and there are no shadow
    // maps, so a vertical face 80 units up catches almost nothing, and the
    // first pass drew the whole tower at the masonry's own value: it came out
    // the same lightness as the sky behind it and simply was not in the
    // picture. Everything here is shaded well up from `wall`, `stone` and
    // `lead` for that reason, and the belfry louvres are `lit` on top of it.
    //
    // **It is decoration, all of it.** The lowest thing here is at `EV + 3`,
    // fifteen units over the gallery deck, which is the highest road on the
    // track. Nothing can reach it, so none of it is in the collider and the
    // whole tower costs the anti-cheat nothing.
    const TWO = TWHW + T;
    for (const [z0, z1] of [[-TWO, -TWHW], [TWHW, TWO]]) {
      span(WX - T, NX, EV + 3.0, TT, z0, z1, shade(wallC, 0.20));
    }
    span(NX - T, NX, EV + 3.0, TT, -TWO, TWO, shade(wallC, 0.20));
    // Clasping buttresses at the four corners, stepped back twice. Without them
    // the tower is a chimney: a plain box is read as scaffolding at this height.
    for (const sx of [-1, 1]) {
      for (const sz of [-1, 1]) {
        const x = sx < 0 ? WX - T : NX, z = sz < 0 ? -TWO : TWO;
        for (let k = 0; k < 3; k++) {
          const d = 4.2 - k * 1.2, top = EV + 3.0 + (TT - EV - 3.0) * (0.42 + k * 0.22);
          span(x - (sx < 0 ? d : 0), x + (sx < 0 ? 0 : d), EV + 3.0, top,
               z - (sz < 0 ? d : 0), z + (sz < 0 ? 0 : d),
               shade(stoneC, 0.22 - k * 0.05));
        }
      }
    }
    // The belfry. Two tall louvres a side, and they are `lit` on purpose: this
    // is the only thing on the track standing above the fog, the sky behind it
    // is nearly black, and an unlit stone box at 80 units simply is not there.
    // Lit, the tower is what you steer at from the churchyard.
    for (const sz of [-1, 1]) {
      for (const o of [-10.0, 10.0]) {
        span(WX + 8.0 + o, WX + 20.0 + o, TT - 26.0, TT - 8.0,
             sz * TWO - sz * 0.9, sz * TWO, candleC, 'lit');
      }
    }
    for (const sx of [-1, 1]) {
      for (const o of [-10.0, 10.0]) {
        const x = sx < 0 ? WX - T : NX;
        span(x, x + sx * 0.9, TT - 26.0, TT - 8.0, o - 6.0, o + 6.0, candleC, 'lit');
      }
    }
    // The parapet, which is what the spire springs from. Corbelled out a unit
    // and a half so the spire does not look like it grew out of the wall.
    span(WX - T - 1.5, NX + 1.5, TT - 2.6, TT, -TWO - 1.5, TWO + 1.5,
         shade(stoneC, 0.34));
    // Pinnacles at the four corners of the parapet. They are what lets the
    // needle spring from a base narrower than the tower without the shoulders
    // reading as a mistake - the spire steps in, and something stands in the
    // corner it stepped out of.
    for (const sx of [-1, 1]) {
      for (const sz of [-1, 1]) {
        const x = sx < 0 ? WX - T + 3.4 : NX - 3.4, z = sz * (TWO - 3.4);
        for (let k = 0; k < 9; k++) {
          const f = k / 9, w = 3.4 * (1 - f * 0.92);
          span(x - w, x + w, TT + 14.0 * f, TT + 14.0 * (f + 1 / 9),
               z - w, z + w, shade(stoneC, 0.18 - f * 0.04), f > 0.5 ? 'lit' : 0);
        }
      }
    }
    // **The needle.** Seventy-two units over a 39-wide base, tapered to a point
    // over twenty-eight treads - the same trick as the nave roof and for the
    // same reason, that anything coarser reads as a stack of boxes. Lead rather
    // than stone, because it is the one surface up here the moon gets to and it
    // wants to be the lighter of the two.
    const SPIRE = 28, SBASE = TWO * 0.66;
    for (let k = 0; k < SPIRE; k++) {
      const f = k / SPIRE, g = (k + 1) / SPIRE;
      const w0 = SBASE * (1 - f);
      const y0 = TT + (ST - TT) * f, y1 = TT + (ST - TT) * g;
      // **The whole needle is `lit`, and the edge trim it used to carry is
      // gone.** Two passes got this wrong in opposite directions. Shaded
      // masonry disappears: the key points down, so a near-vertical face 80
      // units up is lit to about the sky's own value whatever colour it is
      // given, and the top of the spire dissolved into the violet above the
      // sky's bright band. Then lighting only the four arrises drew the
      // stepping as a white zigzag down each edge - the treads are a couple of
      // pixels at this distance and it read as debris on the roof rather than
      // as a hip. An unlit face is flat by definition, so the cone holds one
      // even value from base to finial and its outline is its outline.
      //
      // **Unlit is not a licence to be bright, and the number you write is
      // not the number you get.** At `shade(leadC, 0.40)` this was the
      // lightest surface anywhere on the track - a white cone over a black
      // churchyard - because an unlit face is drawn at full value while
      // everything round it is shaded down. Dropping it to a slate `0.16`
      // barely moved it, which is the second half of the trap: an unlit colour
      // is lifted linear->sRGB on the way out and the lift is enormous at the
      // dark end, so #5b6267 leaves the shader at about #b0b4b8. It is the
      // same defect Rickety Rails' roof has, with the sign flipped. Going
      // *under* `leadC` is what actually darkens it: -0.42 is #24292c in
      // source and reads as a mid grey on screen, which separates from both
      // the violet above the sky's bright band and the deck's 0x372a4d without
      // being a lamp.
      const cx = (WX - T + NX) / 2, hx0 = ((NX - WX + T) / 2) * 0.66;
      span(cx - hx0 * (1 - f), cx + hx0 * (1 - f), y0, y1, -w0, w0,
           shade(leadC, -0.42 - f * 0.06), 'lit');
    }
    // And a cross, because a needle that just stops is a needle that was cut.
    //
    // **It has to actually be one.** The first version was a six-by-six block
    // with a pin standing on it, which at this distance is a bollard on the
    // roof: the thing that makes a cross legible is the *arm*, and it did not
    // have one. A shaft a unit and a half thick with a five-unit arm across it
    // reads from the churchyard and costs three boxes. The arm runs in z
    // because the west front faces down the lap and z is across your view from
    // the only place anybody sees it from.
    const FCX = (WX - T + NX) / 2, CX = 0.75;
    span(FCX - 1.7, FCX + 1.7, ST - 0.9, ST + 0.9, -1.7, 1.7,
         shade(stoneC, 0.22), 'lit');                       // where it is bedded
    span(FCX - CX, FCX + CX, ST, ST + 8.0, -CX, CX, shade(stoneC, 0.26), 'lit');
    span(FCX - CX, FCX + CX, ST + 4.6, ST + 6.1, -2.6, 2.6,
         shade(stoneC, 0.26), 'lit');

    // ---- the fittings ------------------------------------------------------
    // **Pews, and they are pews rather than blocks.** A bench is a seat, a back
    // and two ends, and at four boxes each that is the difference between a
    // nave with furniture in it and a nave with crates in it. They are solid:
    // the nave is thirty-eight wide with a sixteen-unit road down it, so there
    // is room to run wide and something there to regret it with.
    //
    // **And they are the barrier that closes the sanctuary cut, which is why
    // they run the length of the nave and leave no gap a car fits through.**
    // `tools/cut_check.py` had one open paying chord on this track: straight out
    // of the nave at x=757, through an arcade opening, into the north aisle -
    // 34 units of floor to skip 127 units of road, where about 2x pays. A
    // checkpoint cannot close it (the only place a gate would help is the
    // hairpin apex, and `test_gates_have_straight_road_either_side` wants ten
    // units of unrolled straight either side of one) and neither can a rail on
    // the apex, because the cut crosses a whole bay rather than one corner. The
    // pews already stood across it and the chord threaded *between two rows*:
    // benches 6.4 long on a 9.2 pitch leave 2.8-unit gaps, and the car's
    // collision sphere is 2.5 across. 9.4 on a 9.2 pitch leaves none at all -
    // and it has to be *none*, because `cut_check`'s chord is a zero-width line
    // and threads a 0.4-unit slot the car could never take. They overlap by two
    // tenths rather than meeting exactly, so the coincident ends do not fight.
    // The east limit moved with them - the choir is pewed up to the sanctuary
    // step now, because a chord starting past the last row is one that gets out.
    for (let x = NX + 12; x < EX - 8; x += 9.2) {
      for (const s of [-1, 1]) {
        const zn = s * 11.6, zf = s * 18.6;
        const za = Math.min(zn, zf), zb = Math.max(zn, zf);
        const sag = rnd() * 0.35;
        span(x - 4.7, x + 4.7, FY + 1.5 - sag, FY + 2.1 - sag, za, zb, pewC, 'wall');
        span(x - 4.7, x + 4.7, FY + 2.1 - sag, FY + 4.3 - sag, za, za + 0.7,
             shade(pewC, 0.05), 'wall');                       // the back
        for (const e of [za, zb])
          span(x - 4.7, x + 4.7, FY, FY + 2.4, e - 0.35, e + 0.35,
               shade(pewC, -0.06), 'wall');                    // the ends
      }
    }
    // **The sanctuary step and the altar, and both are behind the hairpin.**
    // They were not: the step ran from x=798 and the altar stood at x=821, and
    // the 180 round the sanctuary reaches x=810 with eight units of road either
    // side of it. So the step was a 1.1-unit kerb laid across the apex - which
    // on nine degrees of bank stands 2.1 proud on the outside - and the altar
    // was a solid block three units off the road edge, in front of the painting
    // the whole nave is aimed at. Everything here now starts past x=823, four
    // clear of the outer edge of the widest station in the turn.
    span(823, BX - 3, FY, FY + 1.1, -16, 16, shade(floorC, -0.10), 'deck');
    span(BX - 11, BX - 5, FY + 1.1, FY + 4.6, -5.0, 5.0, shade(stoneC, 0.12), 'wall');
    // Candles on every other pier. What actually lights the nave is `pal.lamps`
    // - see `Lamps` in render.js - because a self-lit box in a black room is a
    // speck, and the reference is a hall with pools of light in it.
    for (let k = 0; k < bays.length; k += 2) {
      const x = bays[k];
      if (x > EX) continue;
      for (const s of [-1, 1]) {
        span(x - 0.8, x + 0.8, FY + 19.4, FY + 21.6, s * (CHW - 3.2), s * (CHW - 1.6),
             candleC, 'lit');
        span(x - 1.3, x + 1.3, FY + 18.8, FY + 19.4, s * (CHW - 3.6), s * (CHW - 1.2),
             shade(stoneC, -0.20));
      }
    }

    // ---- banners -----------------------------------------------------------
    // **The only soft thing in the building, and the only red.** A chapel of
    // grey stone lit by amber candles has no colour in it between the glass and
    // the altarpiece, and the nave is the fifteen seconds of the lap where
    // there is most time to look. These hang on the nave face of the piers the
    // candles skip, so the two alternate down the arcade rather than crowding
    // the same bay - and they hang *below* the candles, which is what keeps a
    // pier reading as one thing with a lamp above and a cloth under it.
    //
    // Two boxes each: the cloth, and a gold hem across the foot. The hem is
    // what stops it reading as a painted rectangle - a banner ends in a weight.
    for (let k = 1; k < bays.length; k += 2) {
      const x = bays[k];
      if (x > EX) continue;
      for (const s of [-1, 1]) {
        const z0 = s * (CHW - 3.5), z1 = s * (CHW - 3.2);
        span(x - 2.4, x + 2.4, FY + 7.0, FY + 16.2, z0, z1, bannerC);
        span(x - 2.4, x + 2.4, FY + 6.4, FY + 7.0, z0 - s * 0.1, z1 + s * 0.1, trimC);
        span(x - 2.6, x + 2.6, FY + 16.2, FY + 16.8, z0 - s * 0.1, z1 + s * 0.1,
             shade(stoneC, -0.16));
      }
    }

    // ---- the coronas -------------------------------------------------------
    // Three iron rings hung over the middle of the nave on chains off the
    // vault, each carrying eight candles.
    //
    // **Hung at 27, which is the one height that works.** The vault is at 42
    // and the gallery deck at 24: higher and the ring is lost in the dark of
    // the roof, lower and the chase camera - which rides four units over the
    // car and swings wide through a corner - clips through it. There is no
    // collider on any of this for the same reason the altarpiece has none: it
    // is over the road, and the one thing that must never change on this track
    // is what the car can hit.
    //
    // The candles are `lit` boxes rather than `Lamps` emitters, and that is
    // deliberate. An emitter would want its position in the palette as a
    // fraction of the lap while the ring is here in world x - the same plan
    // written twice in two languages, which is the mistake this file's own
    // header warns about. The nave already has eight real lights in it; what
    // the coronas owe the picture is shape.
    for (let k = 2; k < bays.length - 1; k += 3) {
      const x = bays[k];
      if (x < NX || x > EX) continue;
      const ry = FY + 27.0, rr = 6.4, ironC = shade(stoneC, -0.30);
      // Two chains up into the dark, so it is hung rather than floating.
      for (const d of [-1, 1])
        span(x - 0.22, x + 0.22, ry + 1.2, NC, d * 2.2 - 0.22, d * 2.2 + 0.22, ironC);
      // The ring, as four bars.
      span(x - rr, x + rr, ry, ry + 1.2, -rr, -rr + 0.7, ironC);
      span(x - rr, x + rr, ry, ry + 1.2, rr - 0.7, rr, ironC);
      span(x - rr, x - rr + 0.7, ry, ry + 1.2, -rr, rr, ironC);
      span(x + rr - 0.7, x + rr, ry, ry + 1.2, -rr, rr, ironC);
      // Eight candles round it, each with a pale tip where a flame would be.
      const seats = [[-1, -1], [-1, 0], [-1, 1], [0, -1], [0, 1], [1, -1], [1, 0], [1, 1]];
      for (const [a, b] of seats) {
        const cx = x + a * (rr - 0.35), cz = b * (rr - 0.35);
        span(cx - 0.3, cx + 0.3, ry + 1.2, ry + 2.9, cz - 0.3, cz + 0.3, candleC, 'lit');
        span(cx - 0.16, cx + 0.16, ry + 2.9, ry + 3.5, cz - 0.16, cz + 0.16, eastC, 'lit');
      }
    }

    // ---- the crypt ---------------------------------------------------------
    // Under the nave, with the chapel's own floor as its ceiling and nothing
    // whatever underneath. Both the floor it has and the lid over it are
    // stamped off the ribbon rather than authored, so the only two openings in
    // the churchyard are the hole the jump falls through and the cutting the
    // road climbs out of - and neither is a number anybody has to keep in step.
    const cryptFloor = [];
    for (let i = 0; i < n; i++) {
      const e = line[i];
      if (!e.air && e.p[1] < CY + 24) cryptFloor.push(e);
    }
    if (cryptFloor.length) {
      // **Nothing rolled gets a floor, and that is the fix for a wall you could
      // hit and for the flagstones that came up through the hairpin.** A banked
      // cross-section sinks its low edge by `hw * sin(bank)` - 6.5 units of
      // half-width at the twelve degrees the crypt hairpin was banked at is 1.35
      // below the slab the straight either side of it stands on, so a third of
      // the road's width was under a flat sheet of flagstones and the inside of
      // every lap scraped along their top edge. Measured 1.23 proud at station
      // 533. It is the same defect as the wall of death's, which is why they are
      // now one rule rather than a `wrad` special case: `lat[1]` is the roll the
      // ribbon actually has, so a corner that is banked, a wall, or anything
      // added later that tilts, all get an open shaft under them instead of a
      // rim to catch. Below is a void on this track anyway.
      const flat = cryptFloor.filter((e) => Math.abs((e.lat || [0, 0, 1])[1]) < 0.02
                                            && Math.abs(e.p[1] - CY) < 4.0);
      const cf = new Uint8Array(GW * GH);      // floor: only the level stretches
      const lid = new Uint8Array(GW * GH);     // ceiling: everywhere underground
      const open = new Uint8Array(GW * GH);    // ...except where the road comes up
      for (const e of flat) stamp(cf, e.p[0], e.p[2], e.hw + 30, 1);
      // **And then punched back out, because leaving a rolled station unstamped
      // is not the same as having no floor under it.** Every stamp reaches 30
      // units past its own road edge, so the level straight either side of a
      // banked corner lays flagstones straight through it whatever the corner
      // itself asked for - which is why excluding the wall of death from `flat`
      // never actually opened its shaft, and why the hairpin still measured 0.96
      // proud after it was excluded too. Clearing wins over stamping here: the
      // slab ends up 16 units clear of any rolled road edge, and what is under
      // the tilted parts of this crypt is the void, which is what they should
      // have been standing over from the start.
      for (const e of cryptFloor)
        if (Math.abs((e.lat || [0, 0, 1])[1]) >= 0.02)
          stamp(cf, e.p[0], e.p[2], e.hw + 16, 0);
      for (const e of cryptFloor) stamp(lid, e.p[0], e.p[2], e.hw + 44, 1);
      for (let i = 0; i < n; i++) {
        const e = line[i];
        if (e.p[1] > CY + 26 || e.air) stamp(open, e.p[0], e.p[2], (e.hw || 7) + 30, 1);
      }
      const rows = (m, y0, y1, colour, hit, skipChapel) => {
        for (let b = 0; b < GH; b++) {
          let a0 = -1;
          for (let a = 0; a <= GW; a++) {
            let on = a < GW && m[a * GH + b] && !open[a * GH + b];
            if (on && skipChapel && inChapel((a + gx0) * G, (b + gz0) * G)) on = false;
            if (on && a0 < 0) a0 = a;
            else if (!on && a0 >= 0) {
              span((a0 + gx0) * G - G / 2, (a - 1 + gx0) * G + G / 2, y0, y1,
                   (b + gz0) * G - G / 2, (b + gz0) * G + G / 2, colour, hit);
              a0 = -1;
            }
          }
        }
      };
      rows(cf, CY - 2.6, CY - 0.12, shade(floorC, -0.46), 'deck', false);
      // The lid. Under the chapel it is already there - that is the chapel's
      // own floor - so this is only the part of the crypt that runs out past
      // the east wall, and from the churchyard it reads as a flagged plot with
      // a hole in it.
      rows(lid, FY - 3.2, FY - 0.12, shade(floorC, -0.30), 'deck', true);

      // The undercroft: piers on the bays' own rhythm with arches turned
      // between them, which is what stops this being a car park. Off the road
      // by the same rule the churchyard's trees use.
      const onRoad = (x, z, pad) => {
        for (const e of cryptFloor) {
          const dx = e.p[0] - x, dz = e.p[2] - z;
          if (dx * dx + dz * dz < (e.hw + pad) * (e.hw + pad)) return true;
        }
        return false;
      };
      const under = (x, z) => {
        const a = Math.round(x / G) - gx0, b = Math.round(z / G) - gz0;
        return a >= 0 && b >= 0 && a < GW && b < GH
            && (lid[a * GH + b] || cf[a * GH + b]) && !open[a * GH + b];
      };
      const pierC = shade(stoneC, -0.30);
      for (let x = 600; x < 1090; x += 21) {
        for (let z = -86; z <= 48; z += 21) {
          if (!under(x, z) || onRoad(x, z, 9)) continue;
          const top = inChapel(x, z) ? FY - 3.2 : FY - 3.2;
          span(x - 2.1, x + 2.1, CY - 3.0, top - 5.0, z - 2.1, z + 2.1, pierC, 'wall');
          span(x - 2.9, x + 2.9, top - 5.0, top - 3.6, z - 2.9, z + 2.9,
               shade(pierC, 0.10), 'wall');                         // the capital
          // Four stubby arch springers, so the ceiling lands on something.
          for (const d of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
            span(x + d[0] * 2.6 - 1.2, x + d[0] * 2.6 + 1.2, top - 3.6, top,
                 z + d[1] * 2.6 - 1.2, z + d[1] * 2.6 + 1.2, shade(pierC, 0.04));
          }
        }
      }
      // What is down here. Sarcophagi on the floor, iron stands with a candle
      // on them, and a skull on about a third of the lids.
      let q = 0;
      for (let x = 606; x < 1090; x += 21) {
        for (let z = -80; z <= 44; z += 21) {
          if (!under(x, z) || onRoad(x, z, 8)) continue;
          const r = rnd();
          if (r < 0.34) {
            const c = shade(stoneC, -0.26 + rnd() * 0.14);
            span(x - 4.7, x + 4.7, CY, CY + 2.2, z - 1.9, z + 1.9, c, 'wall');
            span(x - 4.8, x + 4.8, CY + 2.2, CY + 3.0, z - 2.3, z + 2.3,
                 shade(c, 0.12), 'wall');
            if (rnd() < 0.4) {
              span(x - 0.8, x + 0.8, CY + 3.0, CY + 4.3, z - 0.8, z + 0.8, 0xd8d2c0, 'lit');
              for (const s2 of [-1, 1])
                span(x - 0.35, x + 0.35, CY + 3.6, CY + 4.0,
                     z + s2 * 0.5 - 0.2, z + s2 * 0.5 + 0.2, 0x14161a, 'lit');
            }
          } else if (r < 0.50) {
            // A pricket stand. `bright`, so it glows; what actually lights the
            // crypt is `pal.lamps`, because an unlit box in a black room is a
            // speck rather than a source.
            span(x - 1.5, x + 1.5, CY, CY + 0.5, z - 1.5, z + 1.5, pal.prop2, 'wall');
            span(x - 0.4, x + 0.4, CY + 0.5, CY + 6.4, z - 0.4, z + 0.4, pal.prop2, 'wall');
            span(x - 1.2, x + 1.2, CY + 6.4, CY + 6.9, z - 1.2, z + 1.2, pal.prop2);
            span(x - 0.7, x + 0.7, CY + 6.9, CY + 8.4, z - 0.7, z + 0.7, candleC, 'lit');
          } else if (r < 0.60) {
            // A bricked-up niche with bones stacked in it.
            for (let k = 0; k < 3; k++)
              span(x - 3.0, x + 3.0, CY + 0.4 + k * 1.3, CY + 1.4 + k * 1.3,
                   z - 1.0, z + 1.0, shade(0xcfc6ad, -0.10 - k * 0.06), 'lit');
          }
          q++;
        }
      }
    }

    // ---- the churchyard ----------------------------------------------------
    // Planted on the apron, at the apron's own height, which is the whole of
    // why nothing here hovers. `near` keeps it off the road; `isGrass` keeps it
    // off the holes and off the chapel.
    const plantable = (x, z) => {
      const a = Math.round(x / G) - gx0, b = Math.round(z / G) - gz0;
      if (a < 1 || b < 1 || a >= GW - 1 || b >= GH - 1) return false;
      if (!isGrass(a, b) || near[a * GH + b]) return false;
      for (let d = -1; d <= 1; d++)
        for (let f = -1; f <= 1; f++) if (!isGrass(a + d, b + f)) return false;
      return true;
    };
    const headstone = (x, z, s) => {
      const w = 0.9 + rnd() * 0.9, h = 2.6 + rnd() * 3.4;
      const c = shade(stoneC, -0.06 + rnd() * 0.34);
      span(x - w - 0.4, x + w + 0.4, FY - 0.3, FY + 0.5, z - 0.9, z + 0.9, shade(c, -0.14), 'wall');
      span(x - w, x + w, FY + 0.5, FY + h, z - 0.45, z + 0.45, c, 'wall');
      span(x - w * 0.7, x + w * 0.7, FY + h, FY + h + w * 0.6, z - 0.45, z + 0.45, c, 'wall');
    };
    const tomb = (x, z) => {
      const c = shade(stoneC, -0.12 + rnd() * 0.18);
      span(x - 3.4, x + 3.4, FY - 0.3, FY + 2.2, z - 1.9, z + 1.9, c, 'wall');
      span(x - 3.9, x + 3.9, FY + 2.2, FY + 3.0, z - 2.3, z + 2.3, shade(c, 0.10), 'wall');
      for (const d of [-1, 1]) for (const f of [-1, 1])
        span(x + d * 3.0 - 0.4, x + d * 3.0 + 0.4, FY, FY + 3.6,
             z + f * 1.5 - 0.4, z + f * 1.5 + 0.4, shade(c, -0.10), 'wall');
    };
    const yew = (x, z) => {
      const c = pal.prop, h = 9 + rnd() * 11;
      span(x - 1.0, x + 1.0, FY, FY + h * 0.55, z - 1.0, z + 1.0, shade(c, 0.06), 'wall');
      // Three limbs, each a short stack leaning out - `span` is axis-aligned,
      // so a branch is steps rather than a line, which at this palette's values
      // is a silhouette either way.
      for (let k = 0; k < 3; k++) {
        const a = rnd() * Math.PI * 2, r0 = 1.0 + rnd() * 1.4;
        let px = x, pz = z, py = FY + h * 0.5;
        for (let j = 0; j < 4; j++) {
          const nx = px + Math.cos(a) * r0, nz = pz + Math.sin(a) * r0;
          span(Math.min(px, nx) - 0.5, Math.max(px, nx) + 0.5, py, py + h * 0.14,
               Math.min(pz, nz) - 0.5, Math.max(pz, nz) + 0.5, shade(c, 0.02 * j));
          px = nx; pz = nz; py += h * 0.12;
        }
      }
    };
    for (let a = 2; a < GW - 2; a += 1) {
      for (let b = 2; b < GH - 2; b += 1) {
        const x = (a + gx0) * G + (rnd() - 0.5) * G * 0.7;
        const z = (b + gz0) * G + (rnd() - 0.5) * G * 0.7;
        if (!plantable(x, z)) continue;
        const r = rnd();
        if (r < 0.30) headstone(x, z, 1);
        else if (r < 0.345) tomb(x, z);
        else if (r < 0.375) yew(x, z);
      }
    }
    // The lychgate, over the road at the very start, so the first thing you
    // pass through is a gate into a graveyard.
    {
      const e = line[Math.min(14, n - 1)], p = e.p, lat = e.lat || [0, 0, 1];
      const o = e.hw + 3.4;
      for (const s of [-1, 1]) {
        const px = p[0] + lat[0] * o * s, pz = p[2] + lat[2] * o * s;
        span(px - 1.3, px + 1.3, FY, FY + 9.5, pz - 1.3, pz + 1.3, pal.prop2, 'wall');
      }
      const px = p[0], pz = p[2];
      span(px - 2.0, px + 2.0, FY + 9.5, FY + 10.8, pz - o - 1.6, pz + o + 1.6, pal.prop2);
      for (let k = 0; k < 4; k++) {
        const w = (o + 2.6) * (1 - k / 4);
        span(px - 2.6, px + 2.6, FY + 10.8 + k * 1.1, FY + 11.9 + k * 1.1,
             pz - w, pz + w, shade(pal.prop, 0.10 + k * 0.05));
      }
    }

    // **The two `bounce` pads are undressed, and deliberately.** They carried a
    // pale figure each, and the engine draws a spotted mushroom on a forty-six
    // unit stalk over any `bn` run because Shroom Street is what that was
    // written for. Both are gone: `caps: 0` in the palette turns the toadstool
    // off, and there is nothing standing on the pad any more. A cap indoors
    // wants to be a stretch of chapel floor that throws you, not a landmark -
    // and a `bright` figure on this palette is unlit, so it was the brightest
    // thing on the track sitting exactly where you are trying to look.

    const tbX = 782.0, tbZ = 70.0, tbHW = 8.6, tbHH = tbHW / 4;
    const tbTop = FY + 16.0 + tbHH;
    span(tbX - 0.9, tbX + 0.9, FY, tbTop - tbHH, tbZ - 0.9, tbZ + 0.9,
         shade(stoneC, -0.34), 'wall');
    span(tbX - 1.3, tbX + 1.3, tbTop - tbHH - 0.9, tbTop + tbHH + 0.9,
         tbZ - tbHW - 0.9, tbZ + tbHW + 0.9, shade(stoneC, -0.30), 'wall');
    signs.push({ text: 'TACO BELL', c: [tbX - 1.35, tbTop, tbZ],
                 r: [0, 0, 1], u: [0, 1, 0], hw: tbHW, hh: tbHH,
                 n: [-1, 0, 0] });

    // ---- the altarpiece ----------------------------------------------------
    // The one textured thing on the track, and it hangs where the nave points:
    // you drive at it for four hundred units, and you see it again from the
    // gallery on the way back east.
    const A = B.altarpiece;
    if (A && A.art) {
      const w = A.w, h = A.h, y = FY + 3.5 + h / 2, pad = 1.5;
      span(BX - 1.4, BX - 0.5, y - h / 2 - pad, y + h / 2 + pad,
           -w / 2 - pad, w / 2 + pad, A.frame, 'wall');
      // Stood off the wall's own face, not off the frame's centre. `solid.box`
      // is axis-aligned, and on a diagonal wall its *reach* is
      // `hx*|ux| + hz*|uz|` rather than its thickness - which is how the first
      // version of this painting ended up hung inside the masonry. Here the
      // wall is square to X so the reach is the thickness; the note stays
      // because the next one may not be.
      signs.push({
        art: A.art, aspect: A.aspect,
        c: [BX - 1.7, y, 0], r: [0, 0, 1], u: [0, 1, 0],
        hw: w / 2, hh: h / 2, n: [-1, 0, 0],
      });
    }
  }

  /**
   * The ghosts: small pale things that drift across the road at you.
   *
   * `Movers` is what makes this honest. A mover is posed as a pure function of
   * the **physics step index** - the browser takes it from `Run.stepIndex()`
   * and `verify.py` calls it `i * S + k`, two names for one integer - so a lap
   * re-driven by the anti-cheat meets every ghost in exactly the same place. A
   * wall-clock animation would drift, and a missed contact is binary.
   *
   * **They are walls and never ground.** `Collider.ground`, the racing line,
   * `laptime.py` and every medal are untouched: you can be shoved by one, you
   * cannot drive on one, and the medal times do not know they exist.
   *
   * Where they are is found rather than authored. Each band is a stretch the
   * ribbon already describes - the churchyard is the road before the door, the
   * nave is the low wide road inside it, the crypt is the road forty units
   * down - so a leg that moves takes its ghosts with it.
   */
  function movers(ctx) {
    const { track, shade, mulberry } = ctx;
    const B = ctx.cfg || {};
    const line = track.line, n = line.length;
    const NHW = B.naveHW, CHW = B.colHW, TY = B.trifY, WX = B.westX;
    const CY = B.cryptY, NX = B.narthexX, EX = B.eastX;
    const out = [];

    // Three on the way in, which is where they are worth the most: the
    // churchyard is the fastest, widest, most open stretch on the lap, so
    // something crossing it is the first thing that says what kind of track
    // this is. Then the nave, then the crypt.
    const bands = [
      // the churchyard, on the way in
      { pick: (e) => e.p[0] < WX - 10 && e.p[1] > CY + 20,
        count: 4, hide: 5.0, size: 1.18 },
      // the nave
      { pick: (e) => e.p[1] > CY + 20 && e.p[1] < TY - 10 && e.p[0] > WX
                     && Math.abs(e.p[2]) < NHW && !e.wrad,
        count: 8, hide: 4.0, size: 1.26 },
      // the north aisle, before the ramp starts climbing out of it
      { pick: (e) => e.p[0] > WX && e.p[2] < -24 && e.p[1] > CY + 20
                     && e.p[1] < 6,
        count: 5, hide: 3.5, size: 1.00 },
      // the triforium, running back east twenty-four up
      { pick: (e) => e.p[1] > TY - 4 && e.p[2] > 24 && e.p[0] > NX + 40,
        count: 5, hide: 3.5, size: 1.00 },
      // and the crypt, the level parts of it. **The one that owns the gable.**
      // `scare` forces face 3 on its first ghost and flags the mover, and
      // `Storm` clones that mesh for the thing it throws at you off the roof -
      // so what jumps out at the jump is a ghost you have already driven past
      // in the dark, at the size of a windscreen.
      { pick: (e) => e.p[1] < CY + 12 && !e.wrad,
        count: 5, hide: 4.5, size: 1.24, scare: true },
      // **And the two walls of death, which need their own arithmetic.**
      //
      // Every other band offsets along `lat`, and on a wall `lat` is rolled 84
      // degrees - it is pointing at the floor, so `lat[0]` and `lat[2]` are
      // almost nothing and an offset along them goes nowhere. What a mover
      // needs here is a *horizontal* direction, because `Movers.pose` walks a
      // segment in plan at one fixed `y`: `ax,az -> bx,bz`, and `y` never
      // changes. See `wallBand` below for where that direction comes from.
      //
      // The effect is the one thing this geometry is good for. The middle of a
      // helix is an empty unlit shaft, so a ghost parked in it is invisible
      // until it comes out - and it comes out horizontally, straight at a car
      // that is pinned sideways on the cylinder with no grip budget left to
      // steer with.
      //
      // **One apiece, down from two.** On a wall you cannot lift and you cannot
      // take a different line, so a second one is not a corner to solve, it is
      // a toll - and the two of them arrived close enough together that the
      // first was still in your mirror. The two that came off are in the
      // closing stretch below, where there is something you can do about them.
      { pick: (e) => !!e.wrad, count: 2, hide: 26.0, size: 1.15, wall: true },
      // **The closing stretch, which had nothing in it.** The last two hundred
      // units are the tightest pair of corners out of doors on this track and
      // they run between the tombs, so it is the one stretch where a ghost on
      // the apex is a question rather than a tax: you can brake for it, you can
      // take the long way round it, and you are choosing that with the lap
      // already on the line. East of the chapel, above ground, on the way home.
      { pick: (e) => e.p[0] > EX && e.p[1] > CY + 20 && !e.wrad,
        count: 3, hide: 4.5, size: 1.12 },
    ];
    // Periods in physics steps, coprime enough that they never fall into step
    // with each other. At 120Hz these are 2.4 to 3.3 seconds out and back.
    const PERIOD = [293, 337, 397, 311, 359, 421, 379];
    // **And a ghost's face sets how fast it crosses**, which is the thing that
    // makes four faces read as four *kinds* of ghost rather than as four
    // paint jobs: the plain Boo drifts, the wail is the quick one, and the one
    // from the gable is quicker than anything else out here. Multiplies the
    // period, so bigger is slower.
    const FACE_SPEED = [1.22, 1.0, 0.78, 0.72];
    // Which face each one wears, drawn here rather than per band. A band with
    // one face is a room with one ghost in it repeated, and the nave has eight;
    // seeded, because everything else about these is a pure function of the
    // ribbon and a herd that reshuffles on every load is a herd nobody can
    // learn. **Not `Math.random`** for the same reason.
    const rndFace = mulberry(0xf4c3);

    /** Which way the road is bending here, as a sign along `lat`.
     *
     * **This is what puts a ghost on the driving line instead of beside it.**
     * They used to hide `band.hide` out on alternating sides and reach back to
     * a couple of units short of the centreline, which on a straight is a thing
     * you steer round and in a corner is a thing that waves at you from the
     * run-off: the car is already on the apex, and the apex was the one place
     * nothing ever went. The racing line is not on the track object - `ideal`
     * is the lap *time*, a float - so it is taken from the ribbon, which knows
     * the same thing: the tangent turns toward the inside of the corner, so the
     * sign of `lat . (t2 - t1)` is the apex side. Zero on a straight, and there
     * the old alternation is exactly right.
     */
    const apexSide = (i) => {
      const a = line[i - 1], b = line[i], c = line[i + 1];
      if (!a || !c) return 0;
      const lat = b.lat || [0, 0, 1];
      const t1x = b.p[0] - a.p[0], t1z = b.p[2] - a.p[2];
      const t2x = c.p[0] - b.p[0], t2z = c.p[2] - b.p[2];
      const l1 = Math.hypot(t1x, t1z) || 1, l2 = Math.hypot(t2x, t2z) || 1;
      const d = lat[0] * (t2x / l2 - t1x / l1) + lat[2] * (t2z / l2 - t1z / l1);
      return Math.abs(d) < 0.004 ? 0 : (d > 0 ? 1 : -1);
    };

    /** From a wall station, the horizontal direction to the helix's own axis.
     *
     * The tangent turns toward the centre of the corner, so the change in the
     * plan tangent between one station and the next points at it. That is the
     * same fact `apexSide` uses, taken as a vector instead of a sign - and
     * taken in plan, which is what makes it survive a road rolled onto its
     * side, where `lat` has no useful horizontal part left.
     */
    const axisDir = (i) => {
      const a = line[i - 1], b = line[i], c = line[i + 1];
      if (!a || !c) return null;
      const n1 = Math.hypot(b.p[0] - a.p[0], b.p[2] - a.p[2]) || 1;
      const n2 = Math.hypot(c.p[0] - b.p[0], c.p[2] - b.p[2]) || 1;
      const ux = (c.p[0] - b.p[0]) / n2 - (b.p[0] - a.p[0]) / n1;
      const uz = (c.p[2] - b.p[2]) / n2 - (b.p[2] - a.p[2]) / n1;
      const m = Math.hypot(ux, uz);
      return m < 1e-6 ? null : [ux / m, uz / m];
    };

    // **Unlit and white.** `glow` swaps the mover's Lambert material for a
    // basic one, so these render at the literal colour written here while the
    // chapel around them is multiplied down by a dim moon - which is the whole
    // of why they read as lit from inside rather than as pale grey lumps. Lit,
    // at this track's key light, a white ghost measured about a third of this
    // and vanished into the masonry behind it.
    //
    // **One white, and that is a fix rather than a simplification.** The body
    // used to be three stacked boxes, and the widest of them was a shade darker
    // to suggest a belly - which is not what it did. These are unlit, so a
    // darker box does not shade, it *is* a different colour: a grey slab across
    // the middle of a white ghost, with its own hard edges, reading as a thing
    // inside the thing. Unlit geometry gets its form from its silhouette or it
    // gets none.
    const pale = 0xf2f8ff, dark = 0x080a10;

    /** **Four faces, and which one a ghost wears is the only thing that varies.**
     *
     * Everything else about these is fixed by the road - where they hide and
     * how far they reach. A pool of them with one face is one ghost printed
     * twenty-five times, and you stop seeing any of them by the second lap.
     *
     * **Drawn per ghost, not per band**, which is the difference between four
     * faces and four rooms: a band with its own face is still one ghost as far
     * as the stretch of road you are on is concerned, and the nave has eight of
     * them in a row. The draw is seeded (`rndFace`), because everything else
     * here is a pure function of the ribbon and a herd that reshuffles every
     * load is a herd nobody can learn. The face also sets the crossing speed -
     * see `FACE_SPEED` - so these are four kinds of ghost rather than four
     * paint jobs.
     *
     * Each takes `at(k, y, w, h)` - across the face, up it, and the two
     * half-extents, in units of the body - and `w` is the standard eye width so
     * a face can be drawn relative to it rather than to the body. The last one
     * is the one the gable throws at you, and it is deliberately the only one
     * with teeth in it.
     */
    const FACES = [
      // 0 - the Boo. Round eyes, a small open mouth, nothing angled, and the
      // slowest of the four: the friendly one, so that the others are a change.
      (at, w) => [at(-0.34, 0.34, w, 0.21), at(0.34, 0.34, w, 0.21),
                  at(0, -0.26, w * 1.15, 0.20)],
      // 1 - the scowl. A brow box over the inner top corner of each socket,
      // which is the whole of the expression, and a mouth pulled wide and flat.
      // Middling pace.
      (at, w) => [at(-0.34, 0.34, w, 0.21), at(0.34, 0.34, w, 0.21),
                  at(-0.22, 0.57, w * 0.66, 0.08), at(0.22, 0.57, w * 0.66, 0.08),
                  at(0, -0.28, w * 1.7, 0.12)],
      // 2 - the wail. Tall narrow eyes and a mouth long enough to reach the
      // hem: the one that reads from furthest away, and the quick one.
      (at, w) => [at(-0.32, 0.36, w * 0.7, 0.30), at(0.32, 0.36, w * 0.7, 0.30),
                  at(0, -0.34, w * 0.9, 0.34)],
      // 3 - **the one at the gable**, and the fastest thing on the track.
      // Sockets twice the size of anybody else's, angled by a brow that runs
      // down to the middle, and a maw with four teeth standing in it - two down from the top and two up from the
      // bottom, because an even row is a grin. `Storm` clones this ghost's mesh
      // and throws it at the camera, so it is the only face in here drawn to be
      // looked at from a foot away rather than from across a room.
      (at, w) => [
        at(-0.40, 0.30, w * 1.25, 0.24), at(0.40, 0.30, w * 1.25, 0.24),
        // **One brow per eye, and a gap between them.** They used to be two
        // boxes a side, the inner pair meeting over the nose - which is a
        // unibrow, and a unibrow is a black bar across the top of the face
        // rather than an expression. Two short ones, each sat over the outer
        // half of its own socket and clear of it by a hair, is the whole angle.
        at(-0.34, 0.66, w * 0.85, 0.07), at(0.34, 0.66, w * 0.85, 0.07),
        at(0, -0.38, w * 1.65, 0.36),
      ].concat(
        // The teeth, and they are `pale` rather than `dark`: they stand *in*
        // the maw, so they are the one part of a face that is not a hole. Two
        // down from the top and two up from the bottom, uneven, because a row
        // that lines up is a grin.
        [[-0.26, -0.12, 0.11], [0.22, -0.12, 0.08],
         [-0.08, -0.62, 0.11], [0.20, -0.62, 0.08]].map(([k, y, h]) => {
          const t = at(k, y, w * 0.30, h, 0.05);
          t[6] = pale;
          return t;
        })),
    ];

    let q = 0;
    for (const band of bands) {
      const idx = [];
      for (let i = 8; i < n - 8; i++) if (!line[i].air && band.pick(line[i])) idx.push(i);
      if (idx.length < 20) continue;
      for (let c = 0; c < band.count; c++, q++) {
        // Never on the very ends of a run: the entry and the exit of a section
        // are where the car is already committed to a line it cannot leave.
        const ei = idx[Math.round((0.18 + 0.64 * ((c + 0.5) / band.count))
                                  * (idx.length - 1))];
        const e = line[ei];
        let a, b, y0;
        if (band.wall) {
          // Out of the shaft and onto the road, along the horizontal. `hide` is
          // measured toward the axis, and the reach goes a unit and a half past
          // the station so the far end of the sweep is *in* the surface rather
          // than a hair off it - a ghost that stops level with the road is one
          // you can squeeze past on a bank you cannot steer on.
          const u = axisDir(ei);
          if (!u) { q--; continue; }
          a = [e.p[0] + u[0] * band.hide, e.p[2] + u[1] * band.hide];
          b = [e.p[0] - u[0] * 1.5, e.p[2] - u[1] * 1.5];
          // Level with the station, not stood on top of it: on a wall of death
          // "the ground" is sideways, and the car's own centre is within half a
          // unit of the ribbon's height.
          y0 = e.p[1];
        } else {
          const apex = apexSide(ei);
          // Out of the *outside* of the corner and across to the apex, so the
          // one line that is quick through here is the line something is
          // standing in. On a straight there is no apex to aim at, so they keep
          // alternating.
          const side = apex ? -apex : ((q % 2) ? 1 : -1);
          const reach = apex ? -0.52 * e.hw : -0.15 * e.hw;
          const lat = e.lat || [0, 0, 1];
          const at = (o) => [e.p[0] + lat[0] * o * side, e.p[2] + lat[2] * o * side];
          // **`hide` is measured from the kerb, and it is small now.** It used
          // to be nine units clear of the road edge, which on a 16-wide nave
          // put the near face of a ghost eight units into the dark before the
          // sweep even started - so most of the cycle was spent invisible and
          // the part you saw was the last third of it. Four means it is only
          // just off the kerb at rest, so it is already in the corner of your
          // eye and the crossing is the whole of the movement rather than the
          // end of it.
          a = at(band.hide + e.hw);
          b = at(reach);
          y0 = null;
        }
        // **Small, and low.** A ghost is a thing you hit at bumper height, not
        // a statue: two and a half units of body sitting just over the road, so
        // it reads as something rushing at the car rather than something the
        // car drives into. HY is half the collision box and the parts are
        // measured from its middle, so the whole thing sits at p + HY.
        const S = 1.35 * band.size;
        const HY = 1.45 * S;
        // Which face this one wears. Drawn, except the crypt's first, which
        // always wears the one the gable throws at you - see `FACES`.
        const scare = !!band.scare && c === 0;
        // **The first four are the plain Boo, and then it is a draw.** The
        // churchyard is the opening of the lap and the first ghost anybody ever
        // sees on this track: a scowl or a maw there sets the level at its top
        // and leaves the rest of the lap nowhere to go. Round eyes first, and
        // let the nave be where it turns.
        const fi = scare ? 3 : (q < 4 ? 0 : Math.floor(rndFace() * FACES.length));
        // So the form is the silhouette: nine slabs on an egg profile rather
        // than three boxes on a stack. Half-width `w` at height `y`, wider
        // below the middle than above it, which is the difference between a
        // ghost and a snowman. The same trick the gable face used - a curve is
        // cheap when it is rows of boxes and the row count is what buys it.
        const BODY = [
          [ 1.16, 0.26], [ 0.96, 0.52], [ 0.74, 0.74], [ 0.46, 0.90],
          [ 0.14, 1.00], [-0.20, 1.02], [-0.52, 0.96], [-0.80, 0.84],
        ];
        const body = BODY.map(([y, w], i) => [
          0, y * S, 0,
          w * S, (i === 0 ? 0.20 : 0.19) * S, w * 0.88 * S, pale]);
        out.push({
          ax: a[0], az: a[1], bx: b[0], bz: b[1],
          y: y0 != null ? y0 : e.p[1] + HY + 0.5,
          hx: 1.15 * S, hy: HY, hz: 1.00 * S, glow: 1,
          // Read by `Storm` through `built.movers`, and by nothing else: the
          // pose and the collision box know nothing about it, so the verifier
          // in QuickJS carries the flag and never looks at it.
          scare: scare ? 1 : 0,
          period: Math.round(PERIOD[q % PERIOD.length] * FACE_SPEED[fi]),
          phase: q * 163,
          // Boxes in the mover's own frame: +z is the way it drifts, and y is
          // measured from the middle of the collision box.
          parts: [
            ...body,
            // The hem, in five tags of different lengths so the bottom edge is
            // torn rather than cut. They hang off the widest part of the body
            // and not off a flat base, which is why there is no flat base.
            [-0.66 * S, -1.02 * S,  0.22 * S, 0.22 * S, 0.30 * S, 0.22 * S, pale],
            [-0.22 * S, -1.12 * S, -0.34 * S, 0.24 * S, 0.40 * S, 0.22 * S, pale],
            [ 0.16 * S, -1.00 * S,  0.30 * S, 0.22 * S, 0.28 * S, 0.22 * S, pale],
            [ 0.54 * S, -1.14 * S, -0.10 * S, 0.24 * S, 0.42 * S, 0.24 * S, pale],
            [ 0.04 * S, -1.06 * S, -0.02 * S, 0.30 * S, 0.34 * S, 0.30 * S, pale],
            // The arms, held out across the road rather than along it. A mover
            // drifts on its own +z and the road crosses that square, so the
            // car meets it on +x or -x: reaching the way it is *going* pointed
            // them at the wall. Two boxes apiece, the outer one smaller and
            // lower - a stub with a hand on it, rather than a peg.
            ...[[1, 1], [1, -1], [-1, 1], [-1, -1]].flatMap(([sx, sz]) => [
              [sx * 0.92 * S, -0.30 * S, sz * 0.58 * S,
               0.30 * S, 0.22 * S, 0.26 * S, pale],
              [sx * 1.16 * S, -0.48 * S, sz * 0.70 * S,
               0.20 * S, 0.18 * S, 0.20 * S, pale],
            ]),
            // **A face on the two sides the road is on, and on no others.**
            //
            // It started on +z alone - the way it walks - and the car arrives at
            // ninety degrees to that, so every ghost on the track was a blank
            // white back. Putting it on all four sides fixed that and bought a
            // worse thing: from the car you saw the face meant for you *and*
            // the two meant for nobody, edge-on down the silhouette, so a Boo
            // had four eyes and three mouths.
            //
            // What the player actually sees is settled by `Movers.pose`, which
            // yaws the mover onto its own direction of travel. These walk
            // *across* the road - a to b is along `lat` - so the road runs
            // along the mover's local x, and local +x and -x are the only two
            // sides a car ever sees flat-on. The other two face up and down the
            // ghost's own path and are seen from nowhere.
            //
            // Both of x, not one, and that is the yaw flip rather than
            // indecision: `pose` reverses the heading on the way home, so the
            // side pointing up-road on the way out is the side pointing away on
            // the way back. Two faces is what *one* face costs here, and it
            // costs nothing to look at - the far one is behind the body.
            ...[[1, 0], [-1, 0]].flatMap(([fx, fz]) => {
              // **Where the skin actually is, per axis.** The body is boxes,
              // so its +x surface and its +z surface are at different distances
              // - the slabs are 12% shallower than they are wide. One offset
              // for both is what buried a face inside the white, which is not a
              // face at all, it is nothing.
              const OX = 1.04 * S, OZ = 0.92 * S;
              // Across the face, and into it. **Into it is the number that was
              // wrong**: a feature is only ever seen flat-on, and its depth is
              // what it looks like from ninety degrees away - so a deep one is
              // a black block on the *silhouette* of the ghost beside it, which
              // is where the four-eyed look came from. Just proud of the skin.
              const across = 0.17 * S, deep = 0.11 * S;
              // A feature: `k` across the face, `y` up it, half-extents in
              // those two axes. Which world axis each of those is depends on
              // which side we are drawing, and this is the only place that
              // knows.
              // `b` pushes a feature out along the face's own normal. It
              // exists for the teeth: a box whose outer face is *coplanar* with
              // the maw's flickers, because two surfaces at the same depth give
              // the depth buffer nothing to choose between and which one wins
              // changes with the camera. It read as teeth crawling around
              // inside the mouth. A twentieth of a body proud of it and the
              // question stops being asked.
              const at = (k, y, w, h, b) => (fx
                ? [fx * (OX + (b || 0) * S), y * S, k * S, deep, h * S, w * S, dark]
                : [k * S, y * S, fz * (OZ + (b || 0) * S), w * S, h * S, deep, dark]);
              return FACES[fi](at, across / S);
            }),
          ],
        });
      }
    }
    return out;
  }
})();
