/**
 * The worked examples in the scenery spec.
 *
 * Real functions, not strings, and the spec renders them with
 * `Function.prototype.toString()` - so they are parsed by the browser that
 * ships them and *run*, against a real ribbon, by `test_scenery_code.py`
 * through QuickJS. An example in a spec that does not run is worse than no
 * example at all: it teaches a model to write something that fails, and the
 * model has no other source for this API to correct itself from.
 *
 * Each one is deliberately a whole answer to a whole request, because that is
 * the shape a model imitates. Between them they use every idea a player needs:
 * a fraction of the lap, an offset to one side, standing on the ground, taking
 * colours from the palette, walking a range of stations, and adding the one
 * collider kind that changes how a track drives.
 */

/** A row of sheds down one side, evenly spaced along the lap. */
export function sheds(ctx) {
  const { at, spot, ground, solid, pal, shade } = ctx;
  for (let k = 0; k < 6; k++) {
    const i = at(0.15 + k * 0.06), off = 38;
    const [x, z] = spot(i, off);
    const y = ground(i, off);
    // Alternating shades, so a row reads as separate buildings rather than as
    // one long wall from a distance.
    solid.box(x, y + 4, z, 7, 4, 10,
              shade(pal.prop2 || 0x8a8f96, k % 2 ? -0.1 : 0.05));
  }
}

/**
 * A barrier on the inside of a corner, so the corner cannot be cut.
 *
 * The only kind of scenery a lap time can feel, which is why it is worth having:
 * it is how a real circuit stops you straight-lining a hairpin, and a ribbon
 * rail is not available on a ground track.
 */
export function insideBarrier(ctx) {
  const { at, spot, ground, face, col, KIND, pal } = ctx;
  const from = at(0.40), to = at(0.47), off = -13, h = 1.5;
  for (let i = from; i < to; i++) {
    const [x0, z0] = spot(i, off), [x1, z1] = spot(i + 1, off);
    const y0 = ground(i, off), y1 = ground(i + 1, off);
    const a = [x0, y0, z0], b = [x1, y1, z1];
    const c = [x1, y1 + h, z1], d = [x0, y0 + h, z0];
    // `face` and not `solid.quad`: the world material is FrontSide, so one
    // winding is an invisible wall - which is not an error in either language.
    face(a, b, c, d, pal.rail || 0xd8dde2);
    col.addQuad(a, b, c, d, KIND.WALL);
  }
}

export const EXAMPLES = [
  ['sheds', sheds],
  ['insideBarrier', insideBarrier],
];

/** The source of an example, renamed to the function the sandbox calls. */
export function exampleSource(fn) {
  return fn.toString().replace(/^function\s+\w+/, 'function props');
}
