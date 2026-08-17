// Shroom Street's world: a green gorge, and the mushrooms the road crosses it on.
//
// Two things live in here and only the first one is unusual.
//
// **The ground.** This is a `ground = None` track, so the engine builds no
// collidable plate and the whole of what you can see and run onto is here. It is
// Mount Joy's pattern rather than `pal.terrain`, for the reason
// `docs/track-defects.md` gives: `pal.terrain` samples one height per cell from
// the *nearest* road, which is single-valued, so over anything that stacks it
// fills the volume solid. Here the field is a **lower envelope of upward cones**,
// one per station, and every one of them is at most `y - DROP` at its own
// station - so the ground is arithmetically incapable of coming up through any
// road, for any layout, whatever anybody edits in `track.py` later.
//
// **The chasm is drawn and never collided**, which is Sandy Cove's rule for the
// sea and is the whole reason the crossings work. Falling off a mushroom has to
// be a *fall* - `RESPAWN_DELAY` and back on the road - and a collidable gorge
// floor turns it into a long drop onto grass a hundred units below the racing
// line, where you are neither dead nor racing. So the carve only ever digs
// *down* (same safety property as the roughness) and every cell it dug is left
// out of the collider.
//
// **The mushrooms are not in here.** They were, briefly, and they belong in
// `buildTrack` beside `KIND.BOUNCE` instead: a cap's top and its rim have to
// agree about one radius, and two files cannot hold one number - which is the
// Costco's lesson about `SHELL_X`. So anything using `Builder.bounce` gets a
// mushroom for free, and this file is only the ground one stands over.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.shroom = { props: props };

  // ---- the shape of the ground ---------------------------------------------
  // Two gradients out from the road, for the reason Mount Joy's note sets out:
  // one number cannot be both the verge you run wide onto and how fast the
  // ground climbs away from a distant low station. `FLANK` is the verge, `STEEP`
  // is the hillside past it.
  //
  // Gentler than Mount Joy's on both counts, because this is a meadow rather
  // than a mountain face and because nothing here has to hold a summit up.
  const FLANK = 0.42;      // gradient of the verge, for SOFT units
  const SOFT = 30.0;
  const STEEP = 1.35;      // gradient of the hillside past it
  const FALL = 0.34;       // gradient of the ground falling away from everything
  const APRON = 16.0;      // flat shoulder either side of the road
  const SOFT_TOP = FLANK * SOFT;

  // How far under the tarmac the grass sits. Same two opposing jobs as Mount
  // Joy's: deep enough that the road reads as a ribbon laid on the meadow rather
  // than z-fighting with it, shallow enough to bury `buildTrack`'s trestle legs,
  // which on a track with no ground plane are drawn under every raised station.
  const DROP = 2.6;

  // Resolution and reach. The cost of this is cells x stations and it is the most
  // expensive thing in the track's build - it runs in QuickJS too, where the
  // anti-cheat re-drives laps - so both numbers are as coarse as they can be.
  // 18 and every second station puts it in the same range as Mount Joy's field
  // and Spa's; an 8-unit grid would be five times it.
  const CELLM = 18.0;
  const STRIDE = 2;
  const PAD = 300.0;
  const FAR = 2400.0;      // a drawn-only plate past that, so there is a horizon

  // Roughness, only ever *subtracted* so no amount of it can lift the grass into
  // the road, and faded out near the tarmac so the shoulder stays flat.
  const ROUGH = 6.0, ROUGH_SCALE = 88.0, ROUGH2 = 1.8, ROUGH2_SCALE = 24.0;

  // Past this gradient the grass has not held and the face is bare rock, which is
  // most of what gives the gorge any shape. It has to sit well clear of `FLANK`
  // itself - the whole verge is at exactly that gradient by construction, so a
  // threshold near it paints the verge in grey blotches and reads as dirt.
  const ROCK_STEEP = 0.95;

  // ---- the chasm -----------------------------------------------------------
  // `CHASM_DEPTH` is below the lowest station on the track, not below the caps,
  // so the two crossings sit over one gorge rather than two pits at different
  // depths. `CHASM_INNER` is how wide the flat bottom is and `CHASM_WALL` how
  // fast it climbs back to the meadow.
  //
  // `CHASM_KEEP` is the one that matters: the carve is skipped within this
  // distance of any *solid* station, which is what stops the gorge eating back
  // under the lip you jump from. It has to clear `APRON` with room, or the
  // shoulder either side of the take-off goes with it.
  // **Depth is measured off the nearest crossing station, not off one global
  // floor**, and that is the difference between a canyon and a quarry. Measured
  // globally the carve is `minY - DEPTH` everywhere, so in the *high* meadow -
  // where the road is thirty-odd units above the lowest cap - the cut is thirty
  // units deeper than it should be and reaches a hundred and twenty units
  // further out before its wall climbs back to the surface. What that looked
  // like was two long diagonal trenches across the plan view and roads
  // elsewhere on the track standing on trestles over ground that had been dug
  // out from under them.
  const CHASM_DEPTH = 70.0;
  const CHASM_INNER = 24.0, CHASM_WALL = 1.7;
  // Sized so the wall actually closes: DEPTH / WALL is 41 units of climb, plus
  // the flat bottom, plus a little. A reach much past that is dead arithmetic at
  // best and the quarry above at worst.
  const CHASM_REACH = 80.0, CHASM_KEEP = 34.0;
  // ...and the near edge is *blended* over this rather than switched on at
  // `CHASM_KEEP`. A hard boundary means one cell at meadow height beside a cell
  // at the full carve depth for its distance, which is a single near-vertical
  // 18-unit quad falling seventy units - and eighteen of those around the rim
  // read as grey shards thrown across the infield rather than as a cliff.
  const CHASM_BLEND = 42.0;
  // A cell counts as dug (and so is left out of the collider) once the carve has
  // taken it this far below where the meadow would have been. A margin rather
  // than "any dig at all", because the outermost ring of the carve grazes the
  // meadow by fractions of a unit and punching collider holes there would put
  // gaps in ground you are meant to be able to run onto.
  const HOLLOW = 3.0;

  // The conifers, hardcoded for the reason Mount Joy's are: the palette contract
  // has two structural colour slots and this track needs three - rock, trees and
  // the mushrooms' own cream - and rock is the one `buildTrack` reads for itself.
  const CONIFER = 0x2c6338, CONIFER_DK = 0x21492a, TRUNK = 0x5a4632;

  function props(ctx) {
    const { solid, col, track, pal, bbox, KIND, shade, mulberry, minY } = ctx;
    const rnd = mulberry(20260817);
    const line = track.line;
    const n = line.length;

    // ---- the stations the field is built from ------------------------------
    // Solid road only, **and a mushroom cap does not count as solid road.** An
    // `air` station is a point on a ballistic hint and not a place there is any
    // ground, which is the reason the gorge has a hole in it rather than a
    // bridge - and a cap is the same statement about a place you can stand: it
    // is a mushroom top over a void, so building ground from it fills the gorge
    // in under the one thing the gorge exists for. That cost the first render
    // its whole chasm: every cap came out sitting in a shallow green bowl with
    // its stalk buried, which reads as a disc lying in a field.
    const sx = new Float64Array(n), sy = new Float64Array(n), sz = new Float64Array(n);
    let ns = 0;
    for (let i = 0; i < n; i += STRIDE) {
      const e = line[i];
      if (e.air || e.bn) continue;
      sx[ns] = e.p[0]; sy[ns] = e.p[1]; sz[ns] = e.p[2]; ns++;
    }
    // The last station always counts, whatever the stride landed on, or the road
    // under the flag has no ground derived from it.
    const last = line[n - 1];
    sx[ns] = last.p[0]; sy[ns] = last.p[1]; sz[ns] = last.p[2]; ns++;

    // The crossing corridor: every `air` station, plus the caps themselves. The
    // caps are in here even though they are solid road, because the gorge has to
    // be open *under* a mushroom - a cap whose stalk stands on filled ground is
    // a bollard.
    const cx = new Float64Array(n), cy = new Float64Array(n), cz = new Float64Array(n);
    let nc = 0;
    for (let i = 0; i < n; i++) {
      const e = line[i];
      if (!e.air && !e.bn) continue;
      cx[nc] = e.p[0]; cy[nc] = e.p[1]; cz[nc] = e.p[2]; nc++;
    }

    const bedY = minY - CHASM_DEPTH - 12.0;   // nothing in the field goes below this

    // ---- the field ---------------------------------------------------------
    const x0 = bbox.x0 - PAD, x1 = bbox.x1 + PAD;
    const z0 = bbox.z0 - PAD, z1 = bbox.z1 + PAD;
    const nx = Math.ceil((x1 - x0) / CELLM) + 1;
    const nz = Math.ceil((z1 - z0) / CELLM) + 1;
    const H = new Float64Array(nx * nz);
    const D = new Float64Array(nx * nz);        // distance to the nearest road
    const CUT = new Uint8Array(nx * nz);        // 1 where the chasm was dug

    for (let ix = 0; ix < nx; ix++) {
      const px = x0 + ix * CELLM;
      for (let iz = 0; iz < nz; iz++) {
        const pz = z0 + iz * CELLM;
        let up = Infinity, down = -Infinity, near = Infinity;
        for (let k = 0; k < ns; k++) {
          const dx = sx[k] - px, dz = sz[k] - pz;
          const d = Math.sqrt(dx * dx + dz * dz);
          if (d < near) near = d;
          const base = sy[k] - DROP;
          const o = d - APRON;
          // The up-cone: flat over the shoulder, then the verge, then the
          // hillside. Taking the *minimum* of these over every station is what
          // guarantees the ground is under the road everywhere, because the
          // station's own cone contributes exactly `base` at `d = 0`.
          const u = o <= 0 ? base
                  : o <= SOFT ? base + FLANK * o
                  : base + SOFT_TOP + STEEP * (o - SOFT);
          if (u < up) up = u;
          const w = base - FALL * d;
          if (w > down) down = w;
        }
        let h = Math.min(up, down);

        // Roughness. Subtracted only, and faded in past the shoulder so the
        // verge you run onto stays predictable.
        const t = Math.min(1, Math.max(0, (near - APRON - 8) / 24));
        if (t > 0) {
          h -= t * (ROUGH * noise(px, pz, ROUGH_SCALE, 11)
                    + ROUGH2 * noise(px, pz, ROUGH2_SCALE, 23));
        }
        h = Math.max(bedY, h);

        // The gorge. Only ever digs down, and never within `CHASM_KEEP` of solid
        // road, so it cannot reach the lip's shoulder or any other part of the
        // track that happens to run near a crossing.
        let cut = 0;
        if (nc && near > CHASM_KEEP) {
          let dc = Infinity, ck = -1;
          for (let k = 0; k < nc; k++) {
            const dx = cx[k] - px, dz = cz[k] - pz;
            const d2 = dx * dx + dz * dz;
            if (d2 < dc) { dc = d2; ck = k; }
          }
          dc = Math.sqrt(dc);
          if (dc < CHASM_REACH) {
            // Off the nearest crossing's own height, so each gorge is as deep
            // below its own caps as the other one is below its.
            const hc = cy[ck] - CHASM_DEPTH
                     + Math.max(0, dc - CHASM_INNER) * CHASM_WALL;
            // Ramped in away from solid road rather than switched on, so the
            // rim is a slope made of several cells instead of one vertical quad.
            const kf = Math.min(1, (near - CHASM_KEEP) / CHASM_BLEND);
            if (hc < h) {
              const hn = h + (hc - h) * kf;
              cut = (h - hn >= HOLLOW) ? 1 : 0;
              h = hn;
            }
          }
        }

        const idx = ix * nz + iz;
        H[idx] = h;
        D[idx] = near;
        CUT[idx] = cut;
      }
    }

    const at = (ix, iz) => [x0 + ix * CELLM, H[ix * nz + iz], z0 + iz * CELLM];
    const heightAt = (x, z) => {
      const fx = Math.min(nx - 1.001, Math.max(0, (x - x0) / CELLM));
      const fz = Math.min(nz - 1.001, Math.max(0, (z - z0) / CELLM));
      const ix = Math.floor(fx), iz = Math.floor(fz);
      const tx = fx - ix, tz = fz - iz;
      const a = H[ix * nz + iz], b = H[ix * nz + iz + 1];
      const c = H[(ix + 1) * nz + iz], d = H[(ix + 1) * nz + iz + 1];
      return (a * (1 - tz) + b * tz) * (1 - tx) + (c * (1 - tz) + d * tz) * tx;
    };
    const infoAt = (x, z) => {
      const fx = Math.round(Math.min(nx - 1, Math.max(0, (x - x0) / CELLM)));
      const fz = Math.round(Math.min(nz - 1, Math.max(0, (z - z0) / CELLM)));
      const i = fx * nz + fz;
      return { road: D[i], cut: CUT[i] };
    };

    // ---- draw it, and collide the half you are allowed to drive on ---------
    const grass = pal.ground;
    const rock = pal.prop;
    for (let ix = 0; ix + 1 < nx; ix++) {
      for (let iz = 0; iz + 1 < nz; iz++) {
        // Wound the way the engine's own ground quad is - (x0,z0), (x0,z1),
        // (x1,z1), (x1,z0) - so the face points up. Reverse it and the whole
        // meadow is invisible from every place anybody stands, and nothing
        // anywhere says so.
        const a = at(ix, iz), b = at(ix, iz + 1);
        const c = at(ix + 1, iz + 1), d = at(ix + 1, iz);
        const lo = Math.min(a[1], b[1], c[1], d[1]);
        const hi = Math.max(a[1], b[1], c[1], d[1]);
        const grade = (hi - lo) / CELLM;
        const i0 = ix * nz + iz;
        const dug = CUT[i0] || CUT[ix * nz + iz + 1] ||
                    CUT[(ix + 1) * nz + iz + 1] || CUT[(ix + 1) * nz + iz];
        // Bare rock on anything steep, and everywhere inside the gorge: a cliff
        // face is the one thing in the references that is never green.
        const bare = dug || grade > ROCK_STEEP;
        // Rock gets its variation from two scales, not one. A single term keyed
        // on gradient paints every face of a cliff at nearly the same value,
        // because inside a gorge almost every cell is steep - which came out as
        // flat pale grey sheets. The noise term is what gives the strata.
        const tone = bare
          ? shade(rock, -0.30 + 0.34 * Math.min(1, grade / 2.0)
                        + 0.20 * (noise(a[0], a[2], 52.0, 31) - 0.5))
          : shade(grass, -0.07 + 0.14 * noise(a[0], a[2], 140.0, 5));
        solid.quad(a, b, c, d, tone);
        // The collider stops at the lip of the gorge. See the header: a chasm
        // you land in is not a chasm.
        if (!dug) col.addQuad(a, b, c, d, KIND.OFFROAD);
      }
    }

    // A drawn-only plate out to the horizon, so the meadow does not end in mid
    // air when you are up on the rim. Below the field's own bed, and never
    // collided - it is scenery at a distance and nothing reaches it.
    {
      const y = bedY - 2.0;
      const gx0 = bbox.x0 - FAR, gx1 = bbox.x1 + FAR;
      const gz0 = bbox.z0 - FAR, gz1 = bbox.z1 + FAR;
      solid.quad([gx0, y, gz0], [gx0, y, gz1], [gx1, y, gz1], [gx1, y, gz0],
                 shade(grass, -0.34));
    }

    // The mushrooms themselves are **not** here. They were, and they moved into
    // `buildTrack` next to `KIND.BOUNCE`, because the cap's top and its rim have
    // to agree about one radius and two files cannot hold one number - the
    // Costco's lesson about `SHELL_X`. Anything using `Builder.bounce` now gets a
    // mushroom for free, and this file is only the ground it stands over.
    // ---- conifers ---------------------------------------------------------
    // On the meadow, off the verge, and never over the gorge. `density` is the
    // palette's, and it is low on purpose: the references have a handful of
    // trees on the skyline and the pool's cautionary tale is Sandy Cove coming
    // out a palm plantation.
    const dens = pal.density != null ? pal.density : 0.07;
    // Inset by more than the tallest thing's own footprint, because it is the
    // *corner* of a prop that hangs off the edge of the plate.
    const m = 3;
    for (let ix = m; ix + m < nx; ix += 2) {
      for (let iz = m; iz + m < nz; iz += 2) {
        if (rnd() > dens) continue;
        const px = x0 + ix * CELLM + (rnd() - 0.5) * CELLM;
        const pz = z0 + iz * CELLM + (rnd() - 0.5) * CELLM;
        const info = infoAt(px, pz);
        // Well clear of the road, so a tree is never a thing you hit that is not
        // in the collider, and never inside the gorge.
        if (info.cut || info.road < APRON + 22) continue;
        conifer(px, heightAt(px, pz), pz, 13 + rnd() * 12);
      }
    }

    function conifer(x, y, z, hgt) {
      const r = hgt * 0.20;
      // Trunk, then two tapered tiers. Three tiers is a nicer tree and twice the
      // triangles for something you mostly see in silhouette on a ridge.
      box(x, y, z, r * 0.20, hgt * 0.22, TRUNK);
      tier(x, y + hgt * 0.16, z, r, hgt * 0.52, CONIFER);
      tier(x, y + hgt * 0.52, z, r * 0.66, hgt * 0.48, CONIFER_DK);

      function box(bx, by, bz, br, bh, colr) {
        for (let s = 0; s < 4; s++) {
          const t0 = s * Math.PI / 2, t1 = (s + 1) * Math.PI / 2;
          const p0 = [bx + Math.cos(t0) * br, by, bz + Math.sin(t0) * br];
          const p1 = [bx + Math.cos(t1) * br, by, bz + Math.sin(t1) * br];
          solid.quad(p0, p1, [p1[0], by + bh, p1[2]], [p0[0], by + bh, p0[2]],
                     shade(colr, s === 1 || s === 2 ? -0.16 : 0.04));
        }
      }
      function tier(bx, by, bz, br, bh, colr) {
        for (let s = 0; s < 6; s++) {
          const t0 = s * Math.PI / 3, t1 = (s + 1) * Math.PI / 3;
          const p0 = [bx + Math.cos(t0) * br, by, bz + Math.sin(t0) * br];
          const p1 = [bx + Math.cos(t1) * br, by, bz + Math.sin(t1) * br];
          const tip = [bx, by + bh, bz];
          // A triangle written as a degenerate quad, which is what `quad` is for
          // here - there is no `tri` in the buffer's vocabulary.
          solid.quad(p0, p1, tip, tip, shade(colr, 0.10 - 0.26 * (s / 5)));
        }
      }
    }
  }

  // Cheap value noise. Deterministic on (x, z) and the seed, because the
  // anti-cheat rebuilds this track from the same inputs and has to get the same
  // world - a random ground would fail a lap somebody honestly drove.
  function noise(x, z, scale, seed) {
    const xs = x / scale, zs = z / scale;
    const xi = Math.floor(xs), zi = Math.floor(zs);
    const tx = xs - xi, tz = zs - zi;
    const sx = tx * tx * (3 - 2 * tx), sz = tz * tz * (3 - 2 * tz);
    const h = (a, b) => {
      let v = Math.sin((a * 127.1 + b * 311.7 + seed * 74.7)) * 43758.5453;
      return v - Math.floor(v);
    };
    const a = h(xi, zi), b = h(xi + 1, zi), c = h(xi, zi + 1), d = h(xi + 1, zi + 1);
    return (a * (1 - sx) + b * sx) * (1 - sz) + (c * (1 - sx) + d * sx) * sz;
  }
})();
