// Playground: the poles.
//
// **This file is a barrier, not decoration.** The track is `exposed` and floats
// in empty sky, so running a metre wide is a fall and a respawn - which is
// punishing rather than hard, and on a track whose whole subject is how high up
// a wall you dare to be, it punishes exactly the thing it is asking for.
//
// So the pool's existing answer, taken from Rickety Rails: a rank of posts at
// `hw + POST_OUT`, added to the collider as `KIND.WALL`. They sit off the road,
// so the racing line never touches one and no medal time moves - but a wide
// moment hits a pole instead of finding the void, and you keep the lap.
//
// **It has to be scenery rather than a ribbon `rail`.** `test_barriers_are_opt_in`
// counts walled *stations*, so railing these would cost the track its `exposed`
// flag and take the drop away with it. Same reason as Rickety's timbering, the
// Costco's racking and Silverstone's anti-cut barriers.
//
// `verify.py` re-drives submitted laps through this same file, so a lap that
// leaned on a pole in the browser leans on it on the server too.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.playground = { props: props };

  // The edge beam: a low bar running along each kerb, solid, in the collider.
  //
  // **It replaced a rank of posts, and the posts were doing the right job in the
  // wrong shape.** A track floating in open sky with nothing at the edge is a
  // respawn every time you are half a metre wide, which punishes exactly the
  // thing this one is asking you to do - so something has to be there. But two
  // hundred uprights standing off the kerb is a picket fence down both sides of
  // the whole lap, and on a track whose subject is the road's *orientation* it
  // is the thing you end up looking at.
  //
  // A beam at kerb height does the same work and is almost invisible from the
  // car: it is below the eye line, it follows the road rather than interrupting
  // it, and because `KIND.WALL` is excluded from the ground query it can only
  // ever push the car sideways - it is not a surface anything can drive up and
  // be launched off, which a low solid *ramp* would be.
  const BEAM_OUT = 0.9;        // how far past the kerb its outer face sits
  // Low. At 1.5 it was still catching the car exactly as well but it read, from
  // a chase camera at a grazing angle, as a wide dark shoulder either side of
  // the road rather than as a lip on it - apparent width at that angle is mostly
  // height. `CAR_RADIUS` is 1.25 about a body centre 0.45 up, so the collision
  // sphere reaches from -0.8 to 1.7 and anything over about half a unit is
  // caught just the same.
  const BEAM_H = 0.75;         // how tall, above the road surface
  const BEAM_T = 0.7;          // how thick

  // Where the hoops go, as fractions of the lap. Authored rather than derived,
  // the way Spa places its grandstands and for the same reason: which moments on
  // a track are worth announcing is a fact about the track, not something the
  // ribbon implies. They sit before the things you want to see coming.
  const HOOPS = [0.055, 0.30, 0.40, 0.52, 0.63, 0.72, 0.85];
  const HOOP_R = 5.0;          // thickness of the ring
  const HOOP_SEGS = 30;

  function props(ctx) {
    const { solid, bright, col, track, pal, KIND, shade } = ctx;
    const line = track.line, n = line.length;

    // Both windings on everything. `solid` is a `MeshLambertMaterial`, which is
    // FrontSide, so a quad wound away from the camera is drawn, costed and
    // invisible - and an invisible wall is not an error in either language.
    const face = (a, b, c, d, k) => {
      solid.quad(a, b, c, d, k);
      solid.quad(a, d, c, b, k);
    };

    // **Is this station one you can stand something beside?**
    //
    // `lat` rotates with the surface, and on this track that is not a corner
    // case, it is most of the lap: inside a wall of death `lat` is within two
    // degrees of vertical, so a pole offset "2.2 units to the right, on the
    // road" would be built 2.2 units *under* the road, or over it, standing
    // through the cylinder. Rickety found this with rock pillars drawn across
    // the inside of its loop; here it would be every pole on three walls.
    //
    // 0.85 is about 32 degrees off level, which is also `STICK_TILT` - and that
    // is the right line for a second reason. Past it the car is held on by
    // force rather than by gravity, so it is not going to *fall* off the side;
    // what it does is slide down the wall, and a pole cannot catch that, it can
    // only be in the way of it.
    const flat = (e) => (e.n[1] || 0) > 0.85 && !e.air && !e.pf && !e.bn;

    // One segment of beam, between two stations, in their own frames - so it
    // leans with a cambered road instead of standing through it.
    const seg = (a, bb, side, colour) => {
      const P = (e, sl, su) => {
        const o = e.hw + BEAM_OUT - sl * BEAM_T;
        return [e.p[0] + e.lat[0] * side * o + e.n[0] * su,
                e.p[1] + e.lat[1] * side * o + e.n[1] * su,
                e.p[2] + e.lat[2] * side * o + e.n[2] * su];
      };
      const v = [P(a, 0, 0), P(a, 1, 0), P(a, 1, BEAM_H), P(a, 0, BEAM_H),
                 P(bb, 0, 0), P(bb, 1, 0), P(bb, 1, BEAM_H), P(bb, 0, BEAM_H)];
      face(v[0], v[1], v[2], v[3], colour);
      face(v[4], v[7], v[6], v[5], colour);
      face(v[0], v[4], v[5], v[1], colour);
      face(v[1], v[5], v[6], v[2], colour);
      face(v[2], v[6], v[7], v[3], colour);
      face(v[3], v[7], v[4], v[0], colour);
      // Only the inner face and the top go in the collider. The outer face and
      // the underside are behind it from every direction a car can arrive.
      col.addQuad(v[1], v[5], v[6], v[2], KIND.WALL);
      col.addQuad(v[2], v[6], v[7], v[3], KIND.WALL);
    };

    // **The hoops.** A ring of blocks standing around the road, wider than it
    // and clear of it, drawn unlit so it carries against the sky from a long way
    // off. They are the thing the poles were failing to be: on a road in empty
    // air with nothing under it and no horizon behind it, the oldest entry in
    // `docs/track-defects.md` is a corner that arrives with no warning, and a
    // rank of identical posts does not warn you about anything in particular. A
    // hoop does, because there are seven of them and each one is somewhere.
    //
    // **Nothing about them is solid.** A ring around the road is exactly the
    // shape of thing a car clips on a good lap, and a decoration that can end a
    // run is not a decoration. The poles are the barrier; these are the signage.
    const hoop = (i, colour) => {
      const e = line[Math.max(0, Math.min(n - 1, i | 0))];
      if (e.air) return;
      const p = e.p, l = e.lat, u = e.n;
      // Clear of the road by half its width again. Tight to the kerb the ring
      // came out as a low bar across the top of the frame - a gantry, not a
      // hoop - because from a chase camera you only ever see its upper third.
      const rad = e.hw + 10.0;
      // **All the way round.** This was an arc over the top, on the theory that
      // blocks under the road would read as the track sitting in a barrel; what
      // it actually read as was a row of slabs hanging in the corner of frame,
      // because an arc with two ends is not a shape the eye completes. A closed
      // ring is, and driving through one is the point.
      for (let k = 0; k < HOOP_SEGS; k++) {
        const a = 2 * Math.PI * (k / HOOP_SEGS);
        const cx = Math.cos(a) * rad, cy = Math.sin(a) * rad;
        // **Lit, not `bright`.** Drawn unlit these came out as pale slabs
        // hanging in the corner of the frame - the identical failure the knobs
        // had, for the identical reason: an unlit colour is lifted hard on the
        // way out, so it has no shading, and an object with no shading against a
        // graded sky reads as a hole in the picture rather than as a thing in
        // the world. A hoop is structure and wants to be lit like structure.
        solid.box(p[0] + l[0] * cx + u[0] * cy,
                  p[1] + l[1] * cx + u[1] * cy,
                  p[2] + l[2] * cx + u[2] * cy,
                  HOOP_R * 0.19, HOOP_R * 0.19, HOOP_R * 0.19,
                  k % 2 ? colour : shade(colour, 0.22));
      }
    };
    // **Placed by distance along the lap, not by station index**, and the two
    // are a long way apart on this track. `Builder.wall` lays its stations as
    // fine as the twist needs - under two units apart on a ramp against the
    // usual 3.5 - so the three walls carry a wildly disproportionate share of
    // the index space, and a hoop authored at "a third of the way round" came
    // out somewhere inside the second wall. Spa places its grandstands by
    // fraction of the lap for the same reason.
    const run = new Float64Array(n);
    for (let i = 1; i < n; i++) {
      const a = line[i - 1].p, b = line[i].p;
      run[i] = run[i - 1] + Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
    }
    const atDist = (f) => {
      const want = f * run[n - 1];
      let lo = 0, hi = n - 1;
      while (lo < hi) { const m = (lo + hi) >> 1; if (run[m] < want) lo = m + 1; else hi = m; }
      return lo;
    };
    for (let h = 0; h < HOOPS.length; h++) {
      hoop(atDist(HOOPS[h]), h % 2 ? pal.deco : pal.kerb2);
    }

    // The road's own colour, darkened - not the kerb's. A beam in a *different*
    // hue is a stripe down each side of the track; a beam in a darker shade of
    // the road is the edge of the road, which is what it is.
    const beamCol = shade(pal.road, -0.34);

    for (let i = 1; i < n; i++) {
      const a = line[i - 1], bb = line[i];
      if (!flat(a) || !flat(bb)) continue;
      // Where the ribbon already carries a barrier, the barrier is the answer
      // and a beam outside it is geometry nobody will ever touch.
      if (a.wl || a.wr || bb.wl || bb.wr) continue;
      seg(a, bb, -1, beamCol);
      seg(a, bb, 1, beamCol);
    }
  }
})();
