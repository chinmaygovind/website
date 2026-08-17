/**
 * Tokyo Drift: the city.
 *
 * **The scatter cannot make a city and this is why the track needs its own
 * file.** `addScenery`'s vocabulary is conifer, bigpine, deadtree, palm, rock
 * and block, and `block` is a crate at any distance you actually see it from -
 * so a city built out of props comes out as a scrapyard, thousands of identical
 * small dark boxes carpeting the bounding box. What a city needs is a few
 * hundred things that are *tall*, and nothing in the palette can say that.
 *
 * Everything here is mesh only. Nothing is added to the collider, deliberately
 * and for the same reason the trees are not: the towers stand well back from the
 * road, a car that reaches one has already lost the lap, and putting them in the
 * collider would put them into the anti-cheat's world too - `verify.py` re-drives
 * submitted laps through this exact function, so a triangle added here is a
 * triangle every replayed lap has to agree about.
 *
 * Three rules do all the work:
 *
 * - **A tower may not stand where the road is**, in plan, which is the ordinary
 *   corridor test the scatter already does.
 * - **A tower may not stand *up into* a road passing over it.** This track flies
 *   an expressway 51 units up over ground a tower would otherwise fill, and a
 *   hundred-unit tower under it is a spear through the carriageway. Costco found
 *   the same thing with its rooftop deck's legs: until a track put road over
 *   road, nothing had to ask. So every tower's height is capped under the lowest
 *   road above its own footprint, with headroom.
 * - **Windows are unlit and the walls are not.** The walls go in `solid`
 *   (Lambert, lit by a 0.6 key light at night, so nearly black, which is right);
 *   the windows go in `bright` (Basic, unlit) so they are the same colour at
 *   midnight as they would be at noon. That contrast is the entire effect - a
 *   city at night is black shapes with lit holes in them, and any attempt to
 *   light the walls properly just makes fog-coloured slabs.
 */
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.tokyo = { props: props };

  const GRID = 44;          // tower every GRID units, jittered inside its cell
  const CHANCE = 0.55;      // ...this often
  // Clearance from the road *edge* (the probe subtracts each station's own half
  // width), and it is the number that decides whether this is a city or a
  // business park. At 24 every tower stood back far enough to leave a plaza
  // round the whole track and the neon alleys - 9.5 units wide, the tightest
  // road in the pool - had nothing within forty units of them. 14 puts a wall
  // where an alley needs one. It cannot go much below that: the chase camera
  // trails 11.6 units behind the car and swings wide of the centreline through
  // a corner, so a building closer than this is one the lens goes through.
  const CLEAR = 14;
  const HEAD = 9;           // headroom left under a road passing overhead
  const MIN_H = 26;         // below this a capped tower is dropped instead
  // Window grid. Coarse on purpose: a window is two triangles and there are a
  // few hundred towers, so this is the number that decides whether the city
  // costs five thousand triangles or fifty.
  const WIN_W = 3.0, WIN_H = 2.2, WIN_GAP_X = 6.0, WIN_GAP_Y = 5.5;
  const PROUD = 0.18;       // stand the window off its wall - see below

  // Lit-window colours, weighted warm. Real offices are sodium and fluorescent
  // with the odd cold one; the saturated cyan and magenta are signage bleeding
  // through glass and want to stay rare or the whole skyline turns into a
  // fairground.
  const LIT = [0xffd9a0, 0xffd9a0, 0xffe9c8, 0xfff3dd, 0xbfe4ff, 0x8ff0ff, 0xff8fd0];
  // Neon bands round the top of some towers.
  const NEON = [0x2ff3ff, 0xff3d9a, 0xff6a2f, 0x7d5cff, 0x3dff9a];

  function props(ctx) {
    const { solid, bright, track, pal, bbox, CELL, groundY, mulberry, shade,
            solid_plate } = ctx;
    if (groundY == null) return;              // this track is on the ground
    const rnd = mulberry(20260817);
    const line = track.line;

    // ---- where the road is, bucketed so each cell only looks at what is near --
    //
    // One pass, same trick `buildTerrain` uses: without it this is every cell
    // against every station, which on a 900-station track over a 20x30 grid is
    // half a million distance tests for no reason.
    const B = 64;
    const bx0 = Math.floor((bbox.x0 - 200) / B), bx1 = Math.ceil((bbox.x1 + 200) / B);
    const bz0 = Math.floor((bbox.z0 - 200) / B), bz1 = Math.ceil((bbox.z1 + 200) / B);
    const nbx = bx1 - bx0 + 1, nbz = bz1 - bz0 + 1;
    const buckets = new Array(nbx * nbz);
    for (let i = 0; i < line.length; i++) {
      const e = line[i];
      if (e.air) continue;                    // a gap is not a place there is road
      const gx = Math.floor(e.p[0] / B) - bx0, gz = Math.floor(e.p[2] / B) - bz0;
      if (gx < 0 || gz < 0 || gx >= nbx || gz >= nbz) continue;
      const k = gx * nbz + gz;
      (buckets[k] || (buckets[k] = [])).push(e);
    }
    // Nearest road in plan, and the lowest road height within `reach`, in one
    // walk. Returns null for "no road anywhere near", which is most of the map.
    const probe = (x, z, reach) => {
      const r = Math.ceil(reach / B);
      const gx = Math.floor(x / B) - bx0, gz = Math.floor(z / B) - bz0;
      let near = Infinity, lowAbove = Infinity;
      for (let dx = -r; dx <= r; dx++) {
        for (let dz = -r; dz <= r; dz++) {
          const ix = gx + dx, iz = gz + dz;
          if (ix < 0 || iz < 0 || ix >= nbx || iz >= nbz) continue;
          const cell = buckets[ix * nbz + iz];
          if (!cell) continue;
          for (const e of cell) {
            const d = Math.hypot(e.p[0] - x, e.p[2] - z) - e.hw;
            if (d < near) near = d;
            if (d < reach && e.p[1] < lowAbove) lowAbove = e.p[1];
          }
        }
      }
      return { near, lowAbove };
    };

    // ---- the towers ---------------------------------------------------------
    //
    // **Bounded by the ground, not by the bounding box.** `buildTrack` lays the
    // ground quad at `bbox + CELL * 7` and no further, which on this track is 56
    // units - far tighter than it feels from inside, and nothing about the world
    // says where it stops. The first pass scattered towers out to `bbox + 260`,
    // so everything past the plate stood in the void with its feet on nothing.
    // It showed up worst near the flag, where the layout runs closest to its own
    // bounding box.
    // ...and the city lays its own ground so there is more of it. `buildTrack`'s
    // plate is sized for a track, not for a skyline: at 56 units past the
    // bounding box, a layout whose start sits near a corner - this one does -
    // has almost no room for buildings on that side and opens on an empty
    // plain. `solid_plate` is in the context precisely so scenery can add
    // surface, and this one is drawn a quarter-unit low so it slides under the
    // real plate instead of z-fighting with it across the whole map.
    //
    // It is **mesh only and not in the collider**, which is the honest thing
    // rather than a shortcut: the drivable ground is still the engine's plate,
    // so nothing about where a car can go, or where it respawns, changes.
    const PAD = CELL * 7;
    const EXTRA = 300;
    const px0 = bbox.x0 - PAD - EXTRA, px1 = bbox.x1 + PAD + EXTRA;
    const pz0 = bbox.z0 - PAD - EXTRA, pz1 = bbox.z1 + PAD + EXTRA;
    const x0 = Math.floor(px0 / GRID), x1 = Math.ceil(px1 / GRID);
    const z0 = Math.floor(pz0 / GRID), z1 = Math.ceil(pz1 / GRID);

    // ---- keep the switcher's camera out of a building -----------------------
    //
    // `shotCamera` stands the preview camera **behind the start line** - up to
    // 70 units back and 43 up - and looks forward along the road. Nothing about
    // that is visible from inside this file, and once `CLEAR` came down to 14
    // the first tower placed back there filled the entire card: the preview came
    // out as a black wall with four windows on it, and the only tell was the PNG
    // dropping from 62 kB to 12.
    //
    // So the wedge behind the line is kept empty. Only *behind* - anything ahead
    // of the start is what the shot is pointed at and is supposed to be in it.
    const sp = track.spawn;
    const behindTheLens = (x, z) => {
      const dx = x - sp.p[0], dz = z - sp.p[2];
      if (dx * dx + dz * dz > 120 * 120) return false;
      return dx * sp.fwd[0] + dz * sp.fwd[2] < 12;     // behind, or level with
    };

    for (let gx = x0; gx <= x1; gx++) {
      for (let gz = z0; gz <= z1; gz++) {
        if (rnd() > CHANCE) continue;
        const cx = gx * GRID + (rnd() - 0.5) * GRID * 0.55;
        const cz = gz * GRID + (rnd() - 0.5) * GRID * 0.55;

        // Footprint first, because both tests below are about the footprint and
        // not about the centre - it is a tower's *corner* that ends up over the
        // kerb, the same way it is a hoarding's corner that ends up in a stand.
        const hx = 6 + rnd() * 8, hz = 6 + rnd() * 8;
        const half = Math.hypot(hx, hz);

        // The whole footprint has to be on the plate, not just the centre - it
        // is the corner that hangs off the edge.
        if (cx - hx < px0 || cx + hx > px1 || cz - hz < pz0 || cz + hz > pz1) continue;

        const { near, lowAbove } = probe(cx, cz, half + CLEAR);
        if (near < half + CLEAR) continue;             // too close to the road
        if (behindTheLens(cx, cz)) continue;           // in the opening shot

        let h = 26 + Math.pow(rnd(), 2.0) * 130;       // mostly low, a few tall
        // Capped under anything flying over this footprint. `lowAbove` is the
        // lowest road within reach, so this is conservative by construction.
        if (lowAbove < Infinity) h = Math.min(h, lowAbove - groundY - HEAD);
        if (h < MIN_H) continue;                       // squashed flat - drop it

        tower(cx, cz, hx, hz, h, rnd);
      }
    }

    // ---- the ground ---------------------------------------------------------
    //
    // **One flat quad in one colour is what made the floor dead**, and it is
    // half of every frame on a ground track. The engine draws exactly that, at
    // `bbox + CELL * 7` and no further, so this replaces it: the same surface
    // tessellated into cells, each a slightly different shade.
    //
    // That is what "texture" means in this renderer. Everything here is flat
    // shaded vertex colour with no image maps anywhere except the sponsor
    // boards, so detail comes from having more polygons with different colours
    // on them and from nothing else. Painting shapes onto the flat plate was the
    // first attempt - a street grid, puddles, pools of light - and all of it
    // read as decals lying on lino, because the surface underneath was still
    // obviously one enormous flat thing.
    //
    // Drawn **last**, so every `rnd()` the towers took has already been taken
    // and their layout does not move when this changes. And drawn a hair *above*
    // `groundY` rather than below, so it covers the engine's plate everywhere
    // instead of only outside it - the middle of the map is where you actually
    // drive, and a textured rim round an untextured centre is worse than
    // neither.
    const TILE = 17;
    const gx0 = Math.floor(px0 / TILE), gx1 = Math.ceil(px1 / TILE);
    const gz0 = Math.floor(pz0 / TILE), gz1 = Math.ceil(pz1 / TILE);
    const gy = groundY + 0.06;
    for (let ix = gx0; ix < gx1; ix++) {
      for (let iz = gz0; iz < gz1; iz++) {
        const a = ix * TILE, c = iz * TILE;
        // Wet tarmac: mostly a narrow spread around the base colour, with the
        // occasional much darker cell. The dark ones are what read as standing
        // water, and they work here where drawn puddles did not because they are
        // the surface rather than something lying on it - no edge, no rectangle,
        // just a patch of ground that is darker than the ground beside it.
        const n = rnd();
        const k = n < 0.15 ? -0.30 - rnd() * 0.18 : (rnd() - 0.45) * 0.26;
        // **Wind it the way the engine winds its own ground quad.** `solid` is
        // `FrontSide`, so the opposite order is a floor facing the earth: drawn,
        // costed, and invisible from every place anybody stands. It looked
        // exactly like the tessellation had not been written at all, which is
        // the same trap that spent an afternoon making Spa's pit building an
        // invisible shed - there is no error for it and nothing in the suite can
        // see it.
        solid.quad([a, gy, c], [a, gy, c + TILE],
                   [a + TILE, gy, c + TILE], [a + TILE, gy, c],
                   shade(pal.ground, k));
      }
    }

    /**
     * One building.
     *
     * **Setbacks are what stopped these being underwhelming.** The first version
     * was one box per tower with a window grid on it, and a skyline of nothing
     * but boxes reads as a bar chart however well the windows are done - the eye
     * is looking at silhouettes long before it can resolve a window. So a tall
     * tower is two or three stacked tiers, each stepped in from the one below,
     * and the top of each tier is a ledge you can see against the sky. That plus
     * the masts is most of the difference; the windows were never the problem.
     */
    function tower(cx, cz, hx, hz, h, rnd) {
      const base = groundY;
      // Walls are a shade off the palette's structural colour so the skyline is
      // not one flat silhouette, but they stay dark: at this light level the
      // wall's job is to be the black around the windows.
      const wall = shade(pal.prop2 != null ? pal.prop2 : pal.prop, (rnd() - 0.4) * 0.24);
      // Every tower picks one lit colour, one "how many are on" fraction, and
      // one window style, which is what makes two towers beside each other read
      // as two buildings rather than as one repeated texture.
      const lit = LIT[(rnd() * LIT.length) | 0];
      const on = 0.26 + rnd() * 0.44;
      const strips = rnd() < 0.34;      // continuous vertical glazing

      let tiers = 1;
      if (h > 58 && rnd() < 0.62) tiers = 2;
      if (h > 100 && tiers === 2 && rnd() < 0.55) tiers = 3;

      let y = base, rx = hx, rz = hz, left = h;
      for (let t = 0; t < tiers; t++) {
        const seg = t === tiers - 1 ? left : left * (0.40 + rnd() * 0.22);
        solid.box(cx, y + seg / 2, cz, rx, seg / 2, rz, wall);
        glaze(cx, cz, rx, rz, y, seg, lit, on, strips, rnd);
        y += seg;
        left -= seg;
        if (t < tiers - 1) {
          rx *= 0.62 + rnd() * 0.20;
          rz *= 0.62 + rnd() * 0.20;
        }
      }
      crown(cx, cz, rx, rz, base + h, h, rnd);
    }

    /** Lit windows on all four faces of one tier, as a grid or as strips. */
    function glaze(cx, cz, hx, hz, y0, hgt, lit, on, strips, rnd) {
      const top = y0 + hgt;
      for (let face = 0; face < 4; face++) {
        const alongX = (face & 1) === 0;
        const span = alongX ? hx : hz;
        const cols = Math.max(1, Math.floor((span * 2 - 3) / WIN_GAP_X));
        const sign = face < 2 ? 1 : -1;
        // The glass sits PROUD of the wall rather than flush on it. Two coplanar
        // quads in two different meshes is a depth-buffer coin toss, and what
        // that looks like is the windows flickering on and off as the camera
        // moves - the same bug Costco's roof slab and shelf beams both had.
        // 0.05 is not enough; the run-off's note puts the number nearer 0.15.
        const off = (alongX ? hz : hx) + PROUD;
        // `bright` is DoubleSide, so none of this needs winding care - which is
        // the real reason the unlit buffer is the right home for it and not just
        // a convenience. Anything in `solid` has to be drawn twice or it
        // vanishes the moment it is mirrored to the other side of the building.
        const pane = (u0, u1, ya, yb, col) => {
          const p = (u, yy) => (alongX ? [cx + u, yy, cz + sign * off]
                                       : [cx + sign * off, yy, cz + u]);
          bright.quad(p(u0, ya), p(u1, ya), p(u1, yb), p(u0, yb), col);
        };
        for (let c = 0; c < cols; c++) {
          const u = (c - (cols - 1) / 2) * WIN_GAP_X;
          if (strips && cols >= 3) {
            // One unbroken column of glass, floor to ceiling, lit or dark. Half
            // the towers in a modern skyline are this and none of them read as
            // a grid of squares.
            //
            // **Only where there is room for three of them.** On a narrow face
            // `cols` falls to one, and a single full-height pane centred on a
            // blank wall does not read as glazing at all - it reads as a
            // mistake, a white slab down the middle of the building. Three is
            // the fewest that reads as a repeating element.
            if (rnd() > on) continue;
            pane(u - WIN_W * 0.42, u + WIN_W * 0.42, y0 + 3, Math.max(y0 + 4, top - 2.5), lit);
          } else {
            const rows = Math.max(1, Math.floor((hgt - 7) / WIN_GAP_Y));
            for (let r = 0; r < rows; r++) {
              const y = y0 + 4.5 + r * WIN_GAP_Y;
              if (y + WIN_H > top - 2) break;
              if (rnd() > on) continue;
              pane(u - WIN_W / 2, u + WIN_W / 2, y, y + WIN_H, lit);
            }
          }
        }
      }
    }

    /**
     * What is on the roof. Never nothing on a tall one and rarely anything on a
     * short one - the point of a lit sign is that the buildings without one are
     * the background it reads against.
     */
    function crown(cx, cz, hx, hz, top, h, rnd) {
      const r = rnd();
      if (h > 52 && r < 0.34) {
        // A neon band wrapped round the parapet.
        const col = NEON[(rnd() * NEON.length) | 0];
        const y = top - 4 - rnd() * 8;
        solid.box(cx, y, cz, hx + 0.5, 1.7, hz + 0.5, shade(col, -0.6));
        for (const s of [1, -1]) {
          bright.quad([cx - hx - 0.8, y - 1.3, cz + s * (hz + 0.8)],
                      [cx + hx + 0.8, y - 1.3, cz + s * (hz + 0.8)],
                      [cx + hx + 0.8, y + 1.3, cz + s * (hz + 0.8)],
                      [cx - hx - 0.8, y + 1.3, cz + s * (hz + 0.8)], col);
          bright.quad([cx + s * (hx + 0.8), y - 1.3, cz - hz - 0.8],
                      [cx + s * (hx + 0.8), y - 1.3, cz + hz + 0.8],
                      [cx + s * (hx + 0.8), y + 1.3, cz + hz + 0.8],
                      [cx + s * (hx + 0.8), y + 1.3, cz - hz - 0.8], col);
        }
      } else if (h > 44 && r < 0.68) {
        // A mast with an aircraft light on it. Cheap, and it is the single most
        // effective thing here: a thin vertical against the sky is what stops a
        // roofline being a flat edge, and the red pinprick reads from anywhere
        // on the track.
        const mh = 8 + rnd() * 20;
        solid.box(cx, top + mh / 2, cz, 0.45, mh / 2, 0.45, 0x2a3040);
        bright.box(cx, top + mh + 0.7, cz, 0.9, 0.9, 0.9, 0xff3a3a);
      } else if (r < 0.86) {
        // Plant: a water tank and a housing, off-centre so the roof is not
        // symmetrical about anything.
        const ox = (rnd() - 0.5) * hx, oz = (rnd() - 0.5) * hz;
        solid.box(cx + ox, top + 1.6, cz + oz, hx * 0.28, 1.6, hz * 0.28, 0x333b4c);
        if (rnd() < 0.5) {
          solid.box(cx - ox * 0.6, top + 2.6, cz - oz * 0.6,
                    hx * 0.16, 2.6, hz * 0.16, 0x2c3342);
        }
      }
    }
  }
})();
