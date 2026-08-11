"""What Mount Joy looks like.

A cold, very high, very bright day. Two things make a snow scene read as snow
rather than as a grey scene with white bits in it, and both of them are here:
the **bounce** (`hemi.ground`) is nearly as bright as the sky, because a snowfield
throws almost all of the light back up and that is what removes the dark
undersides from everything; and the sky goes properly deep at the zenith, because
thin air at altitude does, and a pale-all-over dome reads as overcast.

Colours are packed RGB handed to three.js unconverted, so they are picked cooler
than they look - see `tracks/look.py`.
"""

PALETTE = {
    # Plowed asphalt: dark, and blue rather than brown, so the snow beside it
    # does not turn it into mud.
    "road": 0x3b414d,
    "kerb": 0xffffff, "kerb2": 0x2f6fd0,
    # `ground` is the snow. Not pure white - the mountain is shaded off its own
    # normals and a 0xff base leaves the lit faces with nowhere left to go.
    "ground": 0xdfe9f6,
    "snow": 0xf6fbff,
    "rail": 0xf2f7fd,
    # Steel and rock. `buildTrack` draws its own slim legs under raised road in
    # `prop`, and this is the one track in the pool where a lot of road really
    # is up in the air - the ski jump stands on seventy units of trestle - so
    # they want to be the same colour as the tower `scenery.js` builds round
    # them rather than a second material. The conifers are the one colour that
    # is *not* here: they are drawn by this track's own scenery, and there is no
    # third slot in the palette contract to put them in.
    "prop": 0x7d8794, "prop2": 0x59616e,
    # Gates and markers. Orange rather than the usual yellow - against snow and
    # a blue sky, yellow is the one hue with nothing to be seen against.
    "deco": 0xf08a30,
    "fog": 0xd3e0ee,
    # There is a mountain under this track, so the void needs no floor of its
    # own - `buildTrack` draws a distant grey plate at `minY - 34` for any
    # floating track with no `below`, and here that would be a second, lower,
    # differently-coloured ground showing past the edge of the snow. Any `below`
    # at all suppresses it; `void` is the one that then draws nothing.
    "below": {"kind": "void"},
    # Read by this track's own scenery rather than by `addScenery`, which stops
    # at `if (!onGround) continue` - the trees here stand on the mountain, and
    # only `scenery.js` knows what shape that is.
    "density": 0.30,
    "sky": {
        # Thin air: pale and slightly warm at the horizon where there is still
        # some atmosphere to scatter, and very deep straight up where there is
        # not. That gradient is most of what says "altitude".
        "stops": [
            [0.00, 0xbccddc], [0.38, 0xd9e7f3], [0.50, 0xecf4fb],
            [0.60, 0xa6c6e8], [0.78, 0x5b8cce], [1.00, 0x1f4fa8],
        ],
        "glow": 0xfff6e2, "glowStrength": 0.5, "glowMode": "radial",
        "glowFocus": 6,
        # High and behind you on the grid, so the mountain face you launch at is
        # lit rather than in silhouette.
        "sun": {"az": 2.35, "el": 0.52, "color": 0xfffbf2, "size": 300},
        "light": {"color": 0xf4f8ff, "intensity": 1.34,
                  "dir": [-0.51, 0.78, 0.36]},
        # The bounce. Snow returns most of the light that lands on it, so the
        # ground half of the hemisphere is nearly as bright as the sky half -
        # which is why a snowy scene has no dark shadows in it, and why every
        # underside on this track is pale blue rather than black.
        "hemi": {"sky": 0xd9e9fb, "ground": 0xc4d6e8, "intensity": 1.05},
        "fog": 0xd3e0ee, "fogNear": 300, "fogFar": 1700,
    },
}
