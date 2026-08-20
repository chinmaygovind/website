"""A track's layout from above, as an SVG path.

The cheapest useful picture of a track there is, and the only one that is always
available: it is derived from the ribbon, so it costs nothing to keep true and it
cannot go stale the way a rendered image does. A photograph of a track has to be
*taken* - by `tools/shoot_tracks.py`, in a browser, offline - and until somebody
runs that tool a new track has no picture at all.

So this is what a community card wears. It is not a substitute for the render:
the render is the thing on the switcher and in a share card, and
`tools/shoot_user_tracks.py` makes those for published tracks. This is what every
track has from the moment it is saved, and it happens to be the more *useful*
picture of the two - the shape of a lap is what tells one track from another,
and a three-quarter view of some tarmac is not.

Lives here rather than in `starters.py`, which had the only copy, because the
pick screen and the community gallery want the identical drawing and a second
implementation of "normalise a ribbon into a box" is a second chance to squash
one.
"""


def path_for(line, w=200.0, h=96.0, pad=10.0):
    """An SVG path for a station list, normalised into a `w` by `h` box.

    Aspect is preserved and the drawing is centred, because a squashed circuit
    does not read as a circuit.

    The path *breaks* at a station marked `air`: a gap has no road under it, and
    drawing a chord straight across the hole would hide the whole visual point
    of a gap.
    """
    if not line:
        return ""
    xs = [e["p"][0] for e in line]
    zs = [e["p"][2] for e in line]
    x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
    span = max(x1 - x0, z1 - z0, 1e-6)
    k = min((w - 2 * pad) / span, (h - 2 * pad) / span)
    cx, cz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
    out, pen = [], False
    for e in line:
        if e.get("air"):
            pen = False
            continue
        pt = (round(w / 2 + (e["p"][0] - cx) * k, 1),
              round(h / 2 + (e["p"][2] - cz) * k, 1))
        out.append(("M" if not pen else "L") + "%g %g" % pt)
        pen = True
    return " ".join(out)
