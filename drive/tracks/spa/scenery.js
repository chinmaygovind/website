// Spa-Francorchamps: walls on the insides of La Source and Rivage.
//
// Everything else this track stands up - the grandstands, the pit building, the
// gantry, the hoardings, the armco - is in `trackmesh.js`, drawn off the ribbon
// with the rest of the terrain kit. This file exists for one thing the stopwatch
// can see, and it is the same job Silverstone's `insideBarrier` does at the
// arena: a corner you could simply leave out.
//
// La Source is a 170-degree hairpin at radius 22, so the straight line from its
// entry to its exit crosses 160 units of circuit for a 55-unit chord - 2.9x, and
// grass is about half road speed, so it pays from about 2x. Everybody on the
// board was driving it: measured against the ribbon, every lap in the top ten
// ran 17 units wide of the road across the inside of this corner. The backstop
// armco cannot close it - it is 27 units out from the road centre, past the
// gravel, and the cut runs inside that at 24 - and that is the armco doing its
// job, which is to stop a car reaching the trees rather than to stop it cutting.
//
// **It cannot be a ribbon `rail`.** This is a ground track and
// `test_barriers_are_opt_in` requires a ground track to carry no walled stations
// at all, so like the Costco's parapet and Rickety Rails' timbering it is
// collider geometry standing beside the road. Which is also what keeps the medal
// times where they are: `laptime.py` relaxes the racing line to the kerb and no
// further, so a wall outside the kerb is never on it.
//
// The real circuit has a wall exactly here, on the inside of the hairpin, for
// the reason every street-course hairpin does: there is nowhere to put run-off.
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.spa = { props: props };

  // How far the run-off sits under the tarmac - trackmesh's own `GRASS_DROP`.
  // Inside the apron the ground is the road's height less this, and sampling
  // `terrain.height` instead is what makes a barrier zigzag wherever the
  // circuit folds back on itself, which at a hairpin is everywhere.
  const DROP = 1.2;
  // Tall enough to *look* like a barrier from the road, which means measuring
  // it from the road and not from its own footing. It stands on the run-off,
  // `DROP` under the tarmac, so Silverstone's 1.5 would leave three tenths of a
  // unit showing above the racing surface - something the collision sphere
  // still catches and the driver cannot see, which is the worst thing a wall
  // can be. 1.6 above the road is the armco's own height.
  const BAR_H = DROP + 1.6;

  function props(ctx) {
    const { solid, col, track, pal, terrain } = ctx;
    const { KIND, shade } = ctx;
    const line = track.line, n = line.length;
    if (!terrain) return;              // this track always has one; be honest anyway
    const APRON = (pal.terrain && pal.terrain.apron != null) ? pal.terrain.apron : 34;

    // Both faces on everything: the world mesh is `MeshLambertMaterial`, which
    // is `FrontSide`, and geometry placed by a signed side has its winding
    // reversed when that sign flips.
    const face = (a, b, c, d, colr) => {
      solid.quad(a, b, c, d, colr);
      solid.quad(a, d, c, b, colr);
    };
    const at = (f) => Math.max(0, Math.min(n - 1, Math.round(f * (n - 1))));
    const spot = (i, o) => {
      const e = line[i];
      return [e.p[0] + e.lat[0] * o, e.p[2] + e.lat[2] * o];
    };
    const ground = (i, o) => (Math.abs(o) <= APRON
      ? line[i].p[1] - DROP : terrain.height.apply(null, spot(i, o)));

    const railC = pal.rail != null ? pal.rail : 0xd8dde2;
    // Silverstone's `insideBarrier`, with the side told rather than read off the
    // curvature. There it walks a whole corner sequence that changes direction
    // and has to work the inside out per station; here it is one hairpin, whose
    // inside is one sign of `lat` from the entry all the way to the exit - and
    // the part that has to be walled is precisely the part with **no**
    // curvature. The cut is not across the apex: the entry and the exit run
    // parallel about fifty units apart, and the line people drive hops straight
    // from one to the other across the infield, leaving the hairpin out
    // altogether. A barrier that only existed where `curv` is non-zero would sit
    // round the far end of the loop with the shortcut running behind it.
    const wall = (f0, f1, side, gap) => {
      let prev = null;
      for (let i = at(f0); i <= at(f1); i++) {
        const e = line[i];
        const o = (e.hw + gap) * side;
        const [x, z] = spot(i, o);
        const p = [x, ground(i, o), z];
        const q = prev;
        prev = p;
        if (!q) continue;
        const up = (v) => [v[0], v[1] + BAR_H, v[2]];
        face(q, p, up(p), up(q), railC);
        col.addQuad(q, p, up(p), up(q), KIND.WALL);
        // A kerb-height foot under it, so it reads as standing on the ground
        // rather than hovering wherever the sweep and the height field disagree.
        const dn = (v) => [v[0], v[1] - 0.55, v[2]];
        face(dn(q), dn(p), p, q, shade(railC, -0.35));
      }
    };
    // From the end of the pits to the exit kerb, on the inside. It starts just
    // ahead of the checkpoint on the pit straight, which is what makes it
    // complete: a car that leaves the road before the wall begins has missed
    // that gate, and one that leaves after it has a wall in the way for the
    // whole of the entry leg, wherever in the infield it was aiming. Fractions
    // rather than station indices, for the reason the furniture uses them - the
    // ribbon is re-solved for closure on every import and that changes how many
    // stations there are.
    wall(0.046, 0.122, 1, 4.5);

    // Join the mountain-side barriers before and after Rivage. The short wall
    // around the apex still left an entry gap large enough to cut through.
    wall(0.350, 0.450, 1, 4.5);
  }
})();
