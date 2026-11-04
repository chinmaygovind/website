"""What Sahara looks like."""

import math

from tracks.sahara.track import CHAMBER, LANE, PYR_B, PYR_H, PYR_X, PYR_Z, TUNNEL_W

SUN_AZ = -0.8

PALETTE = {
    # Paving, not asphalt: a worn grey-brown with enough chroma to survive the
    # glare, and well darker than the sand so the plan view is not a blob.
    "road": 0x8a6a48, "kerb": 0xfff1d0, "kerb2": 0xd8342a,
    "ground": 0xf0a838, "rail": 0xe8c878,
    "prop": 0xd9a650, "prop2": 0xb98a3c, "deco": 0xe0a91c,
    "fog": 0xdcebf5,
    "pad": 0x34d6cf, "padBase": 0x135a58,
    # No scatter: its rocks read as crates at any distance. No engine
    # trestles either - everything raised stands on scenery.js piers.
    "density": 0,
    "legs": 0,
    "building": {
        "x": PYR_X, "z": PYR_Z, "b": PYR_B, "h": PYR_H,
        "chamber": list(CHAMBER),
        "lane": list(LANE), "laneHW": 2.7, "tunnelW": TUNNEL_W,
        # How far in from the outer face the inner one is: the shell's thickness.
        "thick": 4.0,
        # A tier of masonry. The faces are stepped, which is what makes a
        # pyramid read as built at this size rather than as a smooth cone.
        "tier": 5.0,
        "stone": 0xdba552, "stone2": 0xbf8a3e, "cap": 0xffc22a,
        # Inside is dark on purpose: there is no lighting per region, so the
        # darkness is the colours. Torches, glyphs and lamps are the light.
        "inner": 0x140b05, "inner2": 0x100804, "floor": 0x1c120a,
        "dark": 0x2c1c0e, "dark2": 0x1a1008, "road": 0x1c1611,
        "sand": 0xeea232,
        # The open desert, as a ramp: the deep tone in the troughs, the light
        # on the flats and crests. Authored deep and orange on purpose: a
        # vertex colour is lifted on its way to the screen, and lifted hard,
        # which washes a yellow picked to look right in the file out to khaki
        # (roughly, author (wanted / 255) ^ 2.2). These land as a clear sand
        # yellow and a warm tan.
        "sandDeep": 0xc8701c, "sandLight": 0xffb432,
        # Unlit, so authored dark: see the `bright` notes in track-defects.md.
        "glyph": 0x0fa39a, "glyph2": 0xc98a10, "flame": 0xffa630,
        "water": 0x1f86a0, "grass": 0x6f8a2a, "palm": 0x3f6e22, "trunk": 0x7a5a34,
        "lapis": 0x1f3f8a, "oxblood": 0x6a1a12, "flame2": 0xffe08a,
        "sandfall": 0xc89a52,
    },
    "lamps": {
        # Light only: every flame you can see is a brazier `scenery.js` stands
        # on the masonry, and these are the pools they throw. Fractions measured
        # off the ribbon - re-measure after any layout change.
        "count": 10, "color": 0xffa448, "intensity": 3.2, "range": 50,
        "runs": [
            # Down the middle of every tunnel and the King's chamber, under the
            # roof: the walls are what is lit, and a light on the centreline
            # cannot end up on the far side of a wall when a leg moves.
            {"from": 0.340, "to": 0.752, "every": 7, "off": 0, "up": 7.5, "bare": True},
        ],
    },
    "sky": {
        # Midday desert, after the references: a deep saturated blue overhead
        # coming down to a pale blue at the horizon, with fair-weather cloud.
        # One hue family - the warmth is all in the sand, none in the sky.
        "stops": [
            [0.00, 0xb7d4ec], [0.42, 0xcfe6f6], [0.50, 0xe2f0fa],
            [0.56, 0xa9d2f2], [0.72, 0x5d9fe0], [1.00, 0x2a66c8],
        ],
        "clouds": {"scale": 2.3, "amount": 0.32, "dark": 0xc4d6e6,
                   "light": 0xffffff, "lit": 0.14},
        "glow": 0xfffbef, "glowStrength": 0.45, "glowMode": "radial",
        "glowFocus": 8,
        "sun": {"az": SUN_AZ, "el": 1.05, "color": 0xfffcf2, "size": 260},
        # Lower than noon on purpose: a high sun lights every slope the same,
        # and the dunes are only dunes where one face is lit and one is not.
        "light": {"color": 0xfff6e2, "intensity": 1.6,
                  "dir": [math.sin(SUN_AZ) * 0.74, 0.67, math.cos(SUN_AZ) * 0.74]},
        # The bounce off golden sand: warm, but dim and desaturated enough to
        # land on undersides rather than repaint the world.
        "hemi": {"sky": 0xd6e8f6, "ground": 0xc4a46a, "intensity": 0.9},
        "fog": 0xdcebf5, "fogNear": 380, "fogFar": 1900,
    },
}
